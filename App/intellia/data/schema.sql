-- Intellia analytics schema.
--
-- Explicit DDL on purpose: DataFrame.to_sql type inference is what silently produced
-- is_champion as TEXT 'True' in the original seed.

PRAGMA foreign_keys = ON;

CREATE TABLE users (
    user_id       TEXT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL,
    role          TEXT NOT NULL,
    department    TEXT NOT NULL,
    manager_id    TEXT,
    region        TEXT,
    quota_annual  REAL NOT NULL DEFAULT 0,
    hire_date     TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE accounts (
    account_id     TEXT PRIMARY KEY,
    account_name   TEXT NOT NULL,
    domain         TEXT,
    industry       TEXT,
    region         TEXT,
    segment        TEXT,
    tier           TEXT,
    status         TEXT,
    arr            REAL NOT NULL DEFAULT 0,
    employee_count INTEGER NOT NULL DEFAULT 0,
    owner_id       TEXT REFERENCES users (user_id),
    renewal_date   TEXT,
    health_score   INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT
);

CREATE TABLE contacts (
    contact_id        TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL REFERENCES accounts (account_id),
    first_name        TEXT,
    last_name         TEXT,
    email             TEXT,
    title             TEXT,
    persona_role      TEXT,
    seniority         TEXT,
    influence         INTEGER NOT NULL DEFAULT 0,
    is_champion       INTEGER NOT NULL DEFAULT 0 CHECK (is_champion IN (0, 1)),
    last_contacted_at TEXT,
    created_at        TEXT
);

CREATE TABLE deals (
    deal_id            TEXT PRIMARY KEY,
    account_id         TEXT NOT NULL REFERENCES accounts (account_id),
    owner_id           TEXT NOT NULL REFERENCES users (user_id),
    deal_name          TEXT,
    deal_type          TEXT,
    stage              TEXT,
    amount             REAL NOT NULL DEFAULT 0,
    probability        INTEGER NOT NULL DEFAULT 0 CHECK (probability BETWEEN 0 AND 100),
    forecast_category  TEXT,
    close_date         TEXT,
    created_date       TEXT,
    stage_entered_at   TEXT,
    last_activity_date TEXT,
    next_step          TEXT,
    next_step_due_date TEXT,
    competitor         TEXT,
    source             TEXT,
    win_loss_reason    TEXT
);

CREATE TABLE emails (
    email_id        TEXT PRIMARY KEY,
    thread_id       TEXT,
    account_id      TEXT NOT NULL REFERENCES accounts (account_id),
    contact_id      TEXT,
    deal_id         TEXT,
    sender_email    TEXT,
    recipient_email TEXT,
    direction       TEXT,
    subject         TEXT,
    snippet         TEXT,
    body            TEXT,
    is_reply        INTEGER NOT NULL DEFAULT 0 CHECK (is_reply IN (0, 1)),
    has_attachment  INTEGER NOT NULL DEFAULT 0 CHECK (has_attachment IN (0, 1)),
    sent_at         TEXT,
    sentiment_score REAL NOT NULL DEFAULT 0
);

CREATE TABLE meetings (
    meeting_id           TEXT PRIMARY KEY,
    account_id           TEXT,
    deal_id              TEXT,
    organizer_id         TEXT NOT NULL REFERENCES users (user_id),
    title                TEXT,
    meeting_type         TEXT,
    scheduled_start      TEXT,
    scheduled_end        TEXT,
    duration_minutes     INTEGER NOT NULL DEFAULT 0,
    location             TEXT,
    status               TEXT,
    agenda               TEXT,
    summary              TEXT,
    key_points           TEXT,
    next_steps           TEXT,
    outcome              TEXT,
    attendee_contact_ids TEXT,
    attendee_user_ids    TEXT
);

CREATE TABLE signals (
    signal_id          TEXT PRIMARY KEY,
    account_id         TEXT NOT NULL REFERENCES accounts (account_id),
    contact_id         TEXT,
    owner_id           TEXT,
    signal_type        TEXT,
    playbook           TEXT,
    signal_title       TEXT,
    severity           TEXT,
    score              INTEGER NOT NULL DEFAULT 0,
    status             TEXT,
    detected_at        TEXT,
    expires_at         TEXT,
    action_recommended TEXT,
    source_url         TEXT
);

CREATE TABLE tasks (
    task_id      TEXT PRIMARY KEY,
    account_id   TEXT,
    deal_id      TEXT,
    owner_id     TEXT NOT NULL REFERENCES users (user_id),
    title        TEXT,
    description  TEXT,
    due_date     TEXT,
    priority     TEXT,
    status       TEXT,
    source       TEXT,
    created_at   TEXT,
    completed_at TEXT
);

CREATE TABLE targets (
    target_id     TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users (user_id),
    period_type   TEXT,
    period_start  TEXT,
    period_end    TEXT,
    metric        TEXT,
    target_amount REAL NOT NULL DEFAULT 0
);

CREATE TABLE _meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX idx_accounts_owner    ON accounts (owner_id);
CREATE INDEX idx_contacts_account  ON contacts (account_id);
CREATE INDEX idx_deals_account     ON deals (account_id);
CREATE INDEX idx_deals_owner       ON deals (owner_id);
CREATE INDEX idx_deals_close       ON deals (close_date);
CREATE INDEX idx_deals_created     ON deals (created_date);
CREATE INDEX idx_deals_stage       ON deals (stage);
CREATE INDEX idx_emails_account    ON emails (account_id);
CREATE INDEX idx_emails_thread     ON emails (thread_id);
CREATE INDEX idx_emails_sent       ON emails (sent_at);
CREATE INDEX idx_meetings_org      ON meetings (organizer_id);
CREATE INDEX idx_meetings_start    ON meetings (scheduled_start);
CREATE INDEX idx_signals_account   ON signals (account_id);
CREATE INDEX idx_signals_detected  ON signals (detected_at);
CREATE INDEX idx_tasks_owner       ON tasks (owner_id);
CREATE INDEX idx_tasks_due         ON tasks (due_date);
CREATE INDEX idx_targets_user      ON targets (user_id);
