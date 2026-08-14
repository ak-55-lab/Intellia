"""Claude provider.

The ONLY module that imports ``anthropic`` -- and it does so lazily inside a
try/except so the application runs end to end with the package absent.

API notes that shape this code (Claude Opus 5):
  * ``temperature`` / ``top_p`` / ``top_k`` are rejected -- steer by prompting.
  * ``budget_tokens`` is removed; depth is controlled by ``output_config.effort``.
  * Thinking is ON by default. ``max_tokens`` caps thinking + response text together,
    so it is sized with headroom below.
  * Structured output uses ``output_config.format`` with a JSON schema.
  * ``stop_reason == "refusal"`` returns HTTP 200 -- it must be checked BEFORE
    reading ``content``, or indexing content[0] raises.
  * The knowledge blob is sent as a cached system block (Opus 5's cacheable
    minimum is 512 tokens, so it always qualifies).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from intellia.ai.llm_provider import LLMRequest, LLMResponse
from intellia.ai.structured import extract_json, schema_for
from intellia.utils.logging import get_logger

log = get_logger("claude")

# Effort maps directly onto output_config.effort.
VALID_EFFORT = ("low", "medium", "high", "xhigh", "max")


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-opus-5",
                 fast_model: str = "claude-sonnet-5") -> None:
        self.api_key = api_key
        self.model = model
        self.fast_model = fast_model
        self._client: Optional[Any] = None
        self._import_error: Optional[str] = None

    def model_for(self, task: Any) -> str:
        """The tier this task asked for, or the configured default.

        Routing lives on the task rather than on the provider so the choice is
        visible next to the prompt it applies to, and so the cache key (which
        already includes the model) splits cleanly between tiers.
        """
        return getattr(task, "model", "") or self.model

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self._ensure_client() is not None

    def _ensure_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        if self._import_error:
            return None
        try:
            import anthropic  # imported lazily: mock mode must not require it
        except ImportError as exc:
            self._import_error = str(exc)
            log.info("anthropic package not installed; using deterministic mode.")
            return None
        try:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        except Exception as exc:  # pragma: no cover - construction rarely fails
            self._import_error = str(exc)
            log.warning("Could not construct Anthropic client: %s", exc)
            return None
        return self._client

    # -- request ------------------------------------------------------------------------

    def _system_blocks(self, request: LLMRequest) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        if request.cacheable_system:
            # Stable prefix first, marked for caching. Everything volatile goes after.
            blocks.append({
                "type": "text",
                "text": request.cacheable_system,
                "cache_control": {"type": "ephemeral"},
            })
        if request.system:
            blocks.append({"type": "text", "text": request.system})
        return blocks

    def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._ensure_client()
        if client is None:
            return self._degraded(request, "Anthropic client unavailable")

        effort = request.task.effort if request.task.effort in VALID_EFFORT else "low"
        schema = schema_for(request.task.output_cls)
        model = self.model_for(request.task)

        try:
            message = client.messages.create(
                model=model,
                max_tokens=request.task.max_tokens,
                system=self._system_blocks(request),
                messages=[{"role": "user", "content": request.user}],
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except Exception as exc:
            log.warning("Claude call failed for task %s: %s", request.task.name, exc)
            return self._degraded(request, str(exc))

        # Guard the refusal path before touching content.
        if getattr(message, "stop_reason", None) == "refusal":
            detail = getattr(message, "stop_details", None)
            log.warning("Claude declined task %s (%s)", request.task.name,
                        getattr(detail, "category", "unknown"))
            return self._degraded(request, "request declined by safety classifier")

        text = self._first_text(message)
        payload = extract_json(text)
        if not isinstance(payload, dict):
            log.warning("Claude returned unparseable output for %s", request.task.name)
            return self._degraded(request, "model output was not valid JSON",
                                  raw_text=text)

        usage = getattr(message, "usage", None)
        return LLMResponse(
            payload=payload,
            raw_text=text,
            provider=self.name,
            model=model,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )

    @staticmethod
    def _first_text(message: Any) -> str:
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                return getattr(block, "text", "") or ""
        return ""

    def _degraded(self, request: LLMRequest, reason: str,
                  raw_text: str = "") -> LLMResponse:
        """Fall back to the caller's deterministic builder. Never raises."""
        payload = request.fallback() if request.fallback else None
        return LLMResponse(
            payload=payload,
            raw_text=raw_text,
            provider="mock" if payload else self.name,
            model="deterministic" if payload else self.model,
            warnings=[reason],
        )
