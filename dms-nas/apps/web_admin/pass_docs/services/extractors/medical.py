"""
Экстрактор medical_certificate: нормализация медсправки (086/у и аналоги), vision + текст PDF.
"""

from __future__ import annotations

import re
from typing import Any

from pass_docs.services.extractors.date_norm import normalize_date_iso


def _s(v: object) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    if t.lower() in ("null", "none", "-", "—"):
        return ""
    return t


_MEDICAL_TEXT_FIELDS: tuple[str, ...] = (
    "patient_name",
    "issue_date",
    "valid_until",
    "organization",
    "conclusion",
    "certificate_number",
)


def _empty_medical_from_text() -> dict[str, str]:
    """Полный словарь текстовых полей (пустые строки)."""
    return dict.fromkeys(_MEDICAL_TEXT_FIELDS, "")


def _extract_medical_from_text(text: str) -> dict[str, str]:
    """Эвристики по русскоязычному тексту справки."""
    empty = _empty_medical_from_text()
    if not text or len(text.strip()) < 10:
        return empty

    t = text.replace("\r", "\n")
    out = {**empty}

    for pat in (
        r"(?:ф\.?\s*и\.?\s*о\.?|фио|пациент|гражданин)[:\s]+([А-ЯЁ][А-ЯЁа-яё\-\s]{5,80}?)(?=\n|$|дата)",
        r"(?:ф\.?\s*и\.?\s*о\.?)[:\s]+([А-ЯЁ][^\n]{5,120})",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.:;-")
            if 5 <= len(name) <= 200:
                out["patient_name"] = name
                break

    for pat in (
        r"(?:дата\s*выдачи|выдан[ао]?)[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"(?:от\s*)?(\d{2}[./-]\d{2}[./-]\d{4})\s*(?:г\.?)?\s*(?:года)?",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            iso = normalize_date_iso(m.group(1))
            if iso:
                out["issue_date"] = iso
                break

    for pat in (
        r"(?:действителен\s*до|годен\s*до|до\s*)[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"(?:срок\s*действия)[:\s]*.*?(\d{2}[./-]\d{2}[./-]\d{4})",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            iso = normalize_date_iso(m.group(1))
            if iso:
                out["valid_until"] = iso
                break

    org_m = re.search(
        r"(ГБУЗ|ГУЗ|ООО|АО|Поликлиник|Больниц|Медицинск|Центр)[^\n]{0,120}",
        t,
        re.IGNORECASE,
    )
    if org_m:
        line = re.sub(r"\s+", " ", org_m.group(0)).strip()
        if len(line) > 5:
            out["organization"] = line[:300]

    for pat in (
        r"(?:заключение|диагноз|результат)[:\s]*([^\n]{3,400})",
        r"(?:годен|не\s*годен)[^\n]{0,200}",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            chunk = m.group(1) if m.lastindex else m.group(0)
            out["conclusion"] = re.sub(r"\s+", " ", chunk).strip()[:500]
            break

    cm = re.search(
        r"(?:№|номер|N\s*)[:\s]*([0-9A-Za-z/-]{4,32})",
        t,
        re.IGNORECASE,
    )
    if cm:
        out["certificate_number"] = cm.group(1).strip()[:64]

    return out


def extract_medical_certificate(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    """Нормализованный блок для extracted_json; пустые поля — пустые строки."""
    raw: dict[str, Any] = {}
    if vision_json and isinstance(vision_json, dict):
        raw.update(vision_json)

    text = (pdf_text or "").strip()
    from_text = _extract_medical_from_text(text) if text else _empty_medical_from_text()

    cert = _s(raw.get("certificate_number") or raw.get("number")) or from_text.get(
        "certificate_number", ""
    )
    patient = _s(raw.get("patient_name") or raw.get("full_name")) or from_text.get("patient_name", "")
    org = _s(raw.get("organization") or raw.get("issuer")) or from_text.get("organization", "")
    conclusion = _s(raw.get("conclusion") or raw.get("result")) or from_text.get("conclusion", "")

    issue = normalize_date_iso(raw.get("issue_date") or raw.get("date_of_issue"))
    if not issue:
        issue = from_text.get("issue_date", "")

    valid_until = normalize_date_iso(raw.get("valid_until") or raw.get("expiry_date"))
    if not valid_until:
        valid_until = from_text.get("valid_until", "")

    src = "vision" if vision_json else ("text" if text else "empty")
    if vision_json and text and any(from_text.values()):
        src = "vision+text"

    return {
        "schema": "medical_certificate",
        "certificate_number": cert,
        "issue_date": issue,
        "valid_until": valid_until,
        "patient_name": patient,
        "organization": org,
        "conclusion": conclusion,
        "source": src,
    }
