"""Offline integration of TEST attendance publishing and employee-only view.

Every external API is mocked. No real users, Supabase writes or production data.
"""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

PERIOD = "2026-11-01"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
PAYLOAD = {
    "format_version": 1, "period": "2026-11",
    "entries": [
        {"employee": "PRACOWNIK TEST 01", "work_day": "2026-11-03",
         "day_type": "Pracujący", "absence": "Brak",
         "time_in": "08:00", "time_out": "16:00", "overtime_h": 0},
        {"employee": "PRACOWNIK TEST 02", "work_day": "2026-11-03",
         "day_type": "Pracujący", "absence": "Brak",
         "time_in": "09:00", "time_out": "17:00", "overtime_h": 0},
    ],
}
USERS = [
    {"user_id": U1, "employee_id": "PRACOWNIK TEST 01",
     "email": "test01@example.invalid", "role": "employee", "enabled": True},
    {"user_id": U2, "employee_id": "PRACOWNIK TEST 02",
     "email": "test02@example.invalid", "role": "employee", "enabled": True},
]
APP = """
import streamlit as st
from attendance_publication_ui import render_attendance_publication
render_attendance_publication(2026, 11)
"""


class AttendanceUiIntegrationTests(unittest.TestCase):
    def test_publish_needs_explicit_approval_and_locked_revision(self):
        sent = []
        def publish_api(action, period, **kwargs):
            if action == "status":
                return True, {"published": bool(sent),
                              "publication": {"entry_count": 2, "employee_count": 2}}
            if action == "publish":
                sent.append((period, kwargs))
                return True, {"published": True}
            raise AssertionError("Unknown API action")

        with patch("attendance_publication_ui.publication_api", side_effect=publish_api), \
             patch("attendance_publication_ui.draft_api",
                   return_value=(True, {"found": True, "revision": 7,
                                        "payload": PAYLOAD})), \
             patch("attendance_publication_ui.user_api",
                   return_value=(True, {"users": USERS})):
            app = AppTest.from_string(APP, default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            button = next(b for b in app.button if b.label == "Opublikuj obecność pracownikom")
            self.assertTrue(button.disabled)
            self.assertEqual(sent, [])
            self.assertEqual(len(app.dataframe[0].value), 2)
            next(c for c in app.checkbox
                 if "Zatwierdzam jednorazową publikację" in c.label).check().run()
            self.assertEqual(list(app.exception), [])
            button = next(b for b in app.button if b.label == "Opublikuj obecność pracownikom")
            self.assertFalse(button.disabled)
            self.assertEqual(sent, [])
            button.click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(sent, [(PERIOD, {
                "confirm": "PUBLIKUJ_OBECNOSC", "expected_revision": 7
            })])
            self.assertTrue(app.session_state["_test_attendance_publications"][PERIOD])

    def test_missing_worker_mapping_blocks_publish(self):
        with patch("attendance_publication_ui.publication_api",
                   return_value=(True, {"published": False})), \
             patch("attendance_publication_ui.draft_api",
                   return_value=(True, {"found": True, "revision": 2,
                                        "payload": PAYLOAD})), \
             patch("attendance_publication_ui.user_api",
                   return_value=(True, {"users": USERS[:1]})):
            app = AppTest.from_string(APP, default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertFalse(any(b.label == "Opublikuj obecność pracownikom"
                             for b in app.button))

    def test_employee_view_restricts_query_to_account_id(self):
        import role_views
        calls = []
        def get(table, *, filters, columns, limit):
            calls.append((table, filters, limit))
            if filters.get("user_id") != "eq." + U1:
                raise AssertionError("Employee view queried a different account")
            return [{"work_day": "2026-11-03",
                     "status": "Potwierdzona obecność", "absence_label": "",
                     "time_in": "08:00", "time_out": "16:00", "overtime_h": 0}]
        source = (
            "from role_views import _my_attendance\n"
            "_my_attendance(2026, 11, " + repr(U1) + ")\n"
        )
        with patch.object(role_views, "_get", side_effect=get):
            app = AppTest.from_string(source, default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "v27_test_attendance")
        self.assertEqual(calls[0][1]["user_id"], "eq." + U1)
        self.assertEqual(len(app.dataframe[0].value), 1)


if __name__ == "__main__":
    unittest.main()
