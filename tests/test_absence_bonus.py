"""Regression tests for optional absence deductions (fictional employees)."""
import ast
import pathlib
import types
import unittest

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]


def payroll_function():
    source = (ROOT / "app_v2.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    func = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                and node.name == "calculate_payroll")
    isolated = ast.Module(body=[func], type_ignores=[])
    ns = {
        "pd": pd,
        "normalize_name": lambda name: " ".join(sorted(str(name).upper().split())),
        "st": types.SimpleNamespace(session_state=types.SimpleNamespace(
            ot_magazynier=25, ot_brygadzista=30, ot_kierownik=35,
            kierownik_bonus_multiplier=1.35, forklift_pool=600)),
    }
    exec(compile(ast.fix_missing_locations(isolated), "<payroll>", "exec"), ns)
    return ns["calculate_payroll"]


class AbsenceBonusTests(unittest.TestCase):
    def setUp(self):
        self.calculate = payroll_function()
        self.employees = pd.DataFrame([{
            "OSOBA": "TEST PRACOWNIK", "STANOWISKO": "MAGAZYNIER",
            "FUNKCJA": "SKANOWANIE",
        }])
        self.schedule = pd.DataFrame([
            {"DATA": f"0{day}.11.2026", "OSOBA": "TEST PRACOWNIK",
             "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
             "NIEOBECNOŚĆ": "CHOROBOWE" if day in (1, 3) else "Brak",
             "NADGODZINY (godz.)": 0, "DZIEŃ TYGODNIA": "test"}
            for day in range(1, 5)
        ])
        self.shares = {1: 12.0, 2: 30.0, 3: 18.0, 4: 40.0}

    def run_case(self, enabled, shares=None):
        result, details = self.calculate(
            self.schedule, self.employees, 1000.0,
            pd.DataFrame([{"OSOBA": "TEST PRACOWNIK",
                           "CZAS WÓZKA (godz.)": 0.0}]),
            0.0, 0.0, [], self.shares if shares is None else shares,
            pd.DataFrame(), include_absence_deduction=enabled)
        return result.iloc[0]

    def test_default_ignores_absences(self):
        result = self.run_case(False)
        self.assertAlmostEqual(result["Premia (zł)"], 1000)
        self.assertAlmostEqual(result["% Potrącenia"], 0)

    def test_deduction_uses_workload_not_attendance_ratio(self):
        result = self.run_case(True)
        self.assertAlmostEqual(result["% Potrącenia"], 30)
        self.assertAlmostEqual(result["Premia (zł)"], 700)

    def test_no_absences_no_deduction(self):
        self.schedule["NIEOBECNOŚĆ"] = "Brak"
        self.assertAlmostEqual(self.run_case(True)["Premia (zł)"], 1000)

    def test_absence_on_day_off_is_not_deducted(self):
        self.schedule.loc[0, "DZIEŃ PRACUJĄCY/WOLNY"] = "Wolny"
        result = self.run_case(True)
        self.assertAlmostEqual(result["% Potrącenia"], 18)

    def test_deduction_clamped_to_100_percent(self):
        result = self.run_case(True, {1: 90, 3: 90})
        self.assertAlmostEqual(result["Premia (zł)"], 0)
        self.assertAlmostEqual(result["% Potrącenia"], 100)


if __name__ == "__main__":
    unittest.main()

