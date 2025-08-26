#!/usr/bin/env python3

"""
parse_emails.py
Διαβάζει .eml αρχεία, ταξινομεί email σε 'client' ή 'invoice',
και εξάγει βασικά στοιχεία + flag για PDF συνημμένα.
ΤΩΡΑ: Επιστρέφει και body (plain) και body_html (αν υπάρχει).
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import suppress
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from typing import Any

ATTACHMENT_PLACEHOLDER_RE = re.compile(
    r"\[(?:ATTACHMENT|ΣΥΝΗΜΜΕΝΟ)\s*:\s*([^\]\n]+)\]", re.IGNORECASE
)


def find_placeholder_attachments(text: str):
    return [m.group(1).strip() for m in ATTACHMENT_PLACEHOLDER_RE.finditer(text or "")]


HTML_TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
# Ελληνικά & διεθνή formats τηλεφώνων (π.χ. +30 210..., 69xxxxxxxx, 210-xxxxxxx)
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?)?\d{3,4}[\s\-\.]?\d{3,4}")

INVOICE_KEYWORDS = [
    "invoice",
    "pro forma",
    "proforma",
    "receipt",
    "bill",
    "billing",
    "payment",
    "paid",
    "unpaid",
    "quotation",
    "quote",
    "purchase order",
    "po#",
    "tax invoice",
    "τιμολ",
    "απόδειξη",
    "παραστατικ",
    "πληρωμ",
    "εξόφληση",
    "λογαριασμ",
]

INVOICE_SENDER_HINTS = ["billing", "accounts", "invoices", "accounting", "finance"]

SIGNOFF_CUES = [
    # EN
    "best regards",
    "kind regards",
    "regards",
    "thanks",
    "thank you",
    "sincerely",
    # GR
    "με εκτίμηση",
    "ευχαριστώ",
    "καλή συνέχεια",
    "φιλικά",
    "ευχαριστούμε",
]

CLIENT_CUES = [
    "αίτημα",
    "ζητάω",
    "ζητάμε",
    "θέλουμε",
    "ενδιαφέρον",
    "need",
    "request",
    "platform",
    "system",
    "crm",
    "pos",
    "management",
    "proposal",
    "rfp",
]

INV_NUM_RE = re.compile(r"(?:invoice|τιμολ)[^#\w]{0,10}(?:#\s*)?[A-Z]{0,4}-?\d{3,}", re.IGNORECASE)

NOISE_TOKENS = [
    "διεύθυνση",
    "address",
    "θέση",
    "position",
    "role",
    "τηλ",
    "tel",
    "phone",
    "email",
    "www",
    "site",
    "ιστοσελίδα",
    "έδρα",
    "founder",
    "ceo",
    "owner",
    "ιδιοκτήτης",
    "department",
    "τμήμα",
]


def normalize_ws(text: str) -> str:
    return WS_RE.sub(" ", text or "").strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    no_tags = HTML_TAG_RE.sub(" ", text)
    return normalize_ws(no_tags)


def get_bodies(msg) -> tuple[str, str]:
    """
    Επιστρέφει (body_text, body_html).
    - body_text: προτιμά text/plain, αλλιώς καθαρισμένο html
    - body_html: το πρώτο διαθέσιμο text/html (raw)
    """
    text_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if disp == "attachment":
                continue
            payload = ""
            try:
                payload = part.get_content()
            except Exception:
                try:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        payload = payload.decode(
                            part.get_content_charset() or "utf-8", errors="ignore"
                        )
                except Exception:
                    payload = ""
            if ctype == "text/plain":
                text_parts.append(payload or "")
            elif ctype == "text/html":
                html_parts.append(payload or "")
    else:
        ctype = msg.get_content_type()
        payload = ""
        try:
            payload = msg.get_content()
        except Exception:
            try:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                payload = ""
        if ctype == "text/plain":
            text_parts.append(payload or "")
        elif ctype == "text/html":
            html_parts.append(payload or "")

    body_html = html_parts[0] if html_parts else ""
    if text_parts:
        body_text = normalize_ws("\n".join(text_parts))
    elif body_html:
        body_text = strip_html(body_html)
    else:
        body_text = ""

    return body_text, body_html


def has_pdf_attachments_and_names(msg, body_text: str):
    pdf = False
    names = []

    for part in msg.walk():
        disp = part.get_content_disposition()
        if disp in ("attachment", "inline"):
            fname = part.get_filename() or ""
            names.append(fname)
            if part.get_content_type() == "application/pdf" or fname.lower().endswith(".pdf"):
                pdf = True

    ph = find_placeholder_attachments(body_text)
    if ph:
        names.extend(ph)

    return pdf, names, bool(ph)


def guess_email_type(subject: str, body_text: str, from_addr: str, attachment_names) -> str:
    subj = (subject or "").lower()
    bod = (body_text or "").lower()
    local = from_addr.split("@", 1)[0].lower() if "@" in from_addr else from_addr.lower()
    names = [(n or "").lower() for n in (attachment_names or [])]
    pdf_count = sum(1 for n in names if n.endswith(".pdf"))

    score = 0
    if any(kw in subj for kw in INVOICE_KEYWORDS):
        score += 4
    if any(kw in bod for kw in INVOICE_KEYWORDS):
        score += 1
    if INV_NUM_RE.search(subject or ""):
        score += 2
    if any(h in local for h in INVOICE_SENDER_HINTS):
        score += 2
    if pdf_count >= 1:
        score += 3
    if any(("invoice" in n) or ("τιμολ" in n) or ("receipt" in n) for n in names):
        score += 3

    if any(c in subj for c in CLIENT_CUES):
        score -= 2
    if any(c in bod for c in CLIENT_CUES):
        score -= 1

    no_invoice_signals = (
        pdf_count == 0
        and not any(kw in subj for kw in INVOICE_KEYWORDS)
        and not INV_NUM_RE.search(subject or "")
        and not any(("invoice" in n) or ("τιμολ" in n) or ("receipt" in n) for n in names)
        and not any(h in local for h in INVOICE_SENDER_HINTS)
    )
    if no_invoice_signals:
        return "client"

    return "invoice" if score >= 4 else "client"


def extract_email_and_name(from_header: str):
    name, addr = parseaddr(from_header or "")
    return normalize_ws(name), (addr or "").strip().lower()


def extract_phone(text: str) -> str:
    if not text:
        return ""
    candidates = []
    for m in PHONE_RE.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10:
            candidates.append(digits)
    return max(candidates, key=len) if candidates else ""


def titlecase_safe(s: str) -> str:
    if not s:
        return s
    return " ".join(part.capitalize() for part in re.split(r"[\s._-]+", s) if part)


def clean_company(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"[|·•\-–—,:/]", text)
    for p in parts:
        p = normalize_ws(p)
        low = p.lower()
        if p and not any(tok in low for tok in NOISE_TOKENS) and 2 <= len(p) <= 60:
            return p.strip()
    return normalize_ws(parts[0])[:60].strip() if parts else ""


def guess_company(from_name: str, from_email: str, body_text: str) -> str:
    text = body_text or ""
    # 1) υπογραφή
    sig_lines = []
    for cue in SIGNOFF_CUES:
        idx = text.lower().find(cue)
        if idx != -1:
            sig_lines.append(text[idx : idx + 400])
    candidate_block = "\n".join(sig_lines) if sig_lines else text[:800]

    company_patterns = [
        r"(?:company|organization|org|firm|agency|business)\s*[:\-]\s*(.+)",
        r"(?:εταιρεία|οργανισμός)\s*[:\-]\s*(.+)",
        r"(?:at|from)\s+([A-Z][\w&.,\- ]{2,50})",
    ]
    for pat in company_patterns:
        m = re.search(pat, candidate_block, flags=re.IGNORECASE)
        if m:
            c = normalize_ws(m.group(1))
            c = re.split(
                r"(?:email|e-mail|τηλ|tel|phone|mobile|mob|www|site|address)[:\s]",
                c,
                flags=re.IGNORECASE,
            )[0]
            return c.strip(" -|·:;,")

    # domain -> brand guess
    domain = from_email.split("@", 1)[-1] if "@" in from_email else ""
    base = domain.split(":")[-1].split("/")[-1]
    if base:
        parts = base.split(".")
        if len(parts) >= 2:
            core = parts[-2]
            if core in {"mail", "gmail", "yahoo", "hotmail", "outlook", "live"} and len(parts) >= 3:
                core = parts[-3]
            company = titlecase_safe(core)
            return company

    if from_name and len(from_name.split()) <= 2 and not any(ch in from_name for ch in "@<>"):
        return from_name

    return ""


def guess_person_name(from_name: str, body_text: str) -> str:
    if from_name and len(from_name) >= 2:
        return from_name

    low = (body_text or "").lower()
    for cue in SIGNOFF_CUES:
        i = low.find(cue)
        if i != -1:
            tail = body_text[i : i + 240]
            lines = [normalize_ws(line) for line in tail.splitlines()]
            lines = [line for line in lines if line and line.lower() not in SIGNOFF_CUES]
            if len(lines) >= 2:
                candidate = lines[1]
                if 2 <= len(candidate) <= 60 and not any(
                    tok in candidate.lower()
                    for tok in ["tel", "phone", "email", "@", "www", "http"]
                ):
                    return candidate
    return ""


def parse_eml_file(path: str) -> dict:
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    subject = msg.get("Subject", "")
    date = msg.get("Date", "")
    from_header = msg.get("From", "")
    from_name, from_email = extract_email_and_name(from_header)

    # NEW: πάρ’ τα δύο σώματα
    body_text, body_html = get_bodies(msg)

    has_pdf, attachment_names, has_placeholder = has_pdf_attachments_and_names(msg, body_text)
    email_type = guess_email_type(subject, body_text, from_email, attachment_names)

    phone = extract_phone(subject + "\n" + body_text)
    company = guess_company(from_name, from_email, body_text)
    person = guess_person_name(from_name, body_text)
    company = clean_company(company)

    full_name = person or from_name or ""

    # ένα μικρό preview για λίστες/αναζήτηση
    preview_len = 500
    body_preview = (body_text[:preview_len] + "…") if len(body_text) > preview_len else body_text

    record = {
        "full_name": full_name,
        "email": from_email,
        "phone": phone,
        "company": company,
        "email_type": email_type,  # 'client' | 'invoice'
        "has_pdf_attachments": bool(has_pdf),
        "attachment_names": attachment_names,
        "attachment_placeholder_only": (not has_pdf) and has_placeholder,
        "missing_attachment": (not has_pdf) and has_placeholder,
        "subject": normalize_ws(subject),
        "date": date,
        "source_file": os.path.basename(path),
        # NEW fields
        "body": body_text,  # plain text (καθαρισμένο)
        "body_html": body_html,  # raw html αν υπάρχει
        "body_preview": body_preview,
    }
    return record


def iter_eml_files(root: str) -> Iterator[str]:
    for r, _, files in os.walk(root):
        for n in files:
            if n.lower().endswith(".eml"):
                yield os.path.join(r, n)


def parse_all_emails(emails_dir: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for eml_path in iter_eml_files(emails_dir):
        with suppress(Exception):
            results.append(parse_eml_file(eml_path))
    return results


def main():
    parser = argparse.ArgumentParser(description="Parse .eml files and extract basic info.")
    parser.add_argument(
        "--input", "-i", required=True, help="Path to .eml file or directory containing .eml files"
    )
    parser.add_argument("--out", "-o", required=True, help="Output JSONL path")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    count = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for eml_path in iter_eml_files(args.input):
            try:
                rec = parse_eml_file(eml_path)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
            except Exception as e:
                sys.stderr.write(f"[WARN] Failed to parse {eml_path}: {e}\n")

    print(f"✅ Parsed {count} email(s) -> {args.out}")


if __name__ == "__main__":
    main()
