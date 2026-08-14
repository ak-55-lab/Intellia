"""CSV -> SQLite build.

Typed, transactional and atomic. Column types come from an explicit coercion table, never
from pandas inference.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from intellia.config.settings import SEED_TABLES
from intellia.utils.logging import get_logger

log = get_logger("loader")

INT_COLUMNS = {
    "employee_count", "health_score", "influence", "is_champion", "is_active",
    "probability", "is_reply", "has_attachment", "duration_minutes", "score",
}
FLOAT_COLUMNS = {"arr", "amount", "quota_annual", "sentiment_score", "target_amount"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _to_int(value: str) -> int:
    text = (value or "").strip()
    if text in ("", "nan", "None"):
        return 0
    if text in ("True", "true"):
        return 1
    if text in ("False", "false"):
        return 0
    return int(float(text))


def _to_float(value: str) -> float:
    text = (value or "").strip()
    return 0.0 if text in ("", "nan", "None") else float(text)


def _to_text(value: str) -> str:
    text = "" if value is None else str(value)
    return "" if text in ("nan", "None") else text


def coercer_for(column: str) -> Callable[[str], Any]:
    if column in INT_COLUMNS:
        return _to_int
    if column in FLOAT_COLUMNS:
        return _to_float
    return _to_text


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def source_hashes(data_dir: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for table in SEED_TABLES:
        path = data_dir / "{}.csv".format(table)
        if path.exists():
            out[table] = file_hash(path)
    return out


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info({})".format(table)).fetchall()]


def _validate_dates(conn: sqlite3.Connection) -> List[str]:
    """Cheap sanity pass: date-ish columns must be ISO or empty."""
    problems: List[str] = []
    checks = [("deals", "close_date"), ("deals", "created_date"), ("tasks", "due_date"),
              ("meetings", "scheduled_start"), ("emails", "sent_at")]
    for table, column in checks:
        rows = conn.execute(
            "SELECT {c} FROM {t} WHERE {c} IS NOT NULL AND {c} != '' LIMIT 400".format(
                t=table, c=column)
        ).fetchall()
        for (value,) in rows:
            if not (_DATE_RE.match(value) or _TS_RE.match(value)):
                problems.append("{}.{} has non-ISO value {!r}".format(table, column, value))
                break
    return problems


def load_csvs(conn: sqlite3.Connection, data_dir: Path, schema_sql: str) -> Dict[str, int]:
    """Create the schema and bulk-load every seed CSV inside one transaction."""
    conn.executescript(schema_sql)
    counts: Dict[str, int] = {}

    for table in SEED_TABLES:
        path = data_dir / "{}.csv".format(table)
        if not path.exists():
            raise FileNotFoundError(
                "Seed file missing: {}. Run: python3 Data/generate_dummy_data.py".format(path))

        db_columns = _table_columns(conn, table)
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            csv_columns = [c for c in (reader.fieldnames or []) if c in db_columns]
            missing = [c for c in db_columns if c not in (reader.fieldnames or [])]
            if missing:
                log.warning("%s: CSV is missing columns %s (defaulted)", table, missing)

            coercers = {c: coercer_for(c) for c in csv_columns}
            sql = "INSERT INTO {t} ({cols}) VALUES ({ph})".format(
                t=table,
                cols=", ".join(csv_columns),
                ph=", ".join("?" for _ in csv_columns),
            )
            rows = [tuple(coercers[c](row.get(c, "")) for c in csv_columns) for row in reader]

        conn.executemany(sql, rows)
        counts[table] = len(rows)

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ValueError("Foreign key violations after load: {}".format(violations[:5]))

    problems = _validate_dates(conn)
    if problems:
        raise ValueError("Date normalization failed: {}".format("; ".join(problems)))

    return counts


def build_database(target: Path, data_dir: Path, schema_sql: str,
                   meta: Optional[Dict[str, str]] = None) -> Dict[str, int]:
    """Build into a temp file, verify, then atomically replace the target."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(tmp))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            counts = load_csvs(conn, data_dir, schema_sql)
            for key, value in (meta or {}).items():
                conn.execute("INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
                             (key, value))
        conn.execute("PRAGMA optimize")
    except Exception:
        conn.close()
        if tmp.exists():
            tmp.unlink()
        raise
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass

    os.replace(str(tmp), str(target))
    log.info("Built %s (%s rows)", target.name, sum(counts.values()))
    return counts
