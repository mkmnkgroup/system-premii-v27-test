"""Employee-to-account readiness: pure matching and admin-only UI regression.

Synthetic names and example.invalid accounts; all Supabase requests mocked.
"""
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from employee_account_links import (
    analyze_account_links, normalized_employees, names_from_attendance_draft,
    validate_quick_link,
)

EMP_1 = "TEST PRACOWNIK 01"
EMP_2 = "TEST PRACOWNIK 02"
EMP_3 = "TEST PRACOWNIK 03"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
U3 = "33333333-3333-4333-8333-333333333333"
U4 = "44444444-4444-4444-8444-444444444444"


def account(uid, employee_id, *, active=True, role="employee", email=None):
    return {
        "user_id": uid,
        "email": email or str(uid)[:8] + "@example.invalid",
        "employee_id": employee_id,
        "enabled": active,
        "role": role,
        "display_name": "TEST KONTO",
    }


class EmployeeAccountLinkTests(unittest.TestCase):
    def test_unique_active_mapping_is_counted_even_after_relogin(self):
        rows, totals, unassigned = analyze_account_links(
            [EMP_1, EMP_2, EMP_3, EMP_1],
            [account(U1, "  test   pracownik 01  "),
             account(U2, EMP_2),
             account(U3, "")],
        )
        self.assertEqual(totals, {"total": 3, "linked": 2, "issues": 1})
        self.assertEqual(rows[0]["Status"], "Powiązany")
        self.assertEqual(rows[2]["Status"], "Brak przypisania")
        self.assertEqual(unassigned[0]["user_id"], U3)

    def test_conflicts_roles_and_disabled_accounts_not_counted_as_ready(self):
        cases = [
            ([account(U1, EMP_1, active=False)], "Konto nieaktywne"),
            ([account(U1, EMP_1, role="director")], "Niedozwolona rola"),
            ([account(U1, EMP_1), account(U2, EMP_1)], "Kilka aktywnych kont"),
            ([account("not-a-uuid", EMP_1)], "Błędne konto"),
            ([], "Brak przypisania"),
        ]
        for accounts, expected in cases:
            with self.subTest(expected=expected):
                rows, totals, _ = analyze_account_links([EMP_1], accounts)
                self.assertEqual(rows[0]["Status"], expected)
                self.assertEqual(totals["issues"], 1)
                self.assertEqual(totals["linked"], 0)

    def test_quick_link_can_only_use_unassigned_active_eligible_account(self):
        users = [account(U1, EMP_1), account(U2, "")]
        selected = validate_quick_link(EMP_3, U2, [EMP_1, EMP_3], users)
        self.assertEqual(selected["user_id"], U2)
        with self.assertRaisesRegex(ValueError, "nie jest już wolne"):
            validate_quick_link(EMP_3, U1, [EMP_1, EMP_3], users)
        with self.assertRaisesRegex(ValueError, "uległo zmianie"):
            validate_quick_link(EMP_1, U2, [EMP_1, EMP_3], users)
        with self.assertRaises(ValueError):
            validate_quick_link(EMP_3, U2, [EMP_1, EMP_3],
                                [account(U1, EMP_1), account(U2, EMP_2)])

    def test_names_come_from_saved_attendance_month_not_unsaved_defaults(self):
        payload = {
            "period": "2026-11", "format_version": 1,
            "entries": [
                {"employee": EMP_3, "work_day": "2026-11-03"},
                {"employee": EMP_1, "work_day": "2026-11-03"},
                {"employee": EMP_3, "work_day": "2026-11-04"},
            ],
        }
        self.assertEqual(names_from_attendance_draft(payload, 2026, 11),
                         [EMP_1, EMP_3])
        with self.assertRaisesRegex(ValueError, "format"):
            names_from_attendance_draft(payload, 2026, 12)
        self.assertEqual(normalized_employees(["a  B", "A B", " c "]),
                         ["a B", "c"])

    def test_admin_mapping_ui_read_only_until_explicit_assignment(self):
        users = [account(U1, EMP_1), account(U2, "")]
        calls = []

        def api_mock(action, **kwargs):
            calls.append((action, kwargs))
            if action == "list":
                return True, {"users": users}
            if action == "update":
                return True, {"updated": True}
            raise AssertionError(action)

        code = '''
import streamlit as st
from admin_users import render_employee_links
from unittest.mock import patch
render_employee_links(st.session_state["test_users"])
'''
        with patch("admin_users._source_employees",
                   return_value=([EMP_1, EMP_3], "zapisana ewidencja obecności", None)):
            app = AppTest.from_string(code, default_timeout=25)
            app.session_state["test_users"] = users
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual([m.value for m in app.metric], ["2", "1", "1"])
            self.assertTrue(any(b.label == "Przypisz wybrane konto" for b in app.button))
            self.assertEqual(calls, [])
            with patch("admin_users.api", side_effect=api_mock):
                next(b for b in app.button if b.label == "Przypisz wybrane konto").click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual([c[0] for c in calls], ["list", "update"])
        self.assertEqual(calls[1][1]["employee_id"], EMP_3)
        self.assertEqual(calls[1][1]["user_id"], U2)

    def test_admin_mapping_ui_does_not_overwrite_account_changed_since_display(self):
        stale = [account(U1, EMP_1), account(U2, "")]
        changed = [account(U1, EMP_1), account(U2, EMP_2)]
        calls = []

        def api_mock(action, **kwargs):
            calls.append(action)
            if action == "list":
                return True, {"users": changed}
            raise AssertionError("Unsafe update attempted")

        code = '''
import streamlit as st
from admin_users import render_employee_links
render_employee_links(st.session_state["test_users"])
'''
        with patch("admin_users._source_employees",
                   return_value=([EMP_1, EMP_3], "zapisana ewidencja obecności", None)):
            app = AppTest.from_string(code, default_timeout=25)
            app.session_state["test_users"] = stale
            app.run()
            with patch("admin_users.api", side_effect=api_mock):
                next(b for b in app.button if b.label == "Przypisz wybrane konto").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(calls, ["list"])


if __name__ == "__main__":
    unittest.main()
