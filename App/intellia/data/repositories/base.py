"""Repository base.

Rules for every repository method:

* One static, fully-parameterized SQL string. No f-string SQL, ever.
* Takes a ``Scope``; relies on the temp-table shadowing to narrow rows rather than
  injecting owner predicates itself.
* Returns dataclasses from ``models.domain``, never raw tuples.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

from intellia.data.database import Database
from intellia.data.scope import Scope

T = TypeVar("T")


class BaseRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _rows(self, scope: Optional[Scope], sql: str,
              params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self.db.reader(scope) as conn:
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]

    def _row(self, scope: Optional[Scope], sql: str,
             params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        rows = self._rows(scope, sql, params)
        return rows[0] if rows else None

    def _scalar(self, scope: Optional[Scope], sql: str,
                params: Sequence[Any] = (), default: Any = 0) -> Any:
        row = self._row(scope, sql, params)
        if not row:
            return default
        value = list(row.values())[0]
        return default if value is None else value

    def _map(self, scope: Optional[Scope], sql: str, factory: Callable[[Dict[str, Any]], T],
             params: Sequence[Any] = ()) -> List[T]:
        return [factory(r) for r in self._rows(scope, sql, params)]
