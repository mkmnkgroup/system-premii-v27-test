"""Monthly draft controls live only on Pulpit; opt-in autosave still works elsewhere.

Only fictional data and mocked persistence; no Supabase network calls.
"""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")
OWNER = "11111111-1111-4111-8111-111111111111"
PERIOD = "2026-11-01"
SAVE_BUTTON = "Zapisz wersję roboczą"
RESTORE_BUTTON = "Przywróć zapis z bazy"


def verified_admin(method, path, **kwargs):
    if path == "/auth/v1/user":
        return 200, {"id": OWNER, "email": "fake.admin@example.invalid"}
    if path.startswith("/rest/v1/app_user_profiles?"):
        return 200, [{"user_id": OWNER, "role": "admin",
                      "enabled": True, "employee_id": None}]
    return 400, {}


def module(app, module_name):
    next(r for r in app.radio if r.label == "Moduł").set_value(module_name).run()
    return app


class MonthlyDraftDashboardOnlyTests(unittest.TestCase):
    def test_only_dashboard_has_manual_draft_controls(self):
        context = ("https://example.invalid", "fake-anon", "fake-token",
                   OWNER, PERIOD)
        with patch("app_auth._request", side_effect=verified_admin), \
             patch("test_draft_ui._context", return_value=context), \
             patch("test_draft_ui.read_draft", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45)
            app.session_state["_test_auth_access_token"] = "fake-token"
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertIn(SAVE_BUTTON, [b.label for b in app.button])
            self.assertIn(RESTORE_BUTTON, [b.label for b in app.button])

            for name in ("Harmonogram", "Obecności i nadgodziny",
                         "Dodatki premiowe", "Rozliczenie premii",
                         "Archiwum", "Ustawienia"):
                module(app, name)
                self.assertEqual(list(app.exception), [], name)
                buttons = [b.label for b in app.button]
                self.assertNotIn(SAVE_BUTTON, buttons, name)
                self.assertNotIn(RESTORE_BUTTON, buttons, name)
                # Draft manager must no longer live in the common content.
                self.assertNotIn(
                    "💾 Wersja robocza miesiąca",
                    [ex.label for ex in app.expander],
                    name,
                )
            module(app, "Pulpit")
            self.assertEqual(list(app.exception), [])
            self.assertIn(SAVE_BUTTON, [b.label for b in app.button])

    def test_background_autosave_remains_active_after_leaving_dashboard(self):
        context = ("https://example.invalid", "fake-anon", "fake-token",
                   OWNER, PERIOD)
        saved = []
        storage = {}
        def mock_save(*args):
            _, payload, version = args[-3:]
            self.assertEqual(version, len(saved))
            saved.append(copy.deepcopy(payload))
            storage[PERIOD] = {
                "revision": len(saved), "updated_at": "2026-11-18T12:00:00Z",
            }
            return dict(storage[PERIOD])

        with patch("app_auth._request", side_effect=verified_admin), \
             patch("test_draft_ui._context", return_value=context), \
             patch("test_draft_ui.read_draft", return_value=None), \
             patch("test_draft_ui.save_draft", side_effect=mock_save):
            app = AppTest.from_file(APP, default_timeout=45)
            app.session_state["_test_auth_access_token"] = "fake-token"
            app.run()
            next(b for b in app.button if b.label == SAVE_BUTTON).click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(saved), 1)

            auto = next(c for c in app.checkbox if c.label == "Autozapis w trakcie pracy")
            auto.check().run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(app.session_state["_test_draft_status"][PERIOD]["autowrite"])

            # A committed change made in a different module must be picked
            # up at the final autosave pass, even when controls are hidden.
            app.session_state.rate_pallet = 42.0
            app.session_state["_test_draft_status"][PERIOD]["checked_at"] = 0.0
            module(app, "Dodatki premiowe")
            self.assertEqual(list(app.exception), [])
            self.assertNotIn(SAVE_BUTTON, [b.label for b in app.button])
            self.assertEqual(len(saved), 2)
            self.assertEqual(app.session_state["_test_draft_status"][PERIOD]["revision"], 2)

            module(app, "Pulpit")
            self.assertEqual(list(app.exception), [])
            self.assertTrue(next(
                c for c in app.checkbox if c.label == "Autozapis w trakcie pracy"
            ).value)


if __name__ == "__main__":
    unittest.main()
