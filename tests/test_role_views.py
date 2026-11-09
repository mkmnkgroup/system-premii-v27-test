"""Authorization and visibility tests for role-specific read-only dashboards."""
import ast
from pathlib import Path
import unittest

from role_views import role_sections


class RoleSectionsTests(unittest.TestCase):
    def test_director_sees_only_aggregated_statistics(self):
        self.assertEqual(role_sections("director"), ("statystyki", "porownania"))
        self.assertFalse(set(role_sections("director")) & {
            "premie", "moj_pasek", "moja_obecnosc", "harmonogramy",
            "obecnosc", "moj_miesiac",
        })

    def test_employee_sees_only_own_month_report(self):
        self.assertEqual(role_sections("employee"), (
            "moj_miesiac", "moj_pasek", "moja_obecnosc", "wskazniki",
        ))

    def test_manager_sees_scheduling_and_bonus(self):
        self.assertTrue({"harmonogramy", "premie", "obecnosc"}.issubset(
            role_sections("manager")
        ))
        self.assertNotIn("porownania", role_sections("manager"))

    def test_unknown_roles_fail_closed(self):
        for role in (None, "", "guest", "owner"):
            self.assertEqual(role_sections(role), ())

    def test_role_view_has_no_service_role_key(self):
        source = Path(__file__).resolve().parents[1].joinpath("role_views.py").read_text(encoding="utf8")
        self.assertNotIn("SERVICE_ROLE", source)
        self.assertNotIn("SUPABASE_SECRET", source)
        self.assertIn("_test_auth_access_token", source)

    def test_role_view_syntax(self):
        source = Path(__file__).resolve().parents[1].joinpath("role_views.py").read_text(encoding="utf8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
