"""Connector protocols -- the seam where real integrations replace the local seed.

Services depend on these Protocols, never on repositories directly, so swapping
``SqliteCRMConnector`` for a ``SalesforceCRMConnector`` (or Microsoft Graph for calendar
and mail) is a one-line change in ``bootstrap.py``. Every connector returns the same
``models.domain`` dataclasses, which act as the anti-corruption layer.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

try:  # Protocol is available on 3.8+, but keep the import defensive.
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

    def runtime_checkable(cls):  # type: ignore
        return cls

from intellia.data.scope import Scope
from intellia.models.domain import Account, Contact, Deal, Email, Meeting, Signal, Task


@runtime_checkable
class CRMConnector(Protocol):
    name: str

    def get_accounts(self, scope: Scope, limit: int = 200) -> List[Account]: ...
    def get_account(self, scope: Optional[Scope], account_id: str) -> Optional[Account]: ...
    def get_open_deals(self, scope: Scope, limit: int = 200) -> List[Deal]: ...
    def get_deal(self, scope: Optional[Scope], deal_id: str) -> Optional[Deal]: ...
    def get_contacts(self, scope: Optional[Scope], account_id: str) -> List[Contact]: ...


@runtime_checkable
class CalendarConnector(Protocol):
    name: str

    def get_meetings_for_day(self, scope: Scope, day: date,
                             organizer_id: Optional[str] = None) -> List[Meeting]: ...
    def get_upcoming_meetings(self, scope: Scope, as_of: date, days: int = 7) -> List[Meeting]: ...
    def get_meeting(self, scope: Optional[Scope], meeting_id: str) -> Optional[Meeting]: ...


@runtime_checkable
class EmailConnector(Protocol):
    name: str

    def get_thread(self, scope: Optional[Scope], thread_id: str) -> List[Email]: ...
    def get_recent_messages(self, scope: Optional[Scope], account_id: str,
                            limit: int = 5) -> List[Email]: ...
    def get_unanswered(self, scope: Scope, as_of: date) -> List[Email]: ...


@runtime_checkable
class SignalConnector(Protocol):
    name: str

    def get_active_signals(self, scope: Scope, as_of: date) -> List[Signal]: ...
    def get_signals_for_account(self, scope: Optional[Scope], account_id: str) -> List[Signal]: ...


@runtime_checkable
class TaskConnector(Protocol):
    name: str

    def get_open_tasks(self, scope: Scope) -> List[Task]: ...
    def get_overdue(self, scope: Scope, as_of: date) -> List[Task]: ...
