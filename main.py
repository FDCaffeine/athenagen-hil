# main.py
import argparse
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime
from typing import Any

# --- make stdout/stderr UTF-8 safe on Windows ---
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Local imports
from data_parser.parse_emails import parse_all_emails
from data_parser.parse_forms import parse_all_forms
from data_parser.parse_invoices import parse_all_invoices

# ----------------- Defaults (keep BC for tests/README) -----------------
FORMS_FOLDER_DEF = "dummy_data/forms"
EMAILS_FOLDER_DEF = "dummy_data/emails"
INVOICES_FOLDER_DEF = "dummy_data/invoices"
OUT_DIR_DEF = "outputs"

ALLOWED_STATUS = ["pending", "approved", "rejected", "edited"]

# ----------------- Logging -----------------
LOGGER = logging.getLogger("athenagen")


def setup_logger(out_dir: str, verbose: bool = False) -> None:
    """Set up console + file logging in UTF-8."""
    LOGGER.setLevel(logging.DEBUG)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch_fmt = logging.Formatter("[%(levelname)s] %(message)s")
    ch.setFormatter(ch_fmt)

    # File
    os.makedirs(out_dir, exist_ok=True)
    fh_path = os.path.join(out_dir, "log.txt")
    fh = logging.FileHandler(fh_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fh_fmt)

    # Avoid duplicate handlers if re-called
    LOGGER.handlers.clear()
    LOGGER.addHandler(ch)
    LOGGER.addHandler(fh)


# ----------------- Helpers -----------------
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def ensure_dirs(out_dir: str) -> str:
    backup_dir = os.path.join(out_dir, "_backups")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def backup_existing(path: str, backup_dir: str, enable_backup: bool = True) -> None:
    if not enable_backup or not os.path.exists(path):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"{os.path.basename(path)}.{ts}.bak")
    try:
        with open(path, encoding="utf-8") as fsrc, open(dst, "w", encoding="utf-8") as fdst:
            fdst.write(fsrc.read())
        LOGGER.info(f"[Backup] {dst}")
    except Exception as e:
        LOGGER.warning(f"Backup failed for {path}: {e}")


def safe_dump(obj: Any, path: str, backup_dir: str, enable_backup: bool = True) -> None:
    backup_existing(path, backup_dir, enable_backup)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    LOGGER.info(f"[Wrote] {path}")


INV_RE = re.compile(
    r"(?:invoice|τιμολ(?:όγιο|\.?)|αρ\.?\s*τιμολ(?:ογίου)?)\s*(?:no\.?|#|nr\.?|:)?\s*([A-Z]{0,4}[-/]?\d[\w\-\/]+)",
    re.IGNORECASE,
)


def extract_inv_no(txt: str) -> str | None:
    if not txt:
        return None
    m = INV_RE.search(txt)
    return m.group(1).strip() if m else None


def _force_status(status: Any) -> str:
    return status if status in ALLOWED_STATUS else "pending"


def normalize_common(rec: dict, source: str) -> dict:
    """
    Ενοποιεί κοινά πεδία και ΕΓΓΥΑΤΑΙ ότι θα υπάρχει έγκυρο:
      - source
      - status
      - id (όχι κενό/None)
      - created_at
      - schema_version
      - needs_action
    """
    r = dict(rec)
    r["source"] = source
    r["status"] = _force_status(r.get("status"))
    # πολύ αυστηρό: αν δεν υπάρχει ή είναι "κενό/ψευδές", φτιάξτο
    if not r.get("id"):
        r["id"] = make_id(source)
    r.setdefault("created_at", now_iso())
    r.setdefault("schema_version", "1.0")
    r.setdefault("needs_action", False)
    return r


# ----------------- Core -----------------
def run_pipeline(
    forms_dir: str,
    emails_dir: str,
    invoices_dir: str,
    out_dir: str,
    enable_backup: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Returns a summary dict with counts and totals.
    """
    backup_dir = ensure_dirs(out_dir)

    parsed_forms_path = os.path.join(out_dir, "parsed_forms.json")
    parsed_emails_path = os.path.join(out_dir, "parsed_emails.json")
    parsed_emails_enr = os.path.join(out_dir, "parsed_emails_enriched.json")
    parsed_invoices_path = os.path.join(out_dir, "parsed_invoices.json")
    combined_path = os.path.join(out_dir, "combined_feed.json")

    # 1) Parse safely
    try:
        forms = parse_all_forms(forms_dir)
    except Exception as e:
        LOGGER.error(f"parse_all_forms: {e}")
        forms = []

    try:
        emails = parse_all_emails(emails_dir)
    except Exception as e:
        LOGGER.error(f"parse_all_emails: {e}")
        emails = []

    try:
        invoices = parse_all_invoices(invoices_dir)
    except Exception as e:
        LOGGER.error(f"parse_all_invoices: {e}")
        invoices = []

    if not dry_run:
        safe_dump(forms, parsed_forms_path, backup_dir, enable_backup)
        safe_dump(emails, parsed_emails_path, backup_dir, enable_backup)
        safe_dump(invoices, parsed_invoices_path, backup_dir, enable_backup)
    else:
        LOGGER.info("[Dry-run] Skipped writing parsed_* files")

    # 2) Index invoices by number
    inv_by_no = {
        (r.get("invoice_number") or "").strip(): r for r in invoices if r.get("invoice_number")
    }

    # 3) Enrich emails (match από subject ΚΑΙ body)
    enriched_emails = []
    for e in emails:
        inv_no = extract_inv_no(e.get("subject", "")) or extract_inv_no(e.get("body", ""))
        linked = inv_by_no.get(inv_no) if inv_no else None
        enriched = {
            **e,
            "invoice_number_in_subject": inv_no,
            "matched_invoice_html": bool(linked),
            "matched_invoice_file": linked.get("source_file") if linked else None,
            "matched_invoice_total": linked.get("total") if linked else None,
        }

        # needs_action λογική για invoice-like emails
        needs = enriched.get("email_type") == "invoice" and (
            enriched.get("missing_attachment")
            or not enriched.get("has_pdf_attachments")
            or not enriched.get("matched_invoice_html")
        )
        enriched["needs_action"] = needs

        enriched_emails.append(enriched)

    if not dry_run:
        safe_dump(enriched_emails, parsed_emails_enr, backup_dir, enable_backup)
    else:
        LOGGER.info("[Dry-run] Skipped writing parsed_emails_enriched.json")

    # 4) Normalize & combine
    out = (
        [normalize_common(r, "form") for r in forms]
        + [normalize_common(r, "email") for r in enriched_emails]
        + [normalize_common(r, "invoice_html") for r in invoices]
    )

    # EXTRA SAFETY: δεύτερο πέρασμα για id/status (αν ποτέ κάτι γλιστρήσει)
    for r in out:
        if not r.get("id"):
            r["id"] = make_id(r.get("source", "rec"))
        r["status"] = _force_status(r.get("status"))

    # σταθερή ταξινόμηση
    from contextlib import suppress

    with suppress(Exception):
        out.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    if not dry_run:
        safe_dump(out, combined_path, backup_dir, enable_backup)
    else:
        LOGGER.info("[Dry-run] Skipped writing combined_feed.json")

    # Summary
    inv_total = round(sum((r.get("total") or 0) for r in invoices), 2)
    matched_cnt = sum(1 for e in enriched_emails if e.get("matched_invoice_html"))

    LOGGER.info(f"Outputs in '{out_dir}'")
    LOGGER.info(
        f"Forms: {len(forms)} | Emails: {len(emails)} | "
        f"Invoices: {len(invoices)} | Combined: {len(out)}"
    )
    LOGGER.info(f"Invoice TOTAL: €{inv_total} | Matched email↔invoice: {matched_cnt}")
    LOGGER.info("Tip: streamlit run app.py")

    return {
        "forms": len(forms),
        "emails": len(emails),
        "invoices": len(invoices),
        "combined": len(out),
        "invoice_total": inv_total,
        "matched_email_invoice": matched_cnt,
        "out_dir": out_dir,
    }


# ----------------- CLI -----------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="AthenaGen – Parse & combine inputs into outputs/combined_feed.json"
    )
    p.add_argument("--forms", default=FORMS_FOLDER_DEF, help="Folder with HTML forms")
    p.add_argument("--emails", default=EMAILS_FOLDER_DEF, help="Folder with .eml emails")
    p.add_argument("--invoices", default=INVOICES_FOLDER_DEF, help="Folder with HTML invoices")
    p.add_argument("--out", default=OUT_DIR_DEF, help="Output folder (default: outputs)")
    p.add_argument(
        "--no-backup", action="store_true", help="Disable backups before writing JSON files"
    )
    p.add_argument("--dry-run", action="store_true", help="Run without writing any files")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose console logging")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logger(args.out, verbose=args.verbose)

    try:
        run_pipeline(
            forms_dir=args.forms,
            emails_dir=args.emails,
            invoices_dir=args.invoices,
            out_dir=args.out,
            enable_backup=not args.no_backup,
            dry_run=args.dry_run,
        )
        return 0
    except Exception:
        LOGGER.exception("Pipeline failed with an unhandled exception")
        return 1


if __name__ == "__main__":
    sys.exit(main())
