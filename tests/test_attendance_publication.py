"""Tests for safe published attendance previews."""
from copy import deepcopy
import unittest

from attendance_publication import AttendancePublicationError, prepare_attendance_preview


class AttendancePublicationTests(unittest.TestCase):
    def setUp(self):
        self.id = "11111111-1111-4111-8111-111111111111"
        self.profiles = [{
            "user_id": self.id,
            "employee_id": "FIKCYJNY PRACOWNIK",
            "email": "fake@example.invalid",
            "role": "employee",
            "enabled": True,
        }]
        self.payload = {
            "period": "2026-11", "format_version": 1,
            "entries": [
                {"employee": "FIKCYJNY PRACOWNIK", "work_day": "2026-11-03",
                 "day_type": "Pracujący", "absence": "Brak",
                 "time_in": "08:00", "time_out": "16:00", "overtime_h": 0},
                {"employee": "FIKCYJNY PRACOWNIK", "work_day": "2026-11-04",
                 "day_type": "Pracujący", "absence": "Zwolnienie",
                 "time_in": "", "time_out": "", "overtime_h": 0},
                {"employee": "FIKCYJNY PRACOWNIK", "work_day": "2026-11-08",
                 "day_type": "Wolny", "absence": "Brak",
                 "time_in": "", "time_out": "", "overtime_h": 0},
                {"employee": "FIKCYJNY PRACOWNIK", "work_day": "2026-11-09",
                 "day_type": "Pracujący", "absence": "Brak",
                 "time_in": "", "time_out": "", "overtime_h": 0},
            ],
        }

    def preview(self):
        return prepare_attendance_preview("2026-11-01", self.payload, self.profiles)

    def test_count_not_confirmed_by_empty_time(self):
        rows, count, employees = self.preview()
        self.assertEqual(employees, 1)
        self.assertEqual(len(rows), 4)
        self.assertEqual(count, {
            "Potwierdzona obecność": 1, "Nieobecność": 1,
            "Wolne": 1, "Niepotwierdzony": 1,
        })
        self.assertEqual(rows[1]["Nieobecność"], "Zwolnienie")

    def test_unknown_account_rejected(self):
        self.profiles = []
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_director_and_disabled_rejected(self):
        for role, enabled in (("director", True), ("employee", False)):
            self.profiles[0]["role"] = role
            self.profiles[0]["enabled"] = enabled
            with self.assertRaises(AttendancePublicationError):
                self.preview()

    def test_duplicate_mapping_rejected(self):
        self.profiles.append(deepcopy(self.profiles[0]))
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_duplicate_date_rejected(self):
        self.payload["entries"][1]["work_day"] = "2026-11-03"
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_other_month_rejected(self):
        self.payload["entries"][0]["work_day"] = "2026-12-03"
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_absence_conflict_rejected(self):
        self.payload["entries"][1]["time_in"] = "10:00"
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_off_day_activity_rejected(self):
        self.payload["entries"][2]["overtime_h"] = 1.5
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_invalid_overtime_rejected(self):
        self.payload["entries"][0]["overtime_h"] = -1
        with self.assertRaises(AttendancePublicationError):
            self.preview()

    def test_partial_times_remain_unconfirmed(self):
        self.payload["entries"][0]["time_out"] = ""
        _, counts, _ = self.preview()
        self.assertEqual(counts.get("Potwierdzona obecność", 0), 0)
        self.assertEqual(counts["Niepotwierdzony"], 2)


if __name__ == "__main__":
    unittest.main()
