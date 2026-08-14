"""Local implementations of the connector protocols, backed by the seeded SQLite DB.

A production build would register Salesforce / Microsoft Graph / Gmail implementations
here instead; nothing above this layer changes.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from intellia.data.repositories.activity import (
    EmailRepository, MeetingRepository, SignalRepository, TaskRepository,
)
from intellia.data.repositories.crm import AccountRepository, ContactRepository, DealRepository
from intellia.data.scope import Scope
from intellia.models.domain import Account, Contact, Deal, Email, Meeting, Signal, Task


class SqliteCRMConnector:
    name = "Intellia CRM (local)"

    def __init__(self, accounts: AccountRepository, deals: DealRepository,
                 contacts: ContactRepository) -> None:
        self.accounts, self.deals, self.contacts = accounts, deals, contacts

    def get_accounts(self, scope: Scope, limit: int = 200) -> List[Account]:
        return self.accounts.list_by_scope(scope, limit)

    def get_account(self, scope: Optional[Scope], account_id: str) -> Optional[Account]:
        return self.accounts.get(scope, account_id)

    def get_open_deals(self, scope: Scope, limit: int = 200) -> List[Deal]:
        return self.deals.open_by_scope(scope, limit)

    def get_deal(self, scope: Optional[Scope], deal_id: str) -> Optional[Deal]:
        return self.deals.get(scope, deal_id)

    def get_contacts(self, scope: Optional[Scope], account_id: str) -> List[Contact]:
        return self.contacts.by_account(scope, account_id)


class SqliteCalendarConnector:
    name = "Outlook Calendar (local)"

    def __init__(self, meetings: MeetingRepository) -> None:
        self.meetings = meetings

    def get_meetings_for_day(self, scope: Scope, day: date,
                             organizer_id: Optional[str] = None) -> List[Meeting]:
        return self.meetings.for_day(scope, day, organizer_id)

    def get_upcoming_meetings(self, scope: Scope, as_of: date, days: int = 7) -> List[Meeting]:
        return self.meetings.upcoming(scope, as_of, days)

    def get_meeting(self, scope: Optional[Scope], meeting_id: str) -> Optional[Meeting]:
        return self.meetings.get(scope, meeting_id)


class SqliteEmailConnector:
    name = "Outlook Mail (local)"

    def __init__(self, emails: EmailRepository) -> None:
        self.emails = emails

    def get_thread(self, scope: Optional[Scope], thread_id: str) -> List[Email]:
        return self.emails.thread(scope, thread_id)

    def get_recent_messages(self, scope: Optional[Scope], account_id: str,
                            limit: int = 5) -> List[Email]:
        return self.emails.recent_for_account(scope, account_id, limit)

    def get_unanswered(self, scope: Scope, as_of: date) -> List[Email]:
        return self.emails.unanswered_inbound(scope, as_of)


class SqliteSignalConnector:
    name = "Intellia Signals (local)"

    def __init__(self, signals: SignalRepository) -> None:
        self.signals = signals

    def get_active_signals(self, scope: Scope, as_of: date) -> List[Signal]:
        return self.signals.active(scope, as_of)

    def get_signals_for_account(self, scope: Optional[Scope], account_id: str) -> List[Signal]:
        return self.signals.for_account(scope, account_id)


class SqliteTaskConnector:
    name = "Asana (local)"

    def __init__(self, tasks: TaskRepository) -> None:
        self.tasks = tasks

    def get_open_tasks(self, scope: Scope) -> List[Task]:
        return self.tasks.open_for_scope(scope)

    def get_overdue(self, scope: Scope, as_of: date) -> List[Task]:
        return self.tasks.overdue(scope, as_of)
