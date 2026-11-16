"""Security regression checks for server-side test Supabase token refresh."""
import time
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from auth_rules import bind_user_session
from auth_session import (
    TOKEN_KEYS, clear_auth_tokens, refresh_auth_tokens,
    session_needs_refresh, store_auth_tokens,
)
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")
OLD_ACCESS = "old-header.payload.signature-" * 4
NEW_ACCESS = "new-header.payload.signature-" * 4
OLD_REFRESH = "original-synthetic-refresh-secret"
NEW_REFRESH = "rotated-synthetic-refresh-secret"


def payload(access=NEW_ACCESS, refresh=NEW_REFRESH, ttl=3600):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": ttl,
        "token_type": "bearer",
    }


def valid_auth_api(method, path, **kwargs):
    if method == "POST" and path.endswith("grant_type=refresh_token"):
        if kwargs.get("data") != {"refresh_token": OLD_REFRESH}:
            return 401, {}
        return 200, payload()
    if method == "GET" and path == "/auth/v1/user":
        if kwargs.get("token") != NEW_ACCESS:
            return 401, {}
        return 200, {"id": "synthetic-admin", "email": "admin@example.invalid"}
    if method == "GET" and path.startswith("/rest/v1/app_user_profiles?"):
        if kwargs.get("token") != NEW_ACCESS:
            return 401, {}
        return 200, [{"user_id": "synthetic-admin", "role": "admin",
                      "enabled": True, "employee_id": None}]
    return 204, {}


class SessionTokenTests(unittest.TestCase):
    def test_full_token_pair_is_required_and_not_partially_written(self):
        session = {"_test_auth_access_token": OLD_ACCESS}
        for wrong in (
            {"access_token": NEW_ACCESS, "expires_in": 3600},
            payload(refresh=""),
            payload(ttl=0),
            payload(ttl=True),
            payload(access="not-a-jwt"),
            None,
        ):
            self.assertFalse(store_auth_tokens(session, wrong, now=1000))
            self.assertEqual(session["_test_auth_access_token"], OLD_ACCESS)
            self.assertNotIn("_test_auth_refresh_token", session)
        self.assertTrue(store_auth_tokens(session, payload(), now=1000))
        self.assertEqual(session["_test_auth_expires_at"], 4600)
        self.assertEqual(session["_test_auth_refresh_token"], NEW_REFRESH)

    def test_refresh_happens_before_token_expires(self):
        state = {"_test_auth_expires_at": 1000}
        self.assertFalse(session_needs_refresh(state, now=900))
        self.assertTrue(session_needs_refresh(state, now=911))
        self.assertTrue(session_needs_refresh(state, now=1100))
        self.assertFalse(session_needs_refresh({}, now=1100))

    def test_refresh_rotates_secret_without_exposing_it(self):
        state = {"_test_auth_access_token": OLD_ACCESS,
                 "_test_auth_refresh_token": OLD_REFRESH,
                 "_test_auth_expires_at": 1}
        calls = []
        def requester(*args, **kwargs):
            calls.append((args, kwargs))
            return 200, payload()
        self.assertTrue(refresh_auth_tokens(state, requester, now=1000))
        self.assertEqual(state["_test_auth_access_token"], NEW_ACCESS)
        self.assertEqual(state["_test_auth_refresh_token"], NEW_REFRESH)
        self.assertEqual(state["_test_auth_expires_at"], 4600)
        self.assertEqual(calls, [(("POST", "/auth/v1/token?grant_type=refresh_token"),
                                  {"data": {"refresh_token": OLD_REFRESH}})])

    def test_revoked_and_malformed_refresh_fail_closed(self):
        for status, reply in ((401, {}), (0, {}), (200, {"access_token": NEW_ACCESS}),
                              (200, payload(ttl=0))):
            state = {"_test_auth_access_token": OLD_ACCESS,
                     "_test_auth_refresh_token": OLD_REFRESH,
                     "_test_auth_expires_at": 1}
            self.assertFalse(refresh_auth_tokens(
                state, lambda *a, **kw: (status, reply)))
            for key in TOKEN_KEYS:
                self.assertNotIn(key, state)

    def test_binding_same_user_keeps_rotation_and_drops_old_workspace(self):
        state = {"_test_auth_access_token": NEW_ACCESS,
                 "_test_auth_refresh_token": NEW_REFRESH,
                 "_test_auth_expires_at": 4600,
                 "_test_work_user_id": "different-account",
                 "employees_df": pd.DataFrame({"OSOBA": ["PRIVATE OLD DATA"]}),
                 "_preview_store": {"secret": 123}}
        self.assertTrue(bind_user_session(state, "verified-admin"))
        self.assertEqual(state["_test_auth_access_token"], NEW_ACCESS)
        self.assertEqual(state["_test_auth_refresh_token"], NEW_REFRESH)
        self.assertEqual(state["_test_work_user_id"], "verified-admin")
        self.assertNotIn("employees_df", state)
        self.assertNotIn("_preview_store", state)
        self.assertFalse(bind_user_session(state, "verified-admin"))
        clear_auth_tokens(state)
        for key in TOKEN_KEYS:
            self.assertNotIn(key, state)


class GatewayRefreshIntegrationTests(unittest.TestCase):
    def _app(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_auth_access_token"] = OLD_ACCESS
        app.session_state["_test_auth_refresh_token"] = OLD_REFRESH
        app.session_state["_test_auth_expires_at"] = 1
        return app

    def test_password_login_accepts_only_complete_supabase_session(self):
        app = AppTest.from_file(APP, default_timeout=45)
        self.assertFalse(list(app.run().exception))

        def api(method, path, **kwargs):
            if path == "/auth/v1/token?grant_type=password":
                return 200, payload()
            if path == "/auth/v1/user":
                return 200, {"id": "synthetic-admin", "email": "admin@example.invalid"}
            if path.startswith("/rest/v1/app_user_profiles?"):
                return 200, [{"user_id": "synthetic-admin", "role": "admin",
                              "enabled": True, "employee_id": None}]
            return 204, {}

        with patch("app_auth._request", side_effect=api):
            app.text_input[0].set_value("admin@example.invalid")
            app.text_input[1].set_value("synthetic-demo-password")
            next(b for b in app.button if b.label == "Zaloguj się").click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.session_state["_test_auth_access_token"], NEW_ACCESS)
        self.assertEqual(app.session_state["_test_auth_refresh_token"], NEW_REFRESH)
        self.assertTrue(any(r.label == "Moduł" for r in app.radio))

    def test_password_login_fails_closed_without_refresh_token(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        with patch("app_auth._request",
                   return_value=(200, {"access_token": NEW_ACCESS, "expires_in": 3600})):
            app.text_input[0].set_value("admin@example.invalid")
            app.text_input[1].set_value("synthetic-demo-password")
            next(b for b in app.button if b.label == "Zaloguj się").click().run()
        self.assertFalse(list(app.exception))
        for key in TOKEN_KEYS:
            self.assertNotIn(key, app.session_state)
        self.assertEqual(list(app.radio), [])

    def test_revoked_role_after_refresh_clears_entire_workspace(self):
        app = self._app()
        app.session_state["employees_df"] = pd.DataFrame({"OSOBA": ["OLD SECRET"]})
        def api(method, path, **kwargs):
            if path.endswith("grant_type=refresh_token"):
                return 200, payload()
            if path == "/auth/v1/user":
                return 200, {"id": "synthetic-admin"}
            if path.startswith("/rest/v1/app_user_profiles?"):
                return 200, [{"user_id": "synthetic-admin", "role": "admin",
                              "enabled": False}]
            return 204, {}
        with patch("app_auth._request", side_effect=api):
            app.run()
        self.assertFalse(list(app.exception))
        for key in (*TOKEN_KEYS, "employees_df"):
            self.assertNotIn(key, app.session_state)
        self.assertEqual(list(app.radio), [])

    def test_expired_access_refreshes_and_revalidates_role(self):
        app = self._app()
        with patch("app_auth._request", side_effect=valid_auth_api) as request:
            app.run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.session_state["_test_auth_access_token"], NEW_ACCESS)
        self.assertEqual(app.session_state["_test_auth_refresh_token"], NEW_REFRESH)
        self.assertEqual(app.session_state["_test_work_user_id"], "synthetic-admin")
        self.assertTrue(any(r.label == "Moduł" for r in app.radio))
        self.assertTrue(any(
            c.args[1].endswith("grant_type=refresh_token") for c in request.call_args_list
            if len(c.args) >= 2
        ))

    def test_invalid_refresh_does_not_unlock_or_preserve_old_workspace(self):
        app = self._app()
        app.session_state["_preview_store"] = {"private": "data"}
        app.session_state["employees_df"] = pd.DataFrame({"OSOBA": ["SECRET"]})
        with patch("app_auth._request", return_value=(401, {})):
            app.run()
        self.assertFalse(list(app.exception))
        self.assertEqual(list(app.radio), [])
        self.assertEqual([item.label for item in app.text_input], ["E-mail", "Hasło"])
        for key in (*TOKEN_KEYS, "_preview_store", "employees_df"):
            self.assertNotIn(key, app.session_state)

    def test_logout_revokes_only_current_session_and_drops_tokens(self):
        app = self._app()
        app.session_state["_test_auth_expires_at"] = time.time() + 3600
        app.session_state["_test_auth_access_token"] = NEW_ACCESS

        def api(method, path, **kwargs):
            if path == "/auth/v1/user":
                return 200, {"id": "synthetic-admin", "email": "admin@example.invalid"}
            if path.startswith("/rest/v1/app_user_profiles?"):
                return 200, [{"user_id": "synthetic-admin", "role": "admin",
                              "enabled": True, "employee_id": None}]
            if path == "/auth/v1/logout?scope=local":
                return 204, {}
            return 400, {}

        with patch("app_auth._request", side_effect=api) as request:
            app.run()
            next(b for b in app.button if b.label == "Wyloguj").click().run()
        self.assertFalse(list(app.exception))
        self.assertTrue(any(call.args[1] == "/auth/v1/logout?scope=local"
                            for call in request.call_args_list))
        for key in TOKEN_KEYS:
            self.assertNotIn(key, app.session_state)
        self.assertEqual(list(app.radio), [])
        self.assertEqual([item.label for item in app.text_input], ["E-mail", "Hasło"])


if __name__ == "__main__":
    unittest.main()
