import unittest
from module import customer_report
FIELDS = ("id", "name", "city", "country", "email", "phone", "plan", "language", "timezone", "status", "created", "updated")
class ReportTests(unittest.TestCase):
    def test_order(self):
        customer = dict(zip(FIELDS, ("1", "Mo", "Cairo", "EG", "m@example.test", "", "basic", "ar", "UTC", "active", "2026-01-01", "2026-01-02")))
        expected = "id=1\nname=Mo\ncity=Cairo\ncountry=EG\nemail=m@example.test\nphone=\nplan=basic\nlanguage=ar\ntimezone=UTC\nstatus=active\ncreated=2026-01-01\nupdated=2026-01-02"
        self.assertEqual(customer_report(customer), expected)
    def test_missing_required_field(self):
        with self.assertRaises(KeyError): customer_report({})
if __name__ == "__main__": unittest.main()
