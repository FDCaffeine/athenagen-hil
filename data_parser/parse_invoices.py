# data_parser/parse_invoices.py
from __future__ import annotations

import os
import re
from contextlib import suppress
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup


# ---------- choose best parser ----------
def _pick_parser() -> str:
    for candidate in ("lxml", "html5lib", "html.parser"):
        try:
            BeautifulSoup("<div></div>", candidate)
            return candidate
        except Exception:
            continue
    return "html.parser"


_PARSER = _pick_parser()

# ---------- helpers ----------
WS = re.compile(r"\s+")


def _nw(s: str | None) -> str:
    return WS.sub(" ", (s or "")).strip()


def _norm_amount(tok: str) -> str:
    if tok is None:
        return ""
    t = re.sub(r"[^\d,.\-]", "", tok.strip())
    t = (
        t.replace(".", "").replace(",", ".")
        if ("," in t and t.rfind(",") > t.rfind("."))
        else t.replace(",", "")
    )
    return t


def _to_float(tok: str | None) -> float | None:
    try:
        return float(_norm_amount(tok))
    except Exception:
        return None


DATE_PAT = re.compile(
    r"\b((?:\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})|(?:\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}))\b"
)


def _parse_date_text(text: str) -> str:
    m = DATE_PAT.search(text or "")
    if not m:
        return ""
    raw = m.group(1)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return raw


INV_PATS = [
    re.compile(
        r"(?:τιμολ(?:όγιο|\.?)|invoice)\s*(?:αρ\.|no\.|#|:)?\s*([A-Z]{0,4}[-/]?\d[\w\-\/]+)",
        re.I,
    ),
    re.compile(r"(?:αριθμός|αρ\.)\s*:?[\s]*([A-Z]{0,4}[-/]?\d[\w\-\/]+)", re.I),
]


def _find_invoice_number_from_text(text: str) -> str:
    for p in INV_PATS:
        m = p.search(text)
        if m:
            return _nw(m.group(1))
    return ""


def _find_summary_table(soup: BeautifulSoup):
    div_sum = soup.select_one("div.summary")
    if div_sum:
        tbl = div_sum.find("table")
        if tbl:
            return tbl
    for tbl in soup.find_all("table"):
        if tbl.find(string=re.compile(r"καθαρή\s*αξία|subtotal|net\s*(amount|value)", re.I)):
            return tbl
    return None


def _extract_summary_amounts(
    soup: BeautifulSoup,
) -> tuple[float | None, float | None, float | None, float | None, str]:
    subtotal = vat_amount = vat_rate = total = None
    currency = "EUR"
    tbl = _find_summary_table(soup)
    if not tbl:
        return subtotal, vat_amount, vat_rate, total, currency

    whole_text = _nw(tbl.get_text(" "))
    if "€" in whole_text:
        currency = "EUR"
    elif "$" in whole_text:
        currency = "USD"
    elif "£" in whole_text:
        currency = "GBP"

    for tr in tbl.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) < 2:
            continue
        label = _nw(tds[0].get_text(" "))
        value = _nw(tds[-1].get_text(" "))

        if re.search(r"καθαρή\s*αξία|net\s*(amount|value)|subtotal|προ\s*φπα", label, re.I):
            subtotal = _to_float(value)
        elif re.search(r"φπα|vat", label, re.I):
            m = re.search(r"(?:φπα|vat)\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%", label, re.I)
            if m:
                try:
                    vat_rate = float(_norm_amount(m.group(1)))
                except Exception:
                    vat_rate = None
            vat_amount = _to_float(value)
        elif re.search(r"^σύνολο\b|grand\s*total|total\s*amount|πληρωτέο", label, re.I):
            total = _to_float(value)

    if subtotal is not None and vat_amount is not None and total is None:
        total = round(subtotal + vat_amount, 2)
    if total is not None and subtotal is not None and vat_amount is None:
        diff = round(total - subtotal, 2)
        if diff >= 0:
            vat_amount = diff
    if vat_amount is not None and subtotal is not None and vat_rate is None and subtotal > 0:
        vat_rate = round((vat_amount / subtotal) * 100, 2)

    return subtotal, vat_amount, vat_rate, total, currency


# ----------- extraction helpers για Seller/Buyer/Items ----------
VAT_RE = re.compile(r"ΑΦΜ\s*:\s*([A-Za-z0-9]+)", re.I)
DOY_RE = re.compile(r"ΔΟΥ\s*:\s*([^\|\n]+)", re.I)
PHONE_RE = re.compile(r"(?:Τηλ|Τηλέφωνο)\s*:\s*([0-9\-\+\s]+)", re.I)
EMAIL_RE = re.compile(r"Email\s*:\s*([^\s|]+)", re.I)


def _extract_seller_block(soup: BeautifulSoup) -> dict[str, Any]:
    out = {
        "seller_name": "",
        "seller_email": "",
        "seller_phone": "",
        "seller_vat": "",
        "seller_tax_office": "",
        "seller_address": "",
    }
    header = soup.select_one(".header")
    if not header:
        return out
    company = header.select_one(".company")
    if company:
        out["seller_name"] = _nw(company.get_text())
    divs = header.find_all("div")
    txts = [_nw(d.get_text(" ")) for d in divs]
    # address line: first non meta after name
    for t in txts:
        if t == out["seller_name"]:
            continue
        low = t.lower()
        if ("αφμ" in low) or ("δου" in low) or ("email" in low) or ("τηλ" in low):
            continue
        out["seller_address"] = t
        break
    joined = " | ".join(txts)
    m_vat = VAT_RE.search(joined)
    out["seller_vat"] = _nw(m_vat.group(1)) if m_vat else ""
    m_doy = DOY_RE.search(joined)
    out["seller_tax_office"] = _nw(m_doy.group(1)) if m_doy else ""
    m_tel = PHONE_RE.search(joined)
    out["seller_phone"] = _nw(m_tel.group(1)) if m_tel else ""
    m_em = EMAIL_RE.search(joined)
    out["seller_email"] = _nw(m_em.group(1)) if m_em else ""
    return out


def _get_details_wrapper(details: BeautifulSoup):
    if not details:
        return None
    for child in details.find_all("div", recursive=False):
        style = (child.get("style") or "").lower()
        if "display" in style and "flex" in style:
            return child
    for child in details.find_all("div"):
        style = (child.get("style") or "").lower()
        if "display" in style and "flex" in style:
            return child
    return None


def _extract_header_left_block(details: BeautifulSoup) -> str:
    if not details:
        return ""
    wrapper = _get_details_wrapper(details)
    if not wrapper:
        return ""
    cols = wrapper.find_all("div", recursive=False)
    left = cols[0] if cols else None
    return _nw(left.get_text(" ")) if left else ""


def _extract_buyer_block(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {"buyer_name": "", "buyer_vat": "", "buyer_address": ""}
    details = soup.select_one(".invoice-details")
    if not details:
        return out
    wrapper = _get_details_wrapper(details)
    if not wrapper:
        return out
    cols = wrapper.find_all("div", recursive=False)
    right = cols[1] if len(cols) >= 2 else None
    if not right:
        return out
    raw = right.get_text("\n")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if lines and lines[0].lower().startswith("πελάτης"):
        lines = lines[1:]
    if lines:
        out["buyer_name"] = lines[0]
    vat = ""
    for line in reversed(lines):
        m = VAT_RE.search(line)
        if m:
            vat = m.group(1)
            break
    out["buyer_vat"] = vat
    addr_parts = []
    for line in lines[1:]:
        if VAT_RE.search(line):
            break
        addr_parts.append(line)
    out["buyer_address"] = ", ".join(addr_parts)
    return out


def _extract_payment_and_date(details_text: str) -> tuple[str, str]:
    date_str = _parse_date_text(details_text)
    pay = ""
    m = re.search(r"Τρόπος\s*Πληρωμής\s*:\s*([^\n]+)", details_text, re.I)
    if m:
        pay = _nw(m.group(1))
    return date_str, pay


def _extract_items(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], str]:
    items: list[dict[str, Any]] = []
    currency = "EUR"
    tbl = soup.select_one("table.invoice-table")
    if not tbl:
        return items, currency
    tbody = tbl.find("tbody") or tbl
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        desc = _nw(tds[0].get_text(" "))
        qty = _to_float(_nw(tds[1].get_text(" ")))
        unit = _nw(tds[2].get_text(" "))
        total = _nw(tds[3].get_text(" "))
        sym_text = " ".join([unit, total])
        if "€" in sym_text:
            currency = "EUR"
        elif "$" in sym_text:
            currency = "USD"
        elif "£" in sym_text:
            currency = "GBP"
        items.append(
            {
                "description": desc,
                "quantity": qty,
                "unit_price": _to_float(unit),
                "line_total": _to_float(total),
                "currency": currency,
            }
        )
    return items, currency


# ---------- footer notes ----------
def _extract_footer_notes(soup: BeautifulSoup) -> list[dict[str, str]]:
    """
    Διαβάζει τα <p> κάτω από τη σύνοψη. Περιμένει μορφή:
      <p><strong>Ετικέτα:</strong> Τιμή</p>
    ή γενικό κείμενο. Επιστρέφει [{"label","value"}].
    """
    notes: list[dict[str, str]] = []
    summary_div = soup.select_one("div.summary")
    start = summary_div.find_next("div") if summary_div else None
    if not start:
        start = soup.find("div", attrs={"style": re.compile(r"font-size\s*:\s*12px", re.I)})
    container = start or soup
    for p in container.find_all("p"):
        txt = _nw(p.get_text(" "))
        if not txt:
            continue
        label = ""
        strong = p.find(["strong", "b"])
        if strong:
            label = _nw(strong.get_text()).rstrip(":：").strip()
            full = _nw(p.get_text(" "))
            patt = re.compile(rf"^{re.escape(label)}\s*[:：]?\s*", re.I)
            value = patt.sub("", full).strip()
        else:
            m = re.match(r"(.+?)\s*[:：]\s*(.+)$", txt)
            if m:
                label, value = _nw(m.group(1)), _nw(m.group(2))
            else:
                label, value = "Σημείωση", txt
        notes.append({"label": label, "value": value})
    return notes


# ---------- core (refactor) ----------
def _parse_invoice_soup(soup: BeautifulSoup) -> dict[str, Any]:
    full_text = soup.get_text(" ")

    invoice_number = _find_invoice_number_from_text(full_text)

    seller = _extract_seller_block(soup)

    details = soup.select_one(".invoice-details")
    left_text = _extract_header_left_block(details) if details else ""
    date_str, payment_method = _extract_payment_and_date(left_text)
    if not date_str:
        date_str = _parse_date_text(full_text)

    buyer = _extract_buyer_block(soup)

    items, items_currency = _extract_items(soup)
    subtotal, vat_amount, vat_rate, total, sum_currency = _extract_summary_amounts(soup)
    currency = sum_currency or items_currency or "EUR"

    extra_notes = _extract_footer_notes(soup)

    record: dict[str, Any] = {
        "invoice_number": invoice_number,
        "date": date_str,
        "payment_method": payment_method,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "vat_rate": vat_rate,
        "total": total,
        "currency": currency,
        # Seller
        "seller_name": seller.get("seller_name", ""),
        "seller_email": seller.get("seller_email", ""),
        "seller_phone": seller.get("seller_phone", ""),
        "seller_vat": seller.get("seller_vat", ""),
        "seller_tax_office": seller.get("seller_tax_office", ""),
        "seller_address": seller.get("seller_address", ""),
        # Buyer
        "buyer_name": buyer.get("buyer_name", ""),
        "buyer_vat": buyer.get("buyer_vat", ""),
        "buyer_address": buyer.get("buyer_address", ""),
        # Lines & notes
        "items": items,
        "extra_notes": extra_notes,
        "ext": ".html",
    }
    return record


def parse_invoice_html(html: str) -> dict[str, Any]:
    """Parser για ΕΝΑ τιμολόγιο από HTML string."""
    soup = BeautifulSoup(html, _PARSER)
    return _parse_invoice_soup(soup)


def parse_invoice_file(path: str) -> dict[str, Any]:
    """Parser για ΕΝΑ τιμολόγιο από αρχείο .html."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()
    soup = BeautifulSoup(html, _PARSER)
    rec = _parse_invoice_soup(soup)
    rec["source_file"] = os.path.basename(path)
    return rec


def parse_all_invoices(invoices_dir: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for root, _, files in os.walk(invoices_dir):
        for n in files:
            if os.path.splitext(n)[1].lower() in {".html", ".htm"}:
                path = os.path.join(root, n)
                with suppress(Exception):
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        html = f.read()
                    rec = parse_invoice_html(html)
                    rec["source_file"] = os.path.relpath(path, invoices_dir)
                    out.append(rec)
    return out


# ---------- CLI ----------
if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Parse HTML invoices in a folder")
    ap.add_argument("-i", "--input", required=True, help="Folder with .html invoices")
    ap.add_argument("-o", "--out", required=True, help="Output JSON (array)")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    data = parse_all_invoices(args.input)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Parsed {len(data)} invoice(s) -> {args.out}")
