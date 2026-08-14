"""AI service -- the single entry point services use for LLM work.

Handles caching, structured validation, one repair round-trip, and the guarantee
that a failure never propagates into the render path.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from intellia.ai.cache import LLMCache, cache_key
from intellia.ai.llm_provider import LLMRequest, LLMResponse, TaskSpec
from intellia.ai.structured import coerce
from intellia.utils.logging import get_logger

log = get_logger("ai")


class AIService:
    def __init__(self, provider: Any, cache: LLMCache, mock_provider: Any,
                 reporting_date: str, debug: bool = False) -> None:
        self.provider = provider
        self.mock = mock_provider
        self.cache = cache
        self.reporting_date = reporting_date
        self.debug = debug
        self.call_count = 0          # surfaced in debug mode to prove replay is LLM-free
        self.cache_hits = 0

    @property
    def live(self) -> bool:
        # bootstrap falls back to the mock provider when the client can't be built,
        # so identity, not just `.available`, decides whether we are really live.
        return (self.provider is not self.mock
                and bool(getattr(self.provider, "available", False)))

    @property
    def mode_label(self) -> str:
        if not self.live:
            return "Prepared (deterministic)"
        return getattr(self.provider, "model", "Claude")

    def model_for(self, task: Any) -> str:
        """Which model actually produced a given task's output.

        Surfaced next to the output rather than assumed from the provider, so a
        footer cannot claim the flagship tier wrote something the fast tier did.
        """
        if not self.live:
            return "Prepared (deterministic)"
        if hasattr(self.provider, "model_for"):
            return self.provider.model_for(task)
        return getattr(self.provider, "model", "Claude")

    def run(self, task: TaskSpec, system: str, user: str,
            cache_inputs: Dict[str, Any],
            fallback: Optional[Callable[[], Dict[str, Any]]] = None,
            cacheable_system: str = "", persona_id: str = "",
            use_cache: bool = True) -> Any:
        """Execute one LLM task and return a validated ``task.output_cls`` instance."""
        provider = self.provider if self.live else self.mock
        # Per task, because a task can pin its own tier and two tiers must not
        # share a cache entry.
        model = (provider.model_for(task) if hasattr(provider, "model_for")
                 else getattr(provider, "model", "deterministic"))
        key = cache_key(
            getattr(provider, "name", "mock"),
            model or "deterministic",
            task.name, task.prompt_version,
            dict(cache_inputs, persona=persona_id, date=self.reporting_date),
        )

        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                instance, errors = coerce(cached, task.output_cls)
                if not errors:
                    self.cache_hits += 1
                    return instance
                log.info("Discarding stale cache entry for %s", task.name)

        request = LLMRequest(
            task=task, system=system, user=user,
            cache_key_inputs=cache_inputs,
            cacheable_system=cacheable_system,
            fallback=fallback,
        )

        response = self._complete(provider, request)
        instance, errors = self._validate(task, response)

        if errors and response.payload is not None:
            # One repair round-trip, then give up and use the deterministic fallback.
            log.info("Repairing malformed output for %s: %s", task.name, errors[:3])
            repaired = self._complete(provider, LLMRequest(
                task=task, system=system,
                user=(user + "\n\nYour previous output failed validation:\n- "
                      + "\n- ".join(errors[:8])
                      + "\n\nReturn only corrected JSON matching the schema."),
                cache_key_inputs=cache_inputs,
                cacheable_system=cacheable_system,
                fallback=fallback,
            ))
            instance, errors = self._validate(task, repaired)
            response = repaired

        if errors or instance is None:
            if fallback is not None:
                instance, fb_errors = coerce(fallback(), task.output_cls)
                if not fb_errors:
                    log.warning("Falling back to deterministic output for %s", task.name)
                    return instance
            log.error("Could not produce valid output for %s: %s", task.name, errors[:3])
            return None

        if use_cache:
            self.cache.put(key, response.payload or {}, task.name,
                           response.model, task.prompt_version)
        return instance

    def _complete(self, provider: Any, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        try:
            return provider.complete(request)
        except Exception as exc:  # never raise into a render path
            log.warning("Provider %s raised on %s: %s",
                        getattr(provider, "name", "?"), request.task.name, exc)
            payload = request.fallback() if request.fallback else None
            return LLMResponse(payload=payload, provider="mock", warnings=[str(exc)])

    @staticmethod
    def _validate(task: TaskSpec, response: LLMResponse):
        if response.payload is None:
            return None, ["provider returned no payload"]
        return coerce(response.payload, task.output_cls)
