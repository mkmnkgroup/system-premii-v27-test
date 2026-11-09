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
