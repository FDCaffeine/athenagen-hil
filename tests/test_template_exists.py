import unittest

from .utils import template_headers


class TestTemplateExists(unittest.TestCase):
    def test_template_headers_present(self):
        headers = template_headers()
        self.assertGreater(len(headers), 0, "Template CSV first line appears empty")
        # μερικά συνηθισμένα headers (δεν απαιτείται να υπάρχουν όλα)
        COMMON = {
            "date",
            "type",
            "client_name",
            "company",
            "amount",
            "vat",
            "total_amount",
            "invoice_number",
        }
        # αρκεί τουλάχιστον ένα κοινό header να ταιριάζει
        self.assertTrue(
            COMMON.intersection(set(h.lower() for h in headers)),
            f"No common headers found in template: {headers}",
        )


if __name__ == "__main__":
    unittest.main()
