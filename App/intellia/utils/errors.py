"""User-facing error types.

Nothing in the UI ever renders a traceback. Every failure maps to a short, plain-English
message; the technical detail is logged server-side.
"""

from __future__ import annotations

from typing import Optional


class IntelliaError(Exception):
    """Base class. Carries a message safe to show a user."""

    code = "error"
    default_message = "Something went wrong. Please try again."

    def __init__(self, user_message: Optional[str] = None, detail: Optional[str] = None) -> None:
        self.user_message = user_message or self.default_message
        self.detail = detail or ""
        super().__init__(self.user_message)


class SqlSafetyError(IntelliaError):
    code = "sql_safety"
    default_message = "Only read-only questions about your data are supported."

    def __init__(self, user_message: Optional[str] = None, detail: Optional[str] = None,
                 sql: Optional[str] = None, code: Optional[str] = None) -> None:
        super().__init__(user_message, detail)
        self.sql = sql or ""
        if code:
            self.code = code


class SqlTimeoutError(SqlSafetyError):
    code = "sql_timeout"
    default_message = "That query took too long. Try narrowing the time range or grouping."


class SqlDeniedError(SqlSafetyError):
    code = "sql_denied"
    default_message = "That question needs data this insight can't access. Try rephrasing."


class InsightGenerationError(IntelliaError):
    code = "insight_generation"
    default_message = (
        "I couldn't build that insight from the available data. "
        "Try asking for pipeline by rep, by stage, or by account."
    )


