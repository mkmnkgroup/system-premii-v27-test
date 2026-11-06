"""Tests for Excel roster roundtrip and invalid imports."""
import io
import unittest
import pandas as pd
from employee_excel import validate_employees, read_employees_excel, write_employees_excel


class EmployeeExcelTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([
            {"OSOBA": "TEST OSOBA", "GRUPA": "GRUPA 1",
             "SYSTEM": "PONIEDZIAŁEK-PIĄTEK", "STANOWISKO": "MAGAZYNIER",
             "FUNKCJA": "SKANOWANIE", "UPRAWNIENIA UDT": True},
            {"OSOBA": "DRUGA OSOBA", "GRUPA": "GRUPA 2",
             "SYSTEM": "WTOREK-SOBOTA", "STANOWISKO": "BRYGADZISTA",
             "FUNKCJA": "KONTROLA", "UPRAWNIENIA UDT": False},
        ])

    def test_roundtrip(self):
        actual = read_employees_excel(io.BytesIO(write_employees_excel(self.frame)))
        pd.testing.assert_frame_equal(actual, self.frame)

    def test_missing_columns(self):
        with self.assertRaises(ValueError):
            validate_employees(self.frame.drop(columns=["GRUPA"]))

    def test_duplicate_names(self):
        frame = pd.concat([self.frame, self.frame.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            validate_employees(frame)

    def test_invalid_udt(self):
        frame = self.frame.copy()
        frame["UPRAWNIENIA UDT"] = frame["UPRAWNIENIA UDT"].astype(object)
        frame.loc[0, "UPRAWNIENIA UDT"] = "MOŻE"
        with self.assertRaises(ValueError):
            validate_employees(frame)

    def test_empty_names(self):
        frame = self.frame.copy()
        frame.loc[0, "OSOBA"] = ""
        with self.assertRaises(ValueError):
            validate_employees(frame)


if __name__ == "__main__":
    unittest.main()

