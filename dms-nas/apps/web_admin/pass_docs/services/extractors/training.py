"""
Экстракторы протоколов обучения и удостоверений: охрана труда (В / АБ),
электробезопасность, БДД, СИЗ, УМО.

Общая схема normalized: protocol_number, issue_date, valid_until (YYYY-MM-DD),
holder_name, organization, program_name, conclusion, schema, source.
"""

from __future__ import annotations

import re
from typing import Any

from pass_docs.services.extractors.date_norm import normalize_date_iso


def _s(v: Any) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    if t.lower() in ("null", "none", "-", "—"):
        return ""
    return t


def _dates_from_pdf_text(text: str) -> tuple[str, str]:
    """Первая и вторая найденные даты в тексте (эвристика)."""
    dates: list[str] = []
    for m in re.finditer(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{4})\b", text):
        iso = normalize_date_iso(m.group(1))
        if iso and iso not in dates:
            dates.append(iso)
    issue = dates[0] if dates else ""
    valid_until = dates[1] if len(dates) > 1 else ""
    return issue, valid_until


def _holder_from_text(text: str) -> str:
    for pat in (
        r"(?:ф\.?\s*и\.?\s*о\.?|фио)[:\s]+([А-ЯЁ][А-ЯЁа-яё\-\s]{5,120}?)(?=\n|$)",
        r"(?:слушател|работник)[а-я]*[:\s]+([А-ЯЁ][^\n]{5,120})",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" ,.:;-")[:300]
    return ""


def _org_from_text(text: str) -> str:
    m = re.search(
        r"(ООО|АО|ГБУЗ|ГУП|ПАО|Организац|Учреждени|Центр)[^\n]{0,150}",
        text,
        re.IGNORECASE,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()[:300]
    return ""


def _protocol_no_from_text(text: str) -> str:
    m = re.search(r"(?:№|номер|N\s*)[:\s]*([0-9A-Za-z/-]{4,40})", text, re.IGNORECASE)
    return m.group(1).strip()[:64] if m else ""


def _extract_program(
    schema: str,
    *,
    vision_json: dict[str, Any] | None,
    pdf_text: str | None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if vision_json and isinstance(vision_json, dict):
        raw.update(vision_json)

    text = (pdf_text or "").strip()

    pn = _s(raw.get("protocol_number") or raw.get("number") or raw.get("certificate_number"))
    if not pn and text:
        pn = _protocol_no_from_text(text)

    issue = normalize_date_iso(raw.get("issue_date") or raw.get("date_of_issue"))
    valid_until = normalize_date_iso(raw.get("valid_until") or raw.get("expiry_date"))
    if text and (not issue or not valid_until):
        di, dv = _dates_from_pdf_text(text)
        if not issue:
            issue = di
        if not valid_until:
            valid_until = dv

    holder = _s(raw.get("holder_name") or raw.get("patient_name") or raw.get("full_name"))
    if not holder and text:
        holder = _holder_from_text(text)

    org = _s(raw.get("organization") or raw.get("issuer"))
    if not org and text:
        org = _org_from_text(text)

    program_name = _s(raw.get("program_name") or raw.get("course_name") or raw.get("program"))
    conclusion = _s(raw.get("conclusion") or raw.get("result") or raw.get("group"))

    src = "vision" if vision_json else ("text" if text else "empty")

    return {
        "schema": schema,
        "protocol_number": pn,
        "issue_date": issue,
        "valid_until": valid_until,
        "holder_name": holder,
        "organization": org,
        "program_name": program_name,
        "conclusion": conclusion,
        "source": src,
    }


def extract_safety_protocol_v(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("safety_protocol_v", vision_json=vision_json, pdf_text=pdf_text)


def extract_safety_protocol_ab(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("safety_protocol_ab", vision_json=vision_json, pdf_text=pdf_text)


def extract_electrical_safety(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("electrical_safety", vision_json=vision_json, pdf_text=pdf_text)


def extract_bdd_protocol(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("bdd_protocol", vision_json=vision_json, pdf_text=pdf_text)


def extract_siz_training_protocol(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("siz_training_protocol", vision_json=vision_json, pdf_text=pdf_text)


def extract_umo(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    return _extract_program("umo", vision_json=vision_json, pdf_text=pdf_text)
