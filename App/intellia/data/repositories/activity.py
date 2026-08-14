"""Meeting, email, signal and task repositories."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from intellia.data.repositories.base import BaseRepository
from intellia.data.scope import Scope
from intellia.models.domain import Email, Meeting, Signal, Task

MEETING_SELECT = """
SELECT m.*, a.account_name AS account_name
FROM meetings m
LEFT JOIN accounts a ON m.account_id = a.account_id
"""

EMAIL_SELECT = """
SELECT e.*, a.account_name AS account_name,
       TRIM(COALESCE(c.first_name, '') || ' ' || COALESCE(c.last_name, '')) AS contact_name
FROM emails e
LEFT JOIN accounts a ON e.account_id = a.account_id
LEFT JOIN contacts c ON e.contact_id = c.contact_id
"""

SIGNAL_SELECT = """
SELECT s.*, a.account_name AS account_name
FROM signals s
LEFT JOIN accounts a ON s.account_id = a.account_id
"""

TASK_SELECT = """
SELECT t.*, a.account_name AS account_name
FROM tasks t
LEFT JOIN accounts a ON t.account_id = a.account_id
"""


class MeetingRepository(BaseRepository):
    def get(self, scope: Optional[Scope], meeting_id: str) -> Optional[Meeting]:
        row = self._row(scope, MEETING_SELECT + " WHERE m.meeting_id = ?", (meeting_id,))
        return Meeting.from_row(row) if row else None

    def for_day(self, scope: Scope, day: date, organizer_id: Optional[str] = None) -> List[Meeting]:
        if organizer_id:
            return self._map(
                scope,
                MEETING_SELECT + " WHERE date(m.scheduled_start) = ? AND m.organizer_id = ?"
                                 " ORDER BY m.scheduled_start",
                Meeting.from_row, (day.isoformat(), organizer_id),
            )
        return self._map(
            scope,
            MEETING_SELECT + " WHERE date(m.scheduled_start) = ? ORDER BY m.scheduled_start",
            Meeting.from_row, (day.isoformat(),),
        )

    def upcoming(self, scope: Scope, as_of: date, days: int = 7) -> List[Meeting]:
        return self._map(
            scope,
            MEETING_SELECT + " WHERE date(m.scheduled_start) BETWEEN ? AND ?"
                             " AND m.status = 'Scheduled' ORDER BY m.scheduled_start",
            Meeting.from_row,
            (as_of.isoformat(), (as_of + timedelta(days=days)).isoformat()),
        )

    def recent_for_account(self, scope: Optional[Scope], account_id: str,
                           limit: int = 3) -> List[Meeting]:
        return self._map(
            scope,
            MEETING_SELECT + " WHERE m.account_id = ? AND m.status = 'Completed'"
                             " ORDER BY m.scheduled_start DESC LIMIT ?",
            Meeting.from_row, (account_id, limit),
        )


class EmailRepository(BaseRepository):
    def thread(self, scope: Optional[Scope], thread_id: str) -> List[Email]:
        return self._map(
            scope, EMAIL_SELECT + " WHERE e.thread_id = ? ORDER BY e.sent_at",
            Email.from_row, (thread_id,),
        )

    def recent_for_account(self, scope: Optional[Scope], account_id: str,
                           limit: int = 5) -> List[Email]:
        return self._map(
            scope, EMAIL_SELECT + " WHERE e.account_id = ? ORDER BY e.sent_at DESC LIMIT ?",
            Email.from_row, (account_id, limit),
        )

    def unanswered_inbound(self, scope: Scope, as_of: date, min_age_days: int = 2,
                           limit: int = 25) -> List[Email]:
        """Latest inbound message in a thread with no later outbound reply."""
        cutoff = (as_of - timedelta(days=min_age_days)).isoformat()
        return self._map(
            scope,
            EMAIL_SELECT + """
            WHERE e.direction = 'Inbound'
              AND date(e.sent_at) <= ?
              AND e.sent_at = (SELECT MAX(e2.sent_at) FROM emails e2 WHERE e2.thread_id = e.thread_id)
            ORDER BY e.sentiment_score ASC, e.sent_at DESC
            LIMIT ?
            """,
            Email.from_row, (cutoff, limit),
        )

    def negative_recent(self, scope: Scope, as_of: date, days: int = 30,
                        threshold: float = -0.25, limit: int = 20) -> List[Email]:
        return self._map(
            scope,
            EMAIL_SELECT + " WHERE e.sentiment_score <= ? AND date(e.sent_at) >= ?"
                           " ORDER BY e.sentiment_score ASC LIMIT ?",
            Email.from_row,
            (threshold, (as_of - timedelta(days=days)).isoformat(), limit),
        )


class SignalRepository(BaseRepository):
    def get(self, scope: Optional[Scope], signal_id: str) -> Optional[Signal]:
        row = self._row(scope, SIGNAL_SELECT + " WHERE s.signal_id = ?", (signal_id,))
        return Signal.from_row(row) if row else None

    def active(self, scope: Scope, as_of: date, days: int = 14, min_score: int = 70,
               limit: int = 40) -> List[Signal]:
        return self._map(
            scope,
            SIGNAL_SELECT + " WHERE s.status = 'New' AND s.score >= ?"
                            " AND date(s.detected_at) >= ?"
                            " ORDER BY s.score DESC, s.detected_at DESC LIMIT ?",
            Signal.from_row,
            (min_score, (as_of - timedelta(days=days)).isoformat(), limit),
        )

    def for_account(self, scope: Optional[Scope], account_id: str, limit: int = 5) -> List[Signal]:
        return self._map(
            scope,
            SIGNAL_SELECT + " WHERE s.account_id = ? ORDER BY s.detected_at DESC LIMIT ?",
            Signal.from_row, (account_id, limit),
        )


class TaskRepository(BaseRepository):
    def open_for_scope(self, scope: Scope, limit: int = 60) -> List[Task]:
        return self._map(
            scope,
            TASK_SELECT + " WHERE t.status != 'Done' ORDER BY t.due_date LIMIT ?",
            Task.from_row, (limit,),
        )

    def overdue(self, scope: Scope, as_of: date) -> List[Task]:
        return self._map(
            scope,
            TASK_SELECT + " WHERE t.status != 'Done' AND t.due_date < ? ORDER BY t.due_date",
            Task.from_row, (as_of.isoformat(),),
        )

    def for_account(self, scope: Optional[Scope], account_id: str) -> List[Task]:
        return self._map(
            scope,
            TASK_SELECT + " WHERE t.account_id = ? AND t.status != 'Done' ORDER BY t.due_date",
            Task.from_row, (account_id,),
        )
