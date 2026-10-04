-- RESOLVE row-level security (PLAN §13.6). Phase 6.
--
-- Authorisation is enforced by the database, not by prompts. Data loaders run as the
-- table owner (which bypasses RLS, so `make data-load` keeps working). Request work
-- runs after `SET ROLE resolve_app` (a non-owner role, so RLS applies) with
-- `app.user_id`/`app.role` set per transaction. Policies then restrict every
-- queue-scoped table to the queues the acting user is assigned (user_queues).
--
-- Not-found and not-permitted are intentionally indistinguishable (a filtered row
-- simply does not appear), which avoids leaking existence across queues.

-- A non-login role with no inherent bypass of RLS. The app does: SET ROLE resolve_app.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'resolve_app') THEN
        CREATE ROLE resolve_app NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO resolve_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO resolve_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO resolve_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO resolve_app;

-- Helper: the set of queue_ids the current app.user_id may access.
CREATE OR REPLACE FUNCTION current_user_queues() RETURNS SETOF TEXT
    LANGUAGE sql STABLE AS $$
    SELECT queue_id FROM user_queues
    WHERE user_id = current_setting('app.user_id', true)
$$;

-- Admins see everything; everyone else is restricted to their queues. Used for both
-- the read (USING) and write (WITH CHECK) sides so the app can only touch in-scope rows.
-- ENABLE (not FORCE): the owner-run loaders bypass RLS; resolve_app is subject to it.

ALTER TABLE complaints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS complaints_queue_isolation ON complaints;
CREATE POLICY complaints_queue_isolation ON complaints FOR ALL
    USING (
        current_setting('app.role', true) = 'admin'
        OR queue_id IN (SELECT current_user_queues())
    )
    WITH CHECK (
        current_setting('app.role', true) = 'admin'
        OR queue_id IN (SELECT current_user_queues())
    );

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS accounts_queue_isolation ON accounts;
CREATE POLICY accounts_queue_isolation ON accounts FOR ALL
    USING (
        current_setting('app.role', true) = 'admin'
        OR queue_id IN (SELECT current_user_queues())
    )
    WITH CHECK (
        current_setting('app.role', true) = 'admin'
        OR queue_id IN (SELECT current_user_queues())
    );

-- transactions and disputes inherit scope via their account's queue.
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS transactions_queue_isolation ON transactions;
CREATE POLICY transactions_queue_isolation ON transactions FOR ALL
    USING (
        current_setting('app.role', true) = 'admin'
        OR account_id IN (
            SELECT account_id FROM accounts WHERE queue_id IN (SELECT current_user_queues())
        )
    )
    WITH CHECK (true);

ALTER TABLE disputes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS disputes_queue_isolation ON disputes;
CREATE POLICY disputes_queue_isolation ON disputes FOR ALL
    USING (
        current_setting('app.role', true) = 'admin'
        OR account_id IN (
            SELECT account_id FROM accounts WHERE queue_id IN (SELECT current_user_queues())
        )
    )
    WITH CHECK (true);
