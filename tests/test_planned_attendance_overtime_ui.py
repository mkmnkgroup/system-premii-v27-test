"""Synthetic tests for opt-in attendance assumptions and ergonomic overtime input."""
from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from attendance_drafts import build_attendance_payload, restore_attendance_payload
from planned_attendance import (
    BASIS_COLUMN, PLANNED_BASIS, MANUAL_BASIS,
    attendance_editor_column_order, fill_according_to_plan,
    reconcile_attendance_basis, reconcile_verified_absences,
)

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


def frame():
    return pd.DataFrame([
        {"OSOBA": "TEST PRACOWNIK 01", "DATA": "04.11.2025", "STANOWISKO": "MAGAZYNIER",
         "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "CZAS ZMIANY": "06:00-14:00",
         "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
         "NADGODZINY (godz.)": 2.0},
        {"OSOBA": "TEST PRACOWNIK 01", "DATA": "05.11.2025", "STANOWISKO": "MAGAZYNIER",
         "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "CZAS ZMIANY": "06:00-14:00",
         "NIEOBECNOŚĆ": "CHOROBOWE", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
         "NADGODZINY (godz.)": 0.0},
        {"OSOBA": "TEST PRACOWNIK 01", "DATA": "06.11.2025", "STANOWISKO": "MAGAZYNIER",
         "DZIEŃ PRACUJĄCY/WOLNY": "Wolny", "CZAS ZMIANY": "Wolne",
         "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
         "NADGODZINY (godz.)": 0.0},
        {"OSOBA": "TEST PRACOWNIK 01", "DATA": "07.11.2025", "STANOWISKO": "MAGAZYNIER",
         "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "CZAS ZMIANY": "08:00-17:00",
         "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "07:30", "FAKTYCZNIE WYJŚCIE": "16:15",
         "NADGODZINY (godz.)": 1.5},
        {"OSOBA": "TEST PRACOWNIK 01", "DATA": "08.11.2025", "STANOWISKO": "MAGAZYNIER",
         "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "CZAS ZMIANY": "08:00-16:00",
         "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "",
         "NADGODZINY (godz.)": 0.0},
    ])


class PlannedAttendanceTests(TestCase):
    def test_fill_only_unknown_days_and_preserve_overtime_and_absence(self):
        before = frame()
        after, stats = fill_according_to_plan(before, through=date(2025, 11, 30))
        self.assertEqual(stats["filled"], 1)
        self.assertEqual(stats["absences"], 1)
        self.assertEqual(stats["free"], 1)
        self.assertEqual(stats["existing"], 1)
        self.assertEqual(stats["partial"], 1)
        self.assertEqual((after.at[0, "FAKTYCZNIE WEJŚCIE"],
                          after.at[0, "FAKTYCZNIE WYJŚCIE"]), ("06:00", "14:00"))
        self.assertEqual(after.at[0, "NADGODZINY (godz.)"], 2.0)
        self.assertEqual(after.at[0, BASIS_COLUMN], PLANNED_BASIS)
        self.assertEqual(after.at[1, "NIEOBECNOŚĆ"], "CHOROBOWE")
        self.assertEqual(after.at[1, "FAKTYCZNIE WEJŚCIE"], "")
        self.assertEqual(after.at[3, "FAKTYCZNIE WEJŚCIE"], "07:30")
        self.assertEqual(after.at[4, "FAKTYCZNIE WYJŚCIE"], "")
        self.assertEqual(before.at[0, "FAKTYCZNIE WEJŚCIE"], "", "must not mutate input")

    def test_never_assume_future_or_bad_shift(self):
        df = frame()
        df.loc[0, "DATA"] = "26.11.2026"
        df.loc[0, "CZAS ZMIANY"] = "?"
        result, stats = fill_according_to_plan(df, through=date(2025, 11, 30))
        self.assertEqual(result.at[0, "FAKTYCZNIE WEJŚCIE"], "")
        self.assertEqual(stats["future"], 1)
        bad = frame()
        bad.at[0, "CZAS ZMIANY"] = "niewiadomo"
        _, stats2 = fill_according_to_plan(bad, through=date(2025, 11, 30))
        self.assertEqual(stats2["invalid_shift"], 1)
        with self.assertRaisesRegex(ValueError, "przyszłe"):
            fill_according_to_plan(frame(), through=date(2099, 11, 30))

    def test_reconcile_assumed_hours_after_manual_edit_and_new_absence(self):
        after, _ = fill_according_to_plan(frame(), through=date(2025, 11, 30))
        edited = after.copy()
        edited.at[0, "FAKTYCZNIE WYJŚCIE"] = "15:30"
        updated = reconcile_attendance_basis(edited)
        self.assertEqual(updated.at[0, BASIS_COLUMN], MANUAL_BASIS)
        absence = after.copy()
        absence.at[0, "NIEOBECNOŚĆ"] = "ZWOLNIENIE"
        revised = reconcile_verified_absences(after, absence)
        self.assertEqual(revised.at[0, "FAKTYCZNIE WEJŚCIE"], "")
        self.assertEqual(revised.at[0, "FAKTYCZNIE WYJŚCIE"], "")
        self.assertEqual(revised.at[0, "NADGODZINY (godz.)"], 2.0)

    def test_saved_draft_preserves_basis_and_overtime(self):
        with_plan, _ = fill_according_to_plan(frame(), through=date(2025, 11, 30))
        draft = build_attendance_payload(with_plan, 2025, 11)
        self.assertEqual(draft["entries"][0]["basis"], PLANNED_BASIS)
        restored = restore_attendance_payload(frame(), draft, 2025, 11)
        self.assertEqual(restored.at[0, BASIS_COLUMN], PLANNED_BASIS)
        self.assertEqual(restored.at[0, "NADGODZINY (godz.)"], 2.0)
        legacy = dict(draft)
        legacy["entries"] = [dict(e) for e in draft["entries"]]
        legacy["entries"][0].pop("basis")
        old = restore_attendance_payload(frame(), legacy, 2025, 11)
        self.assertEqual(old.at[0, BASIS_COLUMN], "")

    def test_overtime_worker_date_first_and_position_last(self):
        columns = attendance_editor_column_order(frame())
        self.assertEqual(columns[:3], ["NADGODZINY (godz.)", "OSOBA", "DATA"])
        self.assertEqual(columns[-1], "STANOWISKO")
        self.assertEqual(len(columns), len(set(columns)))

    def test_attendance_module_displays_opt_in_and_editor_order(self):
        with patch("app_auth.login_gate", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45).run()
            next(r for r in app.radio if r.label == "Moduł").set_value("Obecności i nadgodziny").run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any(b.label == "Uzupełnij obecności według harmonogramu"
                            for b in app.button))
        self.assertTrue(any(
            "Zweryfikowałem nieobecności" in c.label for c in app.checkbox
        ))
        self.assertTrue(any(BASIS_COLUMN in d.value.columns for d in app.data_editor))


if __name__ == "__main__":
    import unittest
    unittest.main()
