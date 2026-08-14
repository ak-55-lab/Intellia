"""Three-tier LLM cache: in-process -> disk JSON -> app_state table.

The key deliberately hashes only a whitelisted set of inputs (never the whole prompt), so
cosmetic prompt formatting changes do not invalidate a warm cache. Bumping a task's
``prompt_version`` does.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from intellia.utils.logging import get_logger

log = get_logger("cache")


def cache_key(provider: str, model: str, task: str, prompt_version: str,
              inputs: Dict[str, Any]) -> str:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
    raw = "|".join([provider, model, task, prompt_version, payload])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class LLMCache:
    def __init__(self, cache_dir: Path, db: Optional[Any] = None) -> None:
        self.dir = cache_dir
        self.db = db
        self._memory: Dict[str, Dict[str, Any]] = {}

    def _path(self, key: str) -> Path:
        return self.dir / "{}.json".format(key)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._memory:
            return self._memory[key]

        path = self._path(key)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                self._memory[key] = payload
                return payload
            except (ValueError, OSError):
                log.warning("Corrupt cache entry %s; ignoring.", key)

        if self.db is not None:
            try:
                with self.db.writer() as conn:
                    row = conn.execute(
                        "SELECT payload_json FROM llm_cache WHERE key = ?", (key,)).fetchone()
                if row:
                    payload = json.loads(row[0])
                    self._memory[key] = payload
                    return payload
            except Exception:  # pragma: no cover - cache must never break a render
                log.debug("app_state cache lookup failed for %s", key, exc_info=True)
        return None

    def put(self, key: str, payload: Dict[str, Any], task: str = "",
            model: str = "", prompt_version: str = "") -> None:
        self._memory[key] = payload
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._path(key).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            log.debug("Could not write disk cache for %s", key, exc_info=True)

        if self.db is not None:
            try:
                with self.db.writer() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO llm_cache "
                        "(key, task, model, prompt_version, payload_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (key, task, model, prompt_version, json.dumps(payload),
                         datetime.now().isoformat(timespec="seconds")),
                    )
            except Exception:  # pragma: no cover
                log.debug("app_state cache write failed for %s", key, exc_info=True)

    def clear(self) -> None:
        self._memory.clear()
        if self.dir.exists():
            for path in self.dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
