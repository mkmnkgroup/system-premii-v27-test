"""End-to-end data gates: eligible production -> weights -> attendance -> payslip preview."""
import unittest
import pandas as pd

from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import BRAND, ARTICLE, QTY, DATE, prepare_production
from monthly_publication import prepare_publication, PublicationValidationError


class MonthlyPipelineTests(unittest.TestCase):
    def setUp(self):
        self.production = pd.DataFrame([
            {CLIENT_CATEGORY_COLUMN: "RETAIL", BRAND: "MAKER A", ARTICLE: "A-1", QTY: 2, DATE: "2026-11-02"},
            {CLIENT_CATEGORY_COLUMN: "RETAIL", BRAND: "MAKER B", ARTICLE: "B-2", QTY: 3, DATE: "2026-11-03"},
            {CLIENT_CATEGORY_COLUMN: "test", BRAND: "UNKNOWN", ARTICLE: "NO-WEIGHT", QTY: 1000, DATE: "2026-11-02"},
        ])
        self.weights = pd.DataFrame([
            {"Producent": "MAKER A", "Artykuł": "A-1", "Waga": 0.5},
            {"Producent": "MAKER B", "Artykuł": "B-2", "Waga": 2.0},
        ])
        self.schedule = pd.DataFrame([
            {"OSOBA": "TEST PRACOWNIK 01", "DATA": "02.11.2026",
             "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "Brak",
             "FAKTYCZNIE WEJŚCIE": "08:00", "FAKTYCZNIE WYJŚCIE": "16:00"},
            {"OSOBA": "TEST PRACOWNIK 02", "DATA": "02.11.2026",
             "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący", "NIEOBECNOŚĆ": "CHOROBOWE",
             "FAKTYCZNIE WEJŚCIE": "", "FAKTYCZNIE WYJŚCIE": ""},
        ])
        self.summary = pd.DataFrame([
            {"Pracownik": "TEST PRACOWNIK 01", "Premia (zł)": 150.0,
             "ŁĄCZNA PREMIA / DODATKI (zł)": 180.0, "% Potrącenia": 0.0,
             "Dni przepracowane": 1, "Nadgodziny (zł)": 20.0,
             "Dodatek Wózek (zł)": 10.0, "Dodatek Palety (zł)": 0.0,
             "Premia Specjalna (zł)": 0.0},
            {"Pracownik": "TEST PRACOWNIK 02", "Premia (zł)": 100.0,
             "ŁĄCZNA PREMIA / DODATKI (zł)": 105.0, "% Potrącenia": 25.0,
             "Dni przepracowane": 0, "Nadgodziny (zł)": 0.0,
             "Dodatek Wózek (zł)": 0.0, "Dodatek Palety (zł)": 5.0,
             "Premia Specjalna (zł)": 0.0},
        ])
        self.profiles = [
            {"employee_id": "TEST PRACOWNIK 01",
             "user_id": "11111111-1111-4111-8111-111111111111",
             "role": "employee", "enabled": True},
            {"employee_id": "TEST PRACOWNIK 02",
             "user_id": "22222222-2222-4222-8222-222222222222",
             "role": "employee", "enabled": True},
        ]

    def archive(self, weight_override=None):
        results = prepare_production(
            self.production, self.weights if weight_override is None else weight_override,
            excluded=("test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA"),
        )
        return results, {
            "summary": self.summary,
            "schedule": self.schedule,
            "metrics": {
                "pcs": results["pieces"], "lines": results["positions"],
                "weight": results["weight_kg"], "indicator": 0.10,
            }
        }

    def test_full_two_employee_payslip_preflight(self):
        results, archive = self.archive()
        self.assertEqual(
            (results["excluded_positions"], results["positions"],
             results["pieces"], results["weight_kg"], results["missing_positions"]),
            (1, 2, 5.0, 7.0, 0),
        )
        period, kpis, rows = prepare_publication("Listopad 2026", archive, self.profiles)
        self.assertEqual((period, kpis["weight_kg"]), ("2026-11-01", "7.00"))
        self.assertEqual([r["attended_days"] for r in rows], [1, 0])
        self.assertEqual([r["bonus_final_pln"] for r in rows], ["180.00", "105.00"])

    def test_missing_weight_blocks_publication(self):
        _, archive = self.archive(self.weights.iloc[:1])
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", archive, self.profiles)

    def test_missing_actual_departure_blocks_publication(self):
        _, archive = self.archive()
        self.schedule.loc[0, "FAKTYCZNIE WYJŚCIE"] = ""
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", archive, self.profiles)

    def test_payslip_mismatch_blocks_publication(self):
        _, archive = self.archive()
        self.summary.loc[1, "ŁĄCZNA PREMIA / DODATKI (zł)"] = 200.0
        with self.assertRaises(PublicationValidationError):
            prepare_publication("Listopad 2026", archive, self.profiles)


if __name__ == "__main__":
    unittest.main()
