import json
import os
import unittest
from datetime import date
from unittest.mock import patch
import numpy as np
import pandas as pd
import psycopg
import db_storage as db

class UnitTests(unittest.TestCase):
    def test_separate_password_special_characters(self):
        from psycopg.conninfo import conninfo_to_dict
        secret = "synthetic:@\\'\" #?"
        result = db.configured_connection('postgresql://test_user@localhost/test', secret)
        parsed = conninfo_to_dict(result)
        self.assertEqual(parsed['password'], secret)
        self.assertEqual(parsed['user'], 'test_user')

    def test_url_with_existing_password_is_supported(self):
        value = 'postgresql://test_user:synthetic@localhost/test'
        self.assertEqual(db.configured_connection(value), value)

    def test_invalid_url_does_not_expose_secret(self):
        with self.assertRaises(db.StorageError) as caught:
            db.configured_connection('not a valid connection', 'SENSITIVE_SENTINEL')
        self.assertNotIn('SENSITIVE_SENTINEL', str(caught.exception))

    def test_archive_roundtrip(self):
        frame = pd.DataFrame({'Pracownik': ['TEST PRACOWNIK 01'], 'Premia': [123.45]})
        result = db._decode(json.loads(json.dumps(db._encode({'TEST': {'summary': frame}}))))
        pd.testing.assert_frame_equal(result['TEST']['summary'], frame)

    def test_missing_values(self):
        value = {'missing': pd.NA, 'udt': np.bool_(True), 'date': date(2026, 1, 1)}
        self.assertEqual(db._encode(value), {'missing': None, 'udt': True, 'date': '2026-01-01'})

    def test_nonfinite(self):
        self.assertEqual(db._encode([np.float64('inf'), np.nan, pd.NaT]), [None]*3)

    def test_empty_frame(self):
        frame = pd.DataFrame(columns=['Pracownik', 'Premia'])
        pd.testing.assert_frame_equal(db._decode(db._encode(frame)), frame)

    def test_read_redaction(self):
        with patch.object(db, '_connect', side_effect=Exception('SENSITIVE_SENTINEL')):
            with self.assertRaises(db.StorageError) as caught:
                db.read_versioned('unused', 'settings_v27')
        self.assertNotIn('SENSITIVE_SENTINEL', str(caught.exception))

    def test_write_redaction(self):
        with patch.object(db, '_connect', side_effect=Exception('SENSITIVE_SENTINEL')):
            with self.assertRaises(db.StorageError) as caught:
                db.write_item('unused', 'settings_v27', {}, expected_revision=None)
        self.assertNotIn('SENSITIVE_SENTINEL', str(caught.exception))

    def test_tls(self):
        with patch.object(db.psycopg, 'connect') as connect:
            db._connect('unused')
        self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 10)

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Isolated PostgreSQL service required')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ['TEST_DATABASE_URL']
        with psycopg.connect(cls.dsn) as conn:
            conn.execute('CREATE SCHEMA app_private')
            conn.execute('''CREATE TABLE app_private.app_store (
                item_key text PRIMARY KEY, payload jsonb NOT NULL,
                revision bigint NOT NULL DEFAULT 1, updated_at timestamptz DEFAULT now())''')

    def setUp(self):
        # Override only for disposable local CI container; app always enforces TLS.
        guard = patch.object(db, '_connect', lambda _: psycopg.connect(self.dsn))
        guard.start()
        self.addCleanup(guard.stop)
        with psycopg.connect(self.dsn) as conn:
            conn.execute('TRUNCATE app_private.app_store')

    def test_settings_new_connection(self):
        value = {'base_bonus_salary': 123.0, 'employees_df': [{'OSOBA': 'TEST PRACOWNIK 01'}]}
        rev = db.write_item('test', 'settings_v27', value, expected_revision=None)
        self.assertEqual(db.read_versioned('test', 'settings_v27'), (value, rev))

    def test_archive_new_connection(self):
        frame = pd.DataFrame({'Pracownik': ['TEST PRACOWNIK 01'], 'Premia': [1.5]})
        db.write_item('test', 'archive_v27', {'TEST': {'summary': frame}}, expected_revision=None)
        result, rev = db.read_versioned('test', 'archive_v27')
        pd.testing.assert_frame_equal(result['TEST']['summary'], frame)
        self.assertEqual(rev, 1)

    def test_stale_update_rejected(self):
        rev = db.write_item('test', 'settings_v27', {'value': 1}, expected_revision=None)
        db.write_item('test', 'settings_v27', {'value': 2}, expected_revision=rev)
        with self.assertRaises(db.StorageConflict):
            db.write_item('test', 'settings_v27', {'value': 3}, expected_revision=rev)
        self.assertEqual(db.read_versioned('test', 'settings_v27'), ({'value': 2}, 2))

    def test_concurrent_insert_rejected(self):
        db.write_item('test', 'archive_v27', {'first': 1}, expected_revision=None)
        with self.assertRaises(db.StorageConflict):
            db.write_item('test', 'archive_v27', {'second': 2}, expected_revision=None)

    def test_missing_key(self):
        self.assertEqual(db.read_versioned('test', 'archive_v27'), ({}, None))

    def test_independent_keys(self):
        db.write_item('test', 'settings_v27', {'kind': 'settings'}, expected_revision=None)
        db.write_item('test', 'archive_v27', {'kind': 'archive'}, expected_revision=None)
        self.assertEqual(db.read_versioned('test', 'settings_v27')[0], {'kind': 'settings'})

if __name__ == '__main__':
    unittest.main()

