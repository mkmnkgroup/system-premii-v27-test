"""Security regression tests runnable with the repository's unittest CI command."""
import unittest

from secure_draft_access import (
    DraftAccessDenied,
    authorized_identity,
    isolated_test_connection,
)
from workflow_drafts import draft_key


class User:
    def __init__(self, email="", logged_in=False):
        self.email = email
        self.is_logged_in = logged_in


class SecureDraftAccessTests(unittest.TestCase):
    def test_rejects_unauthenticated_user(self):
        with self.assertRaises(DraftAccessDenied):
            authorized_identity(User("staff@example.com"), ["staff@example.com"])

    def test_rejects_unlisted_user(self):
        with self.assertRaises(DraftAccessDenied):
            authorized_identity(User("other@example.com", True), ["staff@example.com"])

    def test_accepts_only_allowed_logged_in_user(self):
        actual = authorized_identity(
            User("STAFF@example.com", True), ["staff@example.com"]
        )
        self.assertEqual(actual, "staff@example.com")

    def test_rejects_missing_allowlist(self):
        with self.assertRaises(DraftAccessDenied):
            authorized_identity(User("staff@example.com", True), [])

    def test_test_database_must_be_isolated(self):
        with self.assertRaises(DraftAccessDenied):
            isolated_test_connection(
                "postgresql://postgres:password@db.epggtvgjfraflzibqrvr.supabase.co/postgres"
            )
        with self.assertRaises(DraftAccessDenied):
            isolated_test_connection(
                "postgresql://postgres:password@db.bzpfukyugfuybqivjyoz.supabase.co/postgres"
            )
        valid = (
            "postgresql://v27_test_app:password@"
            "db.bzpfukyugfuybqivjyoz.supabase.co/postgres"
        )
        self.assertEqual(isolated_test_connection(valid), valid)

    def test_period_keys_are_scoped_and_validated(self):
        self.assertEqual(
            draft_key("2026-11", "schedule"), "draft_v27:2026-11:schedule"
        )
        with self.assertRaises(ValueError):
            draft_key("2026-13", "schedule")
        with self.assertRaises(ValueError):
            draft_key("2026-11", "unknown")


if __name__ == "__main__":
    unittest.main()
