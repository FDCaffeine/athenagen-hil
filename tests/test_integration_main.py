import unittest

from tests.utils import ALLOWED_SOURCES, ALLOWED_STATUS, load_combined


class TestIntegrationMain(unittest.TestCase):
    def setUp(self):
        self.items = load_combined()

    def test_has_records(self):
        self.assertGreater(len(self.items), 0, "No records found in combined_feed.json")

    def test_minimal_schema(self):
        for i, rec in enumerate(self.items[:100]):  # limit για ταχύτητα
            self.assertIn("source", rec, f"Record {i} missing 'source'")
            self.assertIn(
                rec["source"],
                ALLOWED_SOURCES,
                f"Record {i} has unexpected source: {rec.get('source')}",
            )
            # status μπορεί να μπει από UI, αλλά αν υπάρχει ας είναι έγκυρο
            if "status" in rec:
                self.assertIn(
                    rec["status"], ALLOWED_STATUS, f"Record {i} has invalid status: {rec['status']}"
                )
            # πρέπει να υπάρχει μοναδικό id
            self.assertIn("id", rec, f"Record {i} missing 'id'")
            self.assertTrue(str(rec["id"]).strip(), f"Record {i} 'id' is empty")


if __name__ == "__main__":
    unittest.main()
