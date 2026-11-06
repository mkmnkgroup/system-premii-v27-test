import unittest
import pandas as pd
from incremental_weights import reconcile_weights


class IncrementalWeightsTests(unittest.TestCase):
    def test_additions_and_conflicts_do_not_overwrite(self):
        old = pd.DataFrame({"Producent": ["Bosch", "SKF"], "Artykuł": ["A", "B"], "Waga": [1.0, 2.0]})
        new = pd.DataFrame({"Producent": ["bosch", "SKF", "Valeo"], "Artykuł": ["A", "B", "C"], "Waga": [9.0, 2.0, 3.0]})
        result = reconcile_weights(old, new)
        self.assertEqual(len(result["new_items"]), 1)
        self.assertEqual(len(result["discrepancies"]), 1)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(old.loc[0, "Waga"], 1.0)

    def test_reject_duplicate_keys(self):
        old = pd.DataFrame({"Producent": ["A"], "Artykuł": ["1"], "Waga": [1.0]})
        with self.assertRaises(ValueError):
            reconcile_weights(old, pd.concat([old, old]))

    def test_reject_missing_new_weight(self):
        old = pd.DataFrame({"Producent": ["A"], "Artykuł": ["1"], "Waga": [1.0]})
        incoming = pd.DataFrame({"Producent": ["B"], "Artykuł": ["2"], "Waga": [None]})
        with self.assertRaises(ValueError):
            reconcile_weights(old, incoming)


if __name__ == "__main__":
    unittest.main()

