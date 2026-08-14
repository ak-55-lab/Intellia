"""LLM provider interface and task registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

    def runtime_checkable(cls):  # type: ignore
        return cls


@dataclass(frozen=True)
class TaskSpec:
    """One LLM job: its name, output schema owner, effort, budget and tier.

    ``model`` is per task on purpose. Interactive work (a question, a chart edit)
    runs on the fast tier because the user is waiting and the answer is prose over
    rows that are already computed; the flagship tier is reserved for the two
    tasks whose judgement is the product (the morning brief and meeting prep).
    Empty means "use the configured default".
    """

    name: str
    output_cls: Any
    effort: str = "low"          # low | medium | high
    max_tokens: int = 4000
    prompt_version: str = "1"
    model: str = ""


@dataclass
class LLMRequest:
    task: TaskSpec
    system: str
    user: str
    cache_key_inputs: Dict[str, Any] = field(default_factory=dict)
    cacheable_system: str = ""   # the large, stable prefix worth prompt-caching
    fallback: Optional[Callable[[], Dict[str, Any]]] = None
    """Deterministic payload builder owned by the calling service.

    The service already holds the real domain objects, so its fallback names real
    accounts and deals. ``MockProvider`` simply invokes this, and ``ClaudeProvider``
    falls back to it on refusal or repeated validation failure -- which is why mock mode
    still looks like a working product rather than lorem ipsum.
    """


@dataclass
class LLMResponse:
    payload: Optional[Dict[str, Any]]
    raw_text: str = ""
    provider: str = "mock"
    model: str = ""
    cached: bool = False
    warnings: List[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    available: bool

    def complete(self, request: LLMRequest) -> LLMResponse: ...
