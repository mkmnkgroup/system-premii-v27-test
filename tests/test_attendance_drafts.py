"""Tests for persistent, private test attendance drafts."""
import unittest

import pandas as pd

from attendance_drafts import (
    AttendanceDraftError, attendance_summary, build_attendance_payload,
    restore_attendance_payload,
)


class AttendanceDraftTests(unittest.TestCase):
    def setUp(self):
        self.schedule = pd.DataFrame([
            {
                "OSOBA": "FIKCYJNY PRACOWNIK 01", "DATA": "02.11.2026",
                "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "Brak",
                "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
                "NADGODZINY (godz.)": 0.0,
            },
            {
                "OSOBA": "FIKCYJNY PRACOWNIK 01", "DATA": "03.11.2026",
                "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "CHOROBOWE",
                "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
                "NADGODZINY (godz.)": 0.0,
            },
            {
                "OSOBA": "FIKCYJNY PRACOWNIK 01", "DATA": "08.11.2026",
                "DZIEŃ PRACUJĄCY/WOLNY": "Wolny", "NIEOBECNOŚĆ": "Brak",
                "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
                "NADGODZINY (godz.)": 0.0,
            },
        ])

    def test_empty_times_are_unconfirmed_not_attendance(self):
        stats = attendance_summary(build_attendance_payload(self.schedule, 2026, 11))
        self.assertEqual(stats, {
            "planned": 2, "confirmed": 0, "absent_entries": 1, "unconfirmed": 1,
        })

    def test_restoring_keeps_actual_hours_and_absences(self):
        self.schedule.loc[0, "FAKTYCZNIE WEJŚCIE"] = "08:00"
        self.schedule.loc[0, "FAKTYCZNIE WYJŚCIE"] = "16:00"
        self.schedule.loc[0, "NADGODZINY (godz.)"] = 1.5
        payload = build_attendance_payload(self.schedule, 2026, 11)
        replacement = self.schedule.copy()
        replacement.loc[0, "FAKTYCZNIE WEJŚCIE"] = ""
        replacement.loc[0, "FAKTYCZNIE WYJŚCIE"] = ""
        restored = restore_attendance_payload(replacement, payload, 2026, 11)
        self.assertEqual(restored.loc[0, "FAKTYCZNIE WEJŚCIE"], "08:00")
        self.assertEqual(restored.loc[0, "FAKTYCZNIE WYJŚCIE"], "16:00")
        self.assertEqual(restored.loc[0, "NADGODZINY (godz.)"], 1.5)
        self.assertEqual(restored.loc[1, "NIEOBECNOŚĆ"], "CHOROBOWE")
        self.assertEqual(attendance_summary(payload)["confirmed"], 1)

    def test_month_mismatch_is_rejected(self):
        self.schedule.loc[0, "DATA"] = "02.12.2026"
        with self.assertRaises(AttendanceDraftError):
            build_attendance_payload(self.schedule, 2026, 11)

    def test_duplicate_employee_date_rejected(self):
        self.schedule.loc[1, "DATA"] = "02.11.2026"
        with self.assertRaises(AttendanceDraftError):
            build_attendance_payload(self.schedule, 2026, 11)

    def test_invalid_time_and_hours_rejected(self):
        self.schedule.loc[0, "FAKTYCZNIE WEJŚCIE"] = "25:62"
        with self.assertRaises(AttendanceDraftError):
            build_attendance_payload(self.schedule, 2026, 11)
        self.schedule.loc[0, "FAKTYCZNIE WEJŚCIE"] = "08:00"
        self.schedule.loc[0, "NADGODZINY (godz.)"] = -1
        with self.assertRaises(AttendanceDraftError):
            build_attendance_payload(self.schedule, 2026, 11)

    def test_changed_schedule_is_not_overwritten(self):
        payload = build_attendance_payload(self.schedule, 2026, 11)
        renamed = self.schedule.copy()
        renamed.loc[0, "OSOBA"] = "INNY PRACOWNIK"
        with self.assertRaises(AttendanceDraftError):
            restore_attendance_payload(renamed, payload, 2026, 11)
        shortened = self.schedule.iloc[:-1].copy()
        with self.assertRaises(AttendanceDraftError):
            restore_attendance_payload(shortened, payload, 2026, 11)

    def test_corrupt_payload_does_not_modify_original(self):
        payload = build_attendance_payload(self.schedule, 2026, 11)
        payload["entries"][0]["work_day"] = "2030-11-01"
        original = self.schedule.copy(deep=True)
        with self.assertRaises(AttendanceDraftError):
            restore_attendance_payload(self.schedule, payload, 2026, 11)
        pd.testing.assert_frame_equal(self.schedule, original)

    def test_missing_actual_hours_does_not_infer_presence(self):
        self.schedule.loc[0, "FAKTYCZNIE WEJŚCIE"] = "08:00"
        payload = build_attendance_payload(self.schedule, 2026, 11)
        self.assertEqual(attendance_summary(payload)["confirmed"], 0)


if __name__ == "__main__":
    unittest.main()
