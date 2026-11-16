"""AppTest: save/restore controls and safe opt-in autosave on synthetic admin.

All remote operations are mocked; no real database or account is accessed.
"""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")
USER = "11111111-1111-4111-8111-111111111111"
PERIOD = "2026-11-01"


def verified_admin_api(method, path, **kwargs):
    if path == "/auth/v1/user":
        return 200, {"id": USER, "email": "synthetic-admin@example.invalid"}
    if path.startswith("/rest/v1/app_user_profiles?"):
        return 200, [{"user_id": USER, "role": "admin", "enabled": True,
                      "employee_id": None}]
    if path.startswith("/auth/v1/logout"):
        return 204, {}
    return 400, {}


class DraftSidebarTests(unittest.TestCase):
    def test_unauthenticated_user_never_sees_drafts(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        self.assertEqual(list(app.exception), [])
        self.assertFalse(any("wersję roboczą" in b.label.lower() for b in app.button))

    def test_explicit_save_then_restore_in_new_tab(self):
        stored = {}
        written = []

        def read(*args):
            return copy.deepcopy(stored.get(args[-1]))

        def save(*args):
            period, payload, previous_revision = args[-3:]
            expected = stored.get(period, {}).get("revision", 0)
            if expected != previous_revision:
                raise AssertionError("unexpected revision")
            revision = expected + 1
            stored[period] = {"payload": copy.deepcopy(payload),
                              "revision": revision,
                              "updated_at": "2026-11-16T12:00:00Z"}
            written.append((period, revision))
            return {"revision": revision, "updated_at": stored[period]["updated_at"]}

        context = ("https://example.invalid", "synthetic-anon",
                   "synthetic-access", USER, PERIOD)
        with patch("app_auth._request", side_effect=verified_admin_api), \
             patch("test_draft_ui._context", return_value=context), \
             patch("test_draft_ui.read_draft", side_effect=read), \
             patch("test_draft_ui.save_draft", side_effect=save):
            app = AppTest.from_file(APP, default_timeout=45)
            app.session_state["_test_auth_access_token"] = "synthetic-access"
            app.run()
            self.assertFalse(list(app.exception))
            self.assertTrue(any(b.label == "Zapisz wersję roboczą" for b in app.button))
            app.session_state.current_schedule_df.loc[0, "OSOBA"] = "FAKE SAVED USER"
            next(b for b in app.button if b.label == "Zapisz wersję roboczą").click().run()
            self.assertFalse(list(app.exception))
            self.assertEqual(written, [(PERIOD, 1)])
            self.assertEqual(stored[PERIOD]["payload"]["tables"]["current_schedule_df"][0]["OSOBA"],
                             "FAKE SAVED USER")
            self.assertFalse(app.session_state["_test_draft_status"][PERIOD]["autowrite"])

            # A fresh websocket/tab starts without any session-state draft.
            fresh = AppTest.from_file(APP, default_timeout=45)
            fresh.session_state["_test_auth_access_token"] = "synthetic-access"
            fresh.run()
            self.assertFalse(list(fresh.exception))
            self.assertNotEqual(
                fresh.session_state.current_schedule_df.loc[0, "OSOBA"], "FAKE SAVED USER"
            )
            next(b for b in fresh.button if b.label == "Przywróć zapis z bazy").click().run()
            self.assertFalse(list(fresh.exception))
            self.assertEqual(
                fresh.session_state.current_schedule_df.loc[0, "OSOBA"], "FAKE SAVED USER"
            )
            self.assertEqual(fresh.session_state["_test_draft_status"][PERIOD]["revision"], 1)
            self.assertEqual(written, [(PERIOD, 1)])


if __name__ == "__main__":
    unittest.main()
