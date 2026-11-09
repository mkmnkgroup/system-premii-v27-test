import io
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from preview_storage import load_item, save_item
from employee_excel import read_employees_excel, write_employees_excel
from production_import import BRAND, ARTICLE, QTY, DATE
from client_categories import CLIENT_CATEGORY_COLUMN

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


class PreviewTests(unittest.TestCase):
    def setUp(self):
        # Exercise the legacy calculator independently of the Auth boundary.
        gate = patch("app_auth.login_gate", return_value=None)
        gate.start()
        self.addCleanup(gate.stop)

    def test_session_isolation_and_copy(self):
        first, second = {}, {}
        original = {"summary": pd.DataFrame({"Premia": [123.0]})}
        save_item(first, "archive", original)
        original["summary"].iloc[0, 0] = 0
        self.assertEqual(load_item(second, "archive"), {})
        loaded = load_item(first, "archive")
        self.assertEqual(loaded["summary"].iloc[0, 0], 123)
        loaded["summary"].iloc[0, 0] = 999
        self.assertEqual(load_item(first, "archive")["summary"].iloc[0, 0], 123)

    def test_start_save_and_excel_roundtrip(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        self.assertEqual(list(app.exception), [])
        roster = app.session_state.employees_df
        exported = write_employees_excel(roster)
        imported = read_employees_excel(exported)
        pd.testing.assert_frame_equal(imported, roster)
        next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
        settings_button = next(b for b in app.button if b.label == "💾 Zapisz ustawienia w sesji testowej")
        settings_button.click().run()
        self.assertEqual(list(app.exception), [])
        self.assertIn("settings_v27", app.session_state["_preview_store"])
        # Archive is deliberately unavailable until production is validated and calculated.
        self.assertNotIn("archive_v27", app.session_state["_preview_store"])
        self.assertFalse(AppTest.from_file(APP, default_timeout=45).run().session_state.history_v2)

    def test_uploaded_production_exclusions_and_excel_import(self):
        def excel(frame):
            buffer = io.BytesIO()
            frame.to_excel(buffer, index=False, sheet_name="Pracownicy")
            buffer.name = "fictional.xlsx"
            return buffer

        production = excel(pd.DataFrame({
            CLIENT_CATEGORY_COLUMN: ["EXP_EU", "test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA"],
            BRAND: ["DEMO"] * 6, ARTICLE: ["A1"] * 6, QTY: [10, 999, 999, 999, 999, 999],
            DATE: ["2026-11-05"] * 6,
        }))
        weights = excel(pd.DataFrame({"Producent": ["DEMO"], "Artykuł": ["A1"], "Waga": [2]}))
        roster = excel(pd.DataFrame([{
            "OSOBA": "TEST IMPORT 99", "GRUPA": "GRUPA 1", "SYSTEM": "PONIEDZIAŁEK-PIĄTEK",
            "STANOWISKO": "MAGAZYNIER", "FUNKCJA": "1 SKANOWANIE", "UPRAWNIENIA UDT": False,
        }]))
        original = st.file_uploader

        def upload(label, *args, **kwargs):
            if label == "Wgraj raport produkcji (Excel):":
                return production
            if label == "Aktualna baza wag (Excel .xlsx):":
                return weights
            if label == "📥 Importuj pracowników z Excel (.xlsx)":
                roster.seek(0)
                return roster
            return original(label, *args, **kwargs)

        with patch.object(st, "file_uploader", side_effect=upload), patch.object(
                type(st.sidebar), "file_uploader", lambda self, label, *a, **kw: upload(label, *a, **kw)):
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            next(r for r in app.radio if r.label == "Moduł").set_value("Produkcja i premie").run()
            metrics = {m.label: m.value for m in app.metric}
            self.assertEqual(metrics["Pozycje"], "1")
            self.assertEqual(metrics["Sztuki"], "10")
            self.assertTrue(any("20.00 kg" in s.value for s in app.success))
            next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
            next(b for b in app.button if b.label == "Zatwierdź import listy pracowników").click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(app.session_state.employees_df["OSOBA"].tolist(), ["TEST IMPORT 99"])
            roundtrip = read_employees_excel(write_employees_excel(app.session_state.employees_df))
            self.assertEqual(roundtrip["OSOBA"].tolist(), ["TEST IMPORT 99"])

class AuthEntrypointTests(unittest.TestCase):
    def test_anonymous_user_sees_login_without_payroll(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([field.label for field in app.text_input], ["E-mail", "Hasło"])
        self.assertTrue(any(button.label == "Zaloguj się" for button in app.button))
        self.assertEqual(list(app.radio), [])
        self.assertEqual(list(app.dataframe), [])
        self.assertNotIn("employees_df", app.session_state)
        self.assertNotIn("history_v2", app.session_state)

class PasswordRecoveryTests(unittest.TestCase):
    def test_missing_link_cannot_show_password_form(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_recovery_open"] = True
        with patch("app_auth._request") as request:
            app.run()
            request.assert_not_called()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([f.label for f in app.text_input], ["Link z wiadomości e-mail"])
        self.assertEqual(list(app.radio), [])

    def test_invalid_link_cannot_update_password(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_recovery_open"] = True
        app.session_state["_test_recovery_hash"] = "invalid-test-link"
        with patch("app_auth._request", return_value=(400, {})) as request:
            app.run()
            next(b for b in app.button if b.label == "Potwierdź link odzyskiwania").click().run()
            request.assert_called_once_with("POST", "/auth/v1/verify", data={
                "token_hash": "invalid-test-link", "type": "recovery"})
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.text_input), [])
        self.assertNotIn("_test_recovery_token", app.session_state)

    def test_expired_recovery_session_is_rejected(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_recovery_open"] = True
        app.session_state["_test_recovery_token"] = "expired-test-session"
        with patch("app_auth._request", return_value=(401, {})) as request:
            app.run()
            request.assert_called_once_with("GET", "/auth/v1/user", token="expired-test-session")
        self.assertEqual(list(app.text_input), [])
        self.assertNotIn("_test_recovery_token", app.session_state)

    def test_verified_recovery_updates_then_requires_login(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_recovery_open"] = True
        app.session_state["_test_recovery_hash"] = "synthetic-test-hash"
        def response(method, path, **kwargs):
            if path == "/auth/v1/verify":
                return 200, {"access_token": "synthetic-recovery-session"}
            if path == "/auth/v1/user":
                return 200, {"id": "synthetic-test-user"}
            return 204, {}
        with patch("app_auth._request", side_effect=response) as request:
            app.run()
            next(b for b in app.button if b.label == "Potwierdź link odzyskiwania").click().run()
            self.assertEqual([f.label for f in app.text_input], ["Nowe hasło", "Powtórz nowe hasło"])
            self.assertNotIn("_test_auth_access_token", app.session_state)
            app.text_input[0].set_value("Synthetic-test-only-123!")
            app.text_input[1].set_value("Synthetic-test-only-123!")
            next(b for b in app.button if b.label == "Zapisz nowe hasło").click().run()
            request.assert_any_call("PUT", "/auth/v1/user", token="synthetic-recovery-session",
                                    data={"password": "Synthetic-test-only-123!"})
            request.assert_any_call("POST", "/auth/v1/logout", token="synthetic-recovery-session")
        self.assertEqual(list(app.exception), [])
        self.assertNotIn("_test_recovery_token", app.session_state)
        self.assertEqual([f.label for f in app.text_input], ["E-mail", "Hasło"])

    def test_default_email_callback_requires_server_verification(self):
        app = AppTest.from_file(APP, default_timeout=45)
        callback = {"type": "recovery", "access_token": "synthetic-callback-session", "transfer_id": "test-transfer"}
        with patch("app_auth._recovery_callback", return_value=callback), patch(
                "app_auth._request", return_value=(401, {})) as request:
            app.run()
            request.assert_called_once_with("GET", "/auth/v1/user", token="synthetic-callback-session")
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.text_input), [])
        self.assertNotIn("_test_recovery_token", app.session_state)
        self.assertNotIn("_test_auth_access_token", app.session_state)

class RecoveryFrontendTests(unittest.TestCase):
    def test_ready_handshake_and_single_callback_transfer(self):
        import subprocess
        frontend = Path(__file__).resolve().parents[1] / "recovery_component" / "index.html"
        script = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const source = fs.readFileSync(process.argv[1], "utf8").split("<script>")[1].split("</script>")[0];
const messages = [];
let listener;
let replaced;
const parent = {postMessage: message => messages.push(message)};
const location = {origin: "https://system-premii-v27-test.streamlit.app", pathname: "/", search: "", hash: ""};
const root = {location, history: {replaceState: (_, __, url) => {replaced = url; location.hash = "";}}};
const window = {parent, top: root, addEventListener: (_, callback) => {listener = callback;}};
vm.runInNewContext(source, {window, URLSearchParams, crypto: require("node:crypto").webcrypto});
assert.equal(messages[0].type, "streamlit:componentReady");
assert.equal(messages[0].apiVersion, 1);
listener({source: {}, data: {type: "streamlit:render"}});
assert.equal(messages.length, 1);
listener({source: parent, data: {type: "streamlit:render"}});
assert.equal(messages[1].type, "streamlit:setFrameHeight");
assert.equal(messages.filter(m => m.type === "streamlit:setComponentValue").length, 0);
location.hash = "#type=recovery&access_token=synthetic-frontend-session";
listener({source: parent, data: {type: "streamlit:render"}});
const callbacks = messages.filter(m => m.type === "streamlit:setComponentValue");
assert.equal(callbacks.length, 1);
assert.equal(callbacks[0].value.type, "recovery");
assert.equal(callbacks[0].value.access_token, "synthetic-frontend-session");
assert.equal(replaced, "/");
assert.equal(location.hash, "");
listener({source: parent, data: {type: "streamlit:render"}});
assert.equal(messages.filter(m => m.type === "streamlit:setComponentValue").length, 1);
'''
        result = subprocess.run(["node", "-e", script, str(frontend)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

class AuthenticatedWorkspaceTests(unittest.TestCase):
    def response(self, role="admin", enabled=True, user_id="synthetic-admin"):
        def api(method, path, **kwargs):
            if method == "GET" and path == "/auth/v1/user":
                return 200, {"id": user_id, "email": "admin@example.invalid"}
            if method == "GET" and path.startswith("/rest/v1/app_user_profiles?"):
                return 200, [{"user_id": user_id, "role": role, "enabled": enabled, "employee_id": None}]
            return 204, {}
        return api

    def authenticated_app(self):
        app = AppTest.from_file(APP, default_timeout=45)
        app.session_state["_test_auth_access_token"] = "synthetic-test-access"
        return app

    def test_verified_admin_reaches_workspace_and_employee_settings(self):
        app = self.authenticated_app()
        with patch("app_auth._request", side_effect=self.response()):
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any(r.label == "Moduł" for r in app.radio))
            next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.session_state.employees_df), 3)
            self.assertTrue(any("Zespół i Pracownicy" in h.value for h in app.subheader))

    def test_non_admin_roles_cannot_reach_workspace(self):
        for role in ("employee", "manager", "director"):
            with self.subTest(role=role):
                app = self.authenticated_app()
                with patch("app_auth._request", side_effect=self.response(role=role)):
                    app.run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(list(app.radio), [])
                self.assertNotIn("employees_df", app.session_state)
                self.assertNotIn("history_v2", app.session_state)

    def test_logout_clears_auth_and_all_workspace_data(self):
        app = self.authenticated_app()
        with patch("app_auth._request", side_effect=self.response()):
            app.run()
            app.session_state["_preview_store"] = {"private-test": "old-value"}
            next(b for b in app.button if b.label == "Wyloguj").click().run()
        self.assertEqual(list(app.exception), [])
        for key in ("_test_auth_access_token", "_test_work_user_id", "_preview_store", "employees_df", "history_v2"):
            self.assertNotIn(key, app.session_state)
        self.assertEqual([f.label for f in app.text_input], ["E-mail", "Hasło"])

    def test_identity_switch_discards_previous_workspace(self):
        app = self.authenticated_app()
        app.session_state["_test_work_user_id"] = "previous-user"
        app.session_state["_preview_store"] = {"private-test": "previous-user-data"}
        app.session_state["employees_df"] = pd.DataFrame({"OSOBA": ["PREVIOUS USER EMPLOYEE"]})
        with patch("app_auth._request", side_effect=self.response()):
            app.run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state["_test_work_user_id"], "synthetic-admin")
        self.assertNotIn("_preview_store", app.session_state)
        self.assertNotIn("PREVIOUS USER EMPLOYEE", app.session_state.employees_df["OSOBA"].tolist())

    def test_expired_token_and_disabled_profile_clear_workspace(self):
        for result in (lambda *a, **kw: (401, {}), self.response(enabled=False)):
            app = self.authenticated_app()
            app.session_state["employees_df"] = pd.DataFrame({"OSOBA": ["PRIVATE TEST"]})
            app.session_state["_preview_store"] = {"private-test": "old-value"}
            with patch("app_auth._request", side_effect=result):
                app.run()
            self.assertEqual(list(app.exception), [])
            self.assertNotIn("_test_auth_access_token", app.session_state)
            self.assertNotIn("employees_df", app.session_state)
            self.assertNotIn("_preview_store", app.session_state)
            self.assertEqual(list(app.radio), [])
