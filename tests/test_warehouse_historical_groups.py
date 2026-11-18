"""Warehouse trend and net EUR client-category attribution regression tests.

All production rows are synthetic; the TEST Supabase database is untouched.
"""
import io
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import (
    BRAND, ARTICLE, DATE, QTY, GOODS_VALUE, prepare_production,
    read_production, production_value_candidates,
)
from client_group_analysis import group_workload, estimated_main_bonus_allocation
from warehouse_history import grouped_history, history_client_groups, monthly_history

NET = "Стоимость продажи нетто EUR"
EXCLUDE = ("test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA")
APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")


def sample_report():
    book = Workbook()
    tab = book.active
    tab.append(["Raport testowy"])
    tab.append([CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE, NET, "Opis"])
    tab.append(["GRUPA A", "Bosch", "100", 2, "2026-10-01", "10,00", "sale"])
    tab.append(["GRUPA A", "Bosch", "100", 3, "2026-10-02", "20,00", "sale"])
    tab.append(["GRUPA B", "SKF", "200", 5, "2026-10-02", "4,00", "sale"])
    tab.append(["UA-2", "SKF", "200", 900, "2026-10-02", "9999,00", "duplicate"])
    tab.append(["АНД", "SKF", "200", 900, "2026-10-02", "not-a-value", "duplicate"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def catalog():
    return pd.DataFrame([
        {"Producent": "Bosch", "Artykuł": "100", "Waga": 0.5},
        {"Producent": "SKF", "Artykuł": "200", "Waga": 1.0},
    ])


def archival(label, pos=100, sales=None, clients=None):
    return {
        "summary": pd.DataFrame([
            {"Pracownik": "TEST 01", "Stanowisko": "MAGAZYNIER",
             "Premia (zł)": 110, "Nadgodziny (godz.)": 2,
             "ŁĄCZNA PREMIA / DODATKI (zł)": 220},
            {"Pracownik": "TEST 02", "Stanowisko": "BRYGADZISTA",
             "Premia (zł)": 90, "Nadgodziny (godz.)": 0,
             "ŁĄCZNA PREMIA / DODATKI (zł)": 120},
        ]),
        "metrics": {
            "lines": pos, "pcs": pos * 3, "weight": pos * .5,
            "sales_eur_net": sales, "pallets": 2,
            "client_group_workload": clients,
        },
    }


class ClientGroupAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.data = sample_report()
        self.src = read_production(self.data, value_column=NET)

    def test_explicit_net_eur_field_and_no_arbitrary_auto_selection(self):
        self.assertIn(NET, production_value_candidates(self.data))
        bare = read_production(self.data)
        self.assertNotIn(GOODS_VALUE, bare.columns)
        self.assertIn(GOODS_VALUE, self.src.columns)
        self.assertEqual(list(self.src[GOODS_VALUE])[:3], ["10,00", "20,00", "4,00"])
        with self.assertRaisesRegex(ValueError, "wybranej kolumny"):
            read_production(self.data, value_column="missing column")

    def test_excluded_duplicate_groups_never_counted_even_in_eur(self):
        kpis = prepare_production(self.src, catalog(), EXCLUDE)
        self.assertEqual(kpis["positions"], 3)
        self.assertEqual(kpis["pieces"], 10)
        self.assertEqual(kpis["excluded_positions"], 2)

        result = group_workload(self.src, catalog(), EXCLUDE, value_mode="unit")
        self.assertEqual(result["totals"], {
            "positions": 3, "pieces": 10.0,
            "weight_kg": 7.5, "sales_eur_net": 100.0,
        })
        self.assertEqual(result["excluded_duplicate_positions"], 2)
        self.assertEqual({row["group"] for row in result["groups"]},
                         {"GRUPA A", "GRUPA B"})
        a = next(row for row in result["groups"] if row["group"] == "GRUPA A")
        self.assertEqual(a["sales_eur_net"], 80.0)
        self.assertAlmostEqual(a["share_sales_eur_net"], 0.8)
        self.assertAlmostEqual(sum(v["workload_share"] for v in result["groups"]), 1)
        cost = estimated_main_bonus_allocation(result, 1000)
        self.assertAlmostEqual(sum(row["allocated_main_bonus_pln"] for row in cost), 1000)

    def test_price_per_line_is_not_multiplied_twice(self):
        result = group_workload(self.src, catalog(), EXCLUDE, value_mode="position")
        self.assertEqual(result["totals"]["sales_eur_net"], 34.0)
        self.assertEqual(result["totals"]["pieces"], 10.0)
        self.assertEqual(result["totals"]["weight_kg"], 7.5)

    def test_bad_eligible_net_value_is_not_silently_underreported(self):
        production = self.src.copy()
        production.loc[0, GOODS_VALUE] = "niepoprawna"
        production.loc[3, GOODS_VALUE] = "niepoprawna"  # excluded duplicate
        result = group_workload(production, catalog(), EXCLUDE, value_mode="unit")
        self.assertFalse(result["value_complete"])
        self.assertEqual(result["invalid_value_positions"], 1)
        self.assertIsNone(result["totals"]["sales_eur_net"])
        self.assertTrue(all(row["sales_eur_net"] is None for row in result["groups"]))

    def test_missing_sales_value_does_not_block_original_bonus_model(self):
        bare = read_production(self.data)
        result = group_workload(bare, catalog(), EXCLUDE, value_mode=None)
        self.assertFalse(result["value_selected"])
        self.assertIsNone(result["totals"]["sales_eur_net"])
        self.assertAlmostEqual(sum(row["workload_share"] for row in result["groups"]), 1)


class HistoricalAnalysisTests(unittest.TestCase):
    def test_missing_month_metric_is_unknown_not_zero(self):
        a = archival("Styczeń 2025", sales=10000)
        b = archival("Marzec 2025", sales=None)
        hist = {"Styczeń 2025": a, "Marzec 2025": b}
        rows = monthly_history(hist)
        self.assertEqual([r["date"] for r in rows], ["2025-01", "2025-03"])
        self.assertIsNone(rows[1]["sales_eur_net"])
        self.assertEqual(rows[0]["main_bonus_pln"], 200)
        quarters = grouped_history(rows, "quarter")
        self.assertEqual(quarters[0]["recorded_months"], 2)
        self.assertEqual(quarters[0]["expected_months"], 3)
        self.assertFalse(quarters[0]["complete"])
        self.assertIsNone(quarters[0]["sales_eur_net"])
        self.assertEqual(quarters[0]["total_cost_pln"], 680.0)

    def test_full_semesters_and_partial_years(self):
        names = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
                 "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
        archive = {f"{name} 2025": archival(name, sales=1000) for name in names}
        rows = monthly_history(archive)
        halves = grouped_history(rows, "half")
        self.assertEqual(len(halves), 2)
        self.assertTrue(all(row["complete"] for row in halves))
        self.assertEqual(halves[0]["sales_eur_net"], 6000)
        years = grouped_history(rows, "year")
        self.assertTrue(years[0]["complete"])
        self.assertEqual(years[0]["positions"], 1200)
        partial = grouped_history(rows[:-2], "year")
        self.assertFalse(partial[0]["complete"])
        self.assertEqual(partial[0]["recorded_months"], 10)

    def test_group_cost_allocation_from_persisted_main_bonus(self):
        raw = read_production(sample_report(), value_column=NET)
        c = group_workload(raw, catalog(), EXCLUDE, value_mode="unit")
        history = {
            "Sierpień 2026": archival("Sierpień 2026", sales=100, clients=c),
            "Wrzesień 2026": archival("Wrzesień 2026", sales=100, clients=c),
            "Październik 2026": archival("Październik 2026", sales=None),
        }
        output = history_client_groups(history, list(history))
        self.assertEqual(output["months_with_groups"], 2)
        self.assertEqual(output["missing"], ["Październik 2026"])
        self.assertEqual(output["totals"]["sales_eur_net"], 200.0)
        self.assertAlmostEqual(output["totals"]["allocated_main_bonus_pln"], 400)
        self.assertAlmostEqual(sum(x["share_allocated_main_bonus_pln"] for x in output["groups"]), 1)

    def test_ui_modules_render_old_history_without_group_data(self):
        with patch("app_auth.login_gate", return_value=None):
            app = AppTest.from_file(APP, default_timeout=45)
            app.session_state["history_v2"] = {
                "Sierpień 2026": archival("Sierpień 2026"),
                "Wrzesień 2026": archival("Wrzesień 2026"),
            }
            app.run()
            for name in ("Analizy", "Porównania"):
                next(x for x in app.radio if x.label == "Moduł").set_value(name).run()
                self.assertEqual(list(app.exception), [], name)


if __name__ == "__main__":
    unittest.main()
