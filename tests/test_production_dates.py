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
