import io
import unittest
from payslip_pdf import build_payslip_pdf, payslip_filename


class PayslipPdfTests(unittest.TestCase):
    def row(self, **changes):
        return dict(period="2026-11-01", planned_days=20, attended_days=19,
                    bonus_main_pln="635.36", bonus_additions_pln="0.00",
                    bonus_final_pln="635.36", absence_reduction_pct="63.06", **changes)

    def test_pdf_is_single_page_and_preserves_polish_name_and_published_values(self):
        from pypdf import PdfReader
        pdf = build_payslip_pdf("2026-11-01", "Łukasz Żółć", self.row())
        reader = PdfReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        for value in ("Łukasz Żółć", "Listopad 2026", "635,36 zł netto", "63,06%",
                      "Dni nieobecności", "nie stanowi dokumentu płacowego"):
            self.assertIn(value, text)
        self.assertNotIn("1720", text)

    def test_does_not_reapply_absence_deduction_to_published_main(self):
        from pypdf import PdfReader
        row = self.row()
        row.update(bonus_additions_pln="50.00", bonus_final_pln="685.36")
        text = PdfReader(io.BytesIO(build_payslip_pdf("2026-11-01", "TEST 02", row))).pages[0].extract_text()
        self.assertIn("635,36 zł", text)
        self.assertIn("50,00 zł", text)
        self.assertIn("685,36 zł netto", text)

    def test_mismatched_period_or_total_rejected(self):
        for change in ({"period": "2026-10-01"}, {"bonus_final_pln": "800"},
                       {"bonus_main_pln": "NaN"}, {"absence_reduction_pct": "101"}):
            row = self.row()
            row.update(change)
            with self.assertRaises(ValueError):
                build_payslip_pdf("2026-11-01", "TEST 02", row)

    def test_long_cyrillic_name_and_filename(self):
        from pypdf import PdfReader
        name = "Ш" * 150
        pdf = PdfReader(io.BytesIO(build_payslip_pdf("2026-11-01", name, self.row())))
        self.assertEqual(len(pdf.pages), 1)
        filename = payslip_filename("2026-11-01", "Łukasz / Żółć")
        self.assertTrue(filename.endswith(".pdf"))
        self.assertNotIn("/", filename)

    def test_overtime_is_separate_without_double_counting(self):
        from pypdf import PdfReader
        row = self.row()
        row.update(overtime_hours="4.00", overtime_pay_pln="100.00",
                   bonus_additions_pln="150.00", bonus_final_pln="785.36")
        text = PdfReader(io.BytesIO(build_payslip_pdf("2026-11-01", "TEST 02", row))).pages[0].extract_text()
        for value in ("Nadgodziny (4,00 h)", "100,00 zł", "Pozostałe dodatki", "50,00 zł", "785,36 zł netto"):
            self.assertIn(value, text)

    def test_detailed_payslip_contains_separate_components_and_reasons(self):
        from pypdf import PdfReader
        row = self.row()
        row.update(
            bonus_additions_pln="150.00", bonus_final_pln="785.36",
            overtime_hours="4.00", overtime_pay_pln="100.00",
            overtime_rate_pln="25.00", forklift_hours="2.00",
            forklift_team_hours="10.00", forklift_pay_pln="20.00",
            pallet_team_count="12.00", pallet_rate_pln="5.00",
            pallet_recipients=3, pallet_pay_pln="20.00",
            special_pay_pln="10.00",
            special_details=[{"amount_pln": "10.00",
                              "reason": "Awaryjny rozładunek",
                              "awarded_by": "Kierownik"}],
        )
        pdf = PdfReader(io.BytesIO(build_payslip_pdf("2026-11-01", "Łukasz Żółć", row)))
        self.assertGreaterEqual(len(pdf.pages), 1)
        full_text = " ".join(page.extract_text() for page in pdf.pages)
        for value in ("Dodatek za wózek widłowy", "20,00 zł",
                      "Dodatek za palety", "Premie specjalne",
                      "Awaryjny rozładunek", "25,00 zł",
                      "Palety rozliczone przez zespół", "785,36 zł netto"):
            self.assertIn(value, full_text)
        self.assertEqual(full_text.count("785,36 zł netto"), 1)

    def test_missing_detail_sum_blocks_pdf(self):
        row = self.row()
        row.update(
            bonus_additions_pln="50.00", bonus_final_pln="685.36",
            overtime_pay_pln="20.00", forklift_pay_pln="10.00",
            pallet_pay_pln="10.00", special_pay_pln="5.00",
        )
        with self.assertRaises(ValueError):
            build_payslip_pdf("2026-11-01", "TEST 01", row)

    def test_special_reason_amount_mismatch_blocks_pdf(self):
        row = self.row()
        row.update(
            bonus_additions_pln="10.00", bonus_final_pln="645.36",
            overtime_pay_pln="0.00", forklift_pay_pln="0.00",
            pallet_pay_pln="0.00", special_pay_pln="10.00",
            special_details=[{"amount_pln": "9.00",
                              "reason": "Uznaniowa", "awarded_by": ""}],
        )
        with self.assertRaises(ValueError):
            build_payslip_pdf("2026-11-01", "TEST 01", row)

    def test_legacy_overtime_is_unknown_instead_of_zero(self):
        from pypdf import PdfReader
        text = PdfReader(io.BytesIO(build_payslip_pdf("2026-11-01", "TEST 02", self.row()))).pages[0].extract_text()
        self.assertIn("brak liczby godzin", text)
        self.assertIn("Brak danych", text)

    def test_download_contains_only_authenticated_employees_pdf(self):
        from unittest.mock import patch, MagicMock
        import role_views
        row = self.row()
        row["user_id"] = "own-user"
        profile = {"user_id": "own-user", "employee_id": "Łukasz Żółć"}
        with patch.object(role_views, "_get", side_effect=[[row], [profile]]), \
                patch.object(role_views, "st", MagicMock()) as ui:
            ui.columns.return_value = (MagicMock(), MagicMock())
            role_views._my_payslip("2026-11-01", "own-user")
            call = ui.download_button.call_args
            self.assertEqual(call.args[0], "Pobierz mój pasek (PDF)")
            self.assertTrue(call.args[1].startswith(b"%PDF-"))
            self.assertEqual(call.kwargs["mime"], "application/pdf")
            self.assertTrue(call.kwargs["file_name"].endswith(".pdf"))
        row["user_id"] = "other-user"
        with patch.object(role_views, "_get", side_effect=[[row], [profile]]), \
                patch.object(role_views, "st", MagicMock()) as ui:
            ui.columns.return_value = (MagicMock(), MagicMock())
            role_views._my_payslip("2026-11-01", "own-user")
            ui.download_button.assert_not_called()
