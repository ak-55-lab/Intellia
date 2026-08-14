from __future__ import annotations

from datetime import date
from typing import List, Optional

from intellia.data.repositories.base import BaseRepository
from intellia.models.domain import Target, User


class UserRepository(BaseRepository):
    def get(self, user_id: str) -> Optional[User]:
        row = self._row(None, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        return User.from_row(row) if row else None

    def all_users(self) -> List[User]:
        return self._map(None, "SELECT * FROM users ORDER BY full_name", User.from_row)

    def direct_reports(self, user_id: str) -> List[User]:
        return self._map(
            None,
            "SELECT * FROM users WHERE manager_id = ? ORDER BY quota_annual DESC, full_name",
            User.from_row, (user_id,),
        )

    def selling_reports(self, user_id: str) -> List[User]:
        return self._map(
            None,
            "SELECT * FROM users WHERE manager_id = ? AND quota_annual > 0 ORDER BY full_name",
            User.from_row, (user_id,),
        )


class TargetRepository(BaseRepository):
    def for_user_period(self, user_id: str, period_start: date, period_end: date,
                        period_type: str = "quarter") -> Optional[Target]:
        row = self._row(
            None,
            """
            SELECT * FROM targets
            WHERE user_id = ? AND period_type = ?
              AND period_start <= ? AND period_end >= ?
            LIMIT 1
            """,
            (user_id, period_type, period_start.isoformat(), period_end.isoformat()),
        )
        return Target.from_row(row) if row else None

    def sum_for_users(self, user_ids: List[str], period_start: date, period_end: date,
                      period_type: str = "quarter") -> float:
        if not user_ids:
            return 0.0
        placeholders = ",".join("?" for _ in user_ids)
        sql = (
            "SELECT COALESCE(SUM(target_amount), 0) AS total FROM targets "
            "WHERE period_type = ? AND period_start <= ? AND period_end >= ? "
            "AND user_id IN ({})".format(placeholders)
        )
        params = [period_type, period_start.isoformat(), period_end.isoformat()] + list(user_ids)
        return float(self._scalar(None, sql, params, 0.0))
