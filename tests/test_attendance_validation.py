"""Confirmed presence and incomplete working-day regression checks."""
import unittest
import pandas as pd
from attendance_validation import analyze_attendance, AttendanceValidationError


class AttendanceValidationTests(unittest.TestCase):
    def setUp(self):
        self.rows = pd.DataFrame([
            {"DATA": "02.11.2026", "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
             "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "16:00"},
            {"DATA": "03.11.2026", "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
             "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": ""},
            {"DATA": "04.11.2026", "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
             "NIEOBECNOŚĆ": "CHOROBOWE", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": ""},
            {"DATA": "08.11.2026", "DZIEŃ PRACUJĄCY/WOLNY": "Wolny",
             "NIEOBECNOŚĆ": "Brak", "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": ""}
        ])

    def test_confirmed_not_planned(self):
        result = analyze_attendance(self.rows)
        self.assertEqual((result["planned"], result["confirmed"], result["absent"], result["unconfirmed"]), (3, 1, 1, 1))
        self.assertEqual(result["absent_indices"], (2,))

    def test_publication_fails_on_incomplete_attendance(self):
        with self.assertRaises(AttendanceValidationError):
            analyze_attendance(self.rows, require_complete=True)

    def test_complete_with_absence_passes(self):
        self.rows.loc[1, "FAKTYCZNIE WEJŚCIE"] = "09:00"
        self.rows.loc[1, "FAKTYCZNIE WYJŚCIE"] = "17:00"
        self.assertEqual(analyze_attendance(self.rows, require_complete=True)["confirmed"], 2)

    def test_partial_time_is_not_confirmed(self):
        self.rows.loc[1, "FAKTYCZNIE WEJŚCIE"] = "10:00"
        self.assertEqual(analyze_attendance(self.rows)["unconfirmed"], 1)

    def test_absence_and_work_hours_conflict(self):
        self.rows.loc[2, "FAKTYCZNIE WEJŚCIE"] = "08:00"
        with self.assertRaises(AttendanceValidationError):
            analyze_attendance(self.rows)

    def test_off_day_activity_rejected_for_publication(self):
        self.rows.loc[1, "FAKTYCZNIE WEJŚCIE"] = "09:00"
        self.rows.loc[1, "FAKTYCZNIE WYJŚCIE"] = "17:00"
        self.rows.loc[3, "FAKTYCZNIE WEJŚCIE"] = "08:00"
        with self.assertRaises(AttendanceValidationError):
            analyze_attendance(self.rows, require_complete=True)

    def test_duplicate_date_rejected(self):
        self.rows.loc[1, "DATA"] = "02.11.2026"
        with self.assertRaises(AttendanceValidationError):
            analyze_attendance(self.rows)


if __name__ == "__main__":
    unittest.main()
