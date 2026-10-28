"""
test_validation.py
------------------
Unit tests for validators (utils.py) and match scoring (matching.py).
No database needed. Run: python -m unittest test_validation.py -v
"""

import unittest

from matching import calculate_match_score
from utils import validate_email, validate_enum, validate_phone, validate_positive_int


class TestValidation(unittest.TestCase):
    def test_email_valid(self):
        self.assertTrue(validate_email("test@example.com"))

    def test_email_invalid(self):
        self.assertFalse(validate_email("notanemail"))

    def test_phone_valid(self):
        self.assertTrue(validate_phone("9876543210"))

    def test_phone_too_short(self):
        self.assertFalse(validate_phone("123"))

    def test_phone_non_digits(self):
        self.assertFalse(validate_phone("98765abcde"))

    def test_positive_int_valid(self):
        self.assertTrue(validate_positive_int("5"))

    def test_positive_int_negative(self):
        self.assertFalse(validate_positive_int("-1"))

    def test_positive_int_text(self):
        self.assertFalse(validate_positive_int("abc"))

    def test_enum_valid(self):
        self.assertTrue(validate_enum("FOOD", ["FOOD", "WATER"]))

    def test_enum_case_insensitive(self):
        self.assertTrue(validate_enum("food", ["FOOD", "WATER"]))

    def test_enum_invalid(self):
        self.assertFalse(validate_enum("XYZ", ["FOOD", "WATER"]))


class TestMatchScore(unittest.TestCase):
    def test_same_zone_critical_full_coverage(self):
        # 50 zone + 30 urgency + 20 coverage
        self.assertEqual(calculate_match_score("Zone-A", "Zone-A", "CRITICAL", 100, 200), 100)

    def test_cross_zone_low_urgency(self):
        # 10 zone + 5 urgency + 20 coverage
        self.assertEqual(calculate_match_score("Zone-A", "Zone-B", "LOW", 100, 200), 35)

    def test_partial_coverage(self):
        # 50 zone + 10 urgency + 10 (half coverage)
        self.assertEqual(calculate_match_score("Zone-A", "Zone-A", "MEDIUM", 100, 50), 70)


if __name__ == "__main__":
    unittest.main()
