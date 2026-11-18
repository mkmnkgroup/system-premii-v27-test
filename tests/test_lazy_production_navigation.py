"""Navigation regression: big production Excel is not parsed on unrelated pages.

Synthetic test data only. This uses a mocked uploader and AppTest, no DB writes.
"""
import io
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import BRAND, ARTICLE, DATE, QTY, read_production
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


class LazyProductionLoadTests(unittest.TestCase):
    @staticmethod
    def sample_upload():
        workbook = io.BytesIO()
        pd.DataFrame({
            CLIENT_CATEGORY_COLUMN: ["TEST-NEW-CATEGORY-ONLY-NAVIGATION", "test"],
            BRAND: ["SYNTHETIC", "SYNTHETIC"],
            ARTICLE: ["ONLY-NAV-001", "ONLY-NAV-002"],
            QTY: [1, 999],
            DATE: ["2026-11-06", "2026-11-07"],
        }).to_excel(workbook, index=False)
        workbook.name = "synthetic_navigation_input.xlsx"
        return workbook

    def test_switching_nonproduction_modules_skips_excel_parser(self):
        file = self.sample_upload()
        actual = st.file_uploader
        calls = []

        def upload(label, *args, **kwargs):
            if label == "Wgraj raport produkcji (Excel):":
                return file
            return actual(label, *args, **kwargs)

        def checked_read(bytes_data):
            calls.append(len(bytes_data))
            return read_production(bytes_data)

        with patch("app_auth.login_gate", return_value=None), patch.object(
            st, "file_uploader", side_effect=upload
        ), patch.object(
            type(st.sidebar), "file_uploader", lambda self, label, *a, **kw: upload(label, *a, **kw)
        ), patch("production_import.read_production", side_effect=checked_read):
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(calls, [], "Dashboard should not parse production Excel")
            for module in ("Harmonogram", "Analizy", "Archiwum", "Porównania"):
                next(r for r in app.radio if r.label == "Moduł").set_value(module).run()
                self.assertEqual(list(app.exception), [], module)
                self.assertEqual(calls, [], f"{module} should not parse production Excel")

            # Settings cannot import source files, so it has no source
            # categories until a report has been uploaded in settlement.
            next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(calls, [])
            self.assertFalse(any(
                "TEST-NEW-CATEGORY-ONLY-NAVIGATION" in entry.options
                for entry in app.multiselect
            ))

            # The report uploader appears only in settlement. Parsing is
            # lazy, and missing weights simply pause bonus calculations.
            next(r for r in app.radio if r.label == "Moduł").set_value("Rozliczenie premii").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(calls), 1)

            # Settings may reuse the cached month's report to offer optional
            # exclusion categories, without exposing its upload widget.
            next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(calls), 1)
            category_options = [
                option for entry in app.multiselect
                for option in entry.options
            ]
            self.assertIn("TEST-NEW-CATEGORY-ONLY-NAVIGATION", category_options)

            # Switching modules does not reparse the same imported bytes.
            next(r for r in app.radio if r.label == "Moduł").set_value("Pulpit").run()
            self.assertEqual(len(calls), 1)
            next(r for r in app.radio if r.label == "Moduł").set_value("Ustawienia").run()
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
