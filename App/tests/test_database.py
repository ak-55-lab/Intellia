"""Database build, typing and seed invariants."""

from __future__ import annotations

import sqlite3

import pytest

from intellia.config.settings import SEED_TABLES


def test_all_tables_exist(db):
    with db.raw_reader() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for table in SEED_TABLES:
        assert table in names
    assert "_meta" in names


def test_build_is_idempotent(db):
    """A second call with unchanged CSV hashes must not rebuild."""
    before = db.analytics_path.stat().st_mtime_ns
    rebuilt = db.ensure_built()
    assert rebuilt is False
    assert db.analytics_path.stat().st_mtime_ns == before


def test_is_champion_stored_as_integer(db):
    """Regression: the original seed wrote Python 'True'/'False' strings, which
    silently broke every `is_champion = true` predicate in the few-shot SQL."""
    with db.raw_reader() as conn:
        types = {r[0] for r in conn.execute(
            "SELECT DISTINCT typeof(is_champion) FROM contacts").fetchall()}
        matched = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE is_champion = true").fetchone()[0]
    assert types == {"integer"}
    assert matched > 0


def test_foreign_key_integrity(db):
    with db.raw_reader() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_dates_are_iso(db):
    with db.raw_reader() as conn:
        bad = conn.execute(
            "SELECT COUNT(*) FROM deals "
            "WHERE close_date IS NOT NULL AND close_date != '' "
            "  AND strftime('%Y-%m-%d', close_date) IS NULL").fetchone()[0]
    assert bad == 0


def test_reporting_window_is_populated(db, settings):
    """Every 'current quarter' metric returned zero before the generator rewrite."""
    with db.raw_reader() as conn:
        q3 = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE close_date BETWEEN ? AND ?",
            ("2026-07-01", "2026-09-30")).fetchone()[0]
        won_ytd = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE stage = 'Stage 5 - Closed Won' "
            "AND close_date BETWEEN ? AND ?",
            ("2026-01-01", settings.reporting_date.isoformat())).fetchone()[0]
        renewals = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE deal_type = 'Renewal'").fetchone()[0]
        months = conn.execute(
            "SELECT COUNT(DISTINCT strftime('%Y-%m', created_date)) FROM deals").fetchone()[0]
    assert q3 >= 20
    assert won_ytd >= 25
    assert renewals >= 10
    assert months >= 12


def test_rep_has_meetings_today(db, settings):
    with db.raw_reader() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM meetings WHERE date(scheduled_start) = ? "
            "AND organizer_id = 'USR-3002'",
            (settings.reporting_date.isoformat(),)).fetchone()[0]
    assert count >= 4


def test_manager_has_five_selling_reports(db):
    with db.raw_reader() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE manager_id = 'USR-3003' "
            "AND quota_annual > 0").fetchone()[0]
    assert count == 5


def test_targets_exist_only_for_sellers(db):
    """A manager with their own target row would double-count against their team."""
    with db.raw_reader() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM targets t JOIN users u ON t.user_id = u.user_id "
            "WHERE u.role NOT IN ('AE', 'Senior AE')").fetchone()[0]
    assert rows == 0


def test_sqlite_version_supports_true_keyword():
    assert sqlite3.sqlite_version_info >= (3, 23)
