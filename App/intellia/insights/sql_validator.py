"""Lexical SQL validation -- the first of five independent safety layers.

This layer produces good error messages fast. It is NOT the security boundary:
the sqlite3 authorizer in ``data/database.py`` is, and it runs regardless of what
happens here.
"""

from __future__ import annotations

import re
import sqlite3
from typing import List

from intellia.utils.errors import SqlSafetyError

MAX_SQL_LENGTH = 8000

FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "attach", "detach", "create",
    "replace", "pragma", "vacuum", "reindex", "begin", "commit", "rollback",
    "savepoint", "release", "trigger", "temp", "temporary", "load_extension",
    "randomblob", "writefile", "readfile", "edit", "grant", "revoke", "truncate",
)

# `WITH` is allowed as a leading CTE keyword even though `create` is not.
_LEADING = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_QUALIFIER = re.compile(r"\b(main|temp|sqlite_master|sqlite_temp_master|sqlite_schema)\s*\.",
                        re.IGNORECASE)
_SQLITE_INTERNAL = re.compile(r"\bsqlite_[a-z_]+\b", re.IGNORECASE)


def strip_comments(sql: str) -> str:
    """Remove -- and /* */ comments while respecting string literals.

    Done before any keyword scan so ``SELECT 1 -- ; DROP TABLE deals`` cannot
    smuggle a token past the deny-list.
    """
    out: List[str] = []
    i, n = 0, len(sql)
    quote = ""
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                # Doubled quote is an escape inside SQL string literals.
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = ""
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_statements(sql: str) -> List[str]:
    stripped = strip_comments(sql).strip()
    parts = [p.strip() for p in stripped.split(";")]
    return [p for p in parts if p]


def validate(sql: str) -> str:
    """Return the normalized single-statement SQL, or raise ``SqlSafetyError``."""
    if not sql or not sql.strip():
        raise SqlSafetyError("The insight has no query attached.", sql=sql)

    if len(sql) > MAX_SQL_LENGTH:
        raise SqlSafetyError("That query is too long to run safely.", sql=sql)

    cleaned = strip_comments(sql).strip()
    statements = _split_statements(sql)
    if len(statements) > 1:
        raise SqlSafetyError("Only one query at a time is supported.",
                             detail="{} statements".format(len(statements)), sql=sql)
    if not statements:
        raise SqlSafetyError("The insight has no query attached.", sql=sql)

    body = statements[0]

    if not _LEADING.match(body):
        raise SqlSafetyError("Only read-only questions about your data are supported.",
                             detail="statement does not begin with SELECT or WITH", sql=sql)

    lowered = body.lower()
    for word in FORBIDDEN:
        if re.search(r"\b{}\b".format(re.escape(word)), lowered):
            raise SqlSafetyError(
                "Only read-only questions about your data are supported.",
                detail="forbidden keyword: {}".format(word), sql=sql)

    if _QUALIFIER.search(body) or _SQLITE_INTERNAL.search(body):
        raise SqlSafetyError(
            "That query tried to reach data outside your view.",
            detail="schema-qualified or sqlite_ internal reference", sql=sql)

    # sqlite3 itself is the arbiter of syntactic completeness.
    if not sqlite3.complete_statement(body + ";"):
        raise SqlSafetyError("That query looks incomplete.", sql=sql)

    return body


