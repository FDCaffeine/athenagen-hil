import unittest

from tests.utils import load_combined


class TestInvoicesBasic(unittest.TestCase):
    def setUp(self):
        self.items = load_combined()
        self.invoices = [r for r in self.items if r.get("source") == "invoice_html"]

    def test_invoice_records_have_numbers(self):
        for i, rec in enumerate(self.invoices[:100]):
            # invoice_number να υπάρχει/μη κενό (αν το παράγει ο parser)
            if "invoice_number" in rec:
                self.assertTrue(
                    str(rec["invoice_number"]).strip(), f"Invoice rec {i} has empty invoice_number"
                )

    def test_invoice_amounts_are_numeric(self):
        for i, rec in enumerate(self.invoices[:100]):
            # επιτρέπουμε να λείπουν κάποια, αλλά αν υπάρχουν να είναι αριθμοί >= 0
            for key in ("amount", "vat", "total_amount"):
                if key in rec and rec[key] is not None and rec[key] != "":
                    try:
                        val = float(rec[key])
                    except (ValueError, TypeError):
                        self.fail(f"Invoice rec {i} field '{key}' not numeric: {rec[key]}")
                    self.assertGreaterEqual(val, 0.0, f"Invoice rec {i} field '{key}' negative")


if __name__ == "__main__":
    unittest.main()
