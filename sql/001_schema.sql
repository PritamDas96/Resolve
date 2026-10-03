-- RESOLVE base schema (PLAN §7.6). Phase 1: tables + queue seed data.
--
-- Row-level security, the resolve_app role, audit tables and seeded users are
-- added in Phase 6 (sql/002_rls.sql, sql/003_audit.sql); this file is only the
-- base relational schema and is safe to re-apply (IF NOT EXISTS throughout).
--
-- Divergence from the plan (ADR-014): complaints.narrative_raw / narrative_masked
-- are NULLABLE here. CFPB no longer distributes narrative text, so narratives are
-- synthesised in a later task and backfilled; the complaint metadata loads first.

CREATE TABLE IF NOT EXISTS queues (
    queue_id    TEXT PRIMARY KEY,   -- 'deposits', 'cards', 'mortgage', 'credit_reporting'
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_users (
    user_id TEXT PRIMARY KEY,
    role    TEXT NOT NULL CHECK (role IN ('analyst', 'reviewer', 'auditor', 'admin'))
);

CREATE TABLE IF NOT EXISTS user_queues (
    user_id  TEXT REFERENCES app_users (user_id),
    queue_id TEXT REFERENCES queues (queue_id),
    PRIMARY KEY (user_id, queue_id)
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    queue_id     TEXT NOT NULL REFERENCES queues (queue_id),
    bank         TEXT NOT NULL,
    product_type TEXT NOT NULL,   -- checking, savings, credit_card, mortgage
    opened_on    DATE NOT NULL,
    holder_name  TEXT NOT NULL,   -- synthetic PII
    holder_email TEXT NOT NULL,   -- synthetic PII
    status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id     BIGINT PRIMARY KEY,
    bank             TEXT NOT NULL,
    date_received    DATE NOT NULL,
    product          TEXT NOT NULL,
    sub_product      TEXT,
    issue            TEXT NOT NULL,
    sub_issue        TEXT,
    narrative_raw    TEXT,             -- nullable until narratives are synthesised (ADR-014)
    narrative_masked TEXT,             -- after Presidio (Phase 8)
    queue_id         TEXT NOT NULL REFERENCES queues (queue_id),
    account_id       TEXT REFERENCES accounts (account_id),
    split            TEXT NOT NULL CHECK (split IN ('train', 'val', 'test'))
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id         TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES accounts (account_id),
    posted_on      DATE NOT NULL,
    amount_cents   BIGINT NOT NULL,
    channel        TEXT NOT NULL,   -- debit_card, ach, atm, pos, wire, foreign
    merchant       TEXT,
    statement_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS disputes (
    dispute_id            TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts (account_id),
    txn_id                TEXT REFERENCES transactions (txn_id),
    notice_received_on    DATE NOT NULL,
    notice_channel        TEXT NOT NULL,   -- oral, written
    provisional_credit_on DATE,
    resolved_on           DATE,
    outcome               TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id        UUID PRIMARY KEY,
    complaint_id    BIGINT NOT NULL REFERENCES complaints (complaint_id),
    version         INT NOT NULL,
    body            JSONB NOT NULL,   -- structured letter with citations
    status          TEXT NOT NULL CHECK (status IN ('pending_review', 'approved', 'rejected')),
    created_by      TEXT NOT NULL,
    approved_by     TEXT,
    idempotency_key TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_complaints_queue ON complaints (queue_id);
CREATE INDEX IF NOT EXISTS idx_complaints_account ON complaints (account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (account_id);
CREATE INDEX IF NOT EXISTS idx_disputes_account ON disputes (account_id);

-- The four in-scope queues == the canonical product families (ADR-016).
INSERT INTO queues (queue_id, description) VALUES
    ('deposits', 'Deposit accounts (Reg E / Reg DD)'),
    ('cards', 'Credit and prepaid cards (Reg Z)'),
    ('mortgage', 'Mortgage (Reg X)'),
    ('credit_reporting', 'Credit reporting as furnisher (Reg V)')
ON CONFLICT (queue_id) DO NOTHING;
