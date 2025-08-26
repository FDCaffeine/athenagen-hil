# settings.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
BACKUPS_DIR = OUTPUTS_DIR / "_backups"
EXPORTS_DIR = BASE_DIR / "exports"
DUMMY_DIR = BASE_DIR / "dummy_data"
FORMS_DIR = DUMMY_DIR / "forms"
EMAILS_DIR = DUMMY_DIR / "emails"
INVOICES_DIR = DUMMY_DIR / "invoices"
TEMPLATE_PATH = DUMMY_DIR / "templates" / "data_extraction_template.csv"

COMBINED_PATH = OUTPUTS_DIR / "combined_feed.json"
LOG_PATH = OUTPUTS_DIR / "log.txt"

GSHEET_ID_DEFAULT = os.getenv(
    "GSHEETS_SPREADSHEET_ID", "1B649fKVMBW_LP6C9Up46JFBnGH8Sex8NhXJ6rsMQMLI"
)
GSHEET_WORKSHEET_DEFAULT = os.getenv("GSHEETS_WORKSHEET", "Export")
