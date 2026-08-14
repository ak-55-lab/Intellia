"""Account, contact and deal repositories."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from intellia.data.repositories.base import BaseRepository
from intellia.data.scope import Scope
from intellia.models.domain import Account, Contact, Deal

OPEN_PREDICATE = "d.stage NOT IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')"

DEAL_SELECT = """
SELECT d.*, a.account_name AS account_name, u.full_name AS owner_name
FROM deals d
LEFT JOIN accounts a ON d.account_id = a.account_id
LEFT JOIN users u    ON d.owner_id  = u.user_id
"""


class AccountRepository(BaseRepository):
    def get(self, scope: Optional[Scope], account_id: str) -> Optional[Account]:
        row = self._row(scope, "SELECT * FROM accounts WHERE account_id = ?", (account_id,))
        return Account.from_row(row) if row else None

    def list_by_scope(self, scope: Scope, limit: int = 200) -> List[Account]:
        return self._map(
            scope, "SELECT * FROM accounts ORDER BY arr DESC, account_name LIMIT ?",
            Account.from_row, (limit,),
        )

    def search_by_name(self, scope: Scope, term: str, limit: int = 8) -> List[Account]:
        return self._map(
            scope,
            "SELECT * FROM accounts WHERE lower(account_name) LIKE lower(?) "
            "ORDER BY arr DESC LIMIT ?",
            Account.from_row, ("%{}%".format(term), limit),
        )

    def renewals_due(self, scope: Scope, within_days: int, as_of: date) -> List[Account]:
        horizon = date.fromordinal(as_of.toordinal() + within_days)
        return self._map(
            scope,
            "SELECT * FROM accounts WHERE renewal_date != '' AND renewal_date <= ? "
            "AND status = 'Customer' ORDER BY renewal_date",
            Account.from_row, (horizon.isoformat(),),
        )


class ContactRepository(BaseRepository):
    def by_account(self, scope: Optional[Scope], account_id: str) -> List[Contact]:
        return self._map(
            scope,
            "SELECT * FROM contacts WHERE account_id = ? ORDER BY influence DESC",
            Contact.from_row, (account_id,),
        )

    def champions_for_account(self, scope: Optional[Scope], account_id: str) -> List[Contact]:
        return self._map(
            scope,
            "SELECT * FROM contacts WHERE account_id = ? AND is_champion = 1",
            Contact.from_row, (account_id,),
        )

    def get_many(self, scope: Optional[Scope], contact_ids: List[str]) -> List[Contact]:
        if not contact_ids:
            return []
        placeholders = ",".join("?" for _ in contact_ids)
        return self._map(
            scope,
            "SELECT * FROM contacts WHERE contact_id IN ({})".format(placeholders),
            Contact.from_row, tuple(contact_ids),
        )


class DealRepository(BaseRepository):
    def get(self, scope: Optional[Scope], deal_id: str) -> Optional[Deal]:
        row = self._row(scope, DEAL_SELECT + " WHERE d.deal_id = ?", (deal_id,))
        return Deal.from_row(row) if row else None

    def open_by_scope(self, scope: Scope, limit: int = 200) -> List[Deal]:
        return self._map(
            scope,
            DEAL_SELECT + " WHERE " + OPEN_PREDICATE + " ORDER BY d.amount DESC LIMIT ?",
            Deal.from_row, (limit,),
        )

    def by_account(self, scope: Optional[Scope], account_id: str) -> List[Deal]:
        return self._map(
            scope, DEAL_SELECT + " WHERE d.account_id = ? ORDER BY d.close_date DESC",
            Deal.from_row, (account_id,),
        )

    def closing_between(self, scope: Scope, start: date, end: date,
                        open_only: bool = True) -> List[Deal]:
        predicate = OPEN_PREDICATE if open_only else "1 = 1"
        return self._map(
            scope,
            DEAL_SELECT + " WHERE {} AND d.close_date BETWEEN ? AND ? "
                          "ORDER BY d.close_date, d.amount DESC".format(predicate),
            Deal.from_row, (start.isoformat(), end.isoformat()),
        )

    def stalled(self, scope: Scope, as_of: date, days: int = 21) -> List[Deal]:
        cutoff = date.fromordinal(as_of.toordinal() - days)
        return self._map(
            scope,
            DEAL_SELECT + " WHERE " + OPEN_PREDICATE +
            " AND d.stage_entered_at <= ? ORDER BY d.amount DESC",
            Deal.from_row, (cutoff.isoformat(),),
        )

    def overdue_next_steps(self, scope: Scope, as_of: date) -> List[Deal]:
        return self._map(
            scope,
            DEAL_SELECT + " WHERE " + OPEN_PREDICATE +
            " AND d.next_step != '' AND d.next_step_due_date != ''"
            " AND d.next_step_due_date <= ? ORDER BY d.amount DESC",
            Deal.from_row, (as_of.isoformat(),),
        )
