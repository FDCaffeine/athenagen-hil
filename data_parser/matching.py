# data_parser/matching.py
from __future__ import annotations

from typing import Any

try:
    # προαιρετικό: καλύτερο fuzzy
    from rapidfuzz import fuzz

    HAS_RAPIDFUZZ = True
except Exception:  # rapidfuzz δεν είναι εγκατεστημένο
    HAS_RAPIDFUZZ = False


__all__ = ["normalize_inv", "build_invoice_lookup", "fuzzy_find"]


def normalize_inv(s: str | None) -> str:
    """
    Κανονικοποίηση αριθμού τιμολογίου:
    - uppercase
    - κρατάμε μόνο αλφαριθμητικούς χαρακτήρες
    """
    if not s:
        return ""
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def build_invoice_lookup(invoices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Φτιάχνει index: normalized_invoice_number -> invoice_record
    Συμπεριλαμβάνει ΜΟΝΟ εγγραφές από source == "invoice_html" που έχουν invoice_number.
    """
    out: dict[str, dict[str, Any]] = {}
    for r in invoices:
        if r.get("source") != "invoice_html":
            continue
        inv_no = r.get("invoice_number")
        if not inv_no:
            continue
        key = normalize_inv(inv_no)
        if key:
            out[key] = r
    return out


def fuzzy_find(
    candidate: str,
    lookup: dict[str, Any],
    score_cutoff: int = 85,
) -> tuple[dict[str, Any] | None, int]:
    """
    Βρίσκει το καλύτερο match για έναν πιθανό αριθμό τιμολογίου.
    Επιστρέφει (record_or_None, score).
    - Αν είναι exact match -> (rec, 100)
    - Αλλιώς fuzzy (rapidfuzz αν υπάρχει, αλλιώς naive "contains")
    - Αν score < cutoff -> (None, best_score)
    """
    key = normalize_inv(candidate)
    if not key:
        return None, 0

    # exact
    if key in lookup:
        return lookup[key], 100

    best_rec: dict[str, Any] | None = None
    best_score = 0

    if HAS_RAPIDFUZZ:
        for k, rec in lookup.items():
            # partial_ratio για “υπο-αλφαριθμητικά” matches
            score = int(fuzz.partial_ratio(key, k))
            if score > best_score:
                best_score = score
                best_rec = rec
    else:
        # naive fallback: contains -> 80, αλλιώς 0
        for k, rec in lookup.items():
            if key and (key in k or k in key):
                score = 80
                if score > best_score:
                    best_score = score
                    best_rec = rec

    if best_score >= score_cutoff and best_rec is not None:
        return best_rec, best_score
    return None, best_score
