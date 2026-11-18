"""A saved Supabase draft must never silently replace a newly generated schedule.

All server responses are mocked, including compare-and-swap revision checks.
No network calls, no real employees, and no publication.
"""
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from db_storage import _encode

WORKER = "TEST PRACOWNIK 01"
PERIOD = "Listopad 2026"
APP = '''
import streamlit as st
import pandas as pd
from test_schedule_drafts import render_schedule_draft
if "current_schedule_df" not in st.session_state:
    st.session_state.current_schedule_df = pd.DataFrame([{
        "OSOBA": "TEST PRACOWNIK 01",
        "DATA": "01.11.2026",
        "DZIEŃ PRACUJĄCY/WOLNY": "Wolny",
        "CZAS ZMIANY": "Wolne",
    }])
if "schedule_period_key" not in st.session_state:
    st.session_state.schedule_period_key = "Listopad 2026"
render_schedule_draft(2026, 11, "Listopad 2026")
'''


def saved_payload(name="WCZEŚNIEJ ZAPISANY"):
    return {
        "format_version": 1,
        "period": "2026-11",
        "schedule": _encode(pd.DataFrame([{
            "OSOBA": name,
            "DATA": "01.11.2026",
            "DZIEŃ PRACUJĄCY/WOLNY": "Wolny",
            "CZAS ZMIANY": "Wolne",
        }])),
    }


class SavedScheduleConflictTests(unittest.TestCase):
    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_existing_draft_prompts_without_restoring_or_writing(self):
        calls = []

        def api(action, key, **kwargs):
            calls.append((action, kwargs))
            if action == "read":
                return True, {"found": True, "revision": 4,
                              "payload": saved_payload()}
            raise AssertionError("Save must await confirmation")

        with patch("test_schedule_drafts._request", side_effect=api):
            app = AppTest.from_string(APP, default_timeout=30).run()
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([v[0] for v in calls], ["read"])
        self.assertEqual(app.session_state.current_schedule_df.iloc[0]["OSOBA"], WORKER)
        self.assertTrue(any(b.label == "Tak, zastąp zapis w bazie" for b in app.button))
        self.assertTrue(any(b.label == "Anuluj" for b in app.button))

    def test_confirm_overwrites_only_read_revision(self):
        operations = []

        def api(action, key, **kwargs):
            operations.append((action, kwargs))
            if action == "read":
                return True, {"found": True, "revision": 4,
                              "payload": saved_payload()}
            if action == "write":
                if kwargs["expected_revision"] != 4:
                    return False, {"error": "Conflict"}
                return True, {"revision": 5}
            raise AssertionError(action)

        with patch("test_schedule_drafts._request", side_effect=api):
            app = AppTest.from_string(APP, default_timeout=30).run()
            app.session_state["_schedule_local_changes_period"] = PERIOD
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
            self.assertEqual(list(app.exception), [])
            self.button(app, "Tak, zastąp zapis w bazie").click()
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        writes = [kwargs for a, kwargs in operations if a == "write"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["expected_revision"], 4)
        self.assertEqual(writes[0]["payload"]["period"], "2026-11")
        self.assertEqual(
            app.session_state["_test_saved_draft_revision_draft_v27_2026-11_schedule"], 5
        )
        self.assertFalse(app.session_state.get("_schedule_local_changes_period"))

    def test_refuses_stale_version_while_confirming(self):
        reads = 0
        writes = []

        def api(action, key, **kwargs):
            nonlocal reads
            if action == "read":
                reads += 1
                return True, {
                    "found": True,
                    "revision": 4 if reads <= 2 else 6,
                    "payload": saved_payload(),
                }
            if action == "write":
                writes.append(kwargs)
                return True, {"revision": 7}
            raise AssertionError(action)

        with patch("test_schedule_drafts._request", side_effect=api):
            app = AppTest.from_string(APP, default_timeout=30).run()
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
            self.button(app, "Tak, zastąp zapis w bazie").click()
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(reads, 3)
        self.assertEqual(writes, [])
        self.assertEqual(app.session_state.current_schedule_df.iloc[0]["OSOBA"], WORKER)

    def test_existing_known_revision_can_be_saved_normally_without_forced_restore(self):
        writes = []

        def api(action, key, **kwargs):
            if action == "write":
                writes.append(kwargs)
                return True, {"revision": 8}
            raise AssertionError("Known draft should not need preflight read")

        with patch("test_schedule_drafts._request", side_effect=api):
            app = AppTest.from_string(APP, default_timeout=30).run()
            app.session_state["_test_saved_draft_revision_draft_v27_2026-11_schedule"] = 7
            self.button(app, "💾 Zapisz aktualny harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["expected_revision"], 7)

    def test_restore_remains_an_explicit_separate_operation(self):
        with patch("test_schedule_drafts._request", return_value=(
            True, {"found": True, "revision": 8, "payload": saved_payload()}
        )):
            app = AppTest.from_string(APP, default_timeout=30).run()
            app.session_state["_schedule_local_changes_period"] = PERIOD
            self.button(app, "📂 Przywróć szkic z Supabase").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state.current_schedule_df.iloc[0]["OSOBA"], "WCZEŚNIEJ ZAPISANY"
        )
        self.assertFalse(app.session_state.get("_schedule_local_changes_period"))


if __name__ == "__main__":
    unittest.main()
