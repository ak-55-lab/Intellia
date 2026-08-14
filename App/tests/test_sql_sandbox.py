"""The SQL sandbox: the security boundary.

Every escape route gets its own case, and the legitimate-SQL cases matter just as
much: a sandbox that blocks `count(*)` is broken even though it is "safe".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from intellia.config.settings import KNOWLEDGE_DIR
from intellia.insights import sql_validator
from intellia.utils.errors import SqlSafetyError

DESTRUCTIVE = [
    "DROP TABLE deals",
    "DELETE FROM deals",
    "UPDATE deals SET amount = 0",
    "INSERT INTO deals VALUES (1)",
    "ALTER TABLE deals ADD COLUMN x TEXT",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "DETACH DATABASE main",
    "CREATE TABLE evil (a TEXT)",
    "PRAGMA table_info(deals)",
    "VACUUM",
    "REINDEX",
    "BEGIN; SELECT 1",
]


@pytest.mark.parametrize("statement", DESTRUCTIVE)
def test_validator_rejects_destructive(statement):
    with pytest.raises(SqlSafetyError):
        sql_validator.validate(statement)


@pytest.mark.parametrize("statement", [
    "SELECT 1 -- ; DROP TABLE deals",
    "SELECT 1 /* ; DROP TABLE deals */",
])
def test_comment_smuggled_sql_is_neutralised(statement):
    """Comments are stripped before the keyword scan, so the smuggled statement
    is removed rather than rejected -- what survives is a harmless SELECT."""
    cleaned = sql_validator.validate(statement)
    assert "drop" not in cleaned.lower()
    assert cleaned.lower().startswith("select")


@pytest.mark.parametrize("statement", [
    "SELECT 1; DROP TABLE deals",
    "SELECT 1; SELECT 2",
])
def test_validator_rejects_multi_statement(statement):
    with pytest.raises(SqlSafetyError):
        sql_validator.validate(statement)


def test_comment_stripping_preserves_string_literals():
    sql = "SELECT stage FROM deals WHERE stage = 'a -- b'"
    assert "-- b" in sql_validator.strip_comments(sql)


@pytest.mark.parametrize("statement", [
    "SELECT * FROM main.deals",
    "SELECT name FROM sqlite_master",
    "SELECT * FROM temp.deals",
])
def test_validator_rejects_schema_qualifiers(statement):
    with pytest.raises(SqlSafetyError):
        sql_validator.validate(statement)


@pytest.mark.parametrize("statement", [
    "SELECT COUNT(*) FROM deals",
    "SELECT stage, SUM(amount) AS total FROM deals GROUP BY stage",
    "WITH m AS (SELECT strftime('%Y-%m', created_date) k FROM deals) SELECT COUNT(*) FROM m",
    "SELECT ROUND(100.0 * COUNT(*) / NULLIF(COUNT(*), 0), 1) AS pct FROM deals",
])
def test_validator_allows_legitimate_sql(statement):
    assert sql_validator.validate(statement)


# -- authorizer-level (the real boundary) ----------------------------------------------

def _blocked(executor, scope, sql):
    try:
        executor.run(sql, scope)
        return False
    except SqlSafetyError:
        return True


def test_authorizer_blocks_main_qualified_read(db, scope_rep, executor):
    """The lexical layer catches this too, so go straight at the authorizer."""
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT SUM(amount) FROM main.deals").fetchall()


def test_authorizer_blocks_sqlite_master(db, scope_rep):
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT name FROM sqlite_master").fetchall()


def test_authorizer_blocks_unlisted_function(db, scope_rep):
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT randomblob(4) FROM deals LIMIT 1").fetchall()


def test_authorizer_blocks_unlisted_table(db, scope_rep):
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT COUNT(*) FROM _meta").fetchall()


def test_readonly_connection_blocks_writes(db, scope_rep):
    with pytest.raises(Exception):
        with db.reader(scope_rep) as conn:
            conn.execute("INSERT INTO deals (deal_id) VALUES ('x')")


def test_multi_statement_rejected_by_sqlite(db, scope_rep):
    with pytest.raises(Exception):
        with db.reader(scope_rep, sandbox=True) as conn:
            conn.execute("SELECT 1; SELECT 2")


def test_row_limit_truncates_and_flags(db, scope_rep, executor):
    result = executor.run("SELECT deal_id FROM deals", scope_rep, limit=3)
    assert result.row_count == 3
    assert result.truncated is True


def test_describe_reports_columns(executor, scope_rep):
    columns = executor.describe(
        "SELECT stage AS s, SUM(amount) AS total FROM deals GROUP BY stage", scope_rep)
    assert columns == ["s", "total"]


# -- the semantic layer's own examples --------------------------------------------------

def _few_shot_queries():
    text = (KNOWLEDGE_DIR / "text_to_sql_few_shots.md").read_text(encoding="utf-8")
    return [b.strip() for b in re.findall(r"```sql\n(.*?)```", text, re.DOTALL)]


def test_few_shot_queries_all_execute(db, scope_manager, executor):
    """Pins the semantic layer, the schema and the seed data together.

    Every documented example must pass validation and return rows against the
    rebuilt database. That single assertion catches doc drift, schema drift and
    empty-window seed bugs at once.
    """
    queries = _few_shot_queries()
    assert len(queries) >= 18, "expected the documented example set"

    failures, empty = [], []
    for sql in queries:
        try:
            result = executor.run(sql.rstrip().rstrip(";"), scope_manager)
            if result.row_count == 0:
                empty.append(sql.splitlines()[0][:70])
        except Exception as exc:
            failures.append((sql.splitlines()[0][:70], str(exc)[:80]))

    assert not failures, "queries failed to execute: {}".format(failures)
    assert not empty, "queries returned no rows: {}".format(empty)
