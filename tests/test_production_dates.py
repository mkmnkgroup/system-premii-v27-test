import unittest
from datetime import datetime
import pandas as pd
from production_import import parse_production_dates


class ProductionDateTests(unittest.TestCase):
    def test_iso_local_and_excel_dates_keep_november(self):
        values = pd.Series(['2026-11-02', '03.11.2026', datetime(2026, 11, 4),
                            '2026-11-05 08:30:00', '06/11/2026'])
        result = parse_production_dates(values)
        self.assertEqual(result.dt.month.tolist(), [11] * 5)
        self.assertEqual(result.dt.day.tolist(), [2, 3, 4, 5, 6])

    def test_invalid_and_missing_dates_remain_invalid(self):
        result = parse_production_dates(pd.Series(['invalid', None, '2026-13-02']))
        self.assertTrue(result.isna().all())

    def test_outside_month_is_not_changed(self):
        result = parse_production_dates(pd.Series(['2026-02-11']))
        self.assertEqual((result.iloc[0].month, result.iloc[0].day), (2, 11))


    def test_mixed_local_iso_and_excel_datetimes_preserve_calendar_dates(self):
        values = pd.Series([
            "2026-11-05", "05.11.2026", "05/11/2026",
            "2026-11-05 08:30:00", "2026-11-05T08:30:00",
            datetime(2026, 11, 5, 18, 30), pd.Timestamp("2026-11-05"),
            "2026-02-11", "11.02.2026", "31.11.2026", None, "invalid",
        ], dtype=object)
        actual = parse_production_dates(values)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(actual))
        self.assertEqual(actual.index.tolist(), values.index.tolist())
        for i in range(7):
            self.assertEqual((actual.iloc[i].year, actual.iloc[i].month,
                              actual.iloc[i].day), (2026, 11, 5))
        self.assertEqual(actual.iloc[7].strftime("%Y-%m-%d"), "2026-02-11")
        self.assertEqual(actual.iloc[8].strftime("%Y-%m-%d"), "2026-02-11")
        self.assertTrue(actual.iloc[9:].isna().all())

    def test_repeated_dates_keep_row_alignment_and_duplicate_index(self):
        data = pd.Series(
            ["2026-11-02", "03.11.2026", None, "2026-10-04", "05/11/2026"],
            index=[4, 4, 9, 9, 12], dtype=object,
        )
        actual = parse_production_dates(data)
        self.assertEqual(actual.index.tolist(), data.index.tolist())
        self.assertEqual(
            [x.day if pd.notna(x) else None for x in actual],
            [2, 3, None, 4, 5],
        )
        self.assertEqual(actual.iloc[3].month, 10)

