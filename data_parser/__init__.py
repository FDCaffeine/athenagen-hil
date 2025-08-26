# data_parser/__init__.py
from .parse_emails import parse_all_emails
from .parse_forms import parse_all_forms
from .parse_invoices import parse_all_invoices

__all__ = ["parse_all_emails", "parse_all_forms", "parse_all_invoices"]
