-- Run only in the separate v2.7 TEST project as database administrator.
-- No employee data, credentials, or old archive are included here.
BEGIN;
CREATE SCHEMA IF NOT EXISTS app_private;
REVOKE ALL ON SCHEMA app_private FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS app_private.app_store (
    item_key text PRIMARY KEY CHECK (item_key IN ('settings_v27', 'archive_v27')),
    payload jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app_private.app_store ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_private.app_store FROM PUBLIC, anon, authenticated;
-- Provision the dedicated LOGIN role and its password securely outside git.
-- After creating v27_test_app, run 002_test_permissions.sql as administrator.
COMMIT;

