"""Date helpers.

This is the ONLY module permitted to reference wall-clock time, and even then only for
the greeting's time-of-day. Every business date derives from ``REPORTING_DATE`` so the
demo never rots.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from intellia.config.settings import REPORTING_DATE

DATE_FMT = "%Y-%m-%d"
TS_FMT = "%Y-%m-%d %H:%M:%S"


def today() -> date:
    return REPORTING_DATE


def to_date(value: object) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in (DATE_FMT, TS_FMT):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in (TS_FMT, DATE_FMT):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def fmt(value: date) -> str:
    return value.strftime(DATE_FMT)


def quarter_bounds(when: Optional[date] = None) -> Tuple[date, date]:
    when = when or REPORTING_DATE
    q = (when.month - 1) // 3
    start = date(when.year, q * 3 + 1, 1)
    end_month = q * 3 + 3
    last_day = 31 if end_month in (1, 3, 5, 7, 8, 10, 12) else 30 if end_month != 2 else 28
    return start, date(when.year, end_month, last_day)


def quarter_label(when: Optional[date] = None) -> str:
    when = when or REPORTING_DATE
    return "Q{} {}".format((when.month - 1) // 3 + 1, when.year)


def ytd_bounds(when: Optional[date] = None) -> Tuple[date, date]:
    when = when or REPORTING_DATE
    return date(when.year, 1, 1), when


def days_until(target: Optional[date]) -> Optional[int]:
    return None if target is None else (target - REPORTING_DATE).days


def relative_day(target: Optional[date]) -> str:
    """'Today', 'Tomorrow', '3 days overdue', 'in 5 days', or a date."""
    delta = days_until(target)
    if delta is None:
        return ""
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "1 day overdue"
    if delta < 0:
        return "{} days overdue".format(-delta)
    if delta <= 14:
        return "in {} days".format(delta)
    return target.strftime("%b %-d")


def greeting_for(hour: Optional[int] = None) -> str:
    """Morning / afternoon / evening. Uses wall-clock hour only for the salutation."""
    h = datetime.now().hour if hour is None else hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


def refreshed_label(when: Optional[date] = None, clock: str = "07:45") -> str:
    """Footer stamp for every widget: 'Updated 13 Aug 2026, 07:45'.

    The clock is a fixed load stamp rather than wall-clock time, for the same
    reason nothing else here reads the system date: the demo must not rot, and
    two widgets rendered in one pass must not disagree by a second.
    """
    when = when or REPORTING_DATE
    return "Updated {} {} {}, {}".format(
        when.day, when.strftime("%b"), when.year, clock)


def display_date(when: Optional[date] = None) -> str:
    when = when or REPORTING_DATE
    # %-d is platform-specific; build the day number explicitly.
    return "{}, {} {}".format(when.strftime("%A"), when.strftime("%B"), when.day)


def window(days: int) -> Tuple[date, date]:
    return REPORTING_DATE - timedelta(days=days), REPORTING_DATE
