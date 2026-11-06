"""Regression tests: excluded client categories never require weights."""
import unittest
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import BRAND, ARTICLE, QTY, prepare_production


class ExcludedWeightsTests(unittest.TestCase):
    def test_excluded_missing_weights_do_not_block_calculation(self):
        production = pd.DataFrame({
            CLIENT_CATEGORY_COLUMN: ["Standard", "Poza standardem", "Poza standardem"],
            BRAND: ["Bosch", "KACO", "ATG"],
            ARTICLE: ["ABC", "UNKNOWN", "UNKNOWN2"],
            QTY: [2, 1, 3],
        })
        weights = pd.DataFrame({"Producent": ["Bosch"], "Artykuł": ["ABC"], "Waga": [1.5]})
        result = prepare_production(production, weights, excluded=["Poza standardem"])
        self.assertEqual(result["excluded_positions"], 2)
        self.assertEqual(result["positions"], 1)
        self.assertEqual(result["missing_positions"], 0)
        self.assertEqual(result["weight_kg"], 3.0)

    def test_nonexcluded_missing_weight_still_blocks_calculation(self):
        production = pd.DataFrame({
            CLIENT_CATEGORY_COLUMN: ["Standard", "Poza standardem"],
            BRAND: ["KACO", "ATG"], ARTICLE: ["UNKNOWN", "UNKNOWN2"], QTY: [1, 1],
        })
        weights = pd.DataFrame({"Producent": ["Bosch"], "Artykuł": ["ABC"], "Waga": [1.5]})
        result = prepare_production(production, weights, excluded=["Poza standardem"])
        self.assertEqual(result["missing_positions"], 1)
        self.assertIsNone(result["weight_kg"])


if __name__ == "__main__":
    unittest.main()

