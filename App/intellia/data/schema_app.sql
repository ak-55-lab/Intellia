-- Intellia app-state schema (writable).
--
-- Kept in a separate file from the analytics DB so the analytics connection can be
-- opened strictly read-only.

CREATE TABLE IF NOT EXISTS insights (
    id                 TEXT PRIMARY KEY,
    head_version       INTEGER NOT NULL DEFAULT 1,
    category           TEXT NOT NULL DEFAULT 'insights',
    source             TEXT NOT NULL DEFAULT 'builtin',
    created_by_persona TEXT,
    created_at         TEXT,
    updated_at         TEXT
);

CREATE TABLE IF NOT EXISTS insight_versions (
    version_id        TEXT PRIMARY KEY,
    insight_id        TEXT NOT NULL,
    version           INTEGER NOT NULL,
    config_json       TEXT NOT NULL,
    change_note       TEXT,
    created_at        TEXT,
    parent_version_id TEXT,
    UNIQUE (insight_id, version)
);

-- span 0 means "use the widget's own default width"; 1 is half, 2 is full.
CREATE TABLE IF NOT EXISTS layouts (
    persona_id TEXT NOT NULL,
    widget_key TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    visible    INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0, 1)),
    span       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (persona_id, widget_key)
);

-- User-authored canvas blocks: a section title or a text note. They are widgets
-- like any other (they appear in the composer and obey the layout table), so
-- ordering, width and removal need no special cases anywhere else.
CREATE TABLE IF NOT EXISTS canvas_blocks (
    id         TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('heading', 'note')),
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS action_state (
    action_key   TEXT NOT NULL,
    persona_id   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',
    completed_at TEXT,
    note         TEXT,
    PRIMARY KEY (action_key, persona_id)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key            TEXT PRIMARY KEY,
    task           TEXT,
    model          TEXT,
    prompt_version TEXT,
    payload_json   TEXT NOT NULL,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
