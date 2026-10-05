import unittest
from module import multiply
class MultiplyTests(unittest.TestCase):
    def test_positive(self): self.assertEqual(multiply(2, 3), 6)
    def test_zero(self): self.assertEqual(multiply(2, 0), 0)
    def test_negative(self): self.assertEqual(multiply(-2, 3), -6)
    def test_fraction(self): self.assertEqual(multiply(0.5, 4), 2)
if __name__ == "__main__": unittest.main()
