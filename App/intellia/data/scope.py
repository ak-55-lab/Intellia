"""Persona scope.

A ``Scope`` is materialized as SQLite TEMP tables that shadow the real ones. Because
SQLite resolves an unqualified ``deals`` to the temp schema before ``main``, every query
-- repository SQL and LLM-generated SQL alike -- is scoped without any string rewriting.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Sequence

from intellia.config.personas import Persona
from intellia.config.settings import QUERYABLE_TABLES

# How each scoped table narrows to the persona's book. ``{ids}`` expands to bound
# placeholders; nothing is string-interpolated except the placeholder run itself.
SCOPE_PREDICATES = {
    # `users` and `targets` are scoped too. Leaving them as whole copies let a query
    # driven from `users` (e.g. "pipeline by rep") enumerate every seller in the
    # company -- names and quota targets included -- even though their deals were
    # correctly hidden. Scoping them keeps rep-level insights inside the team.
    "users": "user_id IN ({ids})",
    "targets": "user_id IN ({ids})",
    "deals": "owner_id IN ({ids})",
    "accounts": "owner_id IN ({ids}) OR account_id IN (SELECT account_id FROM temp.deals)",
    "contacts": "account_id IN (SELECT account_id FROM temp.accounts)",
    "emails": "account_id IN (SELECT account_id FROM temp.accounts)",
    "signals": "account_id IN (SELECT account_id FROM temp.accounts)",
    "meetings": "organizer_id IN ({ids}) OR account_id IN (SELECT account_id FROM temp.accounts)",
    "tasks": "owner_id IN ({ids})",
}

# Order matters: accounts depends on temp.deals, the rest depend on temp.accounts.
SCOPE_ORDER = ("users", "targets", "deals", "accounts", "contacts", "emails",
               "signals", "meetings", "tasks")


@dataclass(frozen=True)
class Scope:
    """Which users' data is visible."""

    persona_id: str
    user_ids: Optional[List[str]]   # None == unrestricted
    label: str = ""
    primary_user_id: str = ""
    team_size: int = 0

    @property
    def is_unrestricted(self) -> bool:
        return self.user_ids is None

    def cache_key(self) -> str:
        return "{}:{}".format(self.persona_id, ",".join(sorted(self.user_ids or ["*"])))


def team_tree(conn: sqlite3.Connection, root_user_id: str) -> List[str]:
    """The manager plus everyone beneath them, via a recursive CTE over ``manager_id``."""
    rows = conn.execute(
        """
        WITH RECURSIVE tree(user_id) AS (
            SELECT user_id FROM users WHERE user_id = ?
            UNION
            SELECT u.user_id FROM users u JOIN tree t ON u.manager_id = t.user_id
        )
        SELECT user_id FROM tree
        """,
        (root_user_id,),
    ).fetchall()
    return [r[0] for r in rows]


def resolve_scope(conn: sqlite3.Connection, persona: Persona) -> Scope:
    if persona.scope_kind == "all":
        return Scope(persona.id, None, "All revenue", persona.user_id, 0)

    if persona.scope_kind == "team":
        members = team_tree(conn, persona.user_id)
        sellers = conn.execute(
            "SELECT user_id FROM users WHERE manager_id = ? AND quota_annual > 0",
            (persona.user_id,),
        ).fetchall()
        return Scope(
            persona.id, members,
            "{}'s team ({} reps)".format(persona.label.split(" ")[0], len(sellers)),
            persona.user_id, len(sellers),
        )

    return Scope(persona.id, [persona.user_id], "Your book", persona.user_id, 1)


def materialize(conn: sqlite3.Connection, scope: Scope) -> None:
    """Create TEMP shadow tables for every queryable table.

    Unscoped tables (users, targets) are copied whole so that the sandbox authorizer can
    apply one uniform rule: reads must come from the ``temp`` schema.
    """
    ids: Sequence[str] = scope.user_ids or []
    placeholders = ",".join("?" for _ in ids)

    for table in SCOPE_ORDER:
        if scope.is_unrestricted:
            conn.execute("CREATE TEMP TABLE {t} AS SELECT * FROM main.{t}".format(t=table))
            continue
        predicate = SCOPE_PREDICATES[table].format(ids=placeholders or "NULL")
        params = tuple(ids) if "{ids}" in SCOPE_PREDICATES[table] else ()
        conn.execute(
            "CREATE TEMP TABLE {t} AS SELECT * FROM main.{t} WHERE {p}".format(t=table, p=predicate),
            params,
        )

    for table in QUERYABLE_TABLES:
        if table not in SCOPE_ORDER:
            conn.execute("CREATE TEMP TABLE {t} AS SELECT * FROM main.{t}".format(t=table))
