"""Regressions for compact help icons and expanded optional instructions.

All interface tests use a mocked admin login and fictional in-session data.
"""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from workflow_help import (
    MODULE_HELP, BONUS_HELP, SOURCES_HELP, DRAFT_HELP,
    SCHEDULE_DRAFT_HELP, ATTENDANCE_DRAFT_HELP, ARCHIVE_DRAFT_HELP,
)

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app_v2.py")


class ContextHelpTests(TestCase):
    def test_each_module_has_detailed_on_demand_help(self):
        self.assertEqual(set(MODULE_HELP), {
            "schedule", "attendance", "bonuses", "settlement",
            "archive", "analytics", "comparisons", "settings",
        })
        for section, text in MODULE_HELP.items():
            self.assertGreater(len(text), 330, section)
            self.assertIn("**", text, section)
        for name, text in BONUS_HELP.items():
            self.assertGreater(len(text), 190, name)
        for item in (SOURCES_HELP, DRAFT_HELP, SCHEDULE_DRAFT_HELP,
                     ATTENDANCE_DRAFT_HELP, ARCHIVE_DRAFT_HELP):
            self.assertGreater(len(item), 240)

    def test_legacy_etap_captions_and_large_advice_are_not_always_visible(self):
        source = (ROOT / "app_v2.py").read_text(encoding="utf-8")
        self.assertNotIn('st.caption("ETAP 01', source)
        self.assertNotIn('st.caption("ETAP 02', source)
        self.assertNotIn('st.caption("ETAP 03', source)
        self.assertIn('help_heading(\n      "Dodatki do premii"', source)
        self.assertIn('MODULE_HELP["bonuses"]', source)
        helper = (ROOT / "help_ui.py").read_text(encoding="utf-8")
        self.assertIn("st.popover(label", helper)

    def test_main_modules_render_without_help_icon_errors(self):
        with patch("app_auth.login_gate", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            radio = next(r for r in app.radio if r.label == "Moduł")
            for module in ("Harmonogram", "Obecności i nadgodziny",
                           "Dodatki premiowe", "Ustawienia", "Archiwum",
                           "Rozliczenie premii"):
                radio.set_value(module).run()
                self.assertEqual(
                    list(app.exception), [], "Failed to render " + module
                )
                radio = next(r for r in app.radio if r.label == "Moduł")


if __name__ == "__main__":
    import unittest
    unittest.main()
