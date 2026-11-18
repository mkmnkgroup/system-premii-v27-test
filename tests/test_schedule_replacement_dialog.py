"""Schedule replacement must be an explicit modal decision.

Fake local data only; no Supabase login, employee publication or network writes.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


def open_schedule(app):
    next(r for r in app.radio if r.label == "Moduł").set_value("Harmonogram").run()
    return app


class ScheduleReplacementDialogTests(unittest.TestCase):
    def setUp(self):
        self.login = patch("app_auth.login_gate", return_value=None)
        self.login.start()
        self.addCleanup(self.login.stop)

    def test_button_replaces_old_checkbox_with_confirmation(self):
        app = open_schedule(AppTest.from_file(APP, default_timeout=45).run())
        self.assertEqual(list(app.exception), [])
        self.assertFalse(any(
            c.label == "Potwierdzam zastąpienie obecnego harmonogramu"
            for c in app.checkbox
        ))
        self.assertTrue(any(
            b.label == "📅 Wygeneruj nowy harmonogram" for b in app.button
        ))
        self.assertFalse(any(
            b.label == "Tak, zastąp harmonogram" for b in app.button
        ))

    def test_click_opens_dialog_without_overwriting_and_cancel_keeps_data(self):
        app = open_schedule(AppTest.from_file(APP, default_timeout=45).run())
        original = app.session_state.current_schedule_df.copy(deep=True)
        app.session_state.current_schedule_df.loc[0, "OSOBA"] = "RĘCZNIE ZMIENIONY"
        next(b for b in app.button if b.label == "📅 Wygeneruj nowy harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state.current_schedule_df.loc[0, "OSOBA"],
            "RĘCZNIE ZMIENIONY",
        )
        self.assertTrue(any(b.label == "Anuluj" for b in app.button))
        self.assertTrue(any(b.label == "Tak, zastąp harmonogram" for b in app.button))
        next(b for b in app.button if b.label == "Anuluj").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state.current_schedule_df.loc[0, "OSOBA"],
            "RĘCZNIE ZMIENIONY",
        )
        self.assertEqual(app.session_state.schedule_period_key, app.session_state.erp_period_month+" "+str(app.session_state.erp_period_year))

    def test_only_confirmation_overwrites_local_schedule_and_never_saves(self):
        app = open_schedule(AppTest.from_file(APP, default_timeout=45).run())
        app.session_state.current_schedule_df.loc[0, "OSOBA"] = "RĘCZNIE ZMIENIONY"
        app.session_state["_test_schedule_editor_generation"] = 10
        next(b for b in app.button if b.label == "📅 Wygeneruj nowy harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        next(b for b in app.button if b.label == "Tak, zastąp harmonogram").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertNotEqual(
            app.session_state.current_schedule_df.loc[0, "OSOBA"],
            "RĘCZNIE ZMIENIONY",
        )
        self.assertEqual(app.session_state["_test_schedule_editor_generation"], 11)
        self.assertEqual(
            app.session_state["_schedule_local_changes_period"],
            app.session_state.schedule_period_key,
        )
        # A local regeneration cannot trigger persistent archive or draft saves.
        self.assertEqual(app.session_state.history_v2, {})
        self.assertFalse(app.session_state.get("_test_schedule_publication", False))


if __name__ == "__main__":
    unittest.main()
