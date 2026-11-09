"""Startup regression checks for the hosted test Streamlit app."""
import ast
from pathlib import Path
import unittest

APP = Path(__file__).resolve().parents[1] / "app_v2.py"


class StartupImportTests(unittest.TestCase):
    def test_heavy_libraries_are_not_imported_on_startup(self):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        top_level_imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                top_level_imports.append(node.module)
        self.assertFalse(any(str(module).startswith(
            ("plotly", "google.generativeai", "PIL")
        ) for module in top_level_imports), top_level_imports)

    def test_plotly_only_loaded_in_reporting_functions(self):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        lazy_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                lazy_imports.extend(alias.name for alias in node.names)
        self.assertIn("plotly.express", lazy_imports)
        self.assertIn("google.generativeai", lazy_imports)
        self.assertIn("PIL.Image", lazy_imports)

    def test_auth_gateway_is_still_first(self):
        source = APP.read_text(encoding="utf-8")
        self.assertLess(source.index("login_gate()"), source.index("import holidays"))
        self.assertLess(source.index("login_gate()"), source.index("import pandas"))


if __name__ == "__main__":
    unittest.main()
