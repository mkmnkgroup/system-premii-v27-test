"""Tests for the administrator PDF generator and cached bonus computations."""
import io
import unittest
from pathlib import Path

import pandas as pd

from bonus_slip_pdf import (
    BOLD_FONT_PATHS, FONT_PATHS, generate_bonus_slip_pdf,
)
from bonus_analysis_cache import cached_daily_totals, cached_production_totals
from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import ARTICLE, BRAND, DATE, QTY


class AdminBonusSlipTests(unittest.TestCase):
    def test_pdf_uses_bundled_fonts_not_machine_dependent_paths(self):
        self.assertTrue(Path(FONT_PATHS[0]).is_file())
        self.assertTrue(Path(BOLD_FONT_PATHS[0]).is_file())

    def test_admin_pdf_generates_with_polish_characters_and_real_components(self):
        from pypdf import PdfReader
        details = {
            "position": "MAGAZYNIER",
            "base_emp_bonus": 1000,
            "calculated_bonus": 900,
            "deduction_pct": 10,
            "scheduled_days": 22,
            "days_worked": 20,
            "absent_days": 2,
            "total_ot": 2,
            "ot_rate": 25,
            "ot_pay": 50,
            "emp_forklift_hours": 5,
            "total_forklift_hours": 20,
            "emp_forklift_pct": 25,
            "forklift_pool": 160,
            "forklift_pay": 40,
            "pallet_count": 20,
            "pallet_rate": 10,
            "pallet_recipients": 2,
            "pallet_pay": 100,
            "spec_bonus_items": [{"reason": "Praca w piątek", "approved_by": "Brygadzista", "amount": 20}],
            "spec_bonus_val": 20,
            "total_payout": 1110,
            "absences_table": pd.DataFrame([
                {"Data": "01.11.2026", "Rodzaj nieobecności": "Nieobecny",
                 "Udział pracy w miesiącu (%)": 5}
            ]),
        }
        pdf = generate_bonus_slip_pdf("ŻÓŁĆ TEST 01", "Listopad 2026", details, absence_mode=True)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages
        )
        for expected in ["ŻÓŁĆ", "Praca w piątek", "1 110,00 zł", "Nadgodziny"]:
            self.assertIn(expected, text)

    def test_pdf_empty_absences_and_no_additions(self):
        from pypdf import PdfReader
        details = {
            "position": "MAGAZYNIER",
            "base_emp_bonus": 0,
            "calculated_bonus": 0,
            "deduction_pct": 0,
            "scheduled_days": 21,
            "days_worked": 0,
            "absent_days": 0,
            "total_ot": 0,
            "ot_pay": 0,
            "emp_forklift_hours": 0,
            "emp_forklift_pct": 0,
            "forklift_pay": 0,
            "pallet_pay": 0,
            "spec_bonus_val": 0,
            "spec_bonus_items": [],
            "total_payout": 0,
            "absences_table": pd.DataFrame(),
        }
        pdf = generate_bonus_slip_pdf("TEST 01", "Listopad 2026", details)
        text = "\n".join(
            page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages
        )
        self.assertIn("0,00 zł", text)


class CachedProductionTests(unittest.TestCase):
    def test_daily_and_monthly_totals_agree_and_ignore_excluded(self):
        prod = pd.DataFrame([
            {CLIENT_CATEGORY_COLUMN: "RETAIL", BRAND: "Brand A", ARTICLE: "A-1", QTY: 2,
             DATE: "2026-11-02"},
            {CLIENT_CATEGORY_COLUMN: "RETAIL", BRAND: "Brand B", ARTICLE: "B-1", QTY: 3,
             DATE: "2026-11-03"},
            {CLIENT_CATEGORY_COLUMN: "test", BRAND: "X", ARTICLE: "no", QTY: 999,
             DATE: "2026-11-03"},
        ])
        catalog = pd.DataFrame([
            {"Producent": "Brand A", "Artykuł": "A-1", "Waga": 0.5},
            {"Producent": "Brand B", "Artykuł": "B-1", "Waga": 2},
        ])
        summary = cached_production_totals(prod, catalog, ("test",))
        daily, invalid, wrong_month = cached_daily_totals(
            prod, catalog, ("test",), 2026, 11
        )
        self.assertEqual((invalid, wrong_month), (0, 0))
        self.assertEqual(summary["positions"], 2)
        self.assertEqual(summary["weight_kg"], 7)
        self.assertEqual(sum(r["weight"] for r in daily.values()), 7)
        self.assertEqual(daily[2]["weight"], 1)
        self.assertEqual(daily[3]["weight"], 6)

    def test_period_mismatch_is_reported(self):
        prod = pd.DataFrame([{
            CLIENT_CATEGORY_COLUMN: "RETAIL", BRAND: "A", ARTICLE: "1", QTY: 1,
            DATE: "2026-10-02",
        }])
        catalog = pd.DataFrame([{"Producent": "A", "Artykuł": "1", "Waga": 1}])
        _, invalid, wrong_month = cached_daily_totals(
            prod, catalog, (), 2026, 11
        )
        self.assertEqual((invalid, wrong_month), (0, 1))


if __name__ == "__main__":
    unittest.main()
