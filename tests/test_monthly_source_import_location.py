"""Month-scoped production + weight imports belong to settlement, not attendance.

All files and personnel here are synthetic. No database writes or publication.
"""
import io
from pathlib import Path
from unittest.mock import patch
import unittest

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from monthly_sources_ui import record_source, sources_for_period
from production_import import BRAND, ARTICLE, QTY, DATE
from client_categories import CLIENT_CATEGORY_COLUMN

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


def excel(data):
    result = io.BytesIO()
    pd.DataFrame(data).to_excel(result, index=False)
    result.name = "fake-upload.xlsx"
    return result


class MonthlySourceLocationTests(unittest.TestCase):
    def test_saved_sources_are_scoped_to_one_month_and_independent(self):
        state = {}
        november = "Listopad 2026"
        december = "Grudzień 2026"
        production = io.BytesIO(b"production-Nov")
        production.name = "production.xlsx"
        weights = io.BytesIO(b"weights-Nov")
        weights.name = "weights.xlsx"
        self.assertTrue(record_source(state, november, "report", production))
        self.assertTrue(record_source(state, november, "weights", weights))
        self.assertFalse(record_source(state, november, "weights", weights))
        p, w = sources_for_period(state, november)
        self.assertEqual(p.getvalue(), b"production-Nov")
        self.assertEqual(w.getvalue(), b"weights-Nov")
        self.assertEqual(sources_for_period(state, december), (None, None))
        p.read()
        self.assertEqual(sources_for_period(state, november)[0].getvalue(), b"production-Nov")

    def test_import_widgets_only_in_settlement_and_files_survive_navigation(self):
        fake_report = excel({
            CLIENT_CATEGORY_COLUMN: ["EXP_EU"], BRAND: ["DEMO"], ARTICLE: ["A1"],
            QTY: [10], DATE: ["2026-11-05"],
        })
        fake_weights = excel({
            "Producent": ["DEMO"], "Artykuł": ["A1"], "Waga": [2.0],
        })
        calls = []
        def upload(label, *args, **kwargs):
            calls.append(label)
            if label == "Wgraj raport produkcji (Excel):":
                return fake_report
            if label == "Aktualna baza wag (Excel .xlsx):":
                return fake_weights
            return None

        with patch("app_auth.login_gate", return_value=None), \
             patch.object(st, "file_uploader", side_effect=upload):
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            self.assertNotIn("Wgraj raport produkcji (Excel):", calls)
            self.assertNotIn("Aktualna baza wag (Excel .xlsx):", calls)
            menu = next(x for x in app.radio if x.label == "Moduł")
            menu.set_value("Obecności i nadgodziny").run()
            self.assertEqual(list(app.exception), [])
            self.assertNotIn("Wgraj raport produkcji (Excel):", calls)
            self.assertNotIn("Aktualna baza wag (Excel .xlsx):", calls)

            next(x for x in app.radio if x.label == "Moduł").set_value("Rozliczenie premii").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(calls.count("Wgraj raport produkcji (Excel):"), 1)
            self.assertEqual(calls.count("Aktualna baza wag (Excel .xlsx):"), 1)
            source = app.session_state["_test_monthly_sources"]["Listopad 2026"]
            self.assertEqual(source["report"]["name"], "fake-upload.xlsx")
            self.assertEqual(source["weights"]["name"], "fake-upload.xlsx")
            metrics = {m.label: m.value for m in app.metric}
            self.assertEqual(metrics["Pozycje"], "1")
            self.assertEqual(metrics["Sztuki"], "10")

            next(x for x in app.radio if x.label == "Moduł").set_value("Obecności i nadgodziny").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(calls.count("Wgraj raport produkcji (Excel):"), 1)
            self.assertEqual(calls.count("Aktualna baza wag (Excel .xlsx):"), 1)
            p, w = sources_for_period(app.session_state, "Listopad 2026")
            self.assertEqual(p.getvalue(), fake_report.getvalue())
            self.assertEqual(w.getvalue(), fake_weights.getvalue())

            next(x for x in app.selectbox if x.label == "Miesiąc rozliczenia").set_value("Grudzień").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(sources_for_period(app.session_state, "Grudzień 2026"), (None, None))
            self.assertIsNotNone(sources_for_period(app.session_state, "Listopad 2026")[0])


if __name__ == "__main__":
    unittest.main()
