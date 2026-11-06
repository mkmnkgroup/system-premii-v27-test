"""Static regression checks for the presentation-only redesign."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PremiumThemeTests(unittest.TestCase):
    def test_python_files_parse(self):
        for name in ("app_v2.py", "premium_theme.py"):
            with self.subTest(name=name):
                ast.parse((ROOT / name).read_text(encoding="utf-8"))

    def test_both_palettes_and_toggle_exist(self):
        theme = (ROOT / "premium_theme.py").read_text(encoding="utf-8")
        app = (ROOT / "app_v2.py").read_text(encoding="utf-8")
        self.assertIn('"Ciemny"', theme)
        self.assertIn('"Jasny"', theme)
        self.assertIn('st.segmented_control(', app)
        self.assertIn('key="premium_ui_mode"', app)
        self.assertIn('apply_theme(st.session_state.premium_ui_mode)', app)

    def test_theme_does_not_access_storage_or_payroll(self):
        source = (ROOT / "premium_theme.py").read_text(encoding="utf-8")
        for forbidden in ("db_storage", "psycopg", "calculate_payroll", "generate_schedule"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

