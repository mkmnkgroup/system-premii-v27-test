-- TEST DATABASE ONLY. Do not execute against the production Supabase project.
-- Apply after sql/001_test_storage.sql, with a dedicated test database role.
BEGIN;
ALTER TABLE app_private.app_store DROP CONSTRAINT IF EXISTS app_store_item_key_check;
ALTER TABLE app_private.app_store ADD CONSTRAINT app_store_item_key_check
  CHECK (item_key IN ('settings_v27', 'archive_v27') OR
         item_key ~ '^draft_v27:[0-9]{4}-(0[1-9]|1[0-2]):(schedule|attendance|production|weights|bonuses|approval)$');
ALTER TABLE app_private.app_store ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_private.app_store FROM PUBLIC, anon, authenticated;
COMMIT;
