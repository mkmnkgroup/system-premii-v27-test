"""Offline end-to-end fictional monthly settlement.

No Supabase writes, no real employee accounts, and no employee notifications.
Exercises actual Excel imports, eligible weight matching, attendance, payroll,
archive snapshot, pre-publication checks, and both employee/admin PDF renderers.
"""
import ast
import io
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
import unittest

import pandas as pd
from openpyxl import Workbook
from pypdf import PdfReader

from bonus_analysis_cache import cached_daily_totals, cached_production_totals
from bonus_slip_pdf import generate_bonus_slip_pdf
from client_categories import CLIENT_CATEGORY_COLUMN
from monthly_publication import (
    PublicationValidationError, prepare_publication, snapshot_bonus_breakdowns,
)
from payslip_pdf import build_payslip_pdf
from production_import import (
    ARTICLE, BRAND, DATE, QTY, read_production, read_weights,
)

ROOT = Path(__file__).resolve().parents[1]
FIRST = "TEST PRACOWNIK 01"
SECOND = "TEST PRACOWNIK 02"
P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"


def _xlsx(headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def _actual_payroll_function():
    """Isolate the actual calculator, bypassing app login and network I/O."""
    nodes = ast.parse((ROOT / "app_v2.py").read_text(encoding="utf-8")).body
    func = next(
        node for node in nodes
        if isinstance(node, ast.FunctionDef) and node.name == "calculate_payroll"
    )
    normalizer = next(
        node for node in nodes
        if isinstance(node, ast.FunctionDef) and node.name == "normalize_name"
    )
    namespace = {
        "pd": pd,
        "st": SimpleNamespace(session_state=SimpleNamespace(
            ot_magazynier=25, ot_brygadzista=30, ot_kierownik=35,
            kierownik_bonus_multiplier=1.35, forklift_pool=600,
        )),
    }
    module = ast.fix_missing_locations(
        ast.Module(body=[normalizer, func], type_ignores=[])
    )
    exec(compile(module, "<isolated_actual_calculator>", "exec"), namespace)
    return namespace["calculate_payroll"]


def _schedule():
    return pd.DataFrame([
        {
            "OSOBA": FIRST, "DATA": "02.11.2026", "DZIEŃ TYGODNIA": "poniedziałek",
            "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "Brak",
            "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "18:00",
            "NADGODZINY (godz.)": 2.0,
        },
        {
            "OSOBA": FIRST, "DATA": "03.11.2026", "DZIEŃ TYGODNIA": "wtorek",
            "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "CHOROBOWE",
            "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": "",
            "NADGODZINY (godz.)": 0.0,
        },
        {
            "OSOBA": SECOND, "DATA": "02.11.2026", "DZIEŃ TYGODNIA": "poniedziałek",
            "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "Brak",
            "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "16:00",
            "NADGODZINY (godz.)": 0.0,
        },
        {
            "OSOBA": SECOND, "DATA": "03.11.2026", "DZIEŃ TYGODNIA": "wtorek",
            "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "Brak",
            "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "16:00",
            "NADGODZINY (godz.)": 0.0,
        },
    ])


class FullFictionalMonthTests(unittest.TestCase):
    def setUp(self):
        self.employees = pd.DataFrame([
            {"OSOBA": FIRST, "STANOWISKO": "MAGAZYNIER",
             "FUNKCJA": "SKANOWANIE", "UPRAWNIENIA UDT": True},
            {"OSOBA": SECOND, "STANOWISKO": "MAGAZYNIER",
             "FUNKCJA": "SKANOWANIE", "UPRAWNIENIA UDT": True},
        ])
        self.schedule = _schedule()
        self.prod_bytes = _xlsx(
            [CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE],
            [
                ["RETAIL", "Producent A", "A-1", 2, "2026-11-02"],
                ["RETAIL", "Producent B", "B-1", 3, "2026-11-03"],
                ["test", "Nieznany", "BRAK-WAGI", 1000, "2026-11-03"],
            ],
        )
        self.weights_bytes = _xlsx(
            ["Producent", "Artykuł", "Waga"],
            [["Producent A", "A-1", 1.5], ["Producent B", "B-1", 2.0]],
        )
        self.profiles = [
            {"employee_id": FIRST, "user_id": P1, "role": "employee", "enabled": True},
            {"employee_id": SECOND, "user_id": P2, "role": "employee", "enabled": True},
        ]

    def _run_month(self):
        production = read_production(self.prod_bytes)
        weights = read_weights(self.weights_bytes)
        exclusions = ("test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA")
        metrics = cached_production_totals(production, weights, exclusions)
        self.assertEqual(
            (metrics["positions"], metrics["pieces"], metrics["weight_kg"],
             metrics["excluded_positions"], metrics["missing_positions"]),
            (2, 5.0, 9.0, 1, 0),
        )
        days, bad_dates, wrong_month = cached_daily_totals(
            production, weights, exclusions, 2026, 11
        )
        self.assertEqual((bad_dates, wrong_month), (0, 0))
        self.assertAlmostEqual(sum(d["weight"] for d in days.values()), 9.0)

        # Production daily percentages, equal 1/3 weighting for position/piece/weight.
        work_shares = {
            day: ((info["pcs"] / metrics["pieces"] +
                   info["lines"] / metrics["positions"] +
                   info["weight"] / metrics["weight_kg"]) / 3.0) * 100.0
            for day, info in days.items()
        }
        self.assertAlmostEqual(sum(work_shares.values()), 100.0, places=8)
        forklift = pd.DataFrame([
            {"OSOBA": FIRST, "CZAS WÓZKA (godz.)": 5.0},
            {"OSOBA": SECOND, "CZAS WÓZKA (godz.)": 15.0},
        ])
        special = pd.DataFrame([{
            "Pracownik": FIRST, "Kwota netto premii": 80.0,
            "Powód przyznania premii": "Rozładunek specjalny",
            "Kto przyznał": "Kierownik testowy",
        }])
        calculate = _actual_payroll_function()
        summary, details = calculate(
            df_sched=self.schedule,
            employees_df=self.employees,
            max_bonus_per_emp=1000.0,
            forklift_hours_df=forklift,
            total_forklift_hours=20.0,
            pallet_pay_per_selected_emp=100.0,
            selected_pallet_emps=[FIRST, SECOND],
            daily_work_pct_map=work_shares,
            special_bonuses_df=special,
            include_absence_deduction=True,
            pallet_count=20,
            pallet_rate=10,
        )
        breakdowns = snapshot_bonus_breakdowns(summary, details)
        archive = {
            "summary": summary,
            "schedule": self.schedule.copy(),
            "bonus_breakdowns": breakdowns,
            "metrics": {
                "pcs": metrics["pieces"],
                "lines": metrics["positions"],
                "weight": metrics["weight_kg"],
                "indicator": 0.1,
            },
        }
        period, kpis, rows = prepare_publication(
            "Listopad 2026", archive, self.profiles
        )
        return period, kpis, rows, summary, details, archive, work_shares

    def test_calculation_to_published_slip_includes_all_components(self):
        period, kpis, rows, summary, details, _archive, shares = self._run_month()
        self.assertEqual(period, "2026-11-01")
        self.assertEqual(
            (kpis["positions"], kpis["pieces"], kpis["weight_kg"]), (2, 5, "9.00")
        )
        self.assertEqual([row["user_id"] for row in rows], [P1, P2])
        first, second = rows
        self.assertAlmostEqual(float(first["absence_reduction_pct"]), shares[3])
        self.assertEqual(first["planned_days"], 2)
        self.assertEqual(first["attended_days"], 1)
        self.assertEqual(second["attended_days"], 2)
        self.assertEqual(first["overtime_hours"], "2.00")
        self.assertEqual(first["overtime_pay_pln"], "50.00")
        self.assertEqual(first["bonus_breakdown"]["forklift_pay_pln"], "150.00")
        self.assertEqual(second["bonus_breakdown"]["forklift_pay_pln"], "450.00")
        self.assertEqual(first["bonus_breakdown"]["pallet_pay_pln"], "100.00")
        self.assertEqual(first["bonus_breakdown"]["special_bonuses"][0]["amount_pln"], "80.00")
        self.assertEqual(second["bonus_breakdown"]["special_bonuses"], [])

        for row in rows:
            parts = row["bonus_breakdown"]
            total_parts = (
                Decimal(row["bonus_main_pln"]) +
                Decimal(row["overtime_pay_pln"]) +
                Decimal(parts["forklift_pay_pln"]) +
                Decimal(parts["pallet_pay_pln"]) +
                sum((Decimal(i["amount_pln"]) for i in parts["special_bonuses"]), Decimal(0))
            )
            self.assertLessEqual(
                abs(total_parts - Decimal(row["bonus_final_pln"])), Decimal("0.01")
            )

        # Administrator PDF is generated from the same calculator row.
        admin_pdf = generate_bonus_slip_pdf(
            FIRST, "Listopad 2026", details[FIRST], absence_mode=True
        )
        self.assertTrue(admin_pdf.startswith(b"%PDF-"))
        admin_text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(admin_pdf)).pages
        )
        self.assertIn("Rozładunek specjalny", admin_text)

        # Employee PDF is generated from validated publication data, not
        # from an administrative or another employee's in-memory state.
        first_pdf = build_payslip_pdf(
            period, FIRST, {**first, "period": period}
        )
        pages = PdfReader(io.BytesIO(first_pdf)).pages
        self.assertEqual(len(pages), 2)
        employee_text = "\n".join(page.extract_text() for page in pages)
        self.assertIn(FIRST, employee_text)
        self.assertNotIn(SECOND, employee_text)
        self.assertIn("Rozładunek specjalny", employee_text)
        self.assertIn("Nadgodziny", employee_text)
        self.assertIn("150,00 zł", employee_text)
        self.assertIn("100,00 zł", employee_text)

    def test_missing_weights_block_calculation_before_payroll(self):
        production = read_production(self.prod_bytes)
        no_weights = read_weights(_xlsx(
            ["Producent", "Artykuł", "Waga"], [["Producent A", "A-1", 1.5]]
        ))
        summary = cached_production_totals(production, no_weights, ("test",))
        self.assertEqual(summary["missing_positions"], 1)
        self.assertIsNone(summary["weight_kg"])

    def test_unconfirmed_work_day_blocks_publication(self):
        _period, _kpis, _rows, _summary, _details, archive, _shares = self._run_month()
        archive["schedule"] = archive["schedule"].copy()
        archive["schedule"].loc[
            (archive["schedule"]["OSOBA"] == SECOND) &
            (archive["schedule"]["DATA"] == "03.11.2026"),
            "FAKTYCZNIE WYJŚCIE",
        ] = ""
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", archive, self.profiles)

    def test_tampered_special_payment_blocks_publication(self):
        _period, _kpis, _rows, _summary, _details, archive, _shares = self._run_month()
        archive["bonus_breakdowns"][FIRST]["special_bonuses"][0]["amount_pln"] = "500.00"
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", archive, self.profiles)


if __name__ == "__main__":
    unittest.main()
