import io
import unittest
import pandas as pd
from production_import import prepare_production, read_production, read_weights, BRAND, ARTICLE, QTY
from client_categories import CLIENT_CATEGORY_COLUMN


class ProductionImportTests(unittest.TestCase):
    def setUp(self):
        self.production = pd.DataFrame({CLIENT_CATEGORY_COLUMN: ["A", "B", "A"], BRAND: ["Bosch", "SKF", "Bosch"], ARTICLE: ["123", "456", "123"], QTY: ["2", "3", "4"]})
        self.weights = pd.DataFrame({"Producent": ["bosch", "skf"], "Artykuł": ["123", "456"], "Waga": ["0.5", "1.25"]})

    def test_totals_and_repeated_rows(self):
        result = prepare_production(self.production, self.weights)
        self.assertEqual((result["positions"], result["pieces"], result["weight_kg"]), (3, 9, 6.75))

    def test_excluded_category_before_calculation(self):
        result = prepare_production(self.production, self.weights, ["A"])
        self.assertEqual((result["positions"], result["pieces"], result["weight_kg"], result["excluded_positions"]), (1, 3, 3.75, 2))

    def test_missing_weight_blocks_total(self):
        result = prepare_production(self.production, self.weights.iloc[:1])
        self.assertEqual(result["missing_positions"], 1)
        self.assertIsNone(result["weight_kg"])

    def test_duplicate_catalog_key_rejected(self):
        with self.assertRaises(ValueError):
            prepare_production(self.production, pd.concat([self.weights, self.weights.iloc[:1]]))

    def test_catalog_selective_read(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(["Manufacture", "Producent", "Artykuł", "Waga"])
        ws.append(["unused", "Bosch", "123", 0.5])
        out = io.BytesIO(); wb.save(out)
        result = read_weights(out.getvalue())
        self.assertEqual(result.columns.tolist(), ["Producent", "Artykuł", "Waga"])
        self.assertEqual(len(result), 1)

    def test_six_row_header(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        for i in range(5): ws.append(["metadata"])
        ws.append([CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY])
        ws.append(["A", "Bosch", "123", 2])
        out = io.BytesIO(); wb.save(out)
        self.assertEqual(len(read_production(out.getvalue())), 1)


if __name__ == "__main__":
    unittest.main()

