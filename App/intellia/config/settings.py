"""Application settings.

Everything time-related flows from ``REPORTING_DATE``. Nothing in the app may call
``date.today()`` -- see ``intellia.utils.dates``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional

# App/intellia/config/settings.py -> App/intellia/config -> App/intellia -> App -> repo root
APP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_DIR.parent
DATA_DIR = REPO_ROOT / "Data"
KNOWLEDGE_DIR = REPO_ROOT / "Knowledge"
CACHE_DIR = APP_DIR / ".cache"

SCHEMA_VERSION = "3"

# The demo is pinned to this date so it looks identical whenever it is run, and so it
# agrees with Knowledge/semantic_layer.md.
REPORTING_DATE = date(2026, 8, 13)

# Two tiers. The flagship writes the brief and the meeting prep; the fast tier
# answers questions and writes SQL, where latency is felt and depth is not.
DEFAULT_MODEL = "claude-opus-5"
FAST_MODEL = "claude-sonnet-5"

SEED_TABLES = (
    "users", "accounts", "contacts", "deals", "emails", "meetings",
    "signals", "tasks", "targets",
)

# Tables an LLM-generated query is allowed to touch.
QUERYABLE_TABLES = SEED_TABLES

def _read_env_file(path: Path) -> Dict[str, str]:
    """Minimal .env reader -- avoids a python-dotenv dependency."""
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class AppSettings:
    reporting_date: date = REPORTING_DATE
    analytics_db: Path = DATA_DIR / "intellia.db"
    app_state_db: Path = DATA_DIR / "app_state.db"
    data_dir: Path = DATA_DIR
    knowledge_dir: Path = KNOWLEDGE_DIR
    cache_dir: Path = CACHE_DIR
    model: str = DEFAULT_MODEL
    fast_model: str = FAST_MODEL
    api_key: Optional[str] = None
    debug: bool = False
    max_rows: int = 5000
    query_timeout_seconds: float = 5.0
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def llm_available(self) -> bool:
        return bool(self.api_key)


def load_settings() -> AppSettings:
    env = dict(_read_env_file(REPO_ROOT / ".env"))
    env.update({k: v for k, v in os.environ.items() if k.startswith(("ANTHROPIC_", "INTELLIA_"))})

    api_key = (env.get("ANTHROPIC_API_KEY") or "").strip() or None

    # The writable store is redirectable so a test run does not edit the canvas the
    # user is actually looking at. Without it the UI tests add a heading block to
    # the real app_state.db on every run and never take it back, so the canvas
    # collects one more section title each time the suite is run.
    state_override = (env.get("INTELLIA_APP_STATE_DB") or "").strip()
    app_state_db = Path(state_override) if state_override else DATA_DIR / "app_state.db"

    return AppSettings(
        app_state_db=app_state_db,
        model=env.get("INTELLIA_MODEL", DEFAULT_MODEL),
        fast_model=env.get("INTELLIA_FAST_MODEL", FAST_MODEL),
        api_key=api_key,
        debug=env.get("INTELLIA_DEBUG", "0") not in ("0", "", "false", "False"),
        env=env,
    )
