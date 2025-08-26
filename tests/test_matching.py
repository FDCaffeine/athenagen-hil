from data_parser.matching import build_invoice_lookup, fuzzy_find, normalize_inv


def test_normalize_inv_basic():
    assert normalize_inv("INV-001/2024") == "INV0012024"
    assert normalize_inv(None) == ""


def test_build_lookup_and_exact_match():
    invoices = [{"source": "invoice_html", "invoice_number": "INV-123", "total": 100}]
    lookup = build_invoice_lookup(invoices)
    rec = lookup.get(normalize_inv("INV-123"))
    assert rec and rec["total"] == 100


def test_fuzzy_find_threshold():
    invoices = [{"source": "invoice_html", "invoice_number": "INV-123", "total": 100}]
    lookup = build_invoice_lookup(invoices)
    rec, score = fuzzy_find("INV123", lookup, score_cutoff=80)
    assert rec and score >= 80
