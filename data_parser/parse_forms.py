# data_parser/parse_forms.py
import os
import re
from typing import Any

from bs4 import BeautifulSoup


def _pick_parser() -> str:
    """
    Επιλέγει τον καλύτερο διαθέσιμο parser:
    1) lxml  2) html5lib  3) html.parser
    """
    for candidate in ("lxml", "html5lib", "html.parser"):
        try:
            # Πρόχειρο smoke-test: απλά φτιάξε έναν κενό soup με τον parser
            BeautifulSoup("<div></div>", candidate)
            return candidate
        except Exception:
            continue
    return "html.parser"


_PARSER = _pick_parser()


def _normalize_phone(phone: str | None) -> str | None:
    """Καθαρίζει αριθμούς τηλεφώνου (κρατάει μόνο ψηφία και '+')."""
    if not phone:
        return None
    return re.sub(r"[^\d+]", "", phone)


def _get_input_value(soup: BeautifulSoup, name: str):
    """Επιστρέφει την τιμή ενός input/select/textarea με συγκεκριμένο name."""
    el = soup.find(attrs={"name": name})
    if not el:
        return None

    # textarea -> text
    if el.name == "textarea":
        return (el.text or "").strip()

    # select -> selected option value ή κείμενο
    if el.name == "select":
        opt = el.find("option", selected=True) or el.find("option")
        if not opt:
            return None
        return (opt.get("value") or opt.text or "").strip()

    # input -> value attribute
    return (el.get("value") or "").strip()


def parse_form(html_content: str) -> dict:
    """Παίρνει HTML φόρμας και επιστρέφει dict με τα βασικά πεδία."""
    soup = BeautifulSoup(html_content, _PARSER)

    full_name = _get_input_value(soup, "full_name") or _get_input_value(soup, "name")
    email = _get_input_value(soup, "email")
    phone = _normalize_phone(_get_input_value(soup, "phone"))
    company = _get_input_value(soup, "company")
    service = _get_input_value(soup, "service")  # Υπηρεσία Ενδιαφέροντος

    # Προαιρετικά πεδία που μπορούμε να εμφανίσουμε στο UI
    message = _get_input_value(soup, "message")
    submission_date = _get_input_value(soup, "submission_date")
    priority = _get_input_value(soup, "priority")

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "company": company,
        "service": service,
        "message": message,
        "submission_date": submission_date,
        "priority": priority,
    }


def parse_all_forms(forms_dir: str) -> list[dict[str, Any]]:
    """Διαβάζει όλα τα HTML αρχεία φόρμας από τον φάκελο και τα επιστρέφει ως λίστα dicts."""
    extracted: list[dict[str, Any]] = []
    for filename in os.listdir(forms_dir):  # <-- forms_dir
        if filename.lower().endswith(".html"):
            full_path = os.path.join(forms_dir, filename)  # <-- forms_dir
            with open(full_path, encoding="utf-8", errors="ignore") as f:
                data = parse_form(f.read())
            data["source_file"] = filename
            extracted.append(data)
    return extracted


if __name__ == "__main__":
    import json

    folder = "dummy_data/forms"
    parsed = parse_all_forms(folder)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
