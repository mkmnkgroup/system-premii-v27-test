"""Regressions for the compact ERP workspace: left sidebar is navigation only.

All tests use fictitious users and do not access test Supabase credentials.
"""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app_v2.py")

class ErpWorkspaceTests(unittest.TestCase):
    def test_sidebar_never_owns_business_forms_or_account_actions(self):
        for filename in ("app_v2.py", "app_auth.py"):
            text = (ROOT / filename).read_text(encoding="utf-8")
            tree = ast.parse(text)
            prohibited = {
                "file_uploader", "number_input", "selectbox",
                "segmented_control", "button", "write", "checkbox",
                "data_editor", "form",
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    receiver = node.func.value
                    if (isinstance(receiver, ast.Attribute)
                            and isinstance(receiver.value, ast.Name)
                            and receiver.value.id == "st"
                            and receiver.attr == "sidebar"):
                        self.assertNotIn(
                            node.func.attr, prohibited,
                            f"{filename}:{node.lineno} has business input in the sidebar",
                        )
                if isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        ctxt = item.context_expr
                        self.assertFalse(
                            isinstance(ctxt, ast.Attribute)
                            and isinstance(ctxt.value, ast.Name)
                            and ctxt.value.id == "st"
                            and ctxt.attr == "sidebar",
                            f"{filename}:{node.lineno} owns a sidebar context",
                        )

    def test_main_workspace_has_no_large_brand_banner_or_test_warning(self):
        source = (ROOT / "app_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("hero()", source)
        self.assertNotIn('st.warning("WERSJA TESTOWA', source)
        self.assertIn('st.sidebar.markdown("**◈ System Premii 2.7**")', source)
        self.assertIn('st.sidebar.caption("TEST · tylko dane fikcyjne")', source)
        with patch("app_auth.login_gate", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45).run()
        self.assertEqual(list(app.exception), [])
        self.assertFalse(any('<section class="premium-hero"' in item.value for item in app.markdown))
        self.assertFalse(any("WERSJA TESTOWA" in item.value for item in app.warning))

    def test_month_and_year_are_in_workspace_and_module_navigation_survives(self):
        with patch("app_auth.login_gate", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any(w.label == "Miesiąc rozliczenia" for w in app.selectbox))
            self.assertTrue(any(w.label == "Rok" for w in app.number_input))
            self.assertEqual(app.session_state.premium_ui_mode, "Jasny")
            module = next(r for r in app.radio if r.label == "Moduł")
            # Streamlit AppTest exposes formatted labels, while radio values
            # remain the unchanged internal module names.
            for shown, module_name in zip(
                module.options,
                ["Pulpit", "Harmonogram", "Obecności i nadgodziny",
                 "Dodatki premiowe", "Rozliczenie premii", "Archiwum",
                 "Analizy", "Porównania", "Ustawienia"],
            ):
                self.assertTrue(shown.endswith(module_name), shown)
            module.set_value("Ustawienia").run()
            self.assertEqual(list(app.exception), [])
            module = next(r for r in app.radio if r.label == "Moduł")
            module.set_value("Harmonogram").run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any("Harmonogram na wybrany miesiąc" in h.value for h in app.markdown))

if __name__ == "__main__":
    unittest.main()
