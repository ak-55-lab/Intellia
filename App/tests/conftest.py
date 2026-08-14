"""Shared fixtures.

Tests must pass with no ANTHROPIC_API_KEY and with ``anthropic`` absent, so no
fixture here constructs a live provider.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from intellia.config.personas import get_persona  # noqa: E402
from intellia.config.settings import load_settings  # noqa: E402
from intellia.data.database import Database  # noqa: E402
from intellia.data.scope import resolve_scope  # noqa: E402
from intellia.insights.executor import SqlExecutor  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolate_app_state(tmp_path_factory):
    """Send every writable app-state read and write to a throwaway database.

    The UI tests drive the real app, and one of them adds a heading block and
    renames it. Pointed at the shipped Data/app_state.db that block is permanent,
    so a canvas collected one more "Pipeline health" section per test run. Layout
    visibility and insight edits persist the same way.

    Autouse and session scoped because app.py calls load_settings() itself; the
    env var is the only lever that reaches it.
    """
    path = tmp_path_factory.mktemp("app-state") / "app_state.db"
    os.environ["INTELLIA_APP_STATE_DB"] = str(path)
    yield path
    os.environ.pop("INTELLIA_APP_STATE_DB", None)


@pytest.fixture(scope="session")
def settings():
    """Force deterministic mode.

    Clearing the env var is not enough -- ``load_settings`` also reads the repo's
    ``.env``, so the key is blanked on the loaded settings object itself. The whole
    suite must pass with no model available.
    """
    import dataclasses

    os.environ.pop("ANTHROPIC_API_KEY", None)
    return dataclasses.replace(load_settings(), api_key=None)


@pytest.fixture(scope="session")
def db(settings):
    database = Database(settings)
    database.ensure_built()
    return database


@pytest.fixture(scope="session")
def scope_rep(db):
    with db.raw_reader() as conn:
        return resolve_scope(conn, get_persona("rep"))


@pytest.fixture(scope="session")
def scope_manager(db):
    with db.raw_reader() as conn:
        return resolve_scope(conn, get_persona("manager"))


@pytest.fixture(scope="session")
def executor(db, settings):
    return SqlExecutor(db, settings.max_rows, settings.query_timeout_seconds)


@pytest.fixture(scope="session")
def app_context(settings):
    from intellia.bootstrap import build_context
    return build_context(settings)
