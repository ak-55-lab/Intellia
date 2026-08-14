"""Action queue -- fully deterministic.

Actions are extracted from five sources, de-duplicated, then ranked by an explicit
weighted score. No LLM is involved in building or ordering this list, so the queue
renders identically with or without an API key. The LLM is used only on demand, to
explain a single action or draft its email.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from intellia.data.repositories.activity import (
    EmailRepository, MeetingRepository, SignalRepository, TaskRepository,
)
from intellia.data.repositories.crm import DealRepository
from intellia.data.scope import Scope
from intellia.models.action import Action
from intellia.models.domain import Deal
from intellia.utils.dates import days_until

# Scoring weights, kept in one place so ranking is auditable.
SOURCE_WEIGHT = {"deal": 26.0, "signal": 22.0, "meeting": 18.0, "email": 16.0, "task": 14.0}
URGENCY_BONUS = 34.0      # applied on a decay curve against the due date
VALUE_BONUS = 26.0        # applied on a log-ish curve against deal amount
SENTIMENT_PENALTY = 12.0
STALLED_DAYS = 21


def _urgency(due: Optional[date]) -> float:
    """1.0 for overdue, decaying to 0 about three weeks out."""
    delta = days_until(due)
    if delta is None:
        return 0.35
    if delta <= 0:
        return 1.0
    return max(0.0, 1.0 - (delta / 21.0))


def _value(amount: float) -> float:
    if amount <= 0:
        return 0.0
    return min(1.0, amount / 400_000.0)


def _priority_from(score: float) -> str:
    return "High" if score >= 62 else "Medium" if score >= 42 else "Low"


class ActionService:
    def __init__(self, deals: DealRepository, meetings: MeetingRepository,
                 emails: EmailRepository, signals: SignalRepository,
                 tasks: TaskRepository) -> None:
        self.deals, self.meetings = deals, meetings
        self.emails, self.signals, self.tasks = emails, signals, tasks

    # -- extraction --------------------------------------------------------------------

    def _from_deals(self, scope: Scope, as_of: date) -> List[Action]:
        out: List[Action] = []
        for deal in self.deals.overdue_next_steps(scope, as_of):
            score = (SOURCE_WEIGHT["deal"] + URGENCY_BONUS * _urgency(deal.next_step_due_date)
                     + VALUE_BONUS * _value(deal.amount))
            out.append(Action(
                key="deal:{}:next_step".format(deal.deal_id),
                title=deal.next_step or "Advance {}".format(deal.deal_name),
                source="deal", source_label="Deal next step",
                priority=_priority_from(score), score=score,
                due_date=deal.next_step_due_date, ref_type="deal", ref_id=deal.deal_id,
                account_id=deal.account_id, account_name=deal.account_name,
                deal_id=deal.deal_id, deal_name=deal.deal_name, amount=deal.amount,
                why="The committed next step on {} is past its date.".format(deal.deal_name),
                default_action_type="update_crm",
            ))

        for deal in self.deals.stalled(scope, as_of, STALLED_DAYS):
            days = days_until(deal.stage_entered_at)
            stalled_for = -days if days is not None else STALLED_DAYS
            score = (SOURCE_WEIGHT["deal"] + VALUE_BONUS * _value(deal.amount)
                     + min(URGENCY_BONUS, stalled_for * 0.8))
            out.append(Action(
                key="deal:{}:stalled".format(deal.deal_id),
                title="Re-engage {}, {} days in {}".format(
                    deal.account_name or deal.deal_name, stalled_for, deal.stage_short),
                source="deal", source_label="Stalled deal",
                priority=_priority_from(score), score=score,
                due_date=deal.close_date, ref_type="deal", ref_id=deal.deal_id,
                account_id=deal.account_id, account_name=deal.account_name,
                deal_id=deal.deal_id, deal_name=deal.deal_name, amount=deal.amount,
                why="No stage movement for {} days with a close date of {}.".format(
                    stalled_for, deal.close_date),
                default_action_type="draft_email",
            ))
        return out

    def _from_meetings(self, scope: Scope, as_of: date) -> List[Action]:
        out: List[Action] = []
        for meeting in self.meetings.for_day(scope, as_of):
            if not meeting.is_completed:
                continue
            for idx, step in enumerate(meeting.next_steps):
                score = SOURCE_WEIGHT["meeting"] + URGENCY_BONUS * 0.8
                out.append(Action(
                    key="meeting:{}:{}".format(meeting.meeting_id, idx),
                    title=step,
                    source="meeting", source_label="From {}".format(meeting.title),
                    priority=_priority_from(score), score=score,
                    due_date=as_of, ref_type="meeting", ref_id=meeting.meeting_id,
                    account_id=meeting.account_id, account_name=meeting.account_name,
                    deal_id=meeting.deal_id,
                    why="Captured as a next step in {}.".format(meeting.title),
                    default_action_type="create_task",
                ))
        return out

    def _from_emails(self, scope: Scope, as_of: date) -> List[Action]:
        out: List[Action] = []
        for email in self.emails.unanswered_inbound(scope, as_of, min_age_days=2, limit=12):
            negative = email.sentiment_score < -0.2
            score = (SOURCE_WEIGHT["email"] + URGENCY_BONUS * 0.55
                     + (SENTIMENT_PENALTY if negative else 0.0))
            who = email.contact_name or email.sender_email
            out.append(Action(
                key="email:{}".format(email.email_id),
                title="Reply to {}: {}".format(who, email.subject),
                source="email", source_label="Unanswered email",
                priority=_priority_from(score), score=score,
                due_date=as_of, ref_type="email", ref_id=email.email_id,
                account_id=email.account_id, account_name=email.account_name,
                deal_id=email.deal_id, contact_name=who, contact_email=email.sender_email,
                why=("Inbound message with negative sentiment is still unanswered."
                     if negative else "Last message in the thread is still unanswered."),
                default_action_type="draft_email",
                evidence={"sentiment": email.sentiment_score, "snippet": email.snippet},
            ))
        return out

    def _from_signals(self, scope: Scope, as_of: date) -> List[Action]:
        out: List[Action] = []
        for signal in self.signals.active(scope, as_of, days=14, min_score=75, limit=12):
            score = SOURCE_WEIGHT["signal"] + (signal.score / 100.0) * URGENCY_BONUS
            out.append(Action(
                key="signal:{}".format(signal.signal_id),
                title="{}: {}".format(signal.account_name, signal.signal_title),
                source="signal", source_label="{} signal".format(signal.signal_type),
                priority=_priority_from(score), score=score,
                due_date=None, ref_type="signal", ref_id=signal.signal_id,
                account_id=signal.account_id, account_name=signal.account_name,
                why=signal.action_recommended,
                default_action_type="draft_email",
                evidence={"score": signal.score, "playbook": signal.playbook},
            ))
        return out

    def _from_tasks(self, scope: Scope, as_of: date) -> List[Action]:
        out: List[Action] = []
        for task in self.tasks.open_for_scope(scope, limit=40):
            score = SOURCE_WEIGHT["task"] + URGENCY_BONUS * _urgency(task.due_date)
            if task.priority == "High":
                score += 8
            out.append(Action(
                key="task:{}".format(task.task_id),
                title=task.title,
                source="task", source_label="Task",
                priority=_priority_from(score), score=score,
                due_date=task.due_date, ref_type="task", ref_id=task.task_id,
                account_id=task.account_id, account_name=task.account_name,
                deal_id=task.deal_id,
                why=task.description or "Open task from your queue.",
                default_action_type="create_task",
            ))
        return out

    # -- assembly ----------------------------------------------------------------------

    def build_queue(self, scope: Scope, as_of: date, limit: int = 12) -> List[Action]:
        candidates: List[Action] = []
        candidates.extend(self._from_deals(scope, as_of))
        candidates.extend(self._from_meetings(scope, as_of))
        candidates.extend(self._from_emails(scope, as_of))
        candidates.extend(self._from_signals(scope, as_of))
        candidates.extend(self._from_tasks(scope, as_of))

        # De-duplicate: the same underlying work often surfaces from two sources
        # (a meeting next step that also became a task, for example).
        seen_titles: Dict[str, Action] = {}
        deduped: List[Action] = []
        for action in sorted(candidates, key=lambda a: a.score, reverse=True):
            fingerprint = "{}|{}".format(
                action.title.strip().lower()[:60], action.account_id or action.deal_id)
            if fingerprint in seen_titles:
                continue
            seen_titles[fingerprint] = action
            deduped.append(action)

        return deduped[:limit]

    def get(self, scope: Scope, as_of: date, key: str) -> Optional[Action]:
        for action in self.build_queue(scope, as_of, limit=200):
            if action.key == key:
                return action
        return None
