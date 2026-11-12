"""Fail-closed tests for the TEST monthly publishing preflight."""
import unittest
import pandas as pd

from monthly_publication import (
    PublicationValidationError,
    period_date,
    prepare_publication,
)


class TestMonthlyPublication(unittest.TestCase):
    def setUp(self):
        self.name = "TEST PRACOWNIK 01"
        self.uid = "11111111-1111-4111-8111-111111111111"
        self.archive = {
            "summary": pd.DataFrame([{
                "Pracownik": self.name,
                "Premia (zł)": 150.0,
                "ŁĄCZNA PREMIA / DODATKI (zł)": 200.0,
                "% Potrącenia": 0.0,
                "Dni przepracowane": 1,
                "Nadgodziny (zł)": 20.0,
                "Dodatek Wózek (zł)": 10.0,
                "Dodatek Palety (zł)": 15.0,
                "Premia Specjalna (zł)": 5.0,
            }]),
            "schedule": pd.DataFrame([{
                "OSOBA": self.name,
                "DATA": "02.11.2026",
                "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
                "NIEOBECNOŚĆ": "Brak",
                "FAKTYCZNIE WEJŚCIE": "08:00",
                "FAKTYCZNIE WYJŚCIE": "16:00",
            }]),
            "metrics": {
                "pcs": 100, "lines": 10, "weight": 500,
                "indicator": 0.05,
            },
        }
        self.profiles = [{
            "user_id": self.uid,
            "employee_id": self.name,
            "role": "employee",
            "enabled": True,
        }]

    def test_one_valid_month(self):
        period, kpis, rows = prepare_publication(
            "Listopad 2026", self.archive, self.profiles
        )
        self.assertEqual(period, "2026-11-01")
        self.assertEqual(kpis["pieces"], 100)
        self.assertEqual(kpis["positions"], 10)
        self.assertEqual(kpis["performance_pct"], "5.00")
        self.assertEqual(rows[0]["user_id"], self.uid)
        self.assertEqual(rows[0]["bonus_main_pln"], "150.00")
        self.assertEqual(rows[0]["bonus_additions_pln"], "50.00")
        self.assertEqual(rows[0]["bonus_final_pln"], "200.00")
        self.assertNotIn("positions", rows[0])

    def test_unknown_account_does_not_publish(self):
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, [])

    def test_disabled_or_director_account_is_rejected(self):
        for role, enabled in (("employee", False), ("director", True)):
            self.profiles[0].update(role=role, enabled=enabled)
            with self.assertRaises(PublicationValidationError):
                prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_duplicate_identity_is_rejected(self):
        self.profiles.append(dict(self.profiles[0]))
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_wrong_bonus_arithmetic_is_rejected(self):
        self.archive["summary"].loc[0, "Premia Specjalna (zł)"] = 500.0
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_missing_schedule_blocks_publication(self):
        self.archive["schedule"] = pd.DataFrame()
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_schedule_from_wrong_month_is_rejected(self):
        self.archive["schedule"].loc[0, "DATA"] = "02.12.2026"
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_attendance_exceeding_plan_is_rejected(self):
        self.archive["summary"].loc[0, "Dni przepracowane"] = 2
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_nan_or_negative_kpis_are_rejected(self):
        for invalid in (float("nan"), -1, None):
            self.archive["metrics"]["pcs"] = invalid
            with self.assertRaises(PublicationValidationError):
                prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_no_presence_without_actual_times(self):
        self.archive["schedule"].loc[0, "FAKTYCZNIE WYJŚCIE"] = ""
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_absence_is_not_attendance(self):
        self.archive["schedule"].loc[0, "NIEOBECNOŚĆ"] = "CHOROBOWE"
        self.archive["schedule"].loc[0, "FAKTYCZNIE WEJŚCIE"] = ""
        self.archive["schedule"].loc[0, "FAKTYCZNIE WYJŚCIE"] = ""
        self.archive["summary"].loc[0, "Dni przepracowane"] = 0
        period, _, rows = prepare_publication("Listopad 2026", self.archive, self.profiles)
        self.assertEqual((period, rows[0]["attended_days"]), ("2026-11-01", 0))

    def test_forged_worked_days_rejected(self):
        self.archive["summary"].loc[0, "Dni przepracowane"] = 0
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_unrecognized_month(self):
        with self.assertRaises(PublicationValidationError):
            period_date("Wrong 2026")


if __name__ == "__main__":
    unittest.main()
