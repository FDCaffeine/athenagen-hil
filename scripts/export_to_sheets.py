# scripts/export_to_sheets.py
import argparse
import json
import os
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

DEFAULT_INPUT = "outputs/combined_feed.json"
DEFAULT_TEMPLATE = "dummy_data/templates/data_extraction_template.csv"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ---------- Credentials ----------
def make_creds(env_var: str = "GCP_SERVICE_ACCOUNT_JSON", sa_file: str | None = None):
    """
    Δημιουργεί Google credentials είτε από ENV JSON είτε από αρχείο .json.
    Προτεραιότητα έχει το ENV (βολικό για CI/CD).
    """
    if os.getenv(env_var):
        info = json.loads(os.environ[env_var])
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    if sa_file and os.path.exists(sa_file):
        return Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    raise SystemExit(
        "❌ Δεν βρέθηκαν credentials. Δώσε ENV GCP_SERVICE_ACCOUNT_JSON ή --sa-file path."
    )


# ---------- Template helpers (συμβατά με το app.py) ----------
def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower().strip() if ch.isalnum())


def read_template_columns(path: str) -> list[str] | None:
    if not path or not os.path.exists(path):
        return None
    try:
        df0 = pd.read_csv(path, nrows=0, sep=None, engine="python", encoding="utf-8-sig")
        cols = [str(c).strip() for c in list(df0.columns)]
        return cols or None
    except Exception:
        try:
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
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


def index_invoices(records: list[dict[str, Any]]):
    return {
        r.get("invoice_number"): r
        for r in records
        if r.get("source") == "invoice_html" and r.get("invoice_number")
    }


def build_template_df(records: list[dict[str, Any]], template_cols: list[str]) -> pd.DataFrame:
    header_map = build_template_mapping(template_cols)
    inv_idx = index_invoices(records)

    rows = []
    for r in records:
        src = (r.get("source") or "").strip()

        # date
        if src == "form":
            date_val = _coalesce(r.get("submission_date"), r.get("created_at"))
        elif src == "email":
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        else:
            date_val = _coalesce(r.get("date"), r.get("created_at"))
        date_val = _as_date_str(date_val)

        # type
        if src == "invoice_html":
            type_val = "invoice"
        elif src == "email":
            type_val = _coalesce(r.get("email_type"), "email")
        else:
            type_val = "form"

        client_name = _coalesce(
            r.get("buyer_name"), r.get("full_name"), r.get("name"), r.get("from_name")
        )
        company = _coalesce(r.get("company"), r.get("buyer_name"), r.get("seller_name"))
        service_interest = _coalesce(r.get("service"), r.get("service_interest"))

        inv_no = _coalesce(r.get("invoice_number"), r.get("invoice_number_in_subject"))
        inv_no_str = str(inv_no) if inv_no != "" else ""

        if src == "invoice_html":
            amount = _as_float(r.get("subtotal"))
            vat = _as_float(r.get("vat_amount"))
            total_amount = _as_float(_coalesce(r.get("total")))
        elif src == "email":
            inv = inv_idx.get(inv_no) if inv_no else None
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

        row = {}
        for col in template_cols:
            internal_key = header_map.get(col, "")
            if internal_key:
                row[col] = internal_values.get(internal_key, "")
            else:
                # προσπάθεια 1) raw key 2) normalized match από το record
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


# ---------- Core ----------
def load_records(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        raise SystemExit(f"❌ Δεν βρέθηκε input: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ensure_worksheet(client: gspread.Client, sheet_id: str, worksheet: str):
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows=100, cols=26)
    return ws


def upload_dataframe(df: pd.DataFrame, sheet_id: str, worksheet: str, creds: Credentials) -> str:
    client = gspread.authorize(creds)
    ws = ensure_worksheet(client, sheet_id, worksheet)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True, resize=True)
    return f"✅ Uploaded {len(df)} rows × {len(df.columns)} cols to '{worksheet}'."


def main():
    ap = argparse.ArgumentParser(description="Upload export to Google Sheets via Service Account")
    ap.add_argument("--sheet-id", required=True, help="Google Spreadsheet ID (από το URL)")
    ap.add_argument("--worksheet", default="Export", help="Worksheet/tab name (default: Export)")
    ap.add_argument("--input", default=DEFAULT_INPUT, help=f"Input JSON (default: {DEFAULT_INPUT})")
    ap.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        help=f"Template CSV headers (default: {DEFAULT_TEMPLATE})",
    )
    ap.add_argument(
        "--sa-file",
        default=None,
        help="Path σε service_account.json (εναλλακτικά χρησιμοποίησε ENV GCP_SERVICE_ACCOUNT_JSON)",
    )
    args = ap.parse_args()

    creds = make_creds(sa_file=args.sa_file)

    # Φόρτωσε combined_feed.json
    records = load_records(args.input)

    # Διάβασε headers από template (ή φτιάξε fallback)
    template_cols = read_template_columns(args.template)
    if not template_cols:
        # Fallback: χρησιμοποίησε μερικές βασικές στήλες
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

    # Φτιάξε DF με τους κανόνες του template
    df = build_template_df(records, template_cols)

    # Upload
    msg = upload_dataframe(df, args.sheet_id, args.worksheet, creds)
    print(msg)


if __name__ == "__main__":
    main()
