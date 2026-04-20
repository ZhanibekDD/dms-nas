"""
Экстрактор ru_passport: нормализация полей паспорта РФ из vision JSON или текста PDF.
"""

from __future__ import annotations

import re
from typing import Any

from pass_docs.services.extractors.date_norm import normalize_date_iso


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _clean_str(v: object) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    if t.lower() in ("null", "none", "-", "—"):
        return ""
    return t


def _normalize_issuer_code(v: object) -> str:
    d = _digits(str(v or ""))
    if len(d) >= 6:
        d = d[:6]
        return f"{d[:3]}-{d[3:]}"
    return ""


def _build_full_number(series: str, number: str) -> str:
    """Только цифры: 4 серия + 6 номер, без пробелов."""
    s = _digits(series)[:4]
    n = _digits(number)[:6]
    if len(s) == 4 and len(n) == 6:
        return s + n
    return ""


def _parse_passport_from_text(text: str) -> dict[str, str]:
    """Эвристики по тексту PDF (русский паспорт)."""
    out: dict[str, str] = {
        "series": "",
        "number": "",
        "birth_date": "",
        "issue_date": "",
        "issuer_code": "",
        "registration_address": "",
    }
    if not text or len(text.strip()) < 8:
        return out

    compact = re.sub(r"\s+", "", text)

    m = re.search(r"(\d{4})\s*(\d{6})", compact)
    if m:
        out["series"], out["number"] = m.group(1), m.group(2)

    for pat in (
        r"дата\s*рождения[:\s]*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"рожден[а-я]*[:\s]*(\d{2}[./-]\d{2}[./-]\d{4})",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            out["birth_date"] = normalize_date_iso(m.group(1))
            break

    for pat in (
        r"дата\s*выдачи[:\s]*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"выдан[ао]?[:\s]*.*?(\d{2}[./-]\d{2}[./-]\d{4})",
    ):
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            out["issue_date"] = normalize_date_iso(m.group(1))
            break

    m = re.search(r"(\d{3})[-\s]?(\d{3})(?!\d)", text)
    if m:
        out["issuer_code"] = _normalize_issuer_code(m.group(1) + m.group(2))

    for pat in (
        r"место\s*жительства[:\s]*([^\n]+(?:\n[^\n]+){0,4}?)(?=\n\s*\n|подпись|$)",
        r"место\s*жительства[:\s]*([^\n]+(?:\n[^\n]+){0,3})",
        r"прописк[а-я]*[:\s]*([^\n]+(?:\n[^\n]+){0,3})",
    ):
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            addr = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(addr) > 5:
                out["registration_address"] = addr[:500]
                break

    return out


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
        for k, v in vision_json.items():
            if str(k).lower() in ("iin", "iin_hint", "инн"):
                continue
            raw[k] = v

    text = (pdf_text or "").strip()
    from_pdf = _parse_passport_from_text(text) if text else {}

    series = _clean_str(raw.get("series") or raw.get("passport_series") or from_pdf.get("series"))
    number = _clean_str(raw.get("number") or raw.get("passport_number") or from_pdf.get("number"))

    if not series and not number and text:
        m = re.search(r"(\d{4})\s*(\d{6})", text.replace(" ", ""))
        if m:
            series, number = m.group(1), m.group(2)

    full_number = _build_full_number(series, number)

    last = _clean_str(raw.get("last_name") or raw.get("surname"))
    first = _clean_str(raw.get("first_name") or raw.get("name"))
    middle = _clean_str(raw.get("middle_name") or raw.get("patronymic"))
    parts = [p for p in (last, first, middle) if p]
    full_name = " ".join(parts)

    birth_raw = raw.get("birth_date") or raw.get("date_of_birth")
    birth_date = normalize_date_iso(birth_raw) or (from_pdf.get("birth_date") or "")

    issue_raw = raw.get("issue_date") or raw.get("date_of_issue")
    issue_date = normalize_date_iso(issue_raw) or (from_pdf.get("issue_date") or "")

    issuer_code = _normalize_issuer_code(
        raw.get("issuer_code") or raw.get("subdivision_code") or raw.get("department_code")
    ) or (from_pdf.get("issuer_code") or "")

    reg = _clean_str(
        raw.get("registration_address")
        or raw.get("address")
        or raw.get("place_of_residence")
    )
    if not reg and from_pdf.get("registration_address"):
        reg = from_pdf["registration_address"]

    return {
        "schema": "ru_passport",
        "series": _digits(series)[:4] if series else "",
        "number": _digits(number)[:6] if number else "",
        "full_number": full_number,
        "last_name": last,
        "first_name": first,
        "middle_name": middle,
        "full_name": full_name,
        "birth_date": birth_date,
        "issue_date": issue_date,
        "issuer_code": issuer_code,
        "registration_address": reg,
        "source": "vision" if vision_json else ("text" if text else "empty"),
    }
