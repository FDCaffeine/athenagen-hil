# data_parser/parse_forms.py
from __future__ import annotations

import os
import re
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag


def _pick_parser() -> str:
    """
    Επιλέγει τον καλύτερο διαθέσιμο parser:
    1) lxml  2) html5lib  3) html.parser
    """
    for candidate in ("lxml", "html5lib", "html.parser"):
        try:
            BeautifulSoup("<div></div>", candidate)
            return candidate
        except Exception:
            continue
    return "html.parser"


_PARSER = _pick_parser()


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    # ενιαίο isinstance, σβήνει το SIM101. Το noqa: UP038 σιωπά το hint για union (δεν το θέλουμε εδώ).
    if isinstance(v, (list, tuple)):  # noqa: UP038
        return " ".join(map(str, v))
    return str(v)


def _normalize_phone(phone: str | None) -> str | None:
    """Καθαρίζει αριθμούς τηλεφώνου (κρατάει μόνο ψηφία και '+')."""
    if not phone:
        return None
    return re.sub(r"[^\d+]", "", phone)


def _get_input_value(soup: BeautifulSoup, name: str) -> str | None:
    """Επιστρέφει την τιμή ενός input/select/textarea με συγκεκριμένο name."""
    el = soup.find(attrs={"name": name})
    if not isinstance(el, Tag):
        return None

    # textarea -> text
    if el.name == "textarea":
        val = (el.text or "").strip()
        return val or None

    # select -> selected option value ή κείμενο
    if el.name == "select":
        opt = el.find("option", selected=True) or el.find("option")
        if not isinstance(opt, Tag):
            return None
        val = _as_str(opt.get("value") or opt.text).strip()
        return val or None

    # input -> value attribute (πιθανόν AttributeValueList)
    val = _as_str(el.get("value")).strip()
    return val or None


def parse_form(html_content: str) -> dict[str, Any]:
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
    for filename in os.listdir(forms_dir):
        if filename.lower().endswith(".html"):
            full_path = os.path.join(forms_dir, filename)
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
