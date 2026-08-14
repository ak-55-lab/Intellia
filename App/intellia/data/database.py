"""Database facade: idempotent build, read-only readers, and the SQL sandbox.

Connections are opened per call rather than cached. SQLite open on a ~2 MB file costs
microseconds, and this sidesteps the cross-thread cursor problems that bite cached
``sqlite3`` connections under Streamlit's threading model. Do not "optimize" this into a
shared connection.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from intellia.config.settings import AppSettings, QUERYABLE_TABLES, SCHEMA_VERSION
from intellia.data import loader
from intellia.data.scope import Scope, materialize
from intellia.utils.errors import SqlDeniedError, SqlTimeoutError
from intellia.utils.logging import get_logger

log = get_logger("database")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
APP_SCHEMA_PATH = Path(__file__).with_name("schema_app.sql")

MIN_SQLITE = (3, 23)  # the `true` keyword used by the few-shot SQL

# Scalar/aggregate functions an LLM-generated query may call.
ALLOWED_FUNCTIONS = {
    "sum", "avg", "min", "max", "count", "total", "abs", "round", "coalesce", "ifnull",
    "nullif", "cast", "length", "lower", "upper", "trim", "ltrim", "rtrim", "substr",
    "replace", "strftime", "date", "datetime", "julianday", "printf", "format",
    "group_concat", "iif", "case", "distinct", "row_number", "rank", "dense_rank",
    "sqlite_version", "instr", "like",
}


class Database:
    """Owns both databases and hands out scoped, read-only readers."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.analytics_path = settings.analytics_db
        self.app_state_path = settings.app_state_db
        self._write_lock = threading.Lock()
        self._allowlist: Optional[Dict[str, set]] = None

    # -- build -------------------------------------------------------------------------

    def ensure_built(self, force: bool = False) -> bool:
        """Rebuild only when the schema version or a source CSV hash has changed."""
        if sqlite3.sqlite_version_info < MIN_SQLITE:
            raise RuntimeError(
                "SQLite {} is too old; {}+ is required.".format(
                    sqlite3.sqlite_version, ".".join(str(p) for p in MIN_SQLITE)))

        hashes = loader.source_hashes(self.settings.data_dir)
        expected = {"schema_version": SCHEMA_VERSION, "source_hashes": json.dumps(hashes, sort_keys=True)}

        if not force and self.analytics_path.exists():
            try:
                with sqlite3.connect("file:{}?mode=ro".format(self.analytics_path), uri=True) as c:
                    meta = dict(c.execute("SELECT key, value FROM _meta").fetchall())
                if all(meta.get(k) == v for k, v in expected.items()):
                    self.ensure_app_state()
                    return False
            except sqlite3.Error:
                log.warning("Existing analytics DB unreadable; rebuilding.")

        loader.build_database(
            self.analytics_path, self.settings.data_dir,
            SCHEMA_PATH.read_text(encoding="utf-8"),
            meta=dict(expected, reporting_date=str(self.settings.reporting_date)),
        )
        self._allowlist = None
        self.ensure_app_state()
        return True

    def ensure_app_state(self) -> None:
        self.app_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.writer() as conn:
            conn.executescript(APP_SCHEMA_PATH.read_text(encoding="utf-8"))
            self._migrate_app_state(conn)

    @staticmethod
    def _migrate_app_state(conn: sqlite3.Connection) -> None:
        """Add columns the schema gained after a database was already created.

        ``CREATE TABLE IF NOT EXISTS`` is a no-op on an existing table, so a new
        column has to be added explicitly or an app-state DB from an earlier run
        keeps the old shape and every read of the new column fails.
        """
        for table, column, ddl in (
            ("layouts", "span", "ALTER TABLE layouts ADD COLUMN span INTEGER NOT NULL DEFAULT 0"),
        ):
            existing = {row["name"] for row in
                        conn.execute("PRAGMA table_info({})".format(table)).fetchall()}
            if existing and column not in existing:
                conn.execute(ddl)

    # -- connections -------------------------------------------------------------------

    @contextmanager
    def writer(self) -> Iterator[sqlite3.Connection]:
        """Serialized writable connection to the app-state DB."""
        with self._write_lock:
            conn = sqlite3.connect(str(self.app_state_path))
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    @contextmanager
    def raw_reader(self) -> Iterator[sqlite3.Connection]:
        """Unscoped read-only analytics connection (scope resolution, schema probes)."""
        conn = sqlite3.connect("file:{}?mode=ro".format(self.analytics_path), uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def reader(self, scope: Optional[Scope] = None, sandbox: bool = False,
               timeout: Optional[float] = None) -> Iterator[sqlite3.Connection]:
        """A read-only connection with the persona's scope materialized.

        ``sandbox=True`` additionally installs the authorizer and a progress-handler
        deadline -- use it for any SQL the application did not author itself.
        """
        conn = sqlite3.connect("file:{}?mode=ro".format(self.analytics_path), uri=True)
        conn.row_factory = sqlite3.Row
        try:
            if scope is not None:
                materialize(conn, scope)

            # query_only must be set BEFORE the authorizer, which denies PRAGMA.
            conn.execute("PRAGMA query_only = ON")

            if sandbox:
                conn.set_authorizer(self._authorizer)
                deadline = time.monotonic() + (timeout or self.settings.query_timeout_seconds)
                conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
            yield conn
        finally:
            try:
                conn.set_authorizer(None)
                conn.set_progress_handler(None, 0)
            except sqlite3.Error:
                pass
            conn.close()

    # -- sandbox authorizer ------------------------------------------------------------

    def allowlist(self) -> Dict[str, set]:
        """{table: {columns}} for every queryable table, derived from the live schema."""
        if self._allowlist is None:
            out: Dict[str, set] = {}
            with self.raw_reader() as conn:
                for table in QUERYABLE_TABLES:
                    cols = conn.execute("PRAGMA table_info({})".format(table)).fetchall()
                    out[table] = {r[1] for r in cols}
            self._allowlist = out
        return self._allowlist

    def schema_fingerprint(self) -> str:
        import hashlib

        payload = json.dumps(
            {t: sorted(c) for t, c in self.allowlist().items()}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _authorizer(self, action: int, arg1: Any, arg2: Any, dbname: Any, trigger: Any) -> int:
        # SELECT itself, and the transaction bookkeeping SQLite does implicitly.
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK

        if action == sqlite3.SQLITE_READ:
            table, column = arg1, arg2
            if table in ("sqlite_master", "sqlite_temp_master", "sqlite_schema"):
                return sqlite3.SQLITE_DENY
            allowed = self.allowlist().get(table)
            if allowed is None:
                return sqlite3.SQLITE_DENY
            # Reads must never resolve against `main` -- that is the unscoped data.
            # An unqualified name arrives with dbname None and resolves to the temp
            # shadow; an explicit `main.deals` arrives with dbname 'main' and would
            # bypass the persona's scope, so it is denied here as well as lexically.
            if dbname == "main":
                return sqlite3.SQLITE_DENY
            # An empty column name is SQLite probing table access (e.g. count(*)).
            if column and column not in allowed:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        if action == sqlite3.SQLITE_FUNCTION:
            name = (arg2 or "").lower()
            return sqlite3.SQLITE_OK if name in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY

        return sqlite3.SQLITE_DENY


def translate_sqlite_error(exc: Exception, sql: str = "") -> Exception:
    """Map a raw sqlite3 failure onto a user-safe error."""
    text = str(exc).lower()
    if "interrupted" in text:
        return SqlTimeoutError(detail=str(exc), sql=sql)
    if "not authorized" in text:
        return SqlDeniedError(detail=str(exc), sql=sql)
    if "no such column" in text or "no such table" in text:
        return SqlDeniedError(
            "That question referenced data that doesn't exist in this dataset.",
            detail=str(exc), sql=sql)
    if "only execute one statement" in text:
        return SqlDeniedError("Only one query at a time is supported.", detail=str(exc), sql=sql)
    return SqlDeniedError(detail=str(exc), sql=sql)
