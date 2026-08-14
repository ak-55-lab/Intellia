"""The SQL sandbox.

Kept separate from ``insight_engine`` on purpose: this is the security boundary,
and it must be unit-testable without any of the orchestration around it.

Layers applied here, in order:
  1. lexical validation (``sql_validator``)
  2. read-only connection + ``PRAGMA query_only``      (``Database.reader``)
  3. sqlite3 authorizer: allowlisted tables/columns/functions, no ``main`` reads
  4. progress-handler deadline + row cap
  5. every failure mapped to a plain-English error
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import pandas as pd

from intellia.data.database import Database, translate_sqlite_error
from intellia.data.scope import Scope
from intellia.insights import sql_validator
from intellia.utils.errors import SqlSafetyError
from intellia.utils.logging import get_logger

log = get_logger("executor")


@dataclass
class QueryResult:
    dataframe: pd.DataFrame
    columns: List[Tuple[str, str]] = field(default_factory=list)  # (name, sqlite type)
    truncated: bool = False
    row_count: int = 0
    elapsed_ms: int = 0


class SqlExecutor:
    def __init__(self, db: Database, max_rows: int = 5000,
                 timeout_seconds: float = 5.0) -> None:
        self.db = db
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

    # -- prepare-time check ------------------------------------------------------------

    def describe(self, sql: str, scope: Scope) -> List[str]:
        """Run the statement at LIMIT 0 to learn its output columns.

        The authorizer fires at *prepare* time, so a disallowed table, column or
        function is rejected here before a single row is read.
        """
        body = sql_validator.validate(sql)
        wrapped = "SELECT * FROM ({}) LIMIT 0".format(body)
        try:
            with self.db.reader(scope, sandbox=True, timeout=self.timeout_seconds) as conn:
                cursor = conn.execute(wrapped)
                return [d[0] for d in (cursor.description or [])]
        except SqlSafetyError:
            raise
        except Exception as exc:
            raise translate_sqlite_error(exc, sql)

    # -- execution ---------------------------------------------------------------------

    def run(self, sql: str, scope: Scope, params: Sequence[Any] = (),
            limit: Optional[int] = None) -> QueryResult:
        import time

        body = sql_validator.validate(sql)
        cap = limit or self.max_rows
        started = time.monotonic()

        try:
            with self.db.reader(scope, sandbox=True, timeout=self.timeout_seconds) as conn:
                cursor = conn.execute(body, tuple(params))
                columns = [(d[0], "") for d in (cursor.description or [])]
                rows = cursor.fetchmany(cap + 1)
        except SqlSafetyError:
            raise
        except Exception as exc:
            log.info("Query failed: %s", exc)
            raise translate_sqlite_error(exc, sql)

        truncated = len(rows) > cap
        if truncated:
            rows = rows[:cap]

        frame = pd.DataFrame(
            [tuple(r) for r in rows],
            columns=[c[0] for c in columns] if columns else None,
        )
        return QueryResult(
            dataframe=frame,
            columns=columns,
            truncated=truncated,
            row_count=len(frame),
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    def probe_columns(self, sql: str, scope: Scope) -> List[str]:
        """Legal filter column names -- taken from the engine, never from a guess."""
        try:
            return self.describe(sql, scope)
        except SqlSafetyError:
            return []
