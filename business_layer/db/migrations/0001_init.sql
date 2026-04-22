-- business_layer canonical schema (v1).
--
-- This file is the READABLE source of truth. The applied DDL lives in
-- migrations/0001_init.sql (identical content; duplicated so existing
-- databases can re-run the migration history). Future changes go
-- through NEW migration files, never in-place edits here.
--
-- Conventions:
--   * id TEXT PRIMARY KEY          -- UUIDv7 (time-sortable) generated app-side
--   * created_at INTEGER NOT NULL  -- Unix ms, populated by repos
--   * updated_at INTEGER           -- Unix ms, nullable, stamped on write
--   * Enums expressed via CHECK constraints (portable SQLite + Postgres)
--   * Money stored as INTEGER paise — never floats
--   * No silent triggers; writes are explicit in repository code
--
-- Engine-specific pragmas (foreign_keys=ON, journal_mode=WAL) are set
-- in business_layer/db/engine.py at connect time, not here.


-- ======================================================================
-- IDENTITY + TENANCY
-- ======================================================================

CREATE TABLE IF NOT EXISTS users (
    id                   TEXT PRIMARY KEY,
    role                 TEXT NOT NULL CHECK (role IN ('business','ca','admin')),
    email                TEXT UNIQUE,                 -- CAs sign up with email; business owners don't need it
    phone                TEXT UNIQUE,                 -- business signup channel; CAs optional
    password_hash        TEXT,                        -- argon2id encoded string; NULL when phone-OTP-only
    display_name         TEXT NOT NULL,
    created_at           INTEGER NOT NULL,
    last_login_at        INTEGER,
    locked_until         INTEGER,                     -- brute-force lockout expiry (unix ms)
    failed_login_count   INTEGER NOT NULL DEFAULT 0,
    CHECK ((email IS NOT NULL) OR (phone IS NOT NULL))
);


CREATE TABLE IF NOT EXISTS workspaces (
    id                       TEXT PRIMARY KEY,
    owner_user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                     TEXT NOT NULL,
    gstin                    TEXT,                    -- the workspace's OWN GSTIN
    created_via              TEXT NOT NULL CHECK (created_via IN ('self_signup','invite','admin')),
    tier                     TEXT NOT NULL DEFAULT 'free',
    status                   TEXT NOT NULL DEFAULT 'active',
    region                   TEXT,
    default_extraction_mode  TEXT NOT NULL DEFAULT 'instant'
                             CHECK (default_extraction_mode IN ('instant','scheduled','manual')),
    created_at               INTEGER NOT NULL,
    UNIQUE (owner_user_id)                             -- v1: 1 user = 1 workspace
);


-- ======================================================================
-- INGESTION (pre-extraction)
-- ======================================================================

CREATE TABLE IF NOT EXISTS sources (
    id                         TEXT PRIMARY KEY,
    workspace_id               TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind                       TEXT NOT NULL CHECK (kind IN ('gmail','outlook','whatsapp','upload','folder')),
    label                      TEXT,                   -- user-facing name
    status                     TEXT NOT NULL CHECK (status IN ('stub','connected','error','disconnected')),
    default_extraction_mode    TEXT NOT NULL CHECK (default_extraction_mode IN ('instant','scheduled','manual')),
    credentials_encrypted      BLOB,                   -- AES-GCM ciphertext; NULL for 'upload'/'stub'
    last_polled_at             INTEGER,
    created_at                 INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sources_workspace ON sources(workspace_id);


CREATE TABLE IF NOT EXISTS inbox_messages (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_id         TEXT REFERENCES sources(id) ON DELETE SET NULL,
    external_id       TEXT,                            -- provider's id (gmail msg id, whatsapp msg id)
    sender            TEXT,                            -- email address or contact name
    subject           TEXT,
    received_at       INTEGER NOT NULL,
    content_type      TEXT NOT NULL,                   -- application/pdf, image/png, ...
    file_storage_key  TEXT NOT NULL,                   -- relative path under data/blobs/
    file_size_bytes   INTEGER NOT NULL,
    file_sha256       TEXT NOT NULL,                   -- for integrity + intra-workspace dedup
    status            TEXT NOT NULL CHECK (status IN ('queued','extracting','extracted','failed','ignored')),
    ignored_reason    TEXT,
    created_at        INTEGER NOT NULL,
    UNIQUE (workspace_id, file_sha256)
);
CREATE INDEX IF NOT EXISTS ix_inbox_workspace_received ON inbox_messages(workspace_id, received_at DESC);
CREATE INDEX IF NOT EXISTS ix_inbox_status            ON inbox_messages(workspace_id, status);


-- ======================================================================
-- EXTRACTION OUTPUTS
-- ======================================================================

CREATE TABLE IF NOT EXISTS invoices (
    id                       TEXT PRIMARY KEY,
    workspace_id             TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    inbox_message_id         TEXT NOT NULL REFERENCES inbox_messages(id) ON DELETE RESTRICT,
    vendor_name              TEXT,
    client_name              TEXT,                     -- billed-to entity display name
    client_gstin             TEXT,                     -- drives CA derived-client grouping
    seller_gstin             TEXT,
    invoice_no               TEXT,
    invoice_date             TEXT,                     -- ISO-8601; TEXT for portability
    total_amount_minor       INTEGER,                  -- paise
    currency                 TEXT NOT NULL DEFAULT 'INR',
    status                   TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending','under_review','approved','rejected','flagged')),
    created_at               INTEGER NOT NULL,
    approved_at              INTEGER,
    approved_by_user_id      TEXT REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_invoices_workspace_created   ON invoices(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_invoices_workspace_status    ON invoices(workspace_id, status);
CREATE INDEX IF NOT EXISTS ix_invoices_workspace_clientgst ON invoices(workspace_id, client_gstin);
CREATE INDEX IF NOT EXISTS ix_invoices_workspace_date      ON invoices(workspace_id, invoice_date);


CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                       TEXT PRIMARY KEY,
    workspace_id             TEXT NOT NULL,
    invoice_id               TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    pipeline_version         TEXT NOT NULL,          -- e.g. 'ocr@rapidocr,extract@heuristic,tables@spatial'
    ocr_result_json          TEXT NOT NULL,          -- OCRResult.model_dump_json()
    extraction_result_json   TEXT NOT NULL,
    tables_result_json       TEXT NOT NULL,
    validation_result_json   TEXT,
    ocr_ms                   REAL,
    extract_ms               REAL,
    tables_ms                REAL,
    validate_ms              REAL,
    total_ms                 REAL,
    created_at               INTEGER NOT NULL,
    UNIQUE (invoice_id, pipeline_version)            -- re-run produces new row
);


CREATE TABLE IF NOT EXISTS validation_findings (
    id             TEXT PRIMARY KEY,
    workspace_id   TEXT NOT NULL,
    invoice_id     TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    rule_name      TEXT NOT NULL,
    target         TEXT,
    outcome        TEXT NOT NULL CHECK (outcome IN ('PASS','FAIL','NOT_APPLICABLE')),
    reason         TEXT,
    expected       TEXT,
    observed       TEXT,
    created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vf_workspace_outcome ON validation_findings(workspace_id, outcome);
CREATE INDEX IF NOT EXISTS ix_vf_invoice           ON validation_findings(invoice_id);


-- ======================================================================
-- JOB QUEUE
-- ======================================================================

CREATE TABLE IF NOT EXISTS jobs (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL,
    inbox_message_id   TEXT NOT NULL REFERENCES inbox_messages(id) ON DELETE CASCADE,
    invoice_id         TEXT REFERENCES invoices(id) ON DELETE CASCADE,
    stage              TEXT NOT NULL CHECK (stage IN ('ocr','extract','tables','validate','full')),
    state              TEXT NOT NULL CHECK (state IN ('queued','running','done','failed','cancelled')),
    attempts           INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 3,
    next_run_at        INTEGER NOT NULL,              -- for exponential backoff
    started_at         INTEGER,
    finished_at        INTEGER,
    error_message      TEXT,
    created_at         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_jobs_queue ON jobs(state, next_run_at);


-- ======================================================================
-- AUDIT + SESSIONS + OTP + CA NAME OVERRIDES
-- ======================================================================

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT,                              -- NULL for platform-level (signup, admin)
    actor_user_id   TEXT REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,                     -- 'signup','invoice.created',...
    target_type     TEXT,
    target_id       TEXT,
    metadata_json   TEXT,                              -- NO PII — convention + review
    ts              INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_workspace_ts ON events(workspace_id, ts DESC);
CREATE INDEX IF NOT EXISTS ix_events_action_ts    ON events(action, ts DESC);


CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,                 -- SHA-256 of opaque token
    expires_at   INTEGER NOT NULL,
    user_agent   TEXT,
    ip_address   TEXT,
    revoked_at   INTEGER,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id, expires_at);


CREATE TABLE IF NOT EXISTS otp_challenges (
    id             TEXT PRIMARY KEY,
    phone          TEXT NOT NULL,
    code_hash      TEXT NOT NULL,                      -- SHA-256 of 6-digit code
    purpose        TEXT NOT NULL CHECK (purpose IN ('signup','login')),
    expires_at     INTEGER NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    max_attempts   INTEGER NOT NULL DEFAULT 5,
    used_at        INTEGER,
    created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_otp_phone ON otp_challenges(phone, created_at DESC);


CREATE TABLE IF NOT EXISTS client_label_overrides (
    workspace_id   TEXT NOT NULL,
    client_gstin   TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    updated_at     INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, client_gstin)
);
