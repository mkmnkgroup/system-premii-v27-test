"""Synthetic 15k-row monthly production performance and correctness smoke test.

Runs entirely offline: no real employee details, database writes or network use.
CI timing is diagnostic rather than a claim about actual browser latency.
"""
import io
import time
import unittest

from openpyxl import Workbook

from bonus_analysis_cache import cached_daily_totals, cached_production_totals
from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import ARTICLE, BRAND, DATE, QTY, read_production, read_weights


ROWS = 15000
EXCLUDED_EVERY = 100


def excel(headers, values):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet()
    sheet.append(list(headers))
    for row in values:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class LargeMonthlyProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        started = time.perf_counter()
        cls.raw_production = excel(
            [CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE],
            (
                ("test" if i % EXCLUDED_EVERY == 0 else "EXP_EU",
                 "TEST PRODUCENT", f"FAKE-ART-{i:05d}",
                 (i % 4) + 1, f"2026-11-{(i % 30) + 1:02d}")
                for i in range(ROWS)
            ),
        )
        # No weights for excluded lines: they cannot block payroll.
        cls.raw_weights = excel(
            ["Producent", "Artykuł", "Waga"],
            (
                ("TEST PRODUCENT", f"FAKE-ART-{i:05d}", 0.1 * ((i % 11) + 1))
                for i in range(ROWS) if i % EXCLUDED_EVERY != 0
            ),
        )
        cls.seconds_build = time.perf_counter() - started

    def test_large_excel_to_monthly_and_daily_kpis(self):
        t = time.perf_counter()
        production = read_production(self.raw_production)
        elapsed_read_prod = time.perf_counter() - t
        t = time.perf_counter()
        weights = read_weights(self.raw_weights)
        elapsed_read_weights = time.perf_counter() - t

        t = time.perf_counter()
        monthly = cached_production_totals(production, weights, ("test",))
        elapsed_monthly = time.perf_counter() - t

        t = time.perf_counter()
        daily, invalid_dates, outside_period = cached_daily_totals(
            production, weights, ("test",), 2026, 11
        )
        elapsed_daily = time.perf_counter() - t

        t = time.perf_counter()
        monthly_again = cached_production_totals(production, weights, ("test",))
        daily_again = cached_daily_totals(production, weights, ("test",), 2026, 11)
        elapsed_cached = time.perf_counter() - t

        included = [i for i in range(ROWS) if i % EXCLUDED_EVERY != 0]
        pieces = sum(i % 4 + 1 for i in included)
        kg = sum((i % 4 + 1) * (0.1 * ((i % 11) + 1)) for i in included)
        self.assertEqual(len(production), ROWS)
        self.assertEqual(len(weights), ROWS - ROWS // EXCLUDED_EVERY)
        self.assertEqual(monthly["positions"], len(included))
        self.assertEqual(monthly["excluded_positions"], ROWS - len(included))
        self.assertEqual(monthly["matched_positions"], len(included))
        self.assertEqual(monthly["missing_positions"], 0)
        self.assertEqual(monthly["pieces"], pieces)
        self.assertAlmostEqual(monthly["weight_kg"], kg, places=5)
        self.assertEqual((invalid_dates, outside_period), (0, 0))
        self.assertEqual(sum(item["lines"] for item in daily.values()), len(included))
        self.assertEqual(sum(item["pcs"] for item in daily.values()), pieces)
        self.assertAlmostEqual(sum(item["weight"] for item in daily.values()), kg, places=5)
        self.assertEqual(monthly_again["positions"], monthly["positions"])
        self.assertEqual(daily_again, daily)

        total_seconds = (
            elapsed_read_prod + elapsed_read_weights + elapsed_monthly + elapsed_daily
        )
        print(
            "LARGE_PRODUCTION_BENCHMARK "
            f"rows={ROWS} unique_weights={len(weights)} "
            f"excel_build={self.seconds_build:.3f}s "
            f"production_excel_read={elapsed_read_prod:.3f}s "
            f"weights_excel_read={elapsed_read_weights:.3f}s "
            f"monthly_join={elapsed_monthly:.3f}s "
            f"daily_join={elapsed_daily:.3f}s "
            f"cached_calls={elapsed_cached:.3f}s "
            f"cold_total={total_seconds:.3f}s "
            "(GitHub CI CPU, not actual browser latency)",
            flush=True,
        )
        # A generous regression budget, not a user-visible performance SLA.
        self.assertLess(total_seconds, 60.0, "15k-row pipeline became unusually slow")


if __name__ == "__main__":
    unittest.main()
