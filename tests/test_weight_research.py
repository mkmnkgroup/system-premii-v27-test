import unittest
from urllib.parse import parse_qs, urlparse
from weight_research import product_search_url, validate_weight

class WeightResearchTests(unittest.TestCase):
    def test_search_uses_only_product_identity(self):
        url = product_search_url("Bosch", "0 123/45")
        query = parse_qs(urlparse(url).query)["q"][0]
        self.assertIn("Bosch", query)
        self.assertIn("0 123/45", query)

    def test_positive_weight(self):
        self.assertEqual(validate_weight("0,45"), 0.45)

    def test_invalid_weights(self):
        for value in ("0", "-1", "abc", "100000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_weight(value)

if __name__ == "__main__":
    unittest.main()

