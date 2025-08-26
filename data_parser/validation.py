# data_parser/validation.py
from typing import Any


def validate_email_record(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Επιστρέφει (καθαρισμένο_record, λίστα_λαθών) για email."""
    return d, []


def validate_form_record(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Επιστρέφει (καθαρισμένο_record, λίστα_λαθών) για form."""
    return d, []


def validate_invoice_record(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Επιστρέφει (καθαρισμένο_record, λίστα_λαθών) για invoice."""
    return d, []
