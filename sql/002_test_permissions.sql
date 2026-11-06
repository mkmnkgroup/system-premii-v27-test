-- The role v27_test_app must already exist with LOGIN, NOSUPERUSER,
-- NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS; never use postgres in the app.
BEGIN;
GRANT USAGE ON SCHEMA app_private TO v27_test_app;
GRANT SELECT, INSERT, UPDATE ON app_private.app_store TO v27_test_app;
DROP POLICY IF EXISTS v27_test_access ON app_private.app_store;
CREATE POLICY v27_test_access ON app_private.app_store
    FOR ALL TO v27_test_app USING (true) WITH CHECK (true);
COMMIT;

