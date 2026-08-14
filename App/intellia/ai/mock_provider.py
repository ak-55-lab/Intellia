"""Deterministic provider used when no API key is present.

It does not invent content. Each calling service supplies a ``fallback`` builder that
composes a payload from the same real records the live path would reason over, so the
mock brief names Elena's actual accounts and deals.
"""

from __future__ import annotations

from typing import Any, Dict

from intellia.ai.llm_provider import LLMRequest, LLMResponse


class MockProvider:
    name = "mock"
    available = True

    def __init__(self, label: str = "Intellia (prepared)") -> None:
        self.label = label

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload: Dict[str, Any] = request.fallback() if request.fallback else {}
        return LLMResponse(
            payload=payload,
            raw_text="",
            provider=self.name,
            model="deterministic",
            cached=False,
            warnings=[] if payload else ["No deterministic fallback registered for {}".format(
                request.task.name)],
        )


