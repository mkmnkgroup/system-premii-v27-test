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

    def test_overtime_hours_and_payment_survive_publication_preflight(self):
        self.archive["summary"]["Nadgodziny (godz.)"] = 0.8
        self.archive["schedule"]["NADGODZINY (godz.)"] = 0.8
        _, _, rows = prepare_publication("Listopad 2026", self.archive, self.profiles)
        self.assertEqual(rows[0]["overtime_hours"], "0.80")
        self.assertEqual(rows[0]["overtime_pay_pln"], "20.00")
        self.assertEqual(rows[0]["bonus_final_pln"], "200.00")

    def test_conflicting_overtime_is_rejected(self):
        self.archive["summary"]["Nadgodziny (godz.)"] = 2
        self.archive["schedule"]["NADGODZINY (godz.)"] = 1
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def _add_complete_breakdown(self):
        self.archive["summary"]["Nadgodziny (godz.)"] = 0.8
        self.archive["schedule"]["NADGODZINY (godz.)"] = 0.8
        return {
            self.name: {
                "base_bonus_pln": "150.00",
                "overtime_rate_pln": "25.00",
                "forklift_pay_pln": "10.00",
                "forklift_hours": "2.00",
                "forklift_team_hours": "10.00",
                "forklift_pool_pln": "50.00",
                "pallet_pay_pln": "15.00",
                "pallet_count": "30.00",
                "pallet_rate_pln": "1.00",
                "pallet_recipients": 2,
                "special_bonuses": [
                    {"amount_pln": "5.00", "reason": "Zadanie testowe",
                     "approved_by": "Kierownik testowy"}
                ],
            }
        }

    def test_publishes_detailed_components_without_double_counting(self):
        self.archive["bonus_breakdowns"] = self._add_complete_breakdown()
        _, _, rows = prepare_publication(
            "Listopad 2026", self.archive, self.profiles
        )
        self.assertEqual(rows[0]["bonus_base_pln"], "150.00")
        self.assertEqual(rows[0]["bonus_breakdown"]["pallet_pay_pln"], "15.00")
        self.assertEqual(rows[0]["bonus_breakdown"]["special_bonuses"][0]["reason"],
                         "Zadanie testowe")
        self.assertEqual(rows[0]["bonus_additions_pln"], "50.00")
        self.assertEqual(rows[0]["bonus_final_pln"], "200.00")

    def test_rejects_mismatched_or_missing_breakdown(self):
        breakdowns = self._add_complete_breakdown()
        breakdowns[self.name]["pallet_pay_pln"] = "17.00"
        self.archive["bonus_breakdowns"] = breakdowns
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)
        self.archive["bonus_breakdowns"] = {}
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_rejects_breakdown_with_unknown_employee(self):
        breakdowns = self._add_complete_breakdown()
        breakdowns["OBCY PRACOWNIK"] = dict(breakdowns[self.name])
        self.archive["bonus_breakdowns"] = breakdowns
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", self.archive, self.profiles)

    def test_snapshot_validates_calculator_components(self):
        from monthly_publication import snapshot_bonus_breakdowns
        summary = self.archive["summary"].copy()
        summary["Nadgodziny (godz.)"] = 0.8
        details = {
            self.name: {
                "base_emp_bonus": 150,
                "calculated_bonus": 150,
                "ot_rate": 25,
                "emp_forklift_hours": 2,
                "total_forklift_hours": 10,
                "forklift_pool": 50,
                "forklift_pay": 10,
                "pallet_pay": 15,
                "pallet_count": 30,
                "pallet_rate": 1,
                "pallet_recipients": 2,
                "spec_bonus_items": [
                    {"amount": 5, "reason": "Zadanie testowe",
                     "approved_by": "Kierownik testowy"}
                ],
            }
        }
        result = snapshot_bonus_breakdowns(summary, details)
        self.assertEqual(result[self.name]["base_bonus_pln"], "150.00")
        self.assertEqual(result[self.name]["special_bonuses"][0]["amount_pln"], "5.00")
        details[self.name]["pallet_pay"] = 16
        with self.assertRaises(PublicationValidationError):
            snapshot_bonus_breakdowns(summary, details)

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
