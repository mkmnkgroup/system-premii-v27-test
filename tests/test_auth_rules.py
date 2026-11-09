"""Security tests use unittest, matching GitHub Actions discovery."""
import unittest
from auth_rules import active_role, allowed_module


class TestAuthRules(unittest.TestCase):
    def setUp(self):
        self.user = {"id": "test-uid", "email": "admin@example.invalid"}
        self.admin = {"user_id": "test-uid", "role": "admin", "enabled": True}

    def test_only_matching_enabled_profile_grants_admin(self):
        self.assertEqual(active_role(self.user, [self.admin]), "admin")

    def test_reject_unmatched_profile(self):
        self.assertIsNone(active_role(self.user, [{"user_id": "someone-else", "role": "admin", "enabled": True}]))

    def test_reject_disabled_profile(self):
        self.assertIsNone(active_role(self.user, [{"user_id": "test-uid", "role": "admin", "enabled": False}]))

    def test_reject_duplicate_profiles(self):
        self.assertIsNone(active_role(self.user, [self.admin, self.admin]))

    def test_reject_unrecognized_role(self):
        self.assertIsNone(active_role(self.user, [{"user_id": "test-uid", "role": "owner", "enabled": True}]))

    def test_reject_malformed_responses(self):
        self.assertIsNone(active_role({}, [self.admin]))
        self.assertIsNone(active_role(self.user, None))
        self.assertIsNone(active_role(self.user, []))

    def test_legacy_modules_are_never_exposed(self):
        for role in ("admin", "director", "manager", "employee"):
            self.assertFalse(allowed_module(role, "payroll"))
            self.assertFalse(allowed_module(role, "legacy_dashboard"))
        self.assertTrue(allowed_module("admin", "test_auth_status"))


if __name__ == "__main__":
    unittest.main()
