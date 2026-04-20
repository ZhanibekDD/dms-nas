"""
Перенос полей из extracted_json.normalized в карточку Employee.

Поддерживаются только extractor_kind:
  ru_passport — в Employee только паспортные номера и (если пусто) дата рождения; ФИО из паспорта не пишутся
    в карточку — только preview / сравнение в summary и блок в notes.
  medical_certificate — как раньше; повтор одного и того же документа в notes не дублируется.

Служебный сотрудник общих документов (__COMMON_ORG__) не обновляется.
"""

from __future__ import annotations

import logging
import unicodedata
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


def _is_empty_employee_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, date):
        return False
    return not str(value).strip()


def _serialize_for_conflict(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _passport_id_norm(s: str) -> str:
    return "".join(c for c in (s or "") if c.isalnum()).lower()


def _fio_compare_key(s: str) -> str:
    """Единый ключ сравнения для ФИО (Unicode NFKC + casefold)."""
    return unicodedata.normalize("NFKC", (s or "").strip()).casefold()


def _values_equal_for_passport_sync(field: str, current: Any, incoming: Any) -> bool:
    if field == "birth_date":
        return isinstance(current, date) and isinstance(incoming, date) and current == incoming
    a = _serialize_for_conflict(current)
    b = _serialize_for_conflict(incoming)
    if not a and not b:
        return True
    if field in ("passport_series", "passport_number", "passport_full_number"):
        return _passport_id_norm(a) == _passport_id_norm(b)
    return _fio_compare_key(a) == _fio_compare_key(b)


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


def _passport_name_preview_from_normalized(n: dict[str, Any]) -> dict[str, str]:
    prev: dict[str, str] = {}
    for key, maxlen in (
        ("full_name", 512),
        ("last_name", 128),
        ("first_name", 128),
        ("middle_name", 128),
    ):
        t = _s(n.get(key))
        if t:
            prev[key] = t[:maxlen]
    return prev


def _passport_name_vs_employee(emp: Employee, n: dict[str, Any]) -> list[dict[str, Any]]:
    """ФИО из normalized не пишется в Employee; только сводка для UI.

    В список попадают только: пустое поле в карточке + есть из паспорта (suggested),
    либо реальное расхождение (mismatch). Совпадающие значения не включаются.
    """
    out: list[dict[str, Any]] = []
    for attr, maxlen in (
        ("full_name", 512),
        ("last_name", 128),
        ("first_name", 128),
        ("middle_name", 128),
    ):
        inc = _s(n.get(attr))[:maxlen] if _s(n.get(attr)) else ""
        if not inc:
            continue
        cur = getattr(emp, attr)
        if _is_empty_employee_value(cur):
            out.append(
                {
                    "field": attr,
                    "employee": "",
                    "passport_suggested": inc,
                    "kind": "suggested_not_autofill",
                }
            )
            continue
        if _values_equal_for_passport_sync(attr, cur, inc):
            continue
        out.append(
            {
                "field": attr,
                "employee": _serialize_for_conflict(cur),
                "passport_suggested": inc,
                "kind": "mismatch_not_autofill",
            }
        )
    return out


def _sync_ru_passport(emp: Employee, n: dict[str, Any], *, doc_pk: int) -> dict[str, Any]:
    """
    Паспорт: в карточку — только серия/номер/полный номер и (если пусто) дата рождения.
    ФИО из разбора не записываются в Employee; сводка в summary и отдельный блок в notes.
    """
    applied_fields: list[str] = []
    skipped_existing_fields: list[str] = []
    conflicts: list[dict[str, Any]] = []
    updates: dict[str, Any] = {}

    name_preview = _passport_name_preview_from_normalized(n)
    name_vs = _passport_name_vs_employee(emp, n)

    def _inc_str(key: str, maxlen: int) -> str:
        t = _s(n.get(key))
        return t[:maxlen] if t else ""

    rows: list[tuple[str, Any]] = [
        ("birth_date", _parse_iso_date(n.get("birth_date"))),
        ("passport_series", _inc_str("series", 16)),
        ("passport_number", _inc_str("number", 32)),
        ("passport_full_number", _inc_str("full_number", 64)),
    ]

    for emp_attr, incoming in rows:
        if emp_attr == "birth_date":
            if incoming is None:
                continue
        elif not incoming:
            continue

        current = getattr(emp, emp_attr)
        if _is_empty_employee_value(current):
            updates[emp_attr] = incoming
            applied_fields.append(emp_attr)
        elif _values_equal_for_passport_sync(emp_attr, current, incoming):
            skipped_existing_fields.append(emp_attr)
        else:
            conflicts.append(
                {
                    "field": emp_attr,
                    "existing": _serialize_for_conflict(current),
                    "incoming": _serialize_for_conflict(incoming),
                }
            )
            skipped_existing_fields.append(emp_attr)

    notes_updated = False
    existing_notes = (emp.notes or "").rstrip()
    note_fragments: list[str] = []

    conflict_marker = f"--- Паспорт: расхождение (документ id={doc_pk}) ---"
    if conflicts and conflict_marker not in existing_notes:
        lines = [
            f"{c['field']}: в карточке «{c['existing']}»; из паспорта «{c['incoming']}» — не перезаписано."
            for c in conflicts
        ]
        note_fragments.append(conflict_marker + "\n" + "\n".join(lines))

    fio_marker = f"--- Паспорт: ФИО из разбора (документ id={doc_pk}) ---"
    if name_preview and fio_marker not in existing_notes:
        body_lines = [f"{k}: {v}" for k, v in name_preview.items()]
        note_fragments.append(
            fio_marker
            + "\n"
            + "(в поля full_name / last_name / first_name / middle_name карточки не записывалось)\n"
            + "\n".join(body_lines)
        )

    if note_fragments:
        block = "\n\n".join(note_fragments) + "\n"
        updates["notes"] = (existing_notes + "\n" + block).strip() if existing_notes else block.strip()
        notes_updated = True

    base_response: dict[str, Any] = {
        "extractor_kind": "ru_passport",
        "employee_id": emp.pk,
        "document_id": doc_pk,
        "applied_fields": applied_fields,
        "skipped_existing_fields": skipped_existing_fields,
        "conflicts": conflicts,
        "passport_names_auto_applied": False,
        "passport_name_preview": name_preview,
        "passport_name_vs_employee": name_vs,
    }

    if not updates:
        emn = emp.notes or ""
        reason = "no_passport_fields_to_write"
        if conflicts and conflict_marker in emn:
            reason = "passport_conflicts_notes_already_present"
        elif name_preview and fio_marker in emn and not applied_fields and not conflicts:
            reason = "passport_fio_notes_already_present"
        elif skipped_existing_fields and not conflicts:
            reason = "incoming_matches_existing_employee"
        elif name_preview and not applied_fields and not conflicts:
            reason = "passport_name_preview_only"
        out = {"applied": False, "reason": reason, **base_response}
        out["notes_updated"] = False
        return out

    for k, v in updates.items():
        setattr(emp, k, v)
    emp.save(update_fields=list(updates.keys()))
    logger.debug(
        "Employee pk=%s sync паспорт (док %s): applied=%s skipped=%s conflicts=%s",
        emp.pk,
        doc_pk,
        applied_fields,
        skipped_existing_fields,
        [c["field"] for c in conflicts],
    )

    out = {
        "applied": True,
        **base_response,
        "notes_updated": notes_updated,
        "fields": applied_fields,
    }
    return out


def _sync_medical_certificate(emp: Employee, n: dict[str, Any], *, doc_pk: int) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    fields_out: list[str] = []

    org = _s(n.get("organization"))
    if org and not (emp.company or "").strip():
        updates["company"] = org[:255]
        fields_out.append("company")

    conclusion = _s(n.get("conclusion"))
    if conclusion:
        med_marker = f"--- Медсправка (документ id={doc_pk}) ---"
        existing = (emp.notes or "").rstrip()
        if med_marker in existing:
            pass
        else:
            block = f"\n{med_marker}\nЗаключение: {conclusion}\n"
            updates["notes"] = (existing + block).strip() if existing else block.strip()
            fields_out.append("notes")

    if not updates:
        return {"applied": False, "reason": "no_medical_fields_to_write", "document_id": doc_pk}

    for k, v in updates.items():
        setattr(emp, k, v)
    emp.save(update_fields=list(updates.keys()))
    logger.debug("Employee pk=%s обновлён из медсправки (документ %s): %s", emp.pk, doc_pk, fields_out)
    return {"applied": True, "extractor_kind": "medical_certificate", "fields": fields_out, "employee_id": emp.pk}
