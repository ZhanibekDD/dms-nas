"""
Экстрактор ru_passport: нормализация полей паспорта РФ из vision JSON или текста PDF.
"""

from __future__ import annotations

import re
from typing import Any


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def extract_ru_passport(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    """
    Возвращает словарь для EmployeeDocument.extracted_json (блок normalized).
    vision_json — сырой JSON от модели; pdf_text — извлечённый текст PDF.
    """
    raw: dict[str, Any] = {}
    if vision_json and isinstance(vision_json, dict):
        raw.update(vision_json)

    text = (pdf_text or "").strip()
    series = str(raw.get("series") or raw.get("passport_series") or "").strip()
    number = str(raw.get("number") or raw.get("passport_number") or "").strip()
    full_number = str(raw.get("full_number") or raw.get("passport_full_number") or "").strip()

    if not series and not number and text:
        m = re.search(
            r"(\d{4})\s*(\d{6})",
            text.replace(" ", ""),
        )
        if m:
            series, number = m.group(1), m.group(2)

    if not full_number and series and number:
        full_number = f"{series} {number}".strip()

    return {
        "schema": "ru_passport",
        "series": series,
        "number": number,
        "full_number": full_number,
        "last_name": raw.get("last_name") or raw.get("surname"),
        "first_name": raw.get("first_name") or raw.get("name"),
        "middle_name": raw.get("middle_name") or raw.get("patronymic"),
        "birth_date": raw.get("birth_date"),
        "iin_hint": _digits(str(raw.get("iin") or ""))[:12] or None,
        "source": "vision" if vision_json else ("text" if text else "empty"),
    }
