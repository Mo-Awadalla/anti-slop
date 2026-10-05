import unittest
from module import can_read, title
class PermissionTests(unittest.TestCase):
    def test_owner_allowed(self): self.assertTrue(can_read({"id":"a", "authenticated":True}, {"owner":"a"}))
    def test_stranger_denied(self): self.assertFalse(can_read({"id":"b", "authenticated":True}, {"owner":"a"}))
    def test_logged_out_owner_denied(self): self.assertFalse(can_read({"id":"a", "authenticated":False}, {"owner":"a"}))
    def test_title_unchanged(self): self.assertEqual(title({"title":"record"}), "record")
if __name__ == "__main__": unittest.main()
