"""Context assembly -- 100% deterministic.

Builds the evidence bundle that every LLM task reasons over, and emits a stable
``context_hash`` used as part of the cache key. The LLM never fetches its own data:
it only ranks and writes prose over what this module assembles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from intellia.data.repositories.activity import (
    EmailRepository, MeetingRepository, SignalRepository, TaskRepository,
)
from intellia.data.repositories.crm import AccountRepository, ContactRepository, DealRepository
from intellia.data.scope import Scope
from intellia.models.domain import Account, Contact, Deal, Email, Meeting, Signal, Task
from intellia.utils.formatting import money, truncate

MAX_EMAILS = 6
MAX_MEETINGS = 3
MAX_CONTACTS = 6
MAX_BODY_CHARS = 320


@dataclass
class ContextBundle:
    """Everything the model is allowed to know about one situation."""

    account: Optional[Account] = None
    deal: Optional[Deal] = None
    contacts: List[Contact] = field(default_factory=list)
    emails: List[Email] = field(default_factory=list)
    meetings: List[Meeting] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    meeting: Optional[Meeting] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def valid_ref_ids(self) -> Dict[str, str]:
        """Every id the model may legitimately cite, mapped to its type."""
        refs: Dict[str, str] = {}
        if self.account:
            refs[self.account.account_id] = "account"
        if self.deal:
            refs[self.deal.deal_id] = "deal"
        if self.meeting:
            refs[self.meeting.meeting_id] = "meeting"
        for d in [self.deal] if self.deal else []:
            refs[d.deal_id] = "deal"
        for m in self.meetings:
            refs[m.meeting_id] = "meeting"
        for e in self.emails:
            refs[e.email_id] = "email"
        for s in self.signals:
            refs[s.signal_id] = "signal"
        for t in self.tasks:
            refs[t.task_id] = "task"
        for c in self.contacts:
            refs[c.contact_id] = "contact"
        return refs

    def to_prompt_markdown(self) -> str:
        """Compact markdown rendering -- what actually goes into the prompt."""
        parts: List[str] = []

        if self.account:
            a = self.account
            parts.append(
                "## Account\n"
                "{} ({}) | {} | {} | {} | ARR {} | health {}/100 | renewal {}".format(
                    a.account_name, a.account_id, a.industry, a.segment, a.status,
                    money(a.arr), a.health_score, a.renewal_date or "n/a"))

        if self.deal:
            d = self.deal
            parts.append(
                "## Deal\n"
                "{} ({}) | {} | {} | {} | close {} | prob {}% | forecast {}\n"
                "next step: {} (due {})\ncompetitor: {}".format(
                    d.deal_name, d.deal_id, d.deal_type, d.stage, money(d.amount),
                    d.close_date, d.probability, d.forecast_category,
                    d.next_step or "none", d.next_step_due_date or "n/a",
                    d.competitor or "none"))

        if self.contacts:
            lines = ["- {} ({}): {} | {}{}".format(
                c.full_name, c.contact_id, c.title, c.persona_role,
                " | CHAMPION" if c.is_champion else "") for c in self.contacts[:MAX_CONTACTS]]
            parts.append("## Contacts\n" + "\n".join(lines))

        if self.meeting:
            m = self.meeting
            parts.append(
                "## This meeting\n{} ({}) | {} | {} | {} min\nagenda: {}".format(
                    m.title, m.meeting_id, m.meeting_type,
                    m.scheduled_start.strftime("%Y-%m-%d %H:%M") if m.scheduled_start else "",
                    m.duration_minutes, m.agenda))

        if self.meetings:
            lines = []
            for m in self.meetings[:MAX_MEETINGS]:
                lines.append("- {} ({}) on {}, outcome: {}".format(
                    m.title, m.meeting_id,
                    m.scheduled_start.strftime("%Y-%m-%d") if m.scheduled_start else "",
                    m.outcome or "n/a"))
                for kp in m.key_points[:3]:
                    lines.append("    * {}".format(kp))
            parts.append("## Recent meetings\n" + "\n".join(lines))

        if self.emails:
            lines = []
            for e in self.emails[:MAX_EMAILS]:
                lines.append("- [{}] {} ({}) from {} sentiment {:+.2f}\n    {}".format(
                    e.direction, e.subject, e.email_id,
                    e.contact_name or e.sender_email, e.sentiment_score,
                    truncate(e.body or e.snippet, MAX_BODY_CHARS)))
            parts.append("## Recent email\n" + "\n".join(lines))

        if self.signals:
            lines = ["- {} ({}) score {}: {} | recommended: {}".format(
                s.signal_title, s.signal_id, s.score, s.signal_type, s.action_recommended)
                for s in self.signals]
            parts.append("## Signals\n" + "\n".join(lines))

        if self.tasks:
            lines = ["- {} ({}) due {} [{}]".format(t.title, t.task_id, t.due_date, t.priority)
                     for t in self.tasks]
            parts.append("## Open tasks\n" + "\n".join(lines))

        for key, value in self.extra.items():
            parts.append("## {}\n{}".format(key, value))

        return "\n\n".join(parts)

    def context_hash(self) -> str:
        payload = json.dumps(sorted(self.valid_ref_ids().items()), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ContextService:
    def __init__(self, accounts: AccountRepository, deals: DealRepository,
                 contacts: ContactRepository, meetings: MeetingRepository,
                 emails: EmailRepository, signals: SignalRepository,
                 tasks: TaskRepository) -> None:
        self.accounts, self.deals, self.contacts = accounts, deals, contacts
        self.meetings, self.emails = meetings, emails
        self.signals, self.tasks = signals, tasks

    def for_account(self, scope: Scope, account_id: str,
                    deal_id: str = "") -> ContextBundle:
        bundle = ContextBundle()
        if not account_id:
            return bundle
        bundle.account = self.accounts.get(scope, account_id)
        bundle.contacts = self.contacts.by_account(scope, account_id)[:MAX_CONTACTS]
        bundle.emails = self.emails.recent_for_account(scope, account_id, MAX_EMAILS)
        bundle.meetings = self.meetings.recent_for_account(scope, account_id, MAX_MEETINGS)
        bundle.signals = self.signals.for_account(scope, account_id, 4)
        bundle.tasks = self.tasks.for_account(scope, account_id)[:5]

        if deal_id:
            bundle.deal = self.deals.get(scope, deal_id)
        else:
            open_deals = [d for d in self.deals.by_account(scope, account_id) if d.is_open]
            bundle.deal = max(open_deals, key=lambda d: d.amount) if open_deals else None
        return bundle

    def for_meeting(self, scope: Scope, meeting: Meeting) -> ContextBundle:
        bundle = self.for_account(scope, meeting.account_id, meeting.deal_id)
        bundle.meeting = meeting
        if meeting.attendee_contact_ids:
            attendees = self.contacts.get_many(scope, meeting.attendee_contact_ids)
            if attendees:
                bundle.contacts = attendees
        return bundle

    def for_day(self, scope: Scope, as_of: date) -> ContextBundle:
        """The whole-day evidence set behind the Daily Brief."""
        bundle = ContextBundle()
        bundle.meetings = self.meetings.for_day(scope, as_of)
        bundle.signals = self.signals.active(scope, as_of, days=10, min_score=78, limit=8)
        bundle.emails = self.emails.unanswered_inbound(scope, as_of, min_age_days=2, limit=6)
        bundle.tasks = self.tasks.open_for_scope(scope, limit=10)
        return bundle
