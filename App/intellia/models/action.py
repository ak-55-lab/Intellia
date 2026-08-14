"""Action queue model.

Actions are derived deterministically from meetings, emails, deals, signals and tasks.
The LLM is only used on demand -- to explain one, or to draft an email for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

SOURCE_LABELS = {
    "meeting": "Meeting",
    "email": "Email",
    "deal": "Deal",
    "signal": "Signal",
    "task": "Task",
}


@dataclass(frozen=True)
class Action:
    key: str
    title: str
    source: str                    # meeting | email | deal | signal | task
    source_label: str
    priority: str                  # High | Medium | Low
    score: float
    due_date: Optional[date]
    ref_type: str
    ref_id: str
    account_id: str = ""
    account_name: str = ""
    deal_id: str = ""
    deal_name: str = ""
    amount: float = 0.0
    why: str = ""
    default_action_type: str = "draft_email"
    contact_name: str = ""
    contact_email: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_display(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source.title())


@dataclass
class ExecutionResult:
    ok: bool
    action_type: str
    summary: str
    detail: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    steps: List[str] = field(default_factory=list)
