"""
Экстрактор medical_certificate: заготовка под медсправку (091/у и аналоги).
"""

from __future__ import annotations

from typing import Any


def extract_medical_certificate(
    *,
    vision_json: dict[str, Any] | None = None,
    pdf_text: str | None = None,
) -> dict[str, Any]:
    """Нормализованный блок для extracted_json."""
    raw: dict[str, Any] = {}
    if vision_json and isinstance(vision_json, dict):
        raw.update(vision_json)

    return {
        "schema": "medical_certificate",
        "certificate_number": raw.get("certificate_number") or raw.get("number"),
        "issue_date": raw.get("issue_date") or raw.get("date_of_issue"),
        "valid_until": raw.get("valid_until") or raw.get("expiry_date"),
        "patient_name": raw.get("patient_name") or raw.get("full_name"),
        "organization": raw.get("organization") or raw.get("issuer"),
        "conclusion": raw.get("conclusion") or raw.get("result"),
        "source": "vision" if vision_json else ("text" if (pdf_text or "").strip() else "empty"),
    }
