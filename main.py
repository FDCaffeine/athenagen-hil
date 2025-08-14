# main.py
import os, re, json, uuid
from datetime import datetime

from data_parser.parse_emails import parse_all_emails
from data_parser.parse_forms import parse_all_forms
from data_parser.parse_invoices import parse_all_invoices

FORMS_FOLDER    = "dummy_data/forms"
EMAILS_FOLDER   = "dummy_data/emails"
INVOICES_FOLDER = "dummy_data/invoices"
OUT_DIR         = "outputs"
BACKUP_DIR      = os.path.join(OUT_DIR, "_backups")

PARSED_FORMS_PATH    = os.path.join(OUT_DIR, "parsed_forms.json")
PARSED_EMAILS_PATH   = os.path.join(OUT_DIR, "parsed_emails.json")
PARSED_EMAILS_ENR    = os.path.join(OUT_DIR, "parsed_emails_enriched.json")
PARSED_INVOICES_PATH = os.path.join(OUT_DIR, "parsed_invoices.json")
COMBINED_PATH        = os.path.join(OUT_DIR, "combined_feed.json")

ALLOWED_STATUS = ["pending", "approved", "rejected", "edited"]

# ---------- Helpers ----------
def now_iso(): return datetime.now().isoformat(timespec="seconds")
def make_id(prefix): return f"{prefix}_{uuid.uuid4().hex[:12]}"
def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

def backup_existing(path: str):
    if not os.path.exists(path): return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"{os.path.basename(path)}.{ts}.bak")
    try:
        with open(path, "r", encoding="utf-8") as fsrc, open(dst, "w", encoding="utf-8") as fdst:
            fdst.write(fsrc.read())
        print(f"🗄️  Backup: {dst}")
    except Exception as e:
        print(f"[WARN] backup failed for {path}: {e}")

def safe_dump(obj, path):
    ensure_dirs()
    backup_existing(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    print(f"💾 Wrote: {path}")

INV_RE = re.compile(
    r"(?:invoice|τιμολ(?:όγιο|\.?)|αρ\.?\s*τιμολ(?:ογίου)?)\s*(?:no\.?|#|nr\.?|:)?\s*([A-Z]{0,4}[-/]?\d[\w\-\/]+)",
    re.IGNORECASE
)
def extract_inv_no(txt: str) -> str | None:
    if not txt: return None
    m = INV_RE.search(txt)
    return m.group(1).strip() if m else None

def normalize_common(rec: dict, source: str) -> dict:
    r = dict(rec)
    r["source"] = source
    if r.get("status") not in ALLOWED_STATUS:
        r["status"] = "pending"
    r.setdefault("id", make_id(source))
    r.setdefault("created_at", now_iso())
    r.setdefault("schema_version", "1.0")
    r.setdefault("needs_action", False)
    return r

# ---------- Main ----------
def main():
    ensure_dirs()

    # 1) Parse safely
    try:
        forms = parse_all_forms(FORMS_FOLDER)
    except Exception as e:
        print(f"[ERROR] parse_all_forms: {e}"); forms = []

    try:
        emails = parse_all_emails(EMAILS_FOLDER)
    except Exception as e:
        print(f"[ERROR] parse_all_emails: {e}"); emails = []

    try:
        invoices = parse_all_invoices(INVOICES_FOLDER)
    except Exception as e:
        print(f"[ERROR] parse_all_invoices: {e}"); invoices = []

    safe_dump(forms, PARSED_FORMS_PATH)
    safe_dump(emails, PARSED_EMAILS_PATH)
    safe_dump(invoices, PARSED_INVOICES_PATH)

    # 2) Index invoices by number
    inv_by_no = { (r.get("invoice_number") or "").strip(): r for r in invoices if r.get("invoice_number") }

    # 3) Enrich emails (match από subject ΚΑΙ body)
    enriched_emails = []
    for e in emails:
        inv_no = extract_inv_no(e.get("subject","")) or extract_inv_no(e.get("body",""))
        linked = inv_by_no.get(inv_no) if inv_no else None
        enriched = {
            **e,
            "invoice_number_in_subject": inv_no,
            "matched_invoice_html": bool(linked),
            "matched_invoice_file": linked.get("source_file") if linked else None,
            "matched_invoice_total": linked.get("total") if linked else None,
        }

        # needs_action λογική για invoice-like emails
        needs = False
        if enriched.get("email_type") == "invoice":
            if enriched.get("missing_attachment") or not enriched.get("has_pdf_attachments") or not enriched.get("matched_invoice_html"):
                needs = True
        enriched["needs_action"] = needs

        enriched_emails.append(enriched)

    safe_dump(enriched_emails, PARSED_EMAILS_ENR)

    # 4) Normalize & combine
    out = (
        [normalize_common(r, "form")         for r in forms] +
        [normalize_common(r, "email")        for r in enriched_emails] +
        [normalize_common(r, "invoice_html") for r in invoices]
    )

    # σταθερή ταξινόμηση
    try: out.sort(key=lambda x: x.get("created_at",""), reverse=True)
    except Exception: pass

    safe_dump(out, COMBINED_PATH)

    # Summary
    inv_total = round(sum((r.get("total") or 0) for r in invoices), 2)
    matched_cnt = sum(1 for e in enriched_emails if e.get("matched_invoice_html"))
    print(f"\n✅ Outputs in '{OUT_DIR}'")
    print(f"   Forms: {len(forms)} | Emails: {len(emails)} | Invoices: {len(invoices)} | Combined: {len(out)}")
    print(f"   Invoice TOTAL: €{inv_total} | Matched email↔invoice: {matched_cnt}")
    print("   Tip: streamlit run app.py")

if __name__ == "__main__":
    main()
