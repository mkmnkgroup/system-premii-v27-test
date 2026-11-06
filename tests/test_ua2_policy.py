import unittest
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN, exclude_categories


class UA2PolicyTests(unittest.TestCase):
    def test_ua2_excluded_and_exp_eu_kept(self):
        data = pd.DataFrame({CLIENT_CATEGORY_COLUMN: ['UA-2', 'EXP EU', 'UA-2']})
        kept, excluded = exclude_categories(data, ['UA-2'])
        self.assertEqual(excluded, 2)
        self.assertEqual(kept[CLIENT_CATEGORY_COLUMN].tolist(), ['EXP EU'])


if __name__ == '__main__':
    unittest.main()

