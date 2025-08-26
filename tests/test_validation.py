from data_parser.validation import (
    validate_form_record,
    validate_invoice_record,
)


def test_validate_form_ok():
    clean, errors = validate_form_record({"full_name": "Foo", "email": "a@b.com"})
    assert isinstance(errors, list)


def test_validate_invoice_ok():
    clean, errors = validate_invoice_record({"invoice_number": "INV-1", "total": 10.0})
    assert isinstance(errors, list)
