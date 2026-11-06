import unittest
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN
from production_import import BRAND, ARTICLE, QTY, prepare_production


class MandatoryExclusionsTests(unittest.TestCase):
    def test_five_categories_excluded_before_weight_matching(self):
        categories = ['test', 'UA-2', 'АНД', 'ОПТ_UA', 'ФОП_UA', 'EXP EU']
        production = pd.DataFrame({CLIENT_CATEGORY_COLUMN: categories, BRAND: ['X'] * 5 + ['Bosch'], ARTICLE: ['missing'] * 5 + ['A'], QTY: [1] * 6})
        weights = pd.DataFrame({'Producent': ['Bosch'], 'Artykuł': ['A'], 'Waga': [2.5]})
        result = prepare_production(production, weights, excluded=categories[:5])
        self.assertEqual(result['excluded_positions'], 5)
        self.assertEqual(result['positions'], 1)
        self.assertEqual(result['missing_positions'], 0)
        self.assertEqual(result['weight_kg'], 2.5)

    def test_only_excluded_rows_has_no_eligible_positions(self):
        production = pd.DataFrame({CLIENT_CATEGORY_COLUMN: ['ОПТ_UA'], BRAND: ['X'], ARTICLE: ['unknown'], QTY: [3]})
        weights = pd.DataFrame({'Producent': ['Bosch'], 'Artykuł': ['A'], 'Waga': [2.5]})
        result = prepare_production(production, weights, excluded=['ОПТ_UA'])
        self.assertEqual(result['positions'], 0)
        self.assertEqual(result['excluded_positions'], 1)
        self.assertEqual(result['missing_positions'], 0)


if __name__ == '__main__':
    unittest.main()

