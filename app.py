# app.py
import json
import os
import uuid
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd  # για data_editor/exports
from io import BytesIO

DATA_PATH = "outputs/combined_feed.json"
BACKUP_DIR = "outputs/_backups"
LOG_PATH = "outputs/log.txt"
INVOICES_DIR = "dummy_data/invoices"  # για προεπισκόπηση HTML τιμολογίων
TEMPLATE_PATH = "dummy_data/templates/data_extraction_template.csv"  # export template
EXPORTS_DIR = "exports"  # backup των exports

ALLOWED_STATUS = ["pending", "approved", "rejected", "edited"]


# ------------- Utilities -------------
def ensure_dirs():
    os.makedirs("outputs", exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def log_action(action: str, details: dict | None = None, level: str = "INFO"):
    try:
        ensure_dirs()
        line = {"ts": now_iso(), "level": level, "action": action, "details": details or {}}
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ui_error(msg: str, action: str = "error", details: dict | None = None):
    st.error(msg)
    log_action(action, details=details, level="ERROR")


def ui_warn(msg: str, action: str = "warning", details: dict | None = None):
    st.warning(msg)
    log_action(action, details=details, level="WARN")


def ui_info(msg: str, action: str = "info", details: dict | None = None):
    st.info(msg)
    log_action(action, details=details, level="INFO")


def load_data() -> List[Dict[str, Any]]:
    ensure_dirs()
    if not os.path.exists(DATA_PATH):
        ui_warn("Δεν βρέθηκε το outputs/combined_feed.json. Ξεκινάμε με κενή λίστα.", "data_missing")
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        ui_error("Το αρχείο δεδομένων είναι χαλασμένο (JSON). Θα φορτωθεί κενή λίστα.",
                 "json_decode_error", {"error": str(e)})
        return []
    except Exception as e:
        ui_error("Αποτυχία φόρτωσης δεδομένων.", "load_data_error", {"error": str(e)})
        return []

    # harden
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
            needs = False
            if rec.get("source") == "email" and rec.get("email_type") == "invoice":
                if rec.get("missing_attachment") or not rec.get("matched_invoice_html"):
                    needs = True
            rec["needs_action"] = needs
    except Exception as e:
        ui_error("Σφάλμα στη σκλήρυνση (hardening) των εγγραφών.", "harden_records_error", {"error": str(e)})

    return data


def backup_data(data: List[Dict[str, Any]]):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = os.path.join(BACKUP_DIR, f"combined_feed_{ts}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log_action("backup_data", {"path": p})
    except Exception as e:
        ui_warn("Αποτυχία δημιουργίας backup. Συνεχίζουμε με αποθήκευση.", "backup_error", {"error": str(e)})


def save_data(data: List[Dict[str, Any]]):
    backup_data(data)
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log_action("save_data", {"path": DATA_PATH, "count": len(data)})
    except Exception as e:
        ui_error("Αποτυχία αποθήκευσης δεδομένων.", "save_data_error", {"error": str(e)})


def find_index_by_id(data: List[Dict[str, Any]], rec_id: str) -> int:
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


def find_invoice_record_index_by_number(data: List[Dict[str, Any]], inv_no: str) -> Optional[int]:
    if not inv_no:
        return None
    for i, r in enumerate(data):
        if r.get("source") == "invoice_html" and r.get("invoice_number") == inv_no:
            return i
    return None


# ----- Template helpers -----
def read_template_columns(path: str) -> Optional[list[str]]:
    if not os.path.exists(path):
        return None
    try:
        df0 = pd.read_csv(path, nrows=0, sep=None, engine="python", encoding="utf-8-sig")
        cols = [str(c).strip() for c in list(df0.columns)]
        return cols or None
    except Exception:
        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
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
    """Κανονικοποίηση header: πεζά, χωρίς κενά/underscores/τελείες."""
    return "".join(ch for ch in s.lower().strip() if ch.isalnum())


def build_template_mapping(template_cols: list[str]) -> Dict[str, str]:
    """
    Mapping από κάθε template header -> internal field.
    """
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

    mapping: Dict[str, str] = {}
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
    records: List[Dict[str, Any]],
    template_cols: list[str],
    invoice_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> pd.DataFrame:
    """
    Γεμίζει τις στήλες του template με σωστά δεδομένα.
    """
    header_map = build_template_mapping(template_cols)

    rows = []
    for r in records:
        src = (r.get("source") or "").strip()  # form / email / invoice_html

        # --- date ---
        if src == "form":
            date_val = _coalesce(r.get("submission_date"), r.get("created_at"))
        elif src == "email":
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        else:  # invoice_html
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        date_val = _as_date_str(date_val)

        # --- type ---
        if src == "invoice_html":
            type_val = "invoice"
        elif src == "email":
            type_val = _coalesce(r.get("email_type"), "email")
        else:
            type_val = "form"

        # --- client_name ---
        client_name = _coalesce(
            r.get("buyer_name"),
            r.get("full_name"),
            r.get("name"),
            r.get("from_name"),
        )

        # --- company ---
        company = _coalesce(
            r.get("company"),
            r.get("buyer_name"),
            r.get("seller_name"),
        )

        # --- service_interest ---
        service_interest = _coalesce(r.get("service"), r.get("service_interest"))

        # --- invoice_number ---
        inv_no = _coalesce(r.get("invoice_number"), r.get("invoice_number_in_subject"))
        inv_no_str = str(inv_no) if inv_no != "" else ""

        # --- amounts ---
        if src == "invoice_html":
            amount = _as_float(r.get("subtotal"))
            vat = _as_float(r.get("vat_amount"))
            total_amount = _as_float(_coalesce(r.get("total")))
        elif src == "email":
            inv = invoice_index.get(inv_no) if (invoice_index and inv_no) else None
            if inv:
                amount = _as_float(inv.get("subtotal"))
                vat = _as_float(inv.get("vat_amount"))
                total_amount = _as_float(inv.get("total"))
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
                        [f"{(n or {}).get('label','')}: {(n or {}).get('value','')}".strip(": ").strip() for n in notes]
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

        row = {}
        for col in template_cols:
            internal_key = header_map.get(col, "")
            if internal_key:
                row[col] = internal_values.get(internal_key, "")
            else:
                # δοκίμασε 1) raw key 2) normalized match
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

    df = pd.DataFrame(rows, columns=template_cols)
    return df


def pretty_email_body(text: str) -> str:
    """Κάνει πιο ευανάγνωστο το body ενός email με απλούς κανόνες."""
    if not text:
        return ""
    s = text.strip()

    # Βάλε κενές γραμμές πριν/μετά από κλασικές ενότητες
    s = re.sub(r"(Προσωπ(ικά|ικα)\s+Στοιχεί(α|α)\s*:)", r"\n\1\n", s, flags=re.IGNORECASE)
    s = re.sub(r"(Το\s+προβλ(η|ή)μα\s+μας\s*:)", r"\n\1\n", s, flags=re.IGNORECASE)
    s = re.sub(r"(Θ(έ|ε)λ(ο|ου)με\s+σ(ύ|υ)στημα\s+που\s*:?)", r"\n\1\n", s, flags=re.IGNORECASE)

    # Bullets: ' - ' -> νέα γραμμή + κουκκίδα, εκτός αν είναι ανάμεσα σε ψηφία (π.χ. 2310-987654)
    s = re.sub(r"(?<!\d)\s-\s(?!\d)", "\n• ", s)

    # Σπάσε «1. ... 2. ...» σε ξεχωριστές γραμμές
    s = re.sub(r"\s(?=\d+\.\s)", "\n", s)

    # Μάζεψε πολλαπλές κενές γραμμές
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


# ------------- App -------------
st.set_page_config(page_title="AthenaGen HIL Review", layout="wide")

st.title("AthenaGen – Human-in-the-Loop Review")
st.caption("Δες/επιβεβαίωσε/διόρθωσε εγγραφές από φόρμες, emails και τιμολόγια.")

data = load_data()

# index για γρήγορη ανεύρεση parsed τιμολογίου από EMAIL
try:
    invoice_index = {
        r.get("invoice_number"): r
        for r in data
        if r.get("source") == "invoice_html" and r.get("invoice_number")
    }
except Exception as e:
    invoice_index = {}
    ui_warn("Σφάλμα δημιουργίας invoice index.", "invoice_index_error", {"error": str(e)})

# Sidebar: filters
with st.sidebar:
    st.header("Φίλτρα")
    sources = st.multiselect(
        "Πηγή (source)",
        options=["form", "email", "invoice_html"],
        default=["form", "email", "invoice_html"],
    )
    statuses = st.multiselect(
        "Κατάσταση (status)",
        options=ALLOWED_STATUS,
        default=ALLOWED_STATUS,
    )
    needs_action_only = st.checkbox(
        "Μόνο εγγραφές που χρειάζονται ενέργεια (π.χ. invoice email χωρίς PDF)",
        value=False
    )
    q = st.text_input("Αναζήτηση (subject, όνομα, email, εταιρεία)")

    sort_key = st.selectbox(
        "Ταξινόμηση κατά",
        options=["date", "created_at", "source", "status"],
        index=0
    )
    sort_desc = st.checkbox("Φθίνουσα ταξινόμηση", value=False)

    st.divider()

    # Flash message για rebuild (αν υπάρχει από το προηγούμενο rerun)
    flash = st.session_state.pop("flash_rebuild", None)
    if flash:
        st.success(
            f"✅ Έγινε rebuild δεδομένων — forms: {flash['forms']}, "
            f"emails: {flash['emails']}, invoices: {flash['invoices']} • {flash['ts']}"
        )

    st.subheader("Rebuild feed")
    if st.button("🔄 Τρέξε parsers & ανανέωσε δεδομένα", key="rebuild_btn"):
        try:
            with st.spinner("Τρέχουν οι parsers…"):
                from data_parser.parse_emails import parse_all_emails as _parse_emails
                from data_parser.parse_forms import parse_all_forms as _parse_forms
                from data_parser.parse_invoices import parse_all_invoices as _parse_invoices
                import re as _re

                def _extract_inv_no(txt: str | None):
                    pat = _re.compile(
                        r"(?:invoice|τιμολ(?:όγιο|\.?)|αρ\.?\s*τιμολ(?:ογίου)?)\s*(?:no\.?|#|nr\.?|:)?\s*([A-Z]{0,4}[-/]?\d[\w\-\/]+)",
                        _re.IGNORECASE
                    )
                    m = pat.search(txt or "")
                    return m.group(1).strip() if m else None

                forms = _parse_forms("dummy_data/forms")
                emails = _parse_emails("dummy_data/emails")
                invoices = _parse_invoices("dummy_data/invoices")

                inv_by_no = {(r.get("invoice_number") or "").strip(): r for r in invoices if r.get("invoice_number")}
                enriched_emails = []
                for e in emails:
                    inv_no = _extract_inv_no(e.get("subject", "")) or _extract_inv_no(e.get("body", ""))
                    linked = inv_by_no.get(inv_no) if inv_no else None
                    enriched_emails.append({
                        **e,
                        "invoice_number_in_subject": inv_no,
                        "matched_invoice_html": bool(linked),
                        "matched_invoice_file": linked.get("source_file") if linked else None,
                        "matched_invoice_total": linked.get("total") if linked else None,
                        "needs_action": (e.get("email_type") == "invoice")
                                        and (e.get("missing_attachment") or not e.get("has_pdf_attachments") or not linked),
                    })

                combined = (
                    [{"source": "form", "status": "pending", **r} for r in forms] +
                    [{"source": "email", "status": "pending", **r} for r in enriched_emails] +
                    [{"source": "invoice_html", "status": "pending", **r} for r in invoices]
                )
                save_data(combined)

                # Βάλε flash στο session_state και ΚΑΝΕ rerun
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
def match_query(rec: Dict[str, Any], q: str) -> bool:
    if not q:
        return True
    try:
        hay = " ".join([
            str(rec.get("subject", "")),
            str(rec.get("full_name", "")),
            str(rec.get("email", "")),
            str(rec.get("company", "")),
            str(rec.get("invoice_number", "")),
            str(rec.get("service", "")),
        ]).lower()
        return q.lower() in hay
    except Exception:
        return True


try:
    view = [
        r for r in data
        if r.get("source") in sources
        and r.get("status") in statuses
        and (not needs_action_only or r.get("needs_action"))
        and match_query(r, q)
    ]
except Exception as e:
    view = []
    ui_error("Σφάλμα εφαρμογής φίλτρων/αναζήτησης.", "filter_error", {"error": str(e)})


def safe_sort_key(r: Dict[str, Any]):
    val = r.get(sort_key)
    return val if val is not None else ""


try:
    view = sorted(view, key=safe_sort_key, reverse=sort_desc)
except Exception as e:
    ui_warn("Αποτυχία ταξινόμησης. Εμφάνιση χωρίς ταξινόμηση.", "sort_error", {"error": str(e)})

# Sidebar: list of records
with st.sidebar:
    st.subheader(f"Αποτελέσματα: {len(view)}")
    labels = []
    try:
        for r in view:
            tag = {"form": "FORM", "email": "EMAIL", "invoice_html": "INV"}.get(r.get("source"), r.get("source"))
            title = (
                r.get("subject")
                or r.get("invoice_number")
                or r.get("full_name")
                or r.get("company")
                or r.get("service")
                or r.get("source_file")
                or r["id"]
            )
            labels.append(f"[{tag}] {title}")
    except Exception as e:
        ui_warn("Σφάλμα κατασκευής λιστας sidebar.", "sidebar_list_error", {"error": str(e)})

    sel = st.selectbox("Εγγραφή", options=range(len(view)), format_func=lambda i: labels[i] if view else "")

# -------- Export με Template --------
with st.sidebar:
    st.divider()
    st.subheader("Export (με Template)")

    st.caption(f"Filtered rows: {len(view)} • Total rows: {len(data)}")

    export_scope = st.radio("Τι να εξαχθεί;", options=["Filtered", "All"], index=0, horizontal=True, key="export_scope_radio")
    records_for_export = view if export_scope == "Filtered" else data

    with st.expander("🔎 Debug: δείγμα δεδομένων προς export (πρώτα 10)", expanded=False):
        try:
            st.dataframe(pd.DataFrame(records_for_export[:10]), hide_index=True, use_container_width=True)
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης debug δείγματος.", "export_debug_sample_error", {"error": str(e)})

    template_cols = read_template_columns(TEMPLATE_PATH)
    if not template_cols:
        st.error(f"Δεν βρέθηκαν headers στο template: {TEMPLATE_PATH}")
        st.caption("Τοποθέτησε ένα CSV με μόνο headers στην πρώτη γραμμή.")
        export_enabled = False
    else:
        export_enabled = True
        st.success(f"Template OK ({len(template_cols)} στήλες)")
        with st.expander("🧭 Mapping template → internal keys", expanded=False):
            st.json(build_template_mapping(template_cols))

    save_copy_to_disk = st.checkbox("Αποθήκευση αντιγράφου στο exports/", value=True,
                                    help="Θα γράψει το παραγόμενο αρχείο στον φάκελο exports/")

    if st.button("📄 Προεπισκόπηση Export (πρώτες 20)", disabled=not export_enabled, key="export_preview_btn"):
        try:
            df_preview = build_template_df(records_for_export, template_cols, invoice_index=invoice_index)[:20]
            st.dataframe(df_preview, use_container_width=True, hide_index=True)
        except Exception as e:
            ui_error("Αποτυχία δημιουργίας προεπισκόπησης export.", "export_preview_error", {"error": str(e)})

    # CSV
    try:
        if export_enabled and st.button("⬇️ Export CSV (Template)", key="export_csv_btn"):
            df_export = build_template_df(records_for_export, template_cols, invoice_index=invoice_index)
            csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"export_template_{ts}.csv"

            if save_copy_to_disk:
                try:
                    ensure_dirs()
                    csv_path = os.path.join(EXPORTS_DIR, csv_filename)
                    with open(csv_path, "wb") as f:
                        f.write(csv_bytes)
                    st.success(f"Αποθηκεύτηκε αντίγραφο: {csv_path}")
                    log_action("export_csv_saved", {"rows": len(df_export), "cols": len(template_cols), "path": csv_path, "scope": export_scope})
                except Exception as e:
                    ui_warn("Δεν μπόρεσα να γράψω το CSV στο exports/ (θα πάρεις μόνο το download).",
                            "export_csv_write_warn", {"error": str(e)})

            st.download_button("Λήψη CSV", data=csv_bytes, file_name=csv_filename,
                               mime="text/csv", key=f"download_csv_btn_{ts}")
            log_action("export_csv", {"rows": len(df_export), "cols": len(template_cols), "scope": export_scope})
    except Exception as e:
        ui_error("Αποτυχία export CSV.", "export_csv_error", {"error": str(e)})

    # Excel
    try:
        if export_enabled and st.button("⬇️ Export Excel (Template)", key="export_xlsx_btn"):
            df_export = build_template_df(records_for_export, template_cols, invoice_index=invoice_index)
            buffer = BytesIO()
            try:
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_export.to_excel(writer, index=False, sheet_name="Export")
                excel_bytes = buffer.getvalue()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                xlsx_filename = f"export_template_{ts}.xlsx"

                if save_copy_to_disk:
                    try:
                        ensure_dirs()
                        xlsx_path = os.path.join(EXPORTS_DIR, xlsx_filename)
                        with open(xlsx_path, "wb") as f:
                            f.write(excel_bytes)
                        st.success(f"Αποθηκεύτηκε αντίγραφο: {xlsx_path}")
                        log_action("export_excel_saved", {"rows": len(df_export), "cols": len(template_cols), "path": xlsx_path, "scope": export_scope})
                    except Exception as e:
                        ui_warn("Δεν μπόρεσα να γράψω το Excel στο exports/ (θα πάρεις μόνο το download).",
                                "export_excel_write_warn", {"error": str(e)})

                st.download_button(
                    "Λήψη Excel",
                    data=excel_bytes,
                    file_name=xlsx_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_xlsx_btn_{ts}",
                )
                log_action("export_excel", {"rows": len(df_export), "cols": len(template_cols), "scope": export_scope})
            except ModuleNotFoundError:
                st.error("Λείπει το openpyxl. Τρέξε: `pip install openpyxl`.")
            except Exception as e:
                ui_error("Αποτυχία export Excel.", "export_excel_error", {"error": str(e)})
    except Exception as e:
        ui_error("Σφάλμα στην ενότητα Export.", "export_section_error", {"error": str(e)})

    # Πρόσφατα exports
    with st.expander("📜 Πρόσφατα exports", expanded=False):
        try:
            ensure_dirs()
            files = []
            for fname in os.listdir(EXPORTS_DIR):
                if fname.lower().endswith((".csv", ".xlsx")):
                    fpath = os.path.join(EXPORTS_DIR, fname)
                    try:
                        stat = os.stat(fpath)
                        files.append((fname, fpath, stat.st_mtime, stat.st_size))
                    except Exception:
                        continue
            files.sort(key=lambda x: x[2], reverse=True)
            if not files:
                st.caption("Δεν υπάρχουν ακόμη αρχεία στο exports/.")
            else:
                for fname, fpath, mtime, size in files[:12]:
                    size_kb = max(1, int(size / 1024))
                    st.write(f"• {fname} — ~{size_kb} KB")
                    try:
                        with open(fpath, "rb") as fh:
                            st.download_button("Λήψη", data=fh.read(), file_name=fname, key=f"dl_{fname}")
                    except Exception:
                        st.caption("(Δεν μπόρεσα να ανοίξω το αρχείο για download)")
        except Exception as e:
            ui_warn("Δεν μπόρεσα να διαβάσω το φάκελο exports/.", "exports_list_error", {"error": str(e)})

# -------- Record details --------
if not view:
    ui_info("Δεν βρέθηκαν εγγραφές με τα συγκεκριμένα φίλτρα.", "no_results")
    st.stop()

rec = view[sel]
idx = find_index_by_id(data, rec.get("id", ""))
if idx < 0:
    ui_error("Η επιλεγμένη εγγραφή δεν βρέθηκε στα δεδομένα.", "record_not_found", {"id": rec.get("id")})
    st.stop()

invoice_payload: Optional[Dict[str, Any]] = None
invoice_rec_idx: Optional[int] = None
try:
    if rec.get("source") == "invoice_html":
        invoice_payload = rec
        invoice_rec_idx = idx
    elif rec.get("source") == "email":
        inv_no = rec.get("invoice_number_in_subject")
        if inv_no:
            invoice_payload = invoice_index.get(inv_no)
            invoice_rec_idx = find_invoice_record_index_by_number(data, inv_no)
except Exception as e:
    ui_warn("Σφάλμα αντιστοίχισης email → invoice.", "email_invoice_match_error", {"error": str(e)})

col1, col2 = st.columns([2, 1], gap="large")

with col1:
    st.subheader("Πλήρη στοιχεία")
    try:
        st.json(rec, expanded=False)
    except Exception as e:
        ui_warn("Αποτυχία εμφάνισης JSON εγγραφής.", "json_view_error", {"error": str(e)})

    if rec.get("source") == "email":
        try:
            with st.expander("📧 Περιεχόμενο Email (Plain Text)", expanded=False):
                # Toggle για «όμορφη» προβολή
                pretty_on = st.checkbox(
                    "Μορφοποίηση για ανάγνωση",
                    value=True,
                    key=f"pretty_email_ck_{rec.get('id','')}",
                )
                body_raw = rec.get("body", "")
                body_show = pretty_email_body(body_raw) if pretty_on else body_raw

                st.text_area(
                    "Μήνυμα",
                    value=body_show,
                    height=300,
                    key=f"email_body_{rec.get('id','')}",
                )
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης body (plain).", "email_plain_view_error", {"error": str(e)})

    if invoice_payload:
        st.markdown("### Στοιχεία Τιμολογίου (parsed)")
        try:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Εκδότης**")
                st.write(
                    f"- Επωνυμία: {invoice_payload.get('seller_name','')}\n"
                    f"- Email: {invoice_payload.get('seller_email','')}\n"
                    f"- Τηλέφωνο: {invoice_payload.get('seller_phone','')}\n"
                    f"- ΑΦΜ: {invoice_payload.get('seller_vat','')}\n"
                    f"- ΔΟΥ: {invoice_payload.get('seller_tax_office','')}\n"
                    f"- Διεύθυνση: {invoice_payload.get('seller_address','')}"
                )
            with c2:
                st.markdown("**Πελάτης**")
                st.write(
                    f"- Επωνυμία: {invoice_payload.get('buyer_name','')}\n"
                    f"- ΑΦΜ: {invoice_payload.get('buyer_vat','')}\n"
                    f"- Διεύθυνση: {invoice_payload.get('buyer_address','')}"
                )
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης στοιχείων εκδότη/πελάτη.", "seller_buyer_view_error", {"error": str(e)})

        try:
            c3, c4, c5 = st.columns(3)
            with c3:
                st.metric("Αριθμός", invoice_payload.get("invoice_number", ""))
            with c4:
                st.metric("Ημερομηνία", invoice_payload.get("date", ""))
            with c5:
                st.metric("Πληρωμή", invoice_payload.get("payment_method", ""))
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης βασικών μετρικών τιμολογίου.", "invoice_metrics_error", {"error": str(e)})

        with st.expander("Γραμμές προϊόντων (inline edit)", expanded=False):
            try:
                items = invoice_payload.get("items", []) or []
                editable_rows = []
                for it in items:
                    qty = it.get("quantity")
                    price = it.get("unit_price")
                    try:
                        line_total = round(float(qty) * float(price), 2) if qty is not None and price is not None else it.get("line_total")
                    except Exception:
                        line_total = it.get("line_total")
                    editable_rows.append({
                        "Περιγραφή": it.get("description", ""),
                        "Ποσότητα": qty if qty is not None else 0.0,
                        "Τιμή Μονάδας": price if price is not None else 0.0,
                        "Γραμμή Σύνολο": line_total if line_total is not None else 0.0,
                        "Νόμισμα": it.get("currency", invoice_payload.get("currency", "EUR")),
                    })

                editor_key = f"items_editor_{invoice_payload.get('id') or rec.get('id') or idx}"
                df = pd.DataFrame(editable_rows)
                edited_df = st.data_editor(
                    df,
                    num_rows="dynamic",
                    key=editor_key,
                    use_container_width=True,
                    hide_index=True,
                    disabled=False,
                    column_config={
                        "Περιγραφή": st.column_config.TextColumn("Περιγραφή"),
                        "Ποσότητα": st.column_config.NumberColumn("Ποσότητα", step=1.0, format="%.2f"),
                        "Τιμή Μονάδας": st.column_config.NumberColumn("Τιμή Μονάδας", step=0.10, format="%.2f"),
                        "Γραμμή Σύνολο": st.column_config.NumberColumn("Γραμμή Σύνολο", disabled=True, format="%.2f"),
                        "Νόμισμα": st.column_config.TextColumn("Νόμισμα"),
                    },
                )

                default_currency = invoice_payload.get("currency", "EUR")
                currency_input = st.text_input("Νόμισμα τιμολογίου", value=default_currency)
                vat_rate_val = invoice_payload.get("vat_rate", 24.0)
                try:
                    vat_rate_val = float(vat_rate_val) if vat_rate_val is not None else 24.0
                except Exception:
                    vat_rate_val = 24.0
                vat_rate_input = st.number_input("ΦΠΑ %", min_value=0.0, max_value=99.0, value=vat_rate_val, step=0.5)

                subtotal_calc = 0.0
                cleaned_items = []
                rows_iter = edited_df.to_dict("records") if edited_df is not None else []
                for row in rows_iter:
                    try:
                        qty = float(row.get("Ποσότητα") or 0)
                    except Exception:
                        qty = 0.0
                    try:
                        price = float(row.get("Τιμή Μονάδας") or 0)
                    except Exception:
                        price = 0.0
                    line_total = round(qty * price, 2)
                    subtotal_calc += line_total
                    cleaned_items.append({
                        "description": (row.get("Περιγραφή") or "").strip(),
                        "quantity": qty,
                        "unit_price": price,
                        "line_total": line_total,
                        "currency": (row.get("Νόμισμα") or currency_input or "EUR").strip(),
                    })
                subtotal_calc = round(subtotal_calc, 2)
                vat_amount_calc = round(subtotal_calc * (vat_rate_input / 100.0), 2)
                total_calc = round(subtotal_calc + vat_amount_calc, 2)

                c1, c2, c3 = st.columns(3)
                c1.metric("Καθαρή Αξία (υπολογ.)", f"{subtotal_calc:.2f}")
                c2.metric("ΦΠΑ (υπολογ.)", f"{vat_amount_calc:.2f} ({vat_rate_input:.2f}%)")
                c3.metric("Σύνολο (υπολογ.)", f"{total_calc:.2f}")

                if st.button("Αποθήκευση γραμμών & υπολογισμών", key="save_items_btn"):
                    try:
                        target_idx = invoice_rec_idx if invoice_rec_idx is not None else idx
                        inv_rec = dict(data[target_idx])
                        inv_rec.update({
                            "items": cleaned_items,
                            "currency": currency_input or "EUR",
                            "subtotal": subtotal_calc,
                            "vat_rate": round(float(vat_rate_input), 2),
                            "vat_amount": vat_amount_calc,
                            "total": total_calc,
                            "status": "edited",
                            "updated_at": now_iso(),
                        })
                        data[target_idx] = inv_rec
                        if target_idx == idx:
                            for k, v in inv_rec.items():
                                if k != "id":
                                    rec[k] = v
                        save_data(data)
                        st.success("Αποθηκεύτηκαν οι γραμμές & οι υπολογισμοί.")
                        log_action("save_items_calc", {"record_id": rec.get("id")})
                    except Exception as e:
                        ui_error("Αποτυχία αποθήκευσης γραμμών/υπολογισμών.", "save_items_calc_error", {"error": str(e)})
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης/editor γραμμών προϊόντων.", "items_editor_error", {"error": str(e)})

        try:
            st.markdown("**Σύνοψη**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Καθαρή Αξία", f"{invoice_payload.get('subtotal', '')}")
            vat_val = invoice_payload.get("vat_amount", "")
            vat_rate = invoice_payload.get("vat_rate", "")
            c2.metric("ΦΠΑ", f"{vat_val} ({vat_rate}%)" if vat_rate != "" else f"{vat_val}")
            c3.metric("Σύνολο", f"{invoice_payload.get('total', '')}")
            c4.metric("Νόμισμα", invoice_payload.get("currency", ""))
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης σύνοψης.", "summary_view_error", {"error": str(e)})

        with st.expander("Edit στοιχεία τιμολογίου (εκδότης/πελάτης/πληρωμή)", expanded=False):
            try:
                seller_name  = st.text_input("Επωνυμία Εκδότη", value=invoice_payload.get("seller_name", ""))
                seller_email = st.text_input("Email Εκδότη", value=invoice_payload.get("seller_email", ""))
                seller_phone = st.text_input("Τηλέφωνο Εκδότη", value=invoice_payload.get("seller_phone", ""))
                seller_vat   = st.text_input("ΑΦΜ Εκδότη", value=invoice_payload.get("seller_vat", ""))
                seller_tax_office = st.text_input("ΔΟΥ Εκδότη", value=invoice_payload.get("seller_tax_office", ""))
                seller_address    = st.text_input("Διεύθυνση Εκδότη", value=invoice_payload.get("seller_address", ""))

                buyer_name   = st.text_input("Επωνυμία Πελάτη", value=invoice_payload.get("buyer_name", ""))
                buyer_vat    = st.text_input("ΑΦΜ Πελάτη", value=invoice_payload.get("buyer_vat", ""))
                buyer_address= st.text_input("Διεύθυνση Πελάτη", value=invoice_payload.get("buyer_address", ""))

                payment_method = st.text_input("Τρόπος Πληρωμής", value=invoice_payload.get("payment_method", ""))

                if st.button("Αποθήκευση στοιχείων τιμολογίου", key="save_invoice_meta_btn"):
                    try:
                        target_idx = invoice_rec_idx if invoice_rec_idx is not None else idx
                        inv_rec = dict(data[target_idx])
                        inv_rec.update({
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
                        })
                        data[target_idx] = inv_rec
                        if target_idx == idx:
                            for k, v in inv_rec.items():
                                if k != "id":
                                    rec[k] = v
                        save_data(data)
                        st.success("Αποθηκεύτηκαν τα στοιχεία τιμολογίου (status=edited).")
                        log_action("save_invoice_parties", {"record_id": rec.get("id")})
                    except Exception as e:
                        ui_error("Αποτυχία αποθήκευσης στοιχείων τιμολογίου.", "save_invoice_parties_error", {"error": str(e)})
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης editor στοιχείων τιμολογίου.", "invoice_parties_editor_error", {"error": str(e)})

        with st.expander("Extra πεδία/σημειώσεις από footer", expanded=False):
            try:
                current_notes = invoice_payload.get("extra_notes", [])
                edited_notes = st.data_editor(
                    current_notes,
                    num_rows="dynamic",
                    key=f"footer_notes_{invoice_payload.get('id', idx)}",
                    column_config={"label": st.column_config.TextColumn("Label"),
                                   "value": st.column_config.TextColumn("Value")},
                )
                if st.button("Αποθήκευση footer/σημειώσεων", key="save_footer_btn"):
                    try:
                        clean = []
                        for row in (edited_notes or []):
                            lab = (row.get("label") or "").strip()
                            val = (row.get("value") or "").strip()
                            if lab or val:
                                clean.append({"label": lab, "value": val})
                        target_idx = invoice_rec_idx if invoice_rec_idx is not None else idx
                        inv_rec = dict(data[target_idx])
                        inv_rec["extra_notes"] = clean
                        inv_rec["status"] = "edited"
                        inv_rec["updated_at"] = now_iso()
                        data[target_idx] = inv_rec
                        if target_idx == idx:
                            rec["extra_notes"] = clean
                        save_data(data)
                        st.success("Footer/σημειώσεις αποθηκεύτηκαν.")
                        log_action("save_footer_notes", {"record_id": rec.get("id"), "count": len(clean)})
                    except Exception as e:
                        ui_error("Αποτυχία αποθήκευσης footer/σημειώσεων.", "save_footer_notes_error", {"error": str(e)})
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης editor footer.", "footer_editor_error", {"error": str(e)})

    # -------- Προεπισκόπηση HTML τιμολογίου --------
    preview_html = None
    html_title = None
    try:
        if rec.get("source") == "email" and rec.get("matched_invoice_file"):
            candidate = os.path.join(INVOICES_DIR, rec["matched_invoice_file"])
            if os.path.exists(candidate):
                html_title = f"Προεπισκόπηση Τιμολογίου: {rec['matched_invoice_file']}"
                with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                    preview_html = f.read()
        elif rec.get("source") == "invoice_html" and rec.get("source_file"):
            candidate = os.path.join(INVOICES_DIR, rec["source_file"])
            if os.path.exists(candidate):
                html_title = f"Προεπισκόπηση Τιμολογίου: {rec['source_file']}"
                with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                    preview_html = f.read()
    except Exception as e:
        ui_warn("Αποτυχία ανάγνωσης αρχείου HTML τιμολογίου.", "invoice_html_read_error", {"error": str(e)})
    if preview_html:
        try:
            with st.expander(html_title or "Προεπισκόπηση Τιμολογίου (HTML)", expanded=False):
                st.markdown("<style>.invoice-preview iframe { background: #fff !important; }</style>", unsafe_allow_html=True)
                components.html(preview_html, height=900, scrolling=True)
                st.download_button(
                    "⬇️ Λήψη HTML τιμολογίου",
                    data=preview_html.encode("utf-8"),
                    file_name=(rec.get("matched_invoice_file") or rec.get("source_file") or "invoice.html"),
                    mime="text/html",
                    key="download_html_btn",
                )
        except Exception as e:
            ui_warn("Αποτυχία εμφάνισης προεπισκόπησης HTML.", "invoice_preview_error", {"error": str(e)})

    # -------- Edit γενικά --------
    if rec.get("source") != "invoice_html":
        with st.expander("Edit πεδία (safe form)", expanded=False):
            try:
                new_full_name = st.text_input("Ονοματεπώνυμο", value=rec.get("full_name", ""))
                new_email     = st.text_input("Email", value=rec.get("email", ""))
                new_phone     = st.text_input("Τηλέφωνο", value=rec.get("phone", ""))
                new_company   = st.text_input("Εταιρεία", value=rec.get("company", ""))
                new_service   = st.text_input("Υπηρεσία Ενδιαφέροντος", value=rec.get("service", ""))

                new_subject = new_inv_no = new_total = None
                new_message = new_subdate = new_priority = None

                if rec.get("source") in ("email", "form"):
                    new_subject = st.text_input("Subject (αν υπάρχει)", value=rec.get("subject", ""))

                if rec.get("source") == "form":
                    new_message   = st.text_area("Μήνυμα", value=rec.get("message", ""))
                    new_subdate   = st.text_input("Ημερομηνία Υποβολής (datetime-local)", value=rec.get("submission_date", ""))
                    new_priority  = st.text_input("Προτεραιότητα", value=rec.get("priority", ""))

                if rec.get("source") == "email":
                    new_inv_no = st.text_input("Invoice Number (αν υπάρχει)", value=rec.get("invoice_number", ""))
                    new_total  = st.text_input("Σύνολο (αν υπάρχει)", value=str(rec.get("total", "")))

                if st.button("Αποθήκευση αλλαγών (Edit)", key="save_generic_edit_btn"):
                    try:
                        rec["full_name"] = new_full_name or rec.get("full_name")
                        rec["email"]     = new_email or rec.get("email")
                        rec["phone"]     = new_phone or rec.get("phone")
                        rec["company"]   = new_company or rec.get("company")
                        if new_service:
                            rec["service"] = new_service

                        if new_subject is not None and new_subject != "":
                            rec["subject"] = new_subject

                        if rec.get("source") == "form":
                            rec["message"] = new_message if new_message is not None else rec.get("message")
                            rec["submission_date"] = new_subdate if new_subdate is not None else rec.get("submission_date")
                            rec["priority"] = new_priority if new_priority is not None else rec.get("priority")

                        if new_inv_no is not None and new_inv_no != "":
                            rec["invoice_number"] = new_inv_no
                        if new_total is not None and new_total != "":
                            rec["total"] = parse_total_input(new_total, rec.get("total"))

                        rec["status"] = "edited"
                        rec["updated_at"] = now_iso()
                        data[idx] = rec
                        save_data(data)
                        st.success("Οι αλλαγές αποθηκεύτηκαν (status=edited).")
                        log_action("save_generic_edit", {"record_id": rec.get("id")})
                    except Exception as e:
                        ui_error("Αποτυχία αποθήκευσης αλλαγών.", "save_generic_edit_error", {"error": str(e)})
            except Exception as e:
                ui_warn("Αποτυχία εμφάνισης generic editor.", "generic_editor_error", {"error": str(e)})

with col2:
    st.subheader("Ενέργειες")
    try:
        st.write(f"**Status:** {rec.get('status','pending')}")
        new_status = st.selectbox("Αλλαγή status", ALLOWED_STATUS, index=ALLOWED_STATUS.index(rec.get("status", "pending")))
        if st.button("Εφαρμογή status", key="apply_status_btn"):
            try:
                rec["status"] = new_status
                rec["updated_at"] = now_iso()
                data[idx] = rec
                save_data(data)
                st.success(f"Status → {new_status}")
                log_action("change_status", {"record_id": rec.get("id"), "status": new_status})
            except Exception as e:
                ui_error("Αποτυχία αλλαγής status.", "change_status_error", {"error": str(e)})
    except Exception as e:
        ui_warn("Αποτυχία χειρισμού status.", "status_ui_error", {"error": str(e)})

    st.divider()
    try:
        if st.button("✅ Approve", key="approve_btn"):
            try:
                rec["status"] = "approved"
                rec["updated_at"] = now_iso()
                data[idx] = rec
                save_data(data)
                st.success("Εγκρίθηκε (approved).")
                log_action("approve_record", {"record_id": rec.get("id")})
            except Exception as e:
                ui_error("Αποτυχία έγκρισης.", "approve_error", {"error": str(e)})
        if st.button("⛔ Reject", key="reject_btn"):
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
        ui_warn("Αποτυχία κουμπιών approve/reject.", "approve_reject_ui_error", {"error": str(e)})

    st.divider()
    try:
        with st.form("quick_note"):
            note = st.text_area("Σημειώσεις (προαιρετικά)", value=rec.get("notes", ""))
            submitted = st.form_submit_button("Αποθήκευση σημειώσεων")
            if submitted:
                try:
                    rec["notes"] = note
                    rec["updated_at"] = now_iso()
                    data[idx] = rec
                    save_data(data)
                    st.success("Σημειώσεις αποθηκεύτηκαν.")
                    log_action("save_notes", {"record_id": rec.get("id")})
                except Exception as e:
                    ui_error("Αποτυχία αποθήκευσης σημειώσεων.", "save_notes_error", {"error": str(e)})
    except Exception as e:
        ui_warn("Αποτυχία φόρμας σημειώσεων.", "notes_form_error", {"error": str(e)})

# -------- Log Viewer --------
with st.expander("📜 Log Viewer (outputs/log.txt)", expanded=False):
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                tail = f.readlines()[-400:]
            st.text("".join(tail))
            if st.button("🧹 Καθάρισε το log", key="clear_log_btn"):
                try:
                    open(LOG_PATH, "w", encoding="utf-8").close()
                    st.success("Καθαρίστηκε το log.")
                except Exception as e:
                    ui_error("Αποτυχία καθαρισμού log.", "log_clear_error", {"error": str(e)})
        else:
            st.info("Δεν βρέθηκε log.txt ακόμη.")
    except Exception as e:
        ui_warn("Αποτυχία ανάγνωσης log.", "log_view_error", {"error": str(e)})

st.caption("Tip: Τα δεδομένα γράφονται ξανά στο outputs/combined_feed.json (κρατάμε backup ανά αποθήκευση).")
