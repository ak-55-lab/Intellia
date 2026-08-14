"""Insight persistence -- append-only versioning.

Nothing is mutated in place. Every edit inserts a new ``insight_versions`` row and
re-points ``insights.head_version``, so a failed edit can never damage a working
card and history stays auditable.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from intellia.data.database import Database
from intellia.models.insight import InsightConfig
from intellia.utils.logging import get_logger

log = get_logger("insight_store")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _shipped_fingerprint(config: InsightConfig) -> str:
    """What a builtin definition *is*, ignoring the timestamps a save stamps on."""
    return json.dumps([
        config.title, config.subtitle, config.description, config.generated_sql,
        config.category, config.span, sorted(config.personas),
        asdict_viz(config), config.refresh.cadence_label,
        config.metadata.calculation, config.metadata.data_source,
    ], sort_keys=True)


def asdict_viz(config: InsightConfig) -> Dict[str, object]:
    viz = config.viz
    return {"type": viz.type, "x": viz.x, "y": viz.y, "unit": viz.unit, "sort": viz.sort}


class InsightStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- reads -------------------------------------------------------------------------

    def get(self, insight_id: str) -> Optional[InsightConfig]:
        with self.db.writer() as conn:
            row = conn.execute(
                """
                SELECT v.config_json
                FROM insights i
                JOIN insight_versions v
                  ON v.insight_id = i.id AND v.version = i.head_version
                WHERE i.id = ?
                """,
                (insight_id,),
            ).fetchone()
        return InsightConfig.from_json(row[0]) if row else None

    def list_all(self, persona_id: Optional[str] = None) -> List[InsightConfig]:
        with self.db.writer() as conn:
            rows = conn.execute(
                """
                SELECT v.config_json
                FROM insights i
                JOIN insight_versions v
                  ON v.insight_id = i.id AND v.version = i.head_version
                ORDER BY i.created_at
                """
            ).fetchall()
        configs = [InsightConfig.from_json(r[0]) for r in rows]
        if persona_id:
            configs = [c for c in configs if not c.personas or persona_id in c.personas]
        return configs

    def versions(self, insight_id: str) -> List[Tuple[int, str, str]]:
        """(version, change_note, created_at), newest first."""
        with self.db.writer() as conn:
            rows = conn.execute(
                "SELECT version, COALESCE(change_note, ''), COALESCE(created_at, '') "
                "FROM insight_versions WHERE insight_id = ? ORDER BY version DESC",
                (insight_id,),
            ).fetchall()
        return [(int(r[0]), r[1], r[2]) for r in rows]

    def get_version(self, insight_id: str, version: int) -> Optional[InsightConfig]:
        with self.db.writer() as conn:
            row = conn.execute(
                "SELECT config_json FROM insight_versions "
                "WHERE insight_id = ? AND version = ?",
                (insight_id, version),
            ).fetchone()
        return InsightConfig.from_json(row[0]) if row else None

    # -- writes ------------------------------------------------------------------------

    def save_new(self, config: InsightConfig) -> InsightConfig:
        config.version = 1
        config.metadata.created_at = config.metadata.created_at or _now()
        config.metadata.updated_at = _now()
        version_id = "iv-" + uuid.uuid4().hex[:12]

        with self.db.writer() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO insights "
                "(id, head_version, category, source, created_by_persona, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (config.id, 1, config.category, config.metadata.source,
                 config.metadata.created_by_persona, config.metadata.created_at,
                 config.metadata.updated_at),
            )
            conn.execute(
                "INSERT OR REPLACE INTO insight_versions "
                "(version_id, insight_id, version, config_json, change_note, created_at, "
                " parent_version_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, config.id, 1, config.to_json(), "Created",
                 config.metadata.created_at, None),
            )
        return config

    def save_version(self, config: InsightConfig, change_note: str) -> InsightConfig:
        """Append a new version and advance head. Never mutates the previous one."""
        with self.db.writer() as conn:
            row = conn.execute(
                "SELECT head_version FROM insights WHERE id = ?", (config.id,)).fetchone()
            if row is None:
                return self.save_new(config)
            head = int(row[0])
            parent = conn.execute(
                "SELECT version_id FROM insight_versions WHERE insight_id = ? AND version = ?",
                (config.id, head),
            ).fetchone()

            config.version = head + 1
            config.change_note = change_note
            config.parent_version_id = parent[0] if parent else None
            config.metadata.updated_at = _now()
            version_id = "iv-" + uuid.uuid4().hex[:12]

            conn.execute(
                "INSERT INTO insight_versions "
                "(version_id, insight_id, version, config_json, change_note, created_at, "
                " parent_version_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, config.id, config.version, config.to_json(), change_note,
                 config.metadata.updated_at, config.parent_version_id),
            )
            conn.execute(
                "UPDATE insights SET head_version = ?, updated_at = ? WHERE id = ?",
                (config.version, config.metadata.updated_at, config.id),
            )
        return config

    def restore(self, insight_id: str, version: int) -> Optional[InsightConfig]:
        old = self.get_version(insight_id, version)
        if old is None:
            return None
        return self.save_version(old, "Restored version {}".format(version))

    def delete(self, insight_id: str) -> None:
        with self.db.writer() as conn:
            conn.execute("DELETE FROM insight_versions WHERE insight_id = ?", (insight_id,))
            conn.execute("DELETE FROM insights WHERE id = ?", (insight_id,))

    def seed(self, configs: List[InsightConfig]) -> None:
        """Insert builtin configs, and refresh the ones nobody has edited.

        A builtin still sitting on version 1 is the shipped definition, so a code
        change to its title, copy or SQL should reach the canvas. The moment a
        user edits it, head_version moves past 1 and this leaves it alone: their
        version wins over ours.
        """
        with self.db.writer() as conn:
            existing = {r[0]: int(r[1]) for r in conn.execute(
                "SELECT id, head_version FROM insights").fetchall()}

        for config in configs:
            head = existing.get(config.id)
            if head is None:
                self.save_new(config)
                continue
            if head != 1:
                continue
            current = self.get(config.id)
            if current is None or _shipped_fingerprint(current) != _shipped_fingerprint(config):
                self.save_new(config)

    # -- layout ------------------------------------------------------------------------

    def layout(self, persona_id: str) -> Dict[str, bool]:
        with self.db.writer() as conn:
            rows = conn.execute(
                "SELECT widget_key, visible FROM layouts WHERE persona_id = ? "
                "ORDER BY sort_order", (persona_id,),
            ).fetchall()
        return {r[0]: bool(r[1]) for r in rows}

    def order(self, persona_id: str) -> Dict[str, int]:
        with self.db.writer() as conn:
            rows = conn.execute(
                "SELECT widget_key, sort_order FROM layouts WHERE persona_id = ?",
                (persona_id,)).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def spans(self, persona_id: str) -> Dict[str, int]:
        """Stored width per widget. 0 means the widget's own default."""
        with self.db.writer() as conn:
            rows = conn.execute(
                "SELECT widget_key, span FROM layouts WHERE persona_id = ?",
                (persona_id,)).fetchall()
        return {r[0]: int(r[1] or 0) for r in rows}

    def _upsert(self, conn, persona_id: str, widget_key: str,
                column: str, value: int) -> None:
        conn.execute(
            "INSERT INTO layouts (persona_id, widget_key, sort_order, visible, span) "
            "VALUES (?, ?, COALESCE((SELECT sort_order FROM layouts "
            "  WHERE persona_id = ? AND widget_key = ?), 999), 1, 0) "
            "ON CONFLICT(persona_id, widget_key) DO NOTHING",
            (persona_id, widget_key, persona_id, widget_key),
        )
        conn.execute(
            "UPDATE layouts SET {} = ? WHERE persona_id = ? AND widget_key = ?".format(column),
            (value, persona_id, widget_key),
        )

    def set_visibility(self, persona_id: str, widget_key: str, visible: bool) -> None:
        with self.db.writer() as conn:
            self._upsert(conn, persona_id, widget_key, "visible", 1 if visible else 0)

    def set_span(self, persona_id: str, widget_key: str, span: int) -> None:
        with self.db.writer() as conn:
            self._upsert(conn, persona_id, widget_key, "span", int(span))

    def move(self, persona_id: str, widget_key: str, keys_in_order: List[str],
             delta: int) -> None:
        """Swap a widget with its visible neighbour.

        Streamlit has no drag-and-drop, so reordering is a swap against the list
        the canvas is actually showing. Taking that list from the caller (rather
        than re-deriving it) is what keeps the arrows consistent with what the
        user sees, including when some widgets are hidden.
        """
        if widget_key not in keys_in_order:
            return
        index = keys_in_order.index(widget_key)
        target = index + delta
        if not 0 <= target < len(keys_in_order):
            return
        other = keys_in_order[target]

        with self.db.writer() as conn:
            current = {r[0]: int(r[1]) for r in conn.execute(
                "SELECT widget_key, sort_order FROM layouts WHERE persona_id = ? "
                "AND widget_key IN (?, ?)",
                (persona_id, widget_key, other)).fetchall()}
            # Normalise first: two widgets can share a sort_order (999 default),
            # in which case a naive swap is a no-op.
            for position, key in enumerate(keys_in_order):
                if current.get(key) is None or key in (widget_key, other):
                    self._upsert(conn, persona_id, key, "sort_order", position)
            self._upsert(conn, persona_id, widget_key, "sort_order", target)
            self._upsert(conn, persona_id, other, "sort_order", index)

    def seed_layout(self, persona_id: str, widget_keys: List[str]) -> None:
        with self.db.writer() as conn:
            for order, key in enumerate(widget_keys):
                conn.execute(
                    "INSERT OR IGNORE INTO layouts "
                    "(persona_id, widget_key, sort_order, visible, span) "
                    "VALUES (?, ?, ?, 1, 0)",
                    (persona_id, key, order),
                )

    def reset_layout(self, persona_id: str, defaults: List[str],
                     all_keys: List[str]) -> None:
        with self.db.writer() as conn:
            conn.execute("DELETE FROM layouts WHERE persona_id = ?", (persona_id,))
            for order, key in enumerate(defaults):
                conn.execute(
                    "INSERT INTO layouts (persona_id, widget_key, sort_order, visible, span) "
                    "VALUES (?, ?, ?, 1, 0)", (persona_id, key, order))
            start = len(defaults)
            for offset, key in enumerate(k for k in all_keys if k not in defaults):
                conn.execute(
                    "INSERT INTO layouts (persona_id, widget_key, sort_order, visible, span) "
                    "VALUES (?, ?, ?, 0, 0)", (persona_id, key, start + offset))

    # -- user-authored canvas blocks ---------------------------------------------------

    def blocks(self, persona_id: str) -> List[Dict[str, str]]:
        with self.db.writer() as conn:
            rows = conn.execute(
                "SELECT id, kind, title, body FROM canvas_blocks WHERE persona_id = ? "
                "ORDER BY created_at", (persona_id,)).fetchall()
        return [{"id": r[0], "kind": r[1], "title": r[2], "body": r[3]} for r in rows]

    def add_block(self, persona_id: str, kind: str) -> str:
        block_id = "block." + uuid.uuid4().hex[:10]
        defaults = {"heading": ("Section title", ""),
                    "note": ("Note", "Write anything here.")}
        title, body = defaults.get(kind, defaults["note"])
        with self.db.writer() as conn:
            conn.execute(
                "INSERT INTO canvas_blocks (id, persona_id, kind, title, body, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (block_id, persona_id, kind, title, body, _now()))
        return block_id

    def update_block(self, block_id: str, title: str, body: str) -> None:
        with self.db.writer() as conn:
            conn.execute("UPDATE canvas_blocks SET title = ?, body = ? WHERE id = ?",
                         (title, body, block_id))

    def delete_block(self, block_id: str) -> None:
        with self.db.writer() as conn:
            conn.execute("DELETE FROM canvas_blocks WHERE id = ?", (block_id,))
            conn.execute("DELETE FROM layouts WHERE widget_key = ?", (block_id,))
