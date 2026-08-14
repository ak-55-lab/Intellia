"""Domain entities.

Plain dataclasses on purpose: ``models`` is imported on every code path, including
mock-only mode where ``anthropic`` (and therefore pydantic) may not be installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from intellia.utils.dates import to_date, to_datetime


def _json_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


@dataclass(frozen=True)
class User:
    user_id: str
    full_name: str
    email: str
    role: str
    department: str
    manager_id: Optional[str]
    region: str
    quota_annual: float
    is_active: bool = True

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "User":
        return cls(
            user_id=row["user_id"], full_name=row["full_name"], email=row["email"],
            role=row["role"], department=row["department"],
            manager_id=row.get("manager_id") or None, region=row.get("region", ""),
            quota_annual=float(row.get("quota_annual") or 0),
            is_active=bool(row.get("is_active", 1)),
        )


@dataclass(frozen=True)
class Account:
    account_id: str
    account_name: str
    domain: str
    industry: str
    region: str
    segment: str
    tier: str
    status: str
    arr: float
    employee_count: int
    owner_id: str
    renewal_date: Optional[date]
    health_score: int

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Account":
        return cls(
            account_id=row["account_id"], account_name=row["account_name"],
            domain=row.get("domain", ""), industry=row.get("industry", ""),
            region=row.get("region", ""), segment=row.get("segment", ""),
            tier=row.get("tier", ""), status=row.get("status", ""),
            arr=float(row.get("arr") or 0), employee_count=int(row.get("employee_count") or 0),
            owner_id=row.get("owner_id", ""), renewal_date=to_date(row.get("renewal_date")),
            health_score=int(row.get("health_score") or 0),
        )


@dataclass(frozen=True)
class Contact:
    contact_id: str
    account_id: str
    first_name: str
    last_name: str
    email: str
    title: str
    persona_role: str
    seniority: str
    influence: int
    is_champion: bool

    @property
    def full_name(self) -> str:
        return "{} {}".format(self.first_name, self.last_name).strip()

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Contact":
        return cls(
            contact_id=row["contact_id"], account_id=row["account_id"],
            first_name=row.get("first_name", ""), last_name=row.get("last_name", ""),
            email=row.get("email", ""), title=row.get("title", ""),
            persona_role=row.get("persona_role", ""), seniority=row.get("seniority", ""),
            influence=int(row.get("influence") or 0),
            is_champion=bool(row.get("is_champion") or 0),
        )


@dataclass(frozen=True)
class Deal:
    deal_id: str
    account_id: str
    owner_id: str
    deal_name: str
    deal_type: str
    stage: str
    amount: float
    probability: int
    forecast_category: str
    close_date: Optional[date]
    created_date: Optional[date]
    stage_entered_at: Optional[date]
    last_activity_date: Optional[date]
    next_step: str
    next_step_due_date: Optional[date]
    competitor: str
    source: str
    win_loss_reason: str
    account_name: str = ""
    owner_name: str = ""

    CLOSED = ("Stage 5 - Closed Won", "Stage 5 - Closed Lost")

    @property
    def is_open(self) -> bool:
        return self.stage not in self.CLOSED

    @property
    def is_won(self) -> bool:
        return self.stage == "Stage 5 - Closed Won"

    @property
    def stage_short(self) -> str:
        return self.stage.split(" - ")[-1] if " - " in self.stage else self.stage

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Deal":
        return cls(
            deal_id=row["deal_id"], account_id=row["account_id"], owner_id=row["owner_id"],
            deal_name=row.get("deal_name", ""), deal_type=row.get("deal_type", ""),
            stage=row.get("stage", ""), amount=float(row.get("amount") or 0),
            probability=int(row.get("probability") or 0),
            forecast_category=row.get("forecast_category", ""),
            close_date=to_date(row.get("close_date")),
            created_date=to_date(row.get("created_date")),
            stage_entered_at=to_date(row.get("stage_entered_at")),
            last_activity_date=to_date(row.get("last_activity_date")),
            next_step=row.get("next_step", "") or "",
            next_step_due_date=to_date(row.get("next_step_due_date")),
            competitor=row.get("competitor", "") or "",
            source=row.get("source", "") or "",
            win_loss_reason=row.get("win_loss_reason", "") or "",
            account_name=row.get("account_name", "") or "",
            owner_name=row.get("owner_name", "") or "",
        )


@dataclass(frozen=True)
class Email:
    email_id: str
    thread_id: str
    account_id: str
    contact_id: str
    deal_id: str
    sender_email: str
    recipient_email: str
    direction: str
    subject: str
    snippet: str
    body: str
    is_reply: bool
    sent_at: Optional[datetime]
    sentiment_score: float
    contact_name: str = ""
    account_name: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Email":
        return cls(
            email_id=row["email_id"], thread_id=row.get("thread_id", ""),
            account_id=row.get("account_id", ""), contact_id=row.get("contact_id", "") or "",
            deal_id=row.get("deal_id", "") or "", sender_email=row.get("sender_email", ""),
            recipient_email=row.get("recipient_email", ""), direction=row.get("direction", ""),
            subject=row.get("subject", ""), snippet=row.get("snippet", "") or "",
            body=row.get("body", "") or "", is_reply=bool(row.get("is_reply") or 0),
            sent_at=to_datetime(row.get("sent_at")),
            sentiment_score=float(row.get("sentiment_score") or 0),
            contact_name=row.get("contact_name", "") or "",
            account_name=row.get("account_name", "") or "",
        )


@dataclass(frozen=True)
class Meeting:
    meeting_id: str
    account_id: str
    deal_id: str
    organizer_id: str
    title: str
    meeting_type: str
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    duration_minutes: int
    location: str
    status: str
    agenda: str
    summary: str
    key_points: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    outcome: str = ""
    attendee_contact_ids: List[str] = field(default_factory=list)
    attendee_user_ids: List[str] = field(default_factory=list)
    account_name: str = ""

    @property
    def is_completed(self) -> bool:
        return self.status == "Completed"

    @property
    def time_label(self) -> str:
        return self.scheduled_start.strftime("%H:%M") if self.scheduled_start else ""

    @property
    def attendee_count(self) -> int:
        return len(self.attendee_contact_ids) + len(self.attendee_user_ids)

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Meeting":
        return cls(
            meeting_id=row["meeting_id"], account_id=row.get("account_id", "") or "",
            deal_id=row.get("deal_id", "") or "", organizer_id=row.get("organizer_id", ""),
            title=row.get("title", ""), meeting_type=row.get("meeting_type", ""),
            scheduled_start=to_datetime(row.get("scheduled_start")),
            scheduled_end=to_datetime(row.get("scheduled_end")),
            duration_minutes=int(row.get("duration_minutes") or 0),
            location=row.get("location", ""), status=row.get("status", ""),
            agenda=row.get("agenda", "") or "", summary=row.get("summary", "") or "",
            key_points=_json_list(row.get("key_points")),
            next_steps=_json_list(row.get("next_steps")),
            outcome=row.get("outcome", "") or "",
            attendee_contact_ids=_json_list(row.get("attendee_contact_ids")),
            attendee_user_ids=_json_list(row.get("attendee_user_ids")),
            account_name=row.get("account_name", "") or "",
        )


@dataclass(frozen=True)
class Signal:
    signal_id: str
    account_id: str
    contact_id: str
    owner_id: str
    signal_type: str
    playbook: str
    signal_title: str
    severity: str
    score: int
    status: str
    detected_at: Optional[datetime]
    action_recommended: str
    account_name: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Signal":
        return cls(
            signal_id=row["signal_id"], account_id=row.get("account_id", ""),
            contact_id=row.get("contact_id", "") or "", owner_id=row.get("owner_id", "") or "",
            signal_type=row.get("signal_type", ""), playbook=row.get("playbook", "") or "",
            signal_title=row.get("signal_title", ""), severity=row.get("severity", ""),
            score=int(row.get("score") or 0), status=row.get("status", ""),
            detected_at=to_datetime(row.get("detected_at")),
            action_recommended=row.get("action_recommended", "") or "",
            account_name=row.get("account_name", "") or "",
        )


@dataclass(frozen=True)
class Task:
    task_id: str
    account_id: str
    deal_id: str
    owner_id: str
    title: str
    description: str
    due_date: Optional[date]
    priority: str
    status: str
    source: str
    account_name: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Task":
        return cls(
            task_id=row["task_id"], account_id=row.get("account_id", "") or "",
            deal_id=row.get("deal_id", "") or "", owner_id=row.get("owner_id", ""),
            title=row.get("title", ""), description=row.get("description", "") or "",
            due_date=to_date(row.get("due_date")), priority=row.get("priority", ""),
            status=row.get("status", ""), source=row.get("source", ""),
            account_name=row.get("account_name", "") or "",
        )


@dataclass(frozen=True)
class Target:
    target_id: str
    user_id: str
    period_type: str
    period_start: Optional[date]
    period_end: Optional[date]
    metric: str
    target_amount: float

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Target":
        return cls(
            target_id=row["target_id"], user_id=row["user_id"],
            period_type=row.get("period_type", ""),
            period_start=to_date(row.get("period_start")),
            period_end=to_date(row.get("period_end")),
            metric=row.get("metric", ""),
            target_amount=float(row.get("target_amount") or 0),
        )
