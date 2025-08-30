# app.py
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import Any

import pandas as pd  # για data_editor/exports
import streamlit as st
import streamlit.components.v1 as components

from settings import BACKUPS_DIR, EXPORTS_DIR, LOG_PATH, OUTPUTS_DIR
from settings import COMBINED_PATH as DATA_PATH
from settings import EMAILS_DIR as DUMMY_EMAILS_DIR
from settings import FORMS_DIR as DUMMY_FORMS_DIR
from settings import INVOICES_DIR as DUMMY_INVOICES_DIR

# ---------- Προαιρετικά: Fuzzy matching & Validation ----------
HAS_MATCHING = False
HAS_VALIDATION = False

try:
    from data_parser.matching import build_invoice_lookup as _build_lookup_ext
    from data_parser.matching import fuzzy_find as _fuzzy_find_ext
    from data_parser.matching import normalize_inv as _norm_inv_ext

    HAS_MATCHING = True
except Exception:

    def _norm_inv_ext(s: str | None) -> str:
        if not s:
            return ""
        return "".join(ch for ch in str(s).upper() if ch.isalnum())

    def _build_lookup_ext(invoices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            _norm_inv_ext(r.get("invoice_number")): r
            for r in invoices
            if r.get("source") == "invoice_html" and r.get("invoice_number")
        }

    def _fuzzy_find_ext(
        candidate: str, lookup: dict[str, Any], score_cutoff: int = 0
    ) -> tuple[dict[str, Any] | None, int]:
        key = _norm_inv_ext(candidate)
        if key in lookup:
            return lookup[key], 100
        for k, rec in lookup.items():
            if key and (key in k or k in key):
                return rec, 80
        return None, 0


try:
    from data_parser.validation import validate_email_record as _validate_email_ext
    from data_parser.validation import validate_form_record as _validate_form_ext
    from data_parser.validation import validate_invoice_record as _validate_invoice_ext

    HAS_VALIDATION = True
except Exception:

    def _validate_email_ext(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        return d, []

    def _validate_form_ext(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        return d, []

    def _validate_invoice_ext(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        return d, []


ALLOWED_STATUS = ["pending", "approved", "rejected", "edited"]

# ---------- Multi-language (EL/EN) ----------
I18N = {
    "EL": {
        "LANG": "Γλώσσα",
        "EL": "Ελληνικά",
        "EN": "Αγγλικά",
        "FILTERS": "Φίλτρα",
        "SOURCE_LABEL": "Πηγή (source)",
        "STATUS": "Κατάσταση",
        "APPLY_STATUS": "Εφαρμογή κατάστασης",
        "APPROVE": "Έγκριση",
        "REJECT": "Απόρριψη",
        "ACTIONS": "Ενέργειες",
        "RESULTS": "Αποτελέσματα",
        "RECORD": "Εγγραφή",
        "SEARCH": "Αναζήτηση (subject, όνομα, email, εταιρεία)",
        "SORT_BY": "Ταξινόμηση κατά",
        "DESC_SORT": "Φθίνουσα ταξινόμηση",
        "NEEDS_ACTION_ONLY": "Μόνο εγγραφές που χρειάζονται ενέργεια (π.χ. invoice email χωρίς PDF)",
        "RECORD_DETAILS": "Πλήρη στοιχεία",
        "EMAIL_CONTENT": "Περιεχόμενο Email (Plain Text)",
        "READABILITY_FORMAT": "Μορφοποίηση για ανάγνωση",
        "MESSAGE_BODY": "Μήνυμα",
        "SELLER": "Εκδότης",
        "BUYER": "Πελάτης",
        "INVOICE_NUMBER": "Αριθμός",
        "DATE": "Ημερομηνία",
        "PAYMENT_METHOD": "Πληρωμή",
        "ITEM_LINES": "Γραμμές προϊόντων (inline edit)",
        "CURRENCY_LABEL": "Νόμισμα τιμολογίου",
        "VAT_PERCENT": "ΦΠΑ %",
        "NET_CALC": "Καθαρή Αξία (υπολογ.)",
        "VAT_CALC": "ΦΠΑ (υπολογ.)",
        "TOTAL_CALC": "Σύνολο (υπολογ.)",
        "SAVE_ITEMS_CALC": "Αποθήκευση γραμμών & υπολογισμών",
        "SUMMARY": "Σύνοψη",
        "NET": "Καθαρή Αξία",
        "VAT": "ΦΠΑ",
        "TOTAL": "Σύνολο",
        "CURRENCY": "Νόμισμα",
        "INVOICE_META_EDITOR": "Edit στοιχεία τιμολογίου (εκδότης/πελάτης/πληρωμή)",
        "SELLER_NAME": "Επωνυμία Εκδότη",
        "SELLER_EMAIL": "Email Εκδότη",
        "SELLER_PHONE": "Τηλέφωνο Εκδότη",
        "SELLER_VAT": "ΑΦΜ Εκδότη",
        "SELLER_TAX_OFFICE": "ΔΟΥ Εκδότη",
        "SELLER_ADDRESS": "Διεύθυνση Εκδότη",
        "BUYER_NAME": "Επωνυμία Πελάτη",
        "BUYER_VAT": "ΑΦΜ Πελάτη",
        "BUYER_ADDRESS": "Διεύθυνση Πελάτη",
        "SAVE_INVOICE_META": "Αποθήκευση στοιχείων τιμολογίου",
        "FOOTER_NOTES": "Extra πεδία/σημειώσεις από footer",
        "SAVE_FOOTER_NOTES": "Αποθήκευση footer/σημειώσεων",
        "INVOICE_PREVIEW": "Προεπισκόπηση Τιμολογίου (HTML)",
        "DOWNLOAD_INVOICE_HTML": "⬇️ Λήψη HTML τιμολογίου",
        "SAFE_EDIT": "Edit πεδία (safe form)",
        "FULL_NAME": "Ονοματεπώνυμο",
        "EMAIL": "Email",
        "PHONE": "Τηλέφωνο",
        "COMPANY": "Εταιρεία",
        "SERVICE": "Υπηρεσία Ενδιαφέροντος",
        "SUBJECT_LABEL": "Θέμα",
        "MESSAGE": "Μήνυμα",
        "SUBMISSION_DATE": "Ημερομηνία Υποβολής (datetime-local)",
        "PRIORITY": "Προτεραιότητα",
        "INVOICE_NUMBER_FIELD": "Αριθμός Τιμολογίου",
        "TOTAL_FIELD": "Σύνολο",
        "SAVE_CHANGES": "Αποθήκευση αλλαγών (Edit)",
        "NOTES": "Σημειώσεις (προαιρετικά)",
        "SAVE_NOTES": "Αποθήκευση σημειώσεων",
        "EXPORT": "Εξαγωγή",
        "FILTERED": "Φιλτραρισμένα",
        "ALL": "Όλα",
        "DESTINATION": "Προορισμός",
        "DEST_CSV": "CSV",
        "DEST_XLSX": "Excel",
        "DEST_GSHEETS": "Φύλλα Google",
        "SAVE_COPY": "Αποθήκευση αντιγράφου στο exports/",
        "FILENAME_PREFIX": "Όνομα αρχείου (πρόθεμα)",
        "RUN_EXPORT": "Εκτέλεση εξαγωγής",
        "LAST_EXPORT": "Τελευταία εξαγωγή",
        "DOWNLOAD_FILE": "Λήψη αρχείου",
        "TARGET_SHEET": "Φύλλο προορισμού",
        "OPEN_IN_GSHEETS": "Άνοιγμα στα Φύλλα Google",
        "WORKSHEET": "Φύλλο εργασίας",
        "UPLOAD_MODE": "Τρόπος ανεβάσματος",
        "REPLACE": "Αντικατάσταση",
        "APPEND": "Προσθήκη",
        "TARGET_SHEET_CAPTION": "🎯 Φύλλο Προορισμού:",
        "NEED_CREDS": "Δεν βρέθηκαν Google credentials. Ρύθμισε Env/Secrets ή επικόλλησε το JSON.",
        "EXPORT_READY_CSV": "✅ Έτοιμο CSV ({rows} γραμμές). Δες το κουμπί λήψης παρακάτω.",
        "EXPORT_READY_XLSX": "✅ Έτοιμο Excel ({rows} γραμμές). Δες το κουμπί λήψης παρακάτω.",
        "EXPORT_READY_GS": "✅ Ανέβηκαν {rows} γραμμές στο φύλλο «{ws}» ({mode}).",
        "PRODUCT_DESC": "Περιγραφή",
        "QUANTITY": "Ποσότητα",
        "UNIT_PRICE": "Τιμή Μονάδας",
        "LINE_TOTAL": "Γραμμή Σύνολο",
    },
    "EN": {
        "LANG": "Language",
        "EL": "Greek",
        "EN": "English",
        "FILTERS": "Filters",
        "SOURCE_LABEL": "Source",
        "STATUS": "Status",
        "APPLY_STATUS": "Apply status",
        "APPROVE": "Approve",
        "REJECT": "Reject",
        "ACTIONS": "Actions",
        "RESULTS": "Results",
        "RECORD": "Record",
        "SEARCH": "Search (subject, name, email, company)",
        "SORT_BY": "Sort by",
        "DESC_SORT": "Descending",
        "NEEDS_ACTION_ONLY": "Only records needing action (e.g., invoice email without PDF)",
        "RECORD_DETAILS": "Record details",
        "EMAIL_CONTENT": "Email content (plain text)",
        "READABILITY_FORMAT": "Readability formatting",
        "MESSAGE_BODY": "Message",
        "SELLER": "Seller",
        "BUYER": "Buyer",
        "INVOICE_NUMBER": "Number",
        "DATE": "Date",
        "PAYMENT_METHOD": "Payment",
        "ITEM_LINES": "Line items (inline edit)",
        "CURRENCY_LABEL": "Invoice currency",
        "VAT_PERCENT": "VAT %",
        "NET_CALC": "Net (calc.)",
        "VAT_CALC": "VAT (calc.)",
        "TOTAL_CALC": "Total (calc.)",
        "SAVE_ITEMS_CALC": "Save items & totals",
        "SUMMARY": "Summary",
        "NET": "Net",
        "VAT": "VAT",
        "TOTAL": "Total",
        "CURRENCY": "Currency",
        "INVOICE_META_EDITOR": "Edit invoice meta (seller/buyer/payment)",
        "SELLER_NAME": "Seller name",
        "SELLER_EMAIL": "Seller email",
        "SELLER_PHONE": "Seller phone",
        "SELLER_VAT": "Seller VAT",
        "SELLER_TAX_OFFICE": "Seller tax office",
        "SELLER_ADDRESS": "Seller address",
        "BUYER_NAME": "Buyer name",
        "BUYER_VAT": "Buyer VAT",
        "BUYER_ADDRESS": "Buyer address",
        "SAVE_INVOICE_META": "Save invoice meta",
        "FOOTER_NOTES": "Footer extra fields/notes",
        "SAVE_FOOTER_NOTES": "Save footer/notes",
        "INVOICE_PREVIEW": "Invoice preview (HTML)",
        "DOWNLOAD_INVOICE_HTML": "⬇️ Download invoice HTML",
        "SAFE_EDIT": "Edit fields (safe form)",
        "FULL_NAME": "Full name",
        "EMAIL": "Email",
        "PHONE": "Phone",
        "COMPANY": "Company",
        "SERVICE": "Service interest",
        "SUBJECT_LABEL": "Subject",
        "MESSAGE": "Message",
        "SUBMISSION_DATE": "Submission date (datetime-local)",
        "PRIORITY": "Priority",
        "INVOICE_NUMBER_FIELD": "Invoice number",
        "TOTAL_FIELD": "Total",
        "SAVE_CHANGES": "Save changes (Edit)",
        "NOTES": "Notes (optional)",
        "SAVE_NOTES": "Save notes",
        "EXPORT": "Export",
        "FILTERED": "Filtered",
        "ALL": "All",
        "DESTINATION": "Destination",
        "DEST_CSV": "CSV",
        "DEST_XLSX": "Excel",
        "DEST_GSHEETS": "Google Sheets",
        "SAVE_COPY": "Save a copy to exports/",
        "FILENAME_PREFIX": "File name (prefix)",
        "RUN_EXPORT": "Run export",
        "LAST_EXPORT": "Last export",
        "DOWNLOAD_FILE": "Download file",
        "TARGET_SHEET": "Target sheet",
        "OPEN_IN_GSHEETS": "Open in Google Sheets",
        "WORKSHEET": "Worksheet",
        "UPLOAD_MODE": "Upload mode",
        "REPLACE": "Replace",
        "APPEND": "Append",
        "TARGET_SHEET_CAPTION": "🎯 Target Sheet:",
        "NEED_CREDS": "No Google credentials found. Set Env/Secrets or paste the JSON.",
        "EXPORT_READY_CSV": "✅ CSV ready ({rows} rows). Use the download button below.",
        "EXPORT_READY_XLSX": "✅ Excel ready ({rows} rows). Use the download button below.",
        "EXPORT_READY_GS": "✅ Uploaded {rows} rows to worksheet “{ws}” ({mode}).",
        "PRODUCT_DESC": "Description",
        "QUANTITY": "Quantity",
        "UNIT_PRICE": "Unit price",
        "LINE_TOTAL": "Line total",
    },
}

STATUS_LABELS = {
    "EL": {
        "pending": "Σε εκκρεμότητα",
        "approved": "Εγκρίθηκε",
        "rejected": "Απορρίφθηκε",
        "edited": "Τροποποιήθηκε",
    },
    "EN": {
        "pending": "Pending",
        "approved": "Approved",
        "rejected": "Rejected",
        "edited": "Edited",
    },
}


def _get_lang() -> str:
    return st.session_state.get("ui_lang", "EL")


def _set_lang(lang: str) -> None:
    st.session_state["ui_lang"] = "EL" if lang not in ("EL", "EN") else lang


def t(key: str) -> str:
    lang = _get_lang()
    return I18N.get(lang, {}).get(key, key)


def status_to_label(status_key: str) -> str:
    lang = _get_lang()
    return STATUS_LABELS.get(lang, {}).get(status_key, status_key)


def label_to_status(label: str) -> str:
    lang = _get_lang()
    m = STATUS_LABELS.get(lang, {})
    for k, v in m.items():
        if v == label:
            return k
    return label


# ---------- Utilities ----------
def ensure_dirs() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- Normalization helpers (ίδιο πνεύμα με main.py) ---
def _normalize_common(rec: dict[str, Any], source: str) -> dict[str, Any]:
    out = dict(rec)
    out["source"] = source
    if out.get("status") not in ALLOWED_STATUS:
        out["status"] = "pending"
    if not out.get("id"):
        out["id"] = make_id(source)
    out.setdefault("created_at", now_iso())
    out.setdefault("schema_version", "1.0")
    out.setdefault("needs_action", False)
    if source == "email" and out.get("email_type") == "invoice":
        needs = (
            out.get("missing_attachment")
            or not out.get("has_pdf_attachments")
            or not out.get("matched_invoice_html")
        )
        out["needs_action"] = bool(needs)
    return out


def _harden_list(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hardened: list[dict[str, Any]] = []
    for r in recs:
        src = r.get("source") or (
            "email" if "email_type" in r else ("invoice_html" if "invoice_number" in r else "form")
        )
        hardened.append(_normalize_common(r, src))
    return hardened


def log_action(action: str, details: dict | None = None, level: str = "INFO") -> None:
    try:
        ensure_dirs()
        line = {"ts": now_iso(), "level": level, "action": action, "details": details or {}}
        with Path(LOG_PATH).open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ui_error(msg: str, action: str = "error", details: dict | None = None) -> None:
    st.error(msg)
    log_action(action, details=details, level="ERROR")


def ui_warn(msg: str, action: str = "warning", details: dict | None = None) -> None:
    st.warning(msg)
    log_action(action, details=details, level="WARN")


def ui_info(msg: str, action: str = "info", details: dict | None = None) -> None:
    st.info(msg)
    log_action(action, details=details, level="INFO")


def _norm_invoice_no_local(s: str | None) -> str:
    if not s:
        return ""
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def load_data() -> list[dict[str, Any]]:
    ensure_dirs()
    data_path = Path(DATA_PATH)
    if not data_path.exists():
        ui_warn(
            "Δεν βρέθηκε το outputs/combined_feed.json. Ξεκινάμε με κενή λίστα.", "data_missing"
        )
        return []
    try:
        with data_path.open(encoding="utf-8") as f:
            data: list[dict[str, Any]] = json.load(f)
    except json.JSONDecodeError as e:
        ui_error(
            "Το αρχείο δεδομένων είναι χαλασμένο (JSON). Θα φορτωθεί κενή λίστα.",
            "json_decode_error",
            {"error": str(e)},
        )
        return []
    except Exception as e:
        ui_error("Αποτυχία φόρτωσης δεδομένων.", "load_data_error", {"error": str(e)})
        return []

    try:
        for rec in data:
            if "source" not in rec:
                if "email_type" in rec:
                    rec["source"] = "email"
                elif "invoice_number" in rec:
                    rec["source"] = "invoice_html"
                else:
                    rec["source"] = "form"
            if "status" not in rec or rec["status"] not in ALLOWED_STATUS:
                rec["status"] = "pending"
            if "id" not in rec or not rec["id"]:
                rec["id"] = make_id(rec["source"])
            if "created_at" not in rec:
                rec["created_at"] = now_iso()
            if "schema_version" not in rec:
                rec["schema_version"] = "1.0"

            needs = (
                rec.get("source") == "email"
                and rec.get("email_type") == "invoice"
                and (rec.get("missing_attachment") or not rec.get("matched_invoice_html"))
            )
            rec["needs_action"] = bool(needs)
    except Exception as e:
        ui_error(
            "Σφάλμα στη σκλήρυνση (hardening) των εγγραφών.",
            "harden_records_error",
            {"error": str(e)},
        )

    return data


def backup_data(data: list[dict[str, Any]]) -> None:
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = BACKUPS_DIR / f"combined_feed_{ts}.json"
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log_action("backup_data", {"path": str(p)})
    except Exception as e:
        ui_warn(
            "Αποτυχία δημιουργίας backup. Συνεχίζουμε με αποθήκευση.",
            "backup_error",
            {"error": str(e)},
        )


def save_data(data: list[dict[str, Any]]):
    backup_data(data)
    try:
        hardened = _harden_list(data)  # <- πάντα σκλήρυνση πριν το γράψιμο
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(hardened, f, indent=2, ensure_ascii=False)
        log_action("save_data", {"path": DATA_PATH, "count": len(hardened)})
    except Exception as e:
        ui_error("Αποτυχία αποθήκευσης δεδομένων.", "save_data_error", {"error": str(e)})


def dump_json_artifact(filename: str, payload: Any) -> str | None:
    """
    Γράφει JSON στο outputs/<filename> με ασφαλή UTF-8 και indent, και log.
    Το root του outputs το παίρνουμε από το DATA_PATH για να παίζει σε όλα τα setups.
    """
    try:
        ensure_dirs()
        outputs_root = Path(DATA_PATH).parent
        path = outputs_root / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        log_action(
            "dump_json_artifact",
            {
                "file": filename,
                "path": str(path),
                "count": (len(payload) if isinstance(payload, list | dict) else None),
            },
        )
        return str(path)
    except Exception as e:
        ui_warn(
            "Αποτυχία αποθήκευσης ενδιάμεσου JSON.",
            "dump_json_error",
            {"file": filename, "error": str(e)},
        )
        return None


def find_index_by_id(data: list[dict[str, Any]], rec_id: str) -> int:
    for i, r in enumerate(data):
        if r.get("id") == rec_id:
            return i
    return -1


def parse_total_input(val: str, fallback):
    try:
        clean = str(val).replace("€", "").replace(" ", "").replace(",", "")
        return float(clean)
    except Exception:
        return fallback


def find_invoice_record_index_by_number(data: list[dict[str, Any]], inv_no: str) -> int | None:
    if not inv_no:
        return None
    inv_no_norm = _norm_invoice_no_local(inv_no)
    for i, r in enumerate(data):
        if (
            r.get("source") == "invoice_html"
            and _norm_invoice_no_local(r.get("invoice_number")) == inv_no_norm
        ):
            return i
    return None


# ----- Template helpers -----
def read_template_columns(path: str | PathLike[str]) -> list[str] | None:
    p = str(path)
    if not os.path.exists(p):
        return None
    try:
        df0 = pd.read_csv(p, nrows=0, sep=None, engine="python", encoding="utf-8-sig")
        cols = [str(c).strip() for c in list(df0.columns)]
        return cols or None
    except Exception:
        try:
            with open(p, encoding="utf-8-sig", errors="ignore") as f:
                first = f.readline().strip()
            if not first:
                return None
            if ";" in first:
                parts = first.split(";")
            elif "\t" in first:
                parts = first.split("\t")
            else:
                parts = first.split(",")
            return [p.strip() for p in parts]
        except Exception:
            return None


def _norm(s: str) -> str:
    # Αποφυγή walrus για συμβατότητα με εργαλεία/παρσάρισμα
    s2 = s.lower().strip()
    return "".join(ch for ch in s2 if ch.isalnum())


def build_template_mapping(template_cols: list[str]) -> dict[str, str]:
    canonical = {
        "type": "type",
        "source": "source",
        "date": "date",
        "ημερομηνια": "date",
        "clientname": "client_name",
        "fullname": "client_name",
        "fromname": "client_name",
        "name": "client_name",
        "company": "company",
        "buyername": "company",
        "sellername": "company",
        "service": "service_interest",
        "serviceinterest": "service_interest",
        "amount": "amount",
        "net": "amount",
        "netamount": "amount",
        "subtotal": "amount",
        "καθαρηαξια": "amount",
        "vat": "vat",
        "vatamount": "vat",
        "φπα": "vat",
        "total": "total_amount",
        "totalamount": "total_amount",
        "συνολο": "total_amount",
        "invoicenumber": "invoice_number",
        "invoice": "invoice_number",
        "αρτιμολ": "invoice_number",
        "message": "message",
        "notes": "message",
        "email": "email",
        "phone": "phone",
        "subject": "subject",
        "status": "status",
        "sourcefile": "source_file",
        "id": "id",
    }
    mapping: dict[str, str] = {}
    for col in template_cols:
        key = _norm(col)
        mapping[col] = canonical.get(key, "")
    return mapping


def _coalesce(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return ""


def _as_date_str(v):
    if not v:
        return ""
    s = str(v).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    if " " in s and len(s.split(" ", 1)[0]) >= 8:
        s = s.split(" ", 1)[0]
    return s


def _as_float(v):
    try:
        if v in ("", None):
            return ""
        return float(v)
    except Exception:
        return ""


def build_template_df(
    records: list[dict[str, Any]],
    template_cols: list[str],
    invoice_index: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    header_map = build_template_mapping(template_cols)

    def _lookup_invoice(inv_no: str | None) -> dict[str, Any] | None:
        if not invoice_index:
            return None
        if not inv_no or not isinstance(inv_no, str):
            return None
        inv_key = inv_no
        return invoice_index.get(inv_key) or invoice_index.get(_norm_invoice_no_local(inv_key))

    rows: list[dict[str, Any]] = []

    for r in records:
        src = (r.get("source") or "").strip()

        # --- date ---
        if src == "form":
            date_val = _coalesce(r.get("submission_date"), r.get("created_at"))
        elif src == "email":
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        else:
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        date_val = _as_date_str(date_val)

        # --- type ---
        if src == "invoice_html":
            type_val = "invoice"
        elif src == "email":
            type_val = _coalesce(r.get("email_type"), "email")
        else:
            type_val = "form"

        # --- identity fields ---
        client_name = _coalesce(
            r.get("buyer_name"),
            r.get("full_name"),
            r.get("name"),
            r.get("from_name"),
        )
        company = _coalesce(r.get("company"), r.get("buyer_name"), r.get("seller_name"))
        service_interest = _coalesce(r.get("service"), r.get("service_interest"))

        # --- invoice number (as string ή κενό) ---
        inv_no_val = _coalesce(r.get("invoice_number"), r.get("invoice_number_in_subject"))
        inv_no_str = str(inv_no_val) if inv_no_val != "" else ""

        # --- amounts ---
        if src == "invoice_html":
            amount = _as_float(r.get("subtotal"))
            vat = _as_float(r.get("vat_amount"))
            total_amount = _as_float(_coalesce(r.get("total")))
        elif src == "email":
            inv_rec = _lookup_invoice(inv_no_str if inv_no_str else None)
            if inv_rec:
                amount = _as_float(inv_rec.get("subtotal"))
                vat = _as_float(inv_rec.get("vat_amount"))
                total_amount = _as_float(inv_rec.get("total"))
            else:
                amount = ""
                vat = ""
                total_amount = _as_float(_coalesce(r.get("matched_invoice_total"), r.get("total")))
        else:
            amount = ""
            vat = ""
            total_amount = ""

        # --- message ---
        if src == "form":
            message = _coalesce(r.get("message"))
        elif src == "email":
            message = _coalesce(r.get("body"))
        else:
            notes = r.get("extra_notes") or []
            if isinstance(notes, list) and notes:
                try:
                    message = " | ".join(
                        [
                            f"{(n or {}).get('label', '')}: {(n or {}).get('value', '')}".strip(
                                ": "
                            ).strip()
                            for n in notes
                        ]
                    )
                except Exception:
                    message = ""
            else:
                message = ""

        email = _coalesce(r.get("email"))
        phone = _coalesce(r.get("phone"))
        subject = _coalesce(r.get("subject"))
        status = _coalesce(r.get("status"))
        source_file = _coalesce(r.get("source_file"))
        rid = _coalesce(r.get("id"))

        internal_values = {
            "type": type_val,
            "source": src,
            "date": date_val,
            "client_name": client_name,
            "company": company,
            "service_interest": service_interest,
            "amount": amount,
            "vat": vat,
            "total_amount": total_amount,
            "invoice_number": inv_no_str,
            "message": message,
            "email": email,
            "phone": phone,
            "subject": subject,
            "status": status,
            "source_file": source_file,
            "id": rid,
        }

        row: dict[str, Any] = {}
        for col in template_cols:
            internal_key = header_map.get(col, "")
            if internal_key:
                row[col] = internal_values.get(internal_key, "")
            else:
                raw_try = r.get(col)
                if raw_try is None:
                    norm_col = _norm(col)
                    found = ""
                    for k, v in r.items():
                        if _norm(str(k)) == norm_col:
                            found = v
                            break
                    row[col] = found
                else:
                    row[col] = raw_try

        rows.append(row)

    return pd.DataFrame(rows, columns=template_cols)


def pretty_email_body(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"(Προσωπ(ικά|ικα)\s+Στοιχεί(α|α)\s*:)", r"\n\1\n", s, flags=re.IGNORECASE)
    s = re.sub(r"(Το\s+προβλ(η|ή)μα\s+μας\s*:)", r"\n\1\n", s, flags=re.IGNORECASE)
    s = re.sub(r"(Θ(έ|ε)λ(ο|ου)με\s+σ(ύ|υ)στημα\s+που\s*:?)", r"\n\1\n", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<!\d)\s-\s(?!\d)", "\n• ", s)
    s = re.sub(r"\s(?=\d+\.\s)", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


# ---------- Google Sheets helpers ----------
GSPREAD_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _parse_sheet_id(sheet_url_or_id: str) -> str:
    s = (sheet_url_or_id or "").strip()
    if not s:
        return ""
    m = re.search(r"/d/([a-zA-Z0-9-_]+)/", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", s)
    if m:
        return m.group(1)
    return s


def _detect_creds_from_sources(pasted_json: str | None) -> tuple[dict | None, str | None]:
    try:
        if "gcp_service_account" in st.secrets:
            raw = st.secrets["gcp_service_account"]
            d = json.loads(raw) if isinstance(raw, str) else dict(raw)
            return d, d.get("client_email")
    except Exception:
        pass
    try:
        env_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if env_raw:
            d = json.loads(env_raw)
            return d, d.get("client_email")
    except Exception:
        pass
    try:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.exists(cred_path):
            with open(cred_path, encoding="utf-8") as f:
                d = json.load(f)
            return d, d.get("client_email")
    except Exception:
        pass
    if pasted_json:
        try:
            d = json.loads(pasted_json)
            return d, d.get("client_email")
        except Exception:
            return None, None
    return None, None


def _build_client(creds_dict: dict):
    try:
        import gspread  # lazy import
        from google.oauth2.service_account import Credentials
    except Exception as e:
        raise RuntimeError(
            "Λείπουν οι βιβλιοθήκες gspread / google-auth. Τρέξε: pip install gspread google-auth"
        ) from e

    creds = Credentials.from_service_account_info(creds_dict, scopes=GSPREAD_SCOPES)
    gc = gspread.authorize(creds)
    # Επιστρέφουμε και το WorksheetNotFound για χρήση στο except χωρίς global import
    return gc, gspread.WorksheetNotFound


def upload_dataframe_to_sheet(
    df: pd.DataFrame,
    sheet_id: str,
    worksheet_name: str,
    creds_dict: dict,
    mode: str = "replace",
):
    gc, WorksheetNotFound = _build_client(creds_dict)
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except WorksheetNotFound:
        ws = sh.add_worksheet(
            title=worksheet_name,
            rows=max(len(df) + 10, 1000),
            cols=max(len(df.columns) + 5, 26),
        )
    values = [list(df.columns)] + df.astype(object).where(pd.notnull(df), "").values.tolist()
    if mode == "replace":
        ws.clear()
        ws.update(range_name="A1", values=values, value_input_option="RAW")
    else:
        existing_records = ws.get_all_values()
        start_row = len(existing_records) + 1
        if start_row == 1:
            ws.update(range_name="A1", values=values, value_input_option="RAW")
        else:
            ws.update(range_name=f"A{start_row}", values=values[1:], value_input_option="RAW")
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={ws.id}"


def run_app() -> None:
    # ------------- App -------------
    st.set_page_config(page_title="AthenaGen HIL Review", layout="wide")

    st.title("AthenaGen – Human-in-the-Loop Review")
    st.caption("Δες/επιβεβαίωσε/διόρθωσε εγγραφές από φόρμες, emails και τιμολόγια.")

    data = load_data()

    # index για parsed τιμολόγια (raw + normalized) — explicit types + None-safety
    invoice_index: dict[str, dict[str, Any]] = {}
    invoice_index_combined: dict[str, dict[str, Any]] = {}
    try:
        invoice_index = {
            str(r["invoice_number"]): r
            for r in data
            if r.get("source") == "invoice_html" and r.get("invoice_number")
        }
        invoice_index_norm: dict[str, dict[str, Any]] = {
            _norm_invoice_no_local(str(r["invoice_number"])): r
            for r in data
            if r.get("source") == "invoice_html" and r.get("invoice_number")
        }

        # normalized wins for lookups, but keep raw too
        invoice_index_combined = {**invoice_index_norm, **invoice_index}
    except Exception as exc:
        ui_warn("Σφάλμα δημιουργίας invoice index.", "invoice_index_error", {"error": str(exc)})

    # Sidebar (Filters / Rebuild)
    with st.sidebar:
        # --- Language switch (one-click, instant) ---
        current_lang = _get_lang()
        lang_choice = st.radio(
            t("LANG"),
            options=["EL", "EN"],
            index=(0 if current_lang == "EL" else 1),
            horizontal=True,
            format_func=lambda code: I18N.get(current_lang, {}).get(code, code),
            key="lang_radio",
        )
        if lang_choice != current_lang:
            _set_lang(lang_choice)
            st.rerun()

        st.header(t("FILTERS"))
        sources = st.multiselect(
            t("SOURCE_LABEL"),
            options=["form", "email", "invoice_html"],
            default=["form", "email", "invoice_html"],
        )
        statuses = st.multiselect(
            t("STATUS"),
            options=ALLOWED_STATUS,
            default=ALLOWED_STATUS,
            format_func=lambda s: status_to_label(s),
        )
        needs_action_only = st.checkbox(t("NEEDS_ACTION_ONLY"), value=False)
        q = st.text_input(t("SEARCH"))

        sort_key = st.selectbox(
            t("SORT_BY"), options=["date", "created_at", "source", "status"], index=0
        )
        sort_desc = st.checkbox(t("DESC_SORT"), value=False)

        st.divider()

        # Flash after rebuild
        flash = st.session_state.pop("flash_rebuild", None)
        if flash:
            st.success(
                "✅ Έγινε rebuild δεδομένων — "
                f"forms: {flash['forms']}, emails: {flash['emails']}, "
                f"invoices: {flash['invoices']} • {flash['ts']}"
            )

        st.subheader("Rebuild feed")

        # Fuzzy controls
        if HAS_MATCHING:
            fuzzy_on = st.checkbox("🔎 Fuzzy match invoice numbers (rapidfuzz)", value=True)
            fuzzy_threshold = st.slider("Κατώφλι Fuzzy score", 60, 100, 88, 1)
        else:
            fuzzy_on = False
            fuzzy_threshold = 0
            st.caption("Fuzzy matching module δεν βρέθηκε · γίνεται μόνο exact matching.")

        if st.button("🔄 Τρέξε parsers & ανανέωσε δεδομένα", key="rebuild_btn"):
            try:
                with st.spinner("Τρέχουν οι parsers…"):
                    import re as _re

                    from data_parser.parse_emails import parse_all_emails as _parse_emails
                    from data_parser.parse_forms import parse_all_forms as _parse_forms
                    from data_parser.parse_invoices import parse_all_invoices as _parse_invoices

                    def _extract_inv_no(txt: str | None):
                        pat = _re.compile(
                            r"(?:invoice|τιμολ(?:όγιο|\.?)|αρ\.?\s*τιμολ(?:ογίου)?)\s*(?:no\.?|#|nr\.?|:)?\s*([A-Z]{0,4}[-/]?\d[\w\-\/]+)",
                            _re.IGNORECASE,
                        )
                        m = pat.search(txt or "")
                        return m.group(1).strip() if m else None

                    # --- ΧΡΗΣΗ ΑΠΟΛΥΤΩΝ ΔΙΑΔΡΟΜΩΝ ---
                    forms_raw = _parse_forms(str(DUMMY_FORMS_DIR))
                    emails_raw = _parse_emails(str(DUMMY_EMAILS_DIR))
                    invoices_raw = _parse_invoices(str(DUMMY_INVOICES_DIR))

                    # Validation (αν υπάρχει)
                    def _safe_validate(fn, rec):
                        try:
                            out = fn(rec)
                            if isinstance(out, tuple) and len(out) == 2:
                                clean, errors = out
                            else:
                                clean, errors = out, []
                        except Exception as ex:
                            clean, errors = rec, [str(ex)]
                        clean = dict(clean) if isinstance(clean, dict) else dict(rec)
                        clean["validation_ok"] = len(errors) == 0
                        if errors:
                            clean["validation_errors"] = errors
                        return clean

                    if HAS_VALIDATION:
                        forms = [_safe_validate(_validate_form_ext, r) for r in forms_raw]
                        emails = [_safe_validate(_validate_email_ext, r) for r in emails_raw]
                        invoices = [_safe_validate(_validate_invoice_ext, r) for r in invoices_raw]
                    else:
                        forms, emails, invoices = forms_raw, emails_raw, invoices_raw

                    inv_lookup = _build_lookup_ext(invoices)

                    enriched_emails = []
                    for e in emails:
                        inv_no = _extract_inv_no(e.get("subject", "")) or _extract_inv_no(
                            e.get("body", "")
                        )
                        matched, score = None, None
                        if inv_no:
                            if fuzzy_on:
                                matched, score = _fuzzy_find_ext(
                                    inv_no, inv_lookup, score_cutoff=fuzzy_threshold
                                )
                            else:
                                matched = inv_lookup.get(_norm_inv_ext(inv_no))
                                score = 100 if matched else None

                        enriched_emails.append(
                            {
                                **e,
                                "invoice_number_in_subject": inv_no,
                                "matched_invoice_html": bool(matched),
                                "matched_invoice_file": (
                                    matched.get("source_file") if matched else None
                                ),
                                "matched_invoice_total": matched.get("total") if matched else None,
                                "matched_via": (
                                    "fuzzy"
                                    if (matched and (score is not None and score < 100))
                                    else ("exact" if matched else "none")
                                ),
                                "fuzzy_score": score,
                                "needs_action": (e.get("email_type") == "invoice")
                                and (
                                    e.get("missing_attachment")
                                    or not e.get("has_pdf_attachments")
                                    or not matched
                                ),
                            }
                        )

                    combined = (
                        [{"source": "form", "status": "pending", **r} for r in forms]
                        + [{"source": "email", "status": "pending", **r} for r in enriched_emails]
                        + [{"source": "invoice_html", "status": "pending", **r} for r in invoices]
                    )

                    dump_json_artifact("parsed_forms.json", forms)
                    dump_json_artifact("parsed_emails.json", emails)
                    dump_json_artifact("parsed_emails_enriched.json", enriched_emails)
                    dump_json_artifact("parsed_invoices.json", invoices)

                    save_data(combined)

                    st.session_state["flash_rebuild"] = {
                        "forms": len(forms),
                        "emails": len(emails),
                        "invoices": len(invoices),
                        "ts": now_iso(),
                    }

                st.rerun()
            except Exception as e:
                ui_error("Απέτυχε το rebuild των δεδομένων.", "rebuild_error", {"error": str(e)})

    # Apply filters
    def match_query(rec: dict[str, Any], q: str) -> bool:
        if not q:
            return True
        try:
            hay = " ".join(
                [
                    str(rec.get("subject", "")),
                    str(rec.get("full_name", "")),
                    str(rec.get("email", "")),
                    str(rec.get("company", "")),
                    str(rec.get("invoice_number", "")),
                    str(rec.get("service", "")),
                ]
            ).lower()
            return q.lower() in hay
        except Exception:
            return True

    try:
        view = [
            r
            for r in data
            if r.get("source") in sources
            and r.get("status") in statuses
            and (not needs_action_only or r.get("needs_action"))
            and match_query(r, q)
        ]
    except Exception as e:
        view = []
        ui_error("Σφάλμα εφαρμογής φίλτρων/αναζήτησης.", "filter_error", {"error": str(e)})

    def safe_sort_key(r: dict[str, Any]):
        val = r.get(sort_key)
        return val if val is not None else ""

    try:
        view = sorted(view, key=safe_sort_key, reverse=sort_desc)
    except Exception as e:
        ui_warn("Αποτυχία ταξινόμησης. Εμφάνιση χωρίς ταξινόμηση.", "sort_error", {"error": str(e)})

    # Sidebar: list of records + EXPORT UI
    with st.sidebar:
        st.subheader(f"{t('RESULTS')}: {len(view)}")

        # ---- Export block (AFTER view is computed) ----
        st.markdown("---")
        st.subheader(t("EXPORT"))

        scope = st.radio(t("FILTERED") + " / " + t("ALL"), [t("FILTERED"), t("ALL")], index=0)

        dest_choice = st.selectbox(
            t("DESTINATION"), [t("DEST_CSV"), t("DEST_XLSX"), t("DEST_GSHEETS")]
        )

        # Template columns
        st.caption("Header template (CSV with 1st row as columns)")
        template_file = st.file_uploader(
            "CSV header template", type=["csv"], accept_multiple_files=False, key="tpl_upload"
        )
        if template_file is not None:
            try:
                # read just the header
                df0 = pd.read_csv(
                    template_file, nrows=0, sep=None, engine="python", encoding="utf-8"
                )
                template_cols = [str(c).strip() for c in list(df0.columns)]
            except Exception:
                template_cols = []
        else:
            # Sensible default columns
            template_cols = [
                "type",
                "source",
                "date",
                "client_name",
                "company",
                "service_interest",
                "amount",
                "vat",
                "total_amount",
                "invoice_number",
                "message",
                "email",
                "phone",
                "subject",
                "status",
                "source_file",
                "id",
            ]

        save_copy = st.checkbox(t("SAVE_COPY"), value=True)
        fname_prefix = st.text_input(t("FILENAME_PREFIX"), value="export")

        # Google Sheets specific inputs (only shown if selected)
        sheet_id_input = ""
        worksheet_input = "Sheet1"
        mode_input = t("REPLACE")
        creds_paste = ""
        if dest_choice == t("DEST_GSHEETS"):
            st.markdown(t("TARGET_SHEET_CAPTION"))
            sheet_url_or_id = st.text_input(t("TARGET_SHEET"), value="")
            worksheet_input = st.text_input(t("WORKSHEET"), value="Sheet1")
            mode_input = st.selectbox(t("UPLOAD_MODE"), [t("REPLACE"), t("APPEND")], index=0)
            creds_paste = st.text_area(
                "Service Account JSON (optional if set in env/secrets)", height=140, value=""
            )
            sheet_id_input = _parse_sheet_id(sheet_url_or_id) if sheet_url_or_id else ""

        # --- Export run ---
        run_it = st.button(t("RUN_EXPORT"), key="run_export_btn")

        if run_it:
            try:
                records_for_export = view if scope == t("FILTERED") else data
                df_export = build_template_df(
                    records_for_export, template_cols, invoice_index=invoice_index_combined
                )

                ensure_dirs()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix_clean = (fname_prefix or "export").strip()
                prefix_clean = re.sub(r"[^\w\-]+", "_", prefix_clean)

                if dest_choice == t("DEST_CSV"):
                    # CSV ως string (UTF-8-SIG για Excel compatibility)
                    csv_text = df_export.to_csv(index=False, encoding="utf-8-sig")
                    if save_copy:
                        out_path = EXPORTS_DIR / f"{prefix_clean}_{ts}.csv"
                        with out_path.open("w", encoding="utf-8-sig", newline="") as fh_csv:
                            fh_csv.write(csv_text)
                        st.success(t("EXPORT_READY_CSV").format(rows=len(df_export)))
                        st.download_button(
                            t("DOWNLOAD_FILE"),
                            data=csv_text,
                            file_name=out_path.name,
                            mime="text/csv",
                            key="dl_csv_btn",
                        )
                    else:
                        st.success(t("EXPORT_READY_CSV").format(rows=len(df_export)))
                        st.download_button(
                            t("DOWNLOAD_FILE"),
                            data=csv_text,
                            file_name=f"{prefix_clean}_{ts}.csv",
                            mime="text/csv",
                            key="dl_csv_btn_nofile",
                        )

                elif dest_choice == t("DEST_XLSX"):
                    bio = BytesIO()
                    # openpyxl/xlsxwriter χρησιμοποιείται από pandas writer ανάλογα με το env
                    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
                        df_export.to_excel(writer, index=False, sheet_name="Data")
                    bio.seek(0)
                    xlsx_bytes = bio.getvalue()

                    if save_copy:
                        out_path = EXPORTS_DIR / f"{prefix_clean}_{ts}.xlsx"
                        with out_path.open("wb") as fh_xlsx:
                            fh_xlsx.write(xlsx_bytes)
                        st.success(t("EXPORT_READY_XLSX").format(rows=len(df_export)))
                        st.download_button(
                            t("DOWNLOAD_FILE"),
                            data=xlsx_bytes,
                            file_name=out_path.name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_xlsx_btn",
                        )
                    else:
                        st.success(t("EXPORT_READY_XLSX").format(rows=len(df_export)))
                        st.download_button(
                            t("DOWNLOAD_FILE"),
                            data=xlsx_bytes,
                            file_name=f"{prefix_clean}_{ts}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_xlsx_btn_nofile",
                        )

                else:  # Google Sheets
                    # Βασικοί έλεγχοι εισόδου
                    if not sheet_id_input:
                        st.error(t("TARGET_SHEET") + ": required")
                        st.stop()

                    # Credentials από secrets/env/paste
                    creds_dict, _sa_email = _detect_creds_from_sources(creds_paste)
                    if not creds_dict:
                        st.warning(t("NEED_CREDS"))
                        st.stop()

                    mode_norm = "replace" if mode_input == t("REPLACE") else "append"

                    try:
                        url = upload_dataframe_to_sheet(
                            df_export,
                            sheet_id=sheet_id_input,
                            worksheet_name=worksheet_input or "Sheet1",
                            creds_dict=creds_dict,  # dict[str, Any]
                            mode=mode_norm,
                        )
                        st.success(
                            t("EXPORT_READY_GS").format(
                                ws=worksheet_input or "Sheet1", mode=mode_norm
                            )
                        )
                        st.link_button(t("OPEN_IN_GSHEETS"), url)
                    except Exception as ex:
                        ui_error(
                            "Google Sheets upload failed",
                            "gsheets_upload_error",
                            {"error": str(ex)},
                        )

            except Exception as exc:
                ui_error("Απέτυχε το export.", "export_error", {"error": str(exc)})

        # ---- Record list (labels + selectbox) ----
        labels: list[str] = []
        try:
            for r in view:
                source_map: dict[str, str] = {
                    "form": "FORM",
                    "email": "EMAIL",
                    "invoice_html": "INV",
                }
                src_val = r.get("source")
                src_key: str = src_val if isinstance(src_val, str) else ""
                tag = source_map.get(src_key, src_key)

                title = (
                    r.get("subject")
                    or r.get("invoice_number")
                    or r.get("full_name")
                    or r.get("company")
                    or r.get("service")
                    or r.get("source_file")
                    or r.get("id", "")
                )
                labels.append(f"[{tag}] {title}")

        except Exception as e:
            ui_warn("Σφάλμα κατασκευής λιστας sidebar.", "sidebar_list_error", {"error": str(e)})

        if not view:
            ui_info("Δεν βρέθηκαν εγγραφές με τα συγκεκριμένα φίλτρα.", "no_results")
            st.stop()

        sel = st.selectbox(
            t("RECORD"), options=range(len(view)), format_func=lambda i: labels[i] if view else ""
        )

        # -------- Record details --------
        rec = view[sel]
        idx = find_index_by_id(data, rec.get("id", ""))
        if idx < 0:
            ui_error(
                "Η επιλεγμένη εγγραφή δεν βρέθηκε στα δεδομένα.",
                "record_not_found",
                {"id": rec.get("id")},
            )
            st.stop()

    # ------- Resolve related invoice (if any) -------
    invoice_payload: dict[str, Any] | None = None
    invoice_rec_idx: int | None = None
    try:
        if rec.get("source") == "invoice_html":
            invoice_payload = rec
            invoice_rec_idx = idx
        elif rec.get("source") == "email":
            inv_no_raw = rec.get("invoice_number_in_subject") or rec.get("invoice_number")
            inv_key: str = inv_no_raw if isinstance(inv_no_raw, str) else ""
            if inv_key:
                invoice_payload = invoice_index_combined.get(inv_key) or invoice_index_combined.get(
                    _norm_invoice_no_local(inv_key)
                )
                invoice_rec_idx = find_invoice_record_index_by_number(data, inv_key)
    except Exception as e:
        ui_warn(
            "Σφάλμα αντιστοίχισης email → invoice.",
            "email_invoice_match_error",
            {"error": str(e)},
        )

    # -- Προεπισκόπηση HTML τιμολογίου (θα εμφανιστεί στο col1)
    preview_html: str | None = None
    html_title: str | None = None
    try:
        if rec.get("source") == "email" and rec.get("matched_invoice_file"):
            candidate = DUMMY_INVOICES_DIR / rec["matched_invoice_file"]
            if candidate.exists():
                html_title = f"{t('INVOICE_PREVIEW')}: {rec['matched_invoice_file']}"
                with candidate.open(encoding="utf-8", errors="ignore") as f:
                    preview_html = f.read()
        elif rec.get("source") == "invoice_html" and rec.get("source_file"):
            candidate = DUMMY_INVOICES_DIR / rec["source_file"]
            if candidate.exists():
                html_title = f"{t('INVOICE_PREVIEW')}: {rec['source_file']}"
                with candidate.open(encoding="utf-8", errors="ignore") as f:
                    preview_html = f.read()
    except Exception as e:
        ui_warn(
            "Αποτυχία ανάγνωσης αρχείου HTML τιμολογίου.",
            "invoice_html_read_error",
            {"error": str(e)},
        )

    col1, col2 = st.columns([2, 1], gap="large")

    # -------- ΔΕΞΙ ΠΑΝΕΛ: Ενέργειες / Approve / Notes (ΠΑΝΩ-ΠΑΝΩ) --------
    with col2:
        st.subheader(t("ACTIONS"))
        try:
            st.write(f"**{t('STATUS')}:** {status_to_label(rec.get('status', 'pending'))}")
            status_options_labels = [status_to_label(s) for s in ALLOWED_STATUS]
            current_label = status_to_label(rec.get("status", "pending"))
            new_status_label = st.selectbox(
                t("STATUS"), status_options_labels, index=status_options_labels.index(current_label)
            )
            if st.button(t("APPLY_STATUS"), key="apply_status_btn"):
                try:
                    new_status = label_to_status(new_status_label)
                    rec["status"] = new_status
                    rec["updated_at"] = now_iso()
                    data[idx] = rec
                    save_data(data)
                    st.success(f"{t('STATUS')} → {status_to_label(new_status)}")
                    log_action("change_status", {"record_id": rec.get("id"), "status": new_status})
                except Exception as e:
                    ui_error("Αποτυχία αλλαγής status.", "change_status_error", {"error": str(e)})
        except Exception as e:
            ui_warn("Αποτυχία χειρισμού status.", "status_ui_error", {"error": str(e)})

        st.divider()
        try:
            if st.button(f"✅ {t('APPROVE')}", key="approve_btn"):
                try:
                    rec["status"] = "approved"
                    rec["updated_at"] = now_iso()
                    data[idx] = rec
                    save_data(data)
                    st.success("Εγκρίθηκε (approved).")
                    log_action("approve_record", {"record_id": rec.get("id")})
                except Exception as e:
                    ui_error("Αποτυχία έγκρισης.", "approve_error", {"error": str(e)})
            if st.button(f"⛔ {t('REJECT')}", key="reject_btn"):
                try:
                    rec["status"] = "rejected"
                    rec["updated_at"] = now_iso()
                    data[idx] = rec
                    save_data(data)
                    st.success("Απορρίφθηκε (rejected).")
                    log_action("reject_record", {"record_id": rec.get("id")})
                except Exception as e:
                    ui_error("Αποτυχία απόρριψης.", "reject_error", {"error": str(e)})
        except Exception as e:
            ui_warn(
                "Αποτυχία κουμπιών approve/reject.", "approve_reject_ui_error", {"error": str(e)}
            )

        st.divider()
        try:
            with st.form("quick_note"):
                note = st.text_area(t("NOTES"), value=rec.get("notes", ""))
                submitted = st.form_submit_button(t("SAVE_NOTES"))
                if submitted:
                    try:
                        rec["notes"] = note
                        rec["updated_at"] = now_iso()
                        data[idx] = rec
                        save_data(data)
                        st.success("Σημειώσεις αποθηκεύτηκαν.")
                        log_action("save_notes", {"record_id": rec.get("id")})
                    except Exception as e:
                        ui_error(
                            "Αποτυχία αποθήκευσης σημειώσεων.",
                            "save_notes_error",
                            {"error": str(e)},
                        )
        except Exception as e:
            ui_warn("Αποτυχία φόρμας σημειώσεων.", "notes_form_error", {"error": str(e)})

    # -------- ΑΡΙΣΤΕΡΟ ΠΑΝΕΛ (μπλε): SAFE EDIT + LOG VIEWER ΠΑΝΩ-ΠΑΝΩ --------
    with col1:
        # SAFE EDIT (expanded by default)
        with st.expander(t("SAFE_EDIT"), expanded=True):
            try:
                src = rec.get("source")
                with st.form("safe_edit_form"):
                    if src == "form":
                        full_name = st.text_input(t("FULL_NAME"), value=rec.get("full_name", ""))
                        email = st.text_input(t("EMAIL"), value=rec.get("email", ""))
                        phone = st.text_input(t("PHONE"), value=rec.get("phone", ""))
                        company = st.text_input(t("COMPANY"), value=rec.get("company", ""))
                        service = st.text_input(t("SERVICE"), value=rec.get("service", ""))
                        message = st.text_area(
                            t("MESSAGE"), value=rec.get("message", ""), height=120
                        )
                        submission_date = st.text_input(
                            t("SUBMISSION_DATE"), value=str(rec.get("submission_date", ""))
                        )
                        priority = st.text_input(t("PRIORITY"), value=str(rec.get("priority", "")))
                        submitted = st.form_submit_button(t("SAVE_CHANGES"))
                        if submitted:
                            rec.update(
                                {
                                    "full_name": full_name,
                                    "email": email,
                                    "phone": phone,
                                    "company": company,
                                    "service": service,
                                    "message": message,
                                    "submission_date": submission_date,
                                    "priority": priority,
                                    "updated_at": now_iso(),
                                    "status": rec.get("status", "pending"),
                                }
                            )
                            data[idx] = rec
                            save_data(data)
                            st.success("Αποθηκεύτηκαν οι αλλαγές (form).")

                    elif src == "email":
                        subject = st.text_input(t("SUBJECT_LABEL"), value=rec.get("subject", ""))
                        email_addr = st.text_input(t("EMAIL"), value=rec.get("email", ""))
                        company = st.text_input(t("COMPANY"), value=rec.get("company", ""))
                        submitted = st.form_submit_button(t("SAVE_CHANGES"))
                        if submitted:
                            rec.update(
                                {
                                    "subject": subject,
                                    "email": email_addr,
                                    "company": company,
                                    "updated_at": now_iso(),
                                    "status": rec.get("status", "pending"),
                                }
                            )
                            data[idx] = rec
                            save_data(data)
                            st.success("Αποθηκεύτηκαν οι αλλαγές (email).")

                    else:  # invoice_html – βασικά meta
                        inv_no = st.text_input(
                            t("INVOICE_NUMBER_FIELD"), value=rec.get("invoice_number", "")
                        )
                        total_val = st.text_input(t("TOTAL_FIELD"), value=str(rec.get("total", "")))
                        submitted = st.form_submit_button(t("SAVE_CHANGES"))
                        if submitted:
                            rec.update(
                                {
                                    "invoice_number": inv_no,
                                    "total": parse_total_input(total_val, rec.get("total")),
                                    "updated_at": now_iso(),
                                    "status": rec.get("status", "pending"),
                                }
                            )
                            data[idx] = rec
                            save_data(data)
                            st.success("Αποθηκεύτηκαν οι αλλαγές (invoice).")
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης SAFE EDIT.", "safe_edit_error", {"error": str(e)})

        # LOG VIEWER (πάνω-πάνω, κάτω από SAFE EDIT)
        with st.expander("📜 Log Viewer (outputs/log.txt)", expanded=True):
            try:
                if Path(LOG_PATH).exists():
                    with Path(LOG_PATH).open(encoding="utf-8") as f:
                        tail = f.readlines()[-400:]
                    st.text("".join(tail))
                    if st.button("🧹 Καθάρισε το log", key="clear_log_btn"):
                        try:
                            Path(LOG_PATH).write_text("", encoding="utf-8")
                            st.success("Καθαρίστηκε το log.")
                        except Exception as e:
                            ui_error(
                                "Αποτυχία καθαρισμού log.", "log_clear_error", {"error": str(e)}
                            )
                else:
                    st.info("Δεν βρέθηκε log.txt ακόμη.")
            except Exception as e:
                ui_warn("Αποτυχία ανάγνωσης log.", "log_view_error", {"error": str(e)})

        # EMAIL: περιεχόμενο
        if rec.get("source") == "email":
            try:
                match_caption = []
                if rec.get("matched_via"):
                    match_caption.append(f"matched_via={rec.get('matched_via')}")
                if rec.get("fuzzy_score") is not None:
                    match_caption.append(f"fuzzy_score={rec.get('fuzzy_score')}")
                if match_caption:
                    st.caption(" | ".join(match_caption))

                with st.expander(f"📧 {t('EMAIL_CONTENT')}", expanded=False):
                    pretty_on = st.checkbox(
                        t("READABILITY_FORMAT"),
                        value=True,
                        key=f"pretty_email_ck_{rec.get('id', '')}",
                    )
                    body_raw = rec.get("body", "")
                    body_show = pretty_email_body(body_raw) if pretty_on else body_raw

                    st.text_area(
                        t("MESSAGE_BODY"),
                        value=body_show,
                        height=300,
                        key=f"email_body_{rec.get('id', '')}",
                    )
            except Exception as e:
                ui_warn(
                    "Αποτυχία εμφάνισης editor γενικών πεδίων.",
                    "generic_editor_error",
                    {"error": str(e)},
                )

        # -------- Τιμολόγιο – parsed στοιχεία (headers/metrics) --------
        if invoice_payload:
            st.markdown("### Στοιχεία Τιμολογίου (parsed)")
            try:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**{t('SELLER')}**")
                    st.write(
                        f"- {t('SELLER_NAME')}: {invoice_payload.get('seller_name', '')}\n"
                        f"- {t('SELLER_EMAIL')}: {invoice_payload.get('seller_email', '')}\n"
                        f"- {t('SELLER_PHONE')}: {invoice_payload.get('seller_phone', '')}\n"
                        f"- {t('SELLER_VAT')}: {invoice_payload.get('seller_vat', '')}\n"
                        f"- {t('SELLER_TAX_OFFICE')}: {invoice_payload.get('seller_tax_office', '')}\n"
                        f"- {t('SELLER_ADDRESS')}: {invoice_payload.get('seller_address', '')}"
                    )
                with c2:
                    st.markdown(f"**{t('BUYER')}**")
                    st.write(
                        f"- {t('BUYER_NAME')}: {invoice_payload.get('buyer_name', '')}\n"
                        f"- {t('BUYER_VAT')}: {invoice_payload.get('buyer_vat', '')}\n"
                        f"- {t('BUYER_ADDRESS')}: {invoice_payload.get('buyer_address', '')}"
                    )
            except Exception as e:
                ui_warn(
                    "Αποτυχία εμφάνισης στοιχείων εκδότη/πελάτη.",
                    "seller_buyer_view_error",
                    {"error": str(e)},
                )

            try:
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric(t("INVOICE_NUMBER"), invoice_payload.get("invoice_number", ""))
                with m2:
                    st.metric(t("DATE"), invoice_payload.get("date", ""))
                with m3:
                    st.metric(t("PAYMENT_METHOD"), invoice_payload.get("payment_method", ""))
            except Exception as e:
                ui_warn(
                    "Αποτυχία εμφάνισης βασικών μετρικών τιμολογίου.",
                    "invoice_metrics_error",
                    {"error": str(e)},
                )

            # (continues in Part 5: items editor, summary, meta editor, preview HTML, raw JSON)

            # -------- Items editor --------
            with st.expander(t("ITEM_LINES"), expanded=False):
                try:
                    items = invoice_payload.get("items", []) or []
                    editable_rows: list[dict[str, Any]] = []
                    for it in items:
                        qty = it.get("quantity")
                        price = it.get("unit_price")
                        try:
                            line_total = (
                                round(float(qty) * float(price), 2)
                                if qty is not None and price is not None
                                else it.get("line_total")
                            )
                        except Exception:
                            line_total = it.get("line_total")
                        editable_rows.append(
                            {
                                t("PRODUCT_DESC"): it.get("description", ""),
                                t("QUANTITY"): qty if qty is not None else 0.0,
                                t("UNIT_PRICE"): price if price is not None else 0.0,
                                t("LINE_TOTAL"): line_total if line_total is not None else 0.0,
                                t("CURRENCY"): it.get(
                                    "currency", invoice_payload.get("currency", "EUR")
                                ),
                            }
                        )

                    editor_key = f"items_editor_{invoice_payload.get('id') or rec.get('id') or idx}"
                    df_items = pd.DataFrame(editable_rows)
                    edited_df = st.data_editor(
                        df_items,
                        num_rows="dynamic",
                        key=editor_key,
                        use_container_width=True,
                        hide_index=True,
                        disabled=False,
                        column_config={
                            t("PRODUCT_DESC"): st.column_config.TextColumn(t("PRODUCT_DESC")),
                            t("QUANTITY"): st.column_config.NumberColumn(
                                t("QUANTITY"), step=1.0, format="%.2f"
                            ),
                            t("UNIT_PRICE"): st.column_config.NumberColumn(
                                t("UNIT_PRICE"), step=0.10, format="%.2f"
                            ),
                            t("LINE_TOTAL"): st.column_config.NumberColumn(
                                t("LINE_TOTAL"), disabled=True, format="%.2f"
                            ),
                            t("CURRENCY"): st.column_config.TextColumn(t("CURRENCY")),
                        },
                    )

                    default_currency = invoice_payload.get("currency", "EUR")
                    currency_input = st.text_input(t("CURRENCY_LABEL"), value=default_currency)
                    vat_rate_val = invoice_payload.get("vat_rate", 24.0)
                    try:
                        vat_rate_val = float(vat_rate_val) if vat_rate_val is not None else 24.0
                    except Exception:
                        vat_rate_val = 24.0
                    vat_rate_input = st.number_input(
                        t("VAT_PERCENT"),
                        min_value=0.0,
                        max_value=99.0,
                        value=vat_rate_val,
                        step=0.5,
                    )

                    subtotal_calc = 0.0
                    cleaned_items: list[dict[str, Any]] = []
                    rows_iter = edited_df.to_dict("records") if edited_df is not None else []
                    for row in rows_iter:
                        try:
                            qty = float(row.get(t("QUANTITY")) or 0)
                        except Exception:
                            qty = 0.0
                        try:
                            price = float(row.get(t("UNIT_PRICE")) or 0)
                        except Exception:
                            price = 0.0
                        line_total = round(qty * price, 2)
                        subtotal_calc += line_total
                        cleaned_items.append(
                            {
                                "description": (row.get(t("PRODUCT_DESC")) or "").strip(),
                                "quantity": qty,
                                "unit_price": price,
                                "line_total": line_total,
                                "currency": (
                                    row.get(t("CURRENCY")) or currency_input or "EUR"
                                ).strip(),
                            }
                        )
                    subtotal_calc = round(subtotal_calc, 2)
                    vat_amount_calc = round(subtotal_calc * (vat_rate_input / 100.0), 2)
                    total_calc = round(subtotal_calc + vat_amount_calc, 2)

                    m1, m2, m3 = st.columns(3)
                    m1.metric(t("NET_CALC"), f"{subtotal_calc:.2f}")
                    m2.metric(t("VAT_CALC"), f"{vat_amount_calc:.2f} ({vat_rate_input:.2f}%)")
                    m3.metric(t("TOTAL_CALC"), f"{total_calc:.2f}")

                    if st.button(t("SAVE_ITEMS_CALC"), key="save_items_btn"):
                        try:
                            target_idx = invoice_rec_idx if invoice_rec_idx is not None else idx
                            inv_rec = dict(data[target_idx])
                            inv_rec.update(
                                {
                                    "items": cleaned_items,
                                    "currency": currency_input or "EUR",
                                    "subtotal": subtotal_calc,
                                    "vat_rate": round(float(vat_rate_input), 2),
                                    "vat_amount": vat_amount_calc,
                                    "total": total_calc,
                                    "status": "edited",
                                    "updated_at": now_iso(),
                                }
                            )
                            data[target_idx] = inv_rec
                            if target_idx == idx:
                                for k, v in inv_rec.items():
                                    if k != "id":
                                        rec[k] = v
                            save_data(data)
                            st.success("Αποθηκεύτηκαν οι γραμμές & οι υπολογισμοί.")
                            log_action("save_items_calc", {"record_id": rec.get("id")})
                        except Exception as e:
                            ui_error(
                                "Αποτυχία αποθήκευσης γραμμών/υπολογισμών.",
                                "save_items_calc_error",
                                {"error": str(e)},
                            )
                except Exception as e:
                    ui_warn(
                        "Αποτυχία εμφάνισης/editor γραμμών προϊόντων.",
                        "items_editor_error",
                        {"error": str(e)},
                    )

            # -------- Summary --------
            try:
                st.markdown(f"**{t('SUMMARY')}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("NET"), f"{invoice_payload.get('subtotal', '')}")
                vat_val = invoice_payload.get("vat_amount", "")
                vat_rate_val = invoice_payload.get("vat_rate", "")
                c2.metric(
                    t("VAT"),
                    f"{vat_val} ({vat_rate_val}%)" if vat_rate_val != "" else f"{vat_val}",
                )
                c3.metric(t("TOTAL"), f"{invoice_payload.get('total', '')}")
                c4.metric(t("CURRENCY"), invoice_payload.get("currency", ""))
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης σύνοψης.", "summary_view_error", {"error": str(e)})

            # -------- Invoice meta editor --------
            with st.expander(t("INVOICE_META_EDITOR"), expanded=False):
                try:
                    seller_name = st.text_input(
                        t("SELLER_NAME"), value=invoice_payload.get("seller_name", "")
                    )
                    seller_email = st.text_input(
                        t("SELLER_EMAIL"), value=invoice_payload.get("seller_email", "")
                    )
                    seller_phone = st.text_input(
                        t("SELLER_PHONE"), value=invoice_payload.get("seller_phone", "")
                    )
                    seller_vat = st.text_input(
                        t("SELLER_VAT"), value=invoice_payload.get("seller_vat", "")
                    )
                    seller_tax_office = st.text_input(
                        t("SELLER_TAX_OFFICE"), value=invoice_payload.get("seller_tax_office", "")
                    )
                    seller_address = st.text_input(
                        t("SELLER_ADDRESS"), value=invoice_payload.get("seller_address", "")
                    )

                    buyer_name = st.text_input(
                        t("BUYER_NAME"), value=invoice_payload.get("buyer_name", "")
                    )
                    buyer_vat = st.text_input(
                        t("BUYER_VAT"), value=invoice_payload.get("buyer_vat", "")
                    )
                    buyer_address = st.text_input(
                        t("BUYER_ADDRESS"), value=invoice_payload.get("buyer_address", "")
                    )

                    payment_method = st.text_input(
                        t("PAYMENT_METHOD"), value=invoice_payload.get("payment_method", "")
                    )

                    if st.button(t("SAVE_INVOICE_META"), key="save_invoice_meta_btn"):
                        try:
                            target_idx = invoice_rec_idx if invoice_rec_idx is not None else idx
                            inv_rec = dict(data[target_idx])
                            inv_rec.update(
                                {
                                    "seller_name": seller_name,
                                    "seller_email": seller_email,
                                    "seller_phone": seller_phone,
                                    "seller_vat": seller_vat,
                                    "seller_tax_office": seller_tax_office,
                                    "seller_address": seller_address,
                                    "buyer_name": buyer_name,
                                    "buyer_vat": buyer_vat,
                                    "buyer_address": buyer_address,
                                    "payment_method": payment_method,
                                    "status": "edited",
                                    "updated_at": now_iso(),
                                }
                            )
                            data[target_idx] = inv_rec
                            if target_idx == idx:
                                for k, v in inv_rec.items():
                                    if k != "id":
                                        rec[k] = v
                            save_data(data)
                            st.success("Αποθηκεύτηκαν τα στοιχεία τιμολογίου (status=edited).")
                            log_action("save_invoice_parties", {"record_id": rec.get("id")})
                        except Exception as e:
                            ui_error(
                                "Αποτυχία αποθήκευσης στοιχείων τιμολογίου.",
                                "save_invoice_parties_error",
                                {"error": str(e)},
                            )
                except Exception as e:
                    ui_warn(
                        "Αποτυχία εμφάνισης editor στοιχείων τιμολογίου.",
                        "invoice_parties_editor_error",
                        {"error": str(e)},
                    )

        # -------- Προεπισκόπηση HTML τιμολογίου --------
        if preview_html:
            try:
                with st.expander(html_title or t("INVOICE_PREVIEW"), expanded=False):
                    st.markdown(
                        "<style>.invoice-preview iframe { background: #fff !important; }</style>",
                        unsafe_allow_html=True,
                    )
                    components.html(preview_html, height=900, scrolling=True)
                    st.download_button(
                        t("DOWNLOAD_INVOICE_HTML"),
                        data=preview_html.encode("utf-8"),
                        file_name=(
                            rec.get("matched_invoice_file")
                            or rec.get("source_file")
                            or "invoice.html"
                        ),
                        mime="text/html",
                        key="download_html_btn",
                    )
            except Exception as e:
                ui_warn(
                    "Αποτυχία εμφάνισης προεπισκόπησης HTML.",
                    "invoice_preview_error",
                    {"error": str(e)},
                )

        # -------- RAW JSON --------
        with st.expander(t("RECORD_DETAILS"), expanded=False):
            try:
                st.json(rec, expanded=False)
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης JSON εγγραφής.", "json_view_error", {"error": str(e)})

    st.caption(
        "Tip: Τα δεδομένα γράφονται ξανά στο outputs/combined_feed.json (κρατάμε backup ανά αποθήκευση)."
    )


if __name__ == "__main__":
    run_app()
