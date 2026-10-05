import unittest
from module import receipt_total
class TotalTests(unittest.TestCase):
    def test_total(self): self.assertEqual(receipt_total([10, 20]), 30)
    def test_empty(self): self.assertEqual(receipt_total([]), 0)
    def test_discount(self): self.assertEqual(receipt_total([10, 20], 0.1), 27)
    def test_free(self): self.assertEqual(receipt_total([10, 20], 1), 0)
    def test_negative_rate(self):
        with self.assertRaises(ValueError): receipt_total([10], -0.1)
    def test_excess_rate(self):
        with self.assertRaises(ValueError): receipt_total([10], 1.1)
if __name__ == "__main__": unittest.main()
