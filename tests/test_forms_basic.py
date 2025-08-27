import unittest

from .utils import load_combined


class TestFormsBasic(unittest.TestCase):
    def setUp(self):
        self.items = load_combined()
        self.forms = [r for r in self.items if r.get("source") == "form"]

    def test_form_records_have_some_identity(self):
        # Τουλάχιστον ένα από full_name / company / phone / email να υπάρχει και να μην είναι κενό
        for i, rec in enumerate(self.forms[:100]):
            fields = ["full_name", "company", "phone", "email"]
            present = any((f in rec) and str(rec[f]).strip() for f in fields)
            self.assertTrue(present, f"Form rec {i} lacks identity fields: {fields}")


if __name__ == "__main__":
    unittest.main()
