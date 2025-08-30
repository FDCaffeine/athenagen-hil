# tests/utils.py
import json
import os
import subprocess
import sys
from pathlib import Path

ALLOWED_SOURCES = {"form", "email", "invoice_html"}
ALLOWED_STATUS = {"pending", "approved", "rejected", "edited"}

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
COMBINED = OUTPUTS / "combined_feed.json"
TEMPLATE = ROOT / "dummy_data" / "templates" / "data_extraction_template.csv"


def ensure_combined_feed():
    """
    Φροντίζει να υπάρχει το outputs/combined_feed.json.
    Αν δεν υπάρχει, τρέχει 'python main.py' με εγγυημένο UTF-8 I/O (Windows-safe).
    """
    OUTPUTS.mkdir(exist_ok=True, parents=True)
    if COMBINED.exists():
        return

    cmd = [sys.executable, str(ROOT / "main.py")]

    # Εξασφαλίζουμε UTF-8 για το παιδί process (ιδίως σε Windows/cp1253 κονσόλες)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    # text=True + encoding='utf-8' + errors='replace' αποφεύγουν UnicodeDecodeError
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"main.py failed (code {proc.returncode}).\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def load_combined():
    """
    Επιστρέφει τη λίστα εγγραφών από το combined_feed.json.
    Δέχεται είτε καθαρή λίστα είτε dict με 'items'.
    """
    ensure_combined_feed()
    with open(COMBINED, encoding="utf-8") as f:
        data = json.load(f)

    # Επιτρέπουμε είτε λίστα εγγραφών είτε dict με 'items'
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        raise AssertionError("combined_feed.json must be a list of records or a dict with 'items'.")
    return data


def template_headers():
    """
    Διαβάζει την 1η γραμμή του template (CSV) και επιστρέφει τα headers.
    Υποστηρίζει διαχωριστικά: ',', ';', ή tab.
    """
    assert TEMPLATE.exists(), f"Template not found: {TEMPLATE}"
    with open(TEMPLATE, encoding="utf-8") as f:
        first_line = f.readline().strip("\n\r")

    # επιτρέπουμε comma/semicolon/tab
    for sep in [",", ";", "\t"]:
        if sep in first_line:
            return [h.strip() for h in first_line.split(sep)]

    # fallback (single header ή άδειο)
    return [first_line] if first_line else []
