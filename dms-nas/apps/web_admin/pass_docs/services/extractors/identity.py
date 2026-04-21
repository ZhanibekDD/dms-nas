"""
Экстрактор ru_passport: нормализация полей паспорта РФ из vision JSON или текста PDF.

Постобработка: не путать серию с кодом подразделения, верхняя строка «74 24 175542»,
разделение места рождения и адреса регистрации, предупреждения в normalized.
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


def _vision_text_blob(raw: dict[str, Any]) -> str:
    """Склейка строковых полей vision для поиска верхней строки серия+номер."""
    parts: list[str] = []
    for v in raw.values():
        if isinstance(v, str) and v.strip():
            parts.append(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            parts.append(str(v))
    return " ".join(parts)


def _extract_topline_series_number(
    blob: str,
    issuer_digits: str,
    number_hint: str,
) -> tuple[str, str] | None:
    """
    Верхняя строка паспорта: «74 24 175542», «7424 175542» или слитно 7424175542.
    Отбрасывает варианты, где первые 4 цифры совпадают с кодом подразделения.
    Предпочитает совпадение номера с number_hint из vision.
    """
    if not blob:
        return None
    flat = re.sub(r"\s+", " ", blob)
    nh = _digits(number_hint)[:6]
    cands: list[tuple[str, str]] = []

    def _keep(s4: str, n6: str) -> bool:
        if len(n6) != 6 or len(s4) != 4:
            return False
        if issuer_digits and len(issuer_digits) >= 6 and s4 == issuer_digits[:4]:
            return False
        if _series_is_suffix_artifact(s4, issuer_digits):
            return False
        return True

    for m in re.finditer(r"(\d{2})\D{0,4}(\d{2})\D{0,4}(\d{6})", flat):
        s4, n6 = m.group(1) + m.group(2), m.group(3)
        if _keep(s4, n6):
            cands.append((s4, n6))

    for m in re.finditer(r"(\d{4})\D{0,3}(\d{6})\b", flat):
        s4, n6 = m.group(1), m.group(2)
        if _keep(s4, n6):
            cands.append((s4, n6))

    seen: set[tuple[str, str]] = set()
    uniq: list[tuple[str, str]] = []
    for pair in cands:
        if pair not in seen:
            seen.add(pair)
            uniq.append(pair)
    cands = uniq

    if not cands:
        return None
    if nh:
        for s4, n6 in cands:
            if n6 == nh:
                return s4, n6
    return cands[0]


def _series_is_division_code_shape(s: str) -> bool:
    """Строка вида ###-### как у кода подразделения — не серия паспорта."""
    t = (s or "").strip()
    return bool(re.fullmatch(r"\d{3}\s*[-–]?\s*\d{3}", t))


def _series_is_suffix_artifact(series_digits: str, issuer_digits: str) -> bool:
    """Серия как «0008» внутри 890008 — не настоящая серия паспорта."""
    if len(series_digits) != 4 or len(issuer_digits) < 6:
        return False
    if series_digits == issuer_digits[:4]:
        return False
    return series_digits in issuer_digits


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


def _split_registration_and_birth_place(
    raw: dict[str, Any],
    from_pdf: dict[str, str],
    reg_primary: str,
) -> tuple[str, str, bool]:
    """
    Возвращает (registration_address, birth_place, registration_address_warning).
    """
    warn = False
    bp = _clean_str(raw.get("birth_place") or raw.get("place_of_birth") or raw.get("place_of_birth_city"))
    reg = _clean_str(reg_primary)
    if not reg and from_pdf.get("registration_address"):
        reg = _clean_str(from_pdf["registration_address"])

    low = reg.lower()
    # OCR: «РОД …» / «рог …» вместо части строки места рождения; явные маркеры
    birthish = (
        low.startswith("род ")
        or low.startswith("рог ")
        or low.startswith("г.род")
        or "место рожд" in low
        or "место рождения" in low
        or low.startswith("род.")
        or reg.upper().startswith("РОД ")
    )
    if reg and birthish:
        if not bp:
            bp = reg.strip()[:500]
        reg = ""
        warn = True
    elif bp and reg and bp == reg:
        reg = ""
        warn = True

    return reg[:500], bp[:500], warn


def extract_ru_passport(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    """
    Возвращает словарь для EmployeeDocument.extracted_json (блок normalized).
    vision_json — сырой JSON от модели; pdf_text — извлечённый текст PDF.

    Дополнительно (в том же dict): birth_place, series_conflict_warning,
    issuer_code_used_as_series_warning, registration_address_warning.
    """
    raw: dict[str, Any] = {}
    if vision_json and isinstance(vision_json, dict):
        for k, v in vision_json.items():
            if str(k).lower() in ("iin", "iin_hint", "инн"):
                continue
            raw[k] = v

    text = (pdf_text or "").strip()
    from_pdf = _parse_passport_from_text(text) if text else {}

    issuer_code = _normalize_issuer_code(
        raw.get("issuer_code") or raw.get("subdivision_code") or raw.get("department_code")
    ) or (from_pdf.get("issuer_code") or "")
    iss_d = _digits(issuer_code)

    series = _clean_str(raw.get("series") or raw.get("passport_series") or from_pdf.get("series"))
    number = _clean_str(raw.get("number") or raw.get("passport_number") or from_pdf.get("number"))

    if not series and not number and text:
        m = re.search(r"(\d{4})\s*(\d{6})", text.replace(" ", ""))
        if m:
            series, number = m.group(1), m.group(2)

    blob = _vision_text_blob(raw) + "\n" + text
    num_hint = _clean_str(raw.get("number") or raw.get("passport_number") or "")
    top = _extract_topline_series_number(blob, iss_d, num_hint)

    issuer_used_as_series = False
    series_conflict = False

    def _series_bad(s: str, n: str) -> bool:
        sd = _digits(s)[:4]
        nd = _digits(n)[:6]
        if not sd and not nd:
            return False
        if _series_is_division_code_shape(s):
            return True
        if iss_d and len(iss_d) >= 6 and sd == iss_d[:4]:
            return True
        if iss_d and len(nd) == 6 and sd == iss_d[:4] and nd == iss_d:
            return True
        return False

    if _series_bad(series, number):
        if iss_d and _digits(series)[:4] == iss_d[:4]:
            issuer_used_as_series = True
        if top:
            series, number = top[0], top[1]
            series_conflict = True
        elif from_pdf.get("series") and from_pdf.get("number"):
            ps = _digits(from_pdf["series"])[:4]
            if ps and not (iss_d and len(iss_d) >= 6 and ps == iss_d[:4]):
                series, number = from_pdf["series"], from_pdf["number"]
                series_conflict = True
            else:
                series = ""
                series_conflict = True
        else:
            series = ""
            series_conflict = True

    if _series_bad(series, number) and top:
        series, number = top[0], top[1]
        if iss_d and _digits(series)[:4] == iss_d[:4]:
            issuer_used_as_series = True
        series_conflict = True

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

    reg_in = (
        raw.get("registration_address")
        or raw.get("address")
        or raw.get("place_of_residence")
    )
    reg, birth_place, reg_warn = _split_registration_and_birth_place(raw, from_pdf, _clean_str(reg_in))

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
        "birth_place": birth_place,
        "series_conflict_warning": series_conflict,
        "issuer_code_used_as_series_warning": issuer_used_as_series,
        "registration_address_warning": reg_warn,
        "source": "vision" if vision_json else ("text" if text else "empty"),
    }
