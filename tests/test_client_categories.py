import unittest
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN, category_options, exclude_categories


class ClientCategoryTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({CLIENT_CATEGORY_COLUMN: ["A", "B", " A ", None, "C"], "Sztuki": [1, 2, 3, 4, 5]})

    def test_excludes_selected_only(self):
        filtered, count = exclude_categories(self.df, ["A"])
        self.assertEqual(count, 2)
        self.assertEqual(filtered["Sztuki"].tolist(), [2, 4, 5])
        self.assertEqual(len(self.df), 5)

    def test_empty_selection_keeps_everything(self):
        filtered, count = exclude_categories(self.df, [])
        self.assertEqual(count, 0)
        self.assertEqual(len(filtered), 5)

    def test_missing_column_with_exclusions_fails_closed(self):
        with self.assertRaises(ValueError):
            exclude_categories(pd.DataFrame({"Sztuki": [1]}), ["A"])

    def test_categories_include_saved_not_in_new_file(self):
        self.assertEqual(category_options(self.df, ["D"]), ["A", "B", "C", "D"])

    def test_missing_column_without_exclusions_keeps_everything(self):
        filtered, count = exclude_categories(pd.DataFrame({"Sztuki": [1]}), [])
        self.assertEqual((len(filtered), count), (1, 0))


if __name__ == "__main__":
    unittest.main()

