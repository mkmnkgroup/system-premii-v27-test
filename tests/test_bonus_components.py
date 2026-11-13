"""Regression tests for optional detailed bonus data in worker payslips."""
import io
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bonus_components import parse_bonus_breakdown
from payslip_pdf import build_payslip_pdf


def sample_row():
    return {
        "user_id": "own-id",
        "period": "2026-11-01",
        "planned_days": 20,
        "attended_days": 19,
        "bonus_main_pln": "500.00",
        "bonus_additions_pln": "230.00",
        "bonus_final_pln": "730.00",
        "absence_reduction_pct": "5.00",
        "overtime_hours": "2.00",
        "overtime_pay_pln": "50.00",
        "bonus_breakdown": {
            "overtime_rate_pln": "25.00",
            "forklift_pay_pln": "60.00",
            "forklift_hours": "5",
            "forklift_team_hours": "20",
            "forklift_pool_pln": "240.00",
            "pallet_pay_pln": "40.00",
            "pallet_count": "80",
            "pallet_rate_pln": "2.00",
            "pallet_recipients": 4,
            "special_bonuses": [{
                "amount_pln": "80.00",
                "reason": "Dodatkowe zadanie",
                "approved_by": "Kierownik testowy",
            }],
        },
    }


class BonusBreakdownTests(unittest.TestCase):
    def test_valid_breakdown_sums_to_published_additions(self):
        parsed = parse_bonus_breakdown(sample_row())
        self.assertEqual(parsed["special_total"], Decimal("80.00"))
        self.assertEqual(parsed["additions_total"], Decimal("230.00"))

    def test_legacy_record_has_no_guessed_components(self):
        row = sample_row()
        row.pop("bonus_breakdown")
        self.assertIsNone(parse_bonus_breakdown(row))

    def test_rejects_sum_mismatch(self):
        row = sample_row()
        row["bonus_breakdown"]["forklift_pay_pln"] = "65.00"
        with self.assertRaises(ValueError):
            parse_bonus_breakdown(row)

    def test_rejects_negative_nan_missing_and_unexplained_items(self):
        for bad_value in ["NaN", "-1", None]:
            row = sample_row()
            row["bonus_breakdown"]["pallet_pay_pln"] = bad_value
            with self.assertRaises(ValueError):
                parse_bonus_breakdown(row)
        row = sample_row()
        row["bonus_breakdown"]["special_bonuses"][0]["reason"] = ""
        with self.assertRaises(ValueError):
            parse_bonus_breakdown(row)

    def test_pdf_second_page_has_breakdown_and_consistent_total(self):
        from pypdf import PdfReader
        pdf = build_payslip_pdf("2026-11-01", "Pracownik Testowy", sample_row())
        reader = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 2)
        first, second = (page.extract_text() for page in reader.pages)
        self.assertIn("730,00 zł netto", first)
        self.assertIn("Wózek", second.lower().capitalize() if False else second)
        self.assertIn("Dodatkowe zadanie", second)
        self.assertIn("230,00 zł", second)

    def test_pdf_legacy_stays_one_page(self):
        from pypdf import PdfReader
        row = sample_row()
        row["bonus_breakdown"] = None
        pdf = build_payslip_pdf("2026-11-01", "Pracownik Testowy", row)
        self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages), 1)

    def test_pdf_malformed_breakdown_fails_closed(self):
        row = sample_row()
        row["bonus_breakdown"]["special_bonuses"][0]["amount_pln"] = "NaN"
        with self.assertRaises(ValueError):
            build_payslip_pdf("2026-11-01", "Pracownik Testowy", row)

    def test_employee_panel_does_not_download_other_users_data(self):
        import role_views
        row = sample_row()
        row["user_id"] = "different-id"
        with patch.object(role_views, "_get", side_effect=[[row]]), patch.object(role_views, "st", MagicMock()) as ui:
            ui.columns.return_value = (MagicMock(), MagicMock())
            role_views._my_payslip("2026-11-01", "own-id")
            ui.download_button.assert_not_called()


if __name__ == "__main__":
    unittest.main()
