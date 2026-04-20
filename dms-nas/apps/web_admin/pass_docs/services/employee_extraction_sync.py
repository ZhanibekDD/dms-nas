"""
Перенос полей из extracted_json.normalized в карточку Employee.

Поддерживаются только extractor_kind:
  ru_passport
  medical_certificate

Служебный сотрудник общих документов (__COMMON_ORG__) не обновляется.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from pass_docs.models import Employee, EmployeeDocument

logger = logging.getLogger(__name__)

COMMON_IMPORT_KEY = "__COMMON_ORG__"


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    s = str(value).strip()[:10]
    if len(s) != 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _s(v: Any) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    return "" if t.lower() in ("null", "none", "-", "—") else t


def apply_extracted_normalized_to_employee(doc: EmployeeDocument) -> dict[str, Any]:
    """
    Читает doc.extracted_json['normalized'] и doc.extracted_json['extractor_kind'],
    обновляет связанного Employee при успешном разборе.

    Возвращает словарь для логов / summary (не пишет в extracted_json).
    """
    if doc.parse_status != EmployeeDocument.ParseStatus.OK:
        return {"applied": False, "reason": "parse_status_not_ok"}

    payload = doc.extracted_json or {}
    normalized = payload.get("normalized")
    if not isinstance(normalized, dict):
        return {"applied": False, "reason": "no_normalized"}

    kind = (payload.get("extractor_kind") or "").strip().lower()
    if kind not in ("ru_passport", "medical_certificate"):
        return {"applied": False, "reason": "extractor_not_synced", "extractor_kind": kind}

    employee = doc.employee
    if employee.import_key == COMMON_IMPORT_KEY:
        return {"applied": False, "reason": "common_org_employee"}

    if kind == "ru_passport":
        return _sync_ru_passport(employee, normalized, doc_pk=doc.pk)
    return _sync_medical_certificate(employee, normalized, doc_pk=doc.pk)


def _sync_ru_passport(emp: Employee, n: dict[str, Any], *, doc_pk: int) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    fields_out: list[str] = []

    fn = _s(n.get("full_name"))
    if fn:
        updates["full_name"] = fn[:512]
        fields_out.append("full_name")
    ln = _s(n.get("last_name"))
    if ln:
        updates["last_name"] = ln[:128]
        fields_out.append("last_name")
    fnm = _s(n.get("first_name"))
    if fnm:
        updates["first_name"] = fnm[:128]
        fields_out.append("first_name")
    mn = _s(n.get("middle_name"))
    if mn:
        updates["middle_name"] = mn[:128]
        fields_out.append("middle_name")

    bd = _parse_iso_date(n.get("birth_date"))
    if bd is not None:
        updates["birth_date"] = bd
        fields_out.append("birth_date")

    ser = _s(n.get("series"))
    if ser:
        updates["passport_series"] = ser[:16]
        fields_out.append("passport_series")
    num = _s(n.get("number"))
    if num:
        updates["passport_number"] = num[:32]
        fields_out.append("passport_number")
    pfn = _s(n.get("full_number"))
    if pfn:
        updates["passport_full_number"] = pfn[:64]
        fields_out.append("passport_full_number")

    if not updates:
        return {"applied": False, "reason": "no_passport_fields_to_write", "document_id": doc_pk}

    for k, v in updates.items():
        setattr(emp, k, v)
    emp.save(update_fields=list(updates.keys()))
    logger.debug("Employee pk=%s обновлён из паспорта (документ %s): %s", emp.pk, doc_pk, fields_out)
    return {"applied": True, "extractor_kind": "ru_passport", "fields": fields_out, "employee_id": emp.pk}


def _sync_medical_certificate(emp: Employee, n: dict[str, Any], *, doc_pk: int) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    fields_out: list[str] = []

    org = _s(n.get("organization"))
    if org and not (emp.company or "").strip():
        updates["company"] = org[:255]
        fields_out.append("company")

    conclusion = _s(n.get("conclusion"))
    if conclusion:
        marker = f"(документ id={doc_pk})"
        existing = (emp.notes or "").rstrip()
        if marker in existing and conclusion in existing:
            pass
        else:
            block = f"\n--- Медсправка {marker} ---\nЗаключение: {conclusion}\n"
            updates["notes"] = (existing + block).strip() if existing else block.strip()
            fields_out.append("notes")

    if not updates:
        return {"applied": False, "reason": "no_medical_fields_to_write", "document_id": doc_pk}

    for k, v in updates.items():
        setattr(emp, k, v)
    emp.save(update_fields=list(updates.keys()))
    logger.debug("Employee pk=%s обновлён из медсправки (документ %s): %s", emp.pk, doc_pk, fields_out)
    return {"applied": True, "extractor_kind": "medical_certificate", "fields": fields_out, "employee_id": emp.pk}
