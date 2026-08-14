"""Action execution.

Nothing here sends mail or writes to a CRM. Each handler is the seam where a real
integration would plug in -- the signature and result shape are what production
would use; only the side effect is mocked.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

    def runtime_checkable(cls):  # type: ignore
        return cls

from intellia.models.action import Action, ExecutionResult


@runtime_checkable
class ActionExecutor(Protocol):
    name: str

    def supported(self, action: Action) -> List[str]: ...
    def execute(self, action: Action, action_type: str,
                payload: Optional[Dict[str, Any]] = None) -> ExecutionResult: ...


ACTION_LABELS = {
    "draft_email": "Draft follow-up email",
    "update_crm": "Update CRM opportunity",
    "create_task": "Create task",
    "send_recap": "Send meeting recap",
    "schedule_meeting": "Schedule meeting",
}

# Where each mocked action would really land.
INTEGRATION_TARGET = {
    "draft_email": "Microsoft Graph · Outlook drafts",
    "update_crm": "Salesforce · Opportunity",
    "create_task": "Asana · Tasks",
    "send_recap": "Microsoft Graph · Outlook drafts",
    "schedule_meeting": "Microsoft Graph · Calendar",
}


class MockActionExecutor:
    """Records what would have happened. No external call is ever made."""

    name = "mock"

    def __init__(self, as_of: date) -> None:
        self.as_of = as_of
        self.log: List[Dict[str, Any]] = []

    def supported(self, action: Action) -> List[str]:
        base = [action.default_action_type]
        for kind in ("draft_email", "update_crm", "create_task", "send_recap"):
            if kind not in base:
                base.append(kind)
        return base

    def execute(self, action: Action, action_type: str,
                payload: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        payload = payload or {}
        target = INTEGRATION_TARGET.get(action_type, "External system")
        label = ACTION_LABELS.get(action_type, action_type)

        steps = [
            "Resolving {} {}".format(action.ref_type, action.ref_id),
            "Assembling payload for {}".format(target),
            "Validating against {} schema".format(target.split(" · ")[0]),
            "Staged, not sent (prototype)",
        ]

        summaries = {
            "draft_email": "Draft saved to Outlook",
            "update_crm": "Opportunity updated in Salesforce",
            "create_task": "Task created in Asana",
            "send_recap": "Recap draft saved to Outlook",
            "schedule_meeting": "Invite drafted in Calendar",
        }

        record = {
            "action_key": action.key, "action_type": action_type,
            "target": target, "payload": payload, "at": self.as_of.isoformat(),
        }
        self.log.append(record)

        return ExecutionResult(
            ok=True,
            action_type=action_type,
            summary=summaries.get(action_type, label),
            detail="Prototype: staged for {} but nothing was sent.".format(target),
            payload=payload,
            steps=steps,
        )
