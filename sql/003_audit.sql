-- RESOLVE tamper-evident audit log (PLAN §13.7). Phase 8.
--
-- Every privileged action is appended as a row whose `hash` chains the previous row's
-- hash with this row's canonical content. Altering or deleting any past row breaks the
-- chain from that point on, which verify_audit_chain detects. (A hash chain proves
-- integrity/ordering; it does not prevent an attacker who can also recompute and
-- rewrite every subsequent hash — note that honestly in the threat model.)

CREATE TABLE IF NOT EXISTS audit_log (
    seq        BIGSERIAL PRIMARY KEY,
    ts         TEXT NOT NULL,          -- ISO-8601 string; exact bytes keep the hash chain stable
    actor      TEXT NOT NULL,          -- user_id or 'system'
    action     TEXT NOT NULL,          -- e.g. 'draft.created', 'case.approved'
    resource   TEXT NOT NULL,          -- e.g. 'case/123', 'account/ACC-1'
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    prev_hash  TEXT NOT NULL,          -- hash of the previous row ('GENESIS' for the first)
    hash       TEXT NOT NULL           -- sha256 over (prev_hash + canonical row content)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log (resource);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log (actor);
