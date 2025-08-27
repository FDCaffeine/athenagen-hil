import unittest

from .utils import load_combined


class TestEmailsBasic(unittest.TestCase):
    def setUp(self):
        self.items = load_combined()
        self.emails = [r for r in self.items if r.get("source") == "email"]

    def test_email_records_have_subject_and_sender(self):
        # Δεν απαιτούμε όλα τα πεδία σε όλα τα emails, αλλά τα βασικά καλό είναι να υπάρχουν
        for i, rec in enumerate(self.emails[:100]):
            # subject (αν υπάρχει) να μην είναι κενό
            if "subject" in rec:
                self.assertTrue(str(rec["subject"]).strip(), f"Email rec {i} has empty subject")
            # email πελάτη (αν υπάρχει) να περιέχει '@'
            if "email" in rec:
                val = str(rec["email"])
                self.assertIn("@", val, f"Email rec {i} 'email' doesn't look like an email: {val}")


if __name__ == "__main__":
    unittest.main()
