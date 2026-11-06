import io
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from preview_storage import load_item, save_item
from employee_excel import read_employees_excel, write_employees_excel
from production_import import BRAND, ARTICLE, QTY
from client_categories import CLIENT_CATEGORY_COLUMN

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


class PreviewTests(unittest.TestCase):
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
        for label in ("💾 Zapisz ustawienia w sesji testowej",
                      "💾 Zapisz rozliczenie w archiwum sesji testowej"):
            next(b for b in app.button if b.label == label).click().run()
            self.assertEqual(list(app.exception), [])
        self.assertIn("settings_v27", app.session_state["_preview_store"])
        self.assertIn("archive_v27", app.session_state["_preview_store"])
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
            metrics = {m.label: m.value for m in app.metric}
            self.assertEqual(metrics["Pozycje"], "1")
            self.assertEqual(metrics["Sztuki"], "10")
            self.assertTrue(any("20.00 kg" in s.value for s in app.success))
            next(b for b in app.button if b.label == "Zatwierdź import listy pracowników").click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(app.session_state.employees_df["OSOBA"].tolist(), ["TEST IMPORT 99"])
            roundtrip = read_employees_excel(write_employees_excel(app.session_state.employees_df))
            self.assertEqual(roundtrip["OSOBA"].tolist(), ["TEST IMPORT 99"])
