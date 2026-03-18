"""
Financial document workflow — strict status transition matrix.
"""

import logging

logger = logging.getLogger("svc.finance")

TRANSITIONS: dict[str, list[str]] = {
    "черновик":    ["на_проверке"],
    "на_проверке": ["утверждён", "отклонён"],
    "утверждён":   ["оплачен"],
    "отклонён":    ["черновик"],
    "оплачен":     [],
}

ALLOWED_ROLES: dict[str, list[str]] = {
    "черновик→на_проверке": ["buh", "admin"],
    "на_проверке→утверждён": ["pto", "admin"],
    "на_проверке→отклонён": ["pto", "admin"],
    "утверждён→оплачен":    ["buh", "admin"],
    "отклонён→черновик":    ["buh", "admin"],
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, [])


def change_status(db, doc_id: int, new_status: str,
                  user_id: int, user_role: str, comment: str = "") -> dict:
    """
    Attempt to change finance_doc status.
    Idempotent: if already in target status, returns ok.
    """
    doc = db.get_finance_doc(doc_id)
    if not doc:
        return {"ok": False, "error": "document not found"}

    current = doc["status"]
    if current == new_status:
        return {"ok": True, "idempotent": True}

    if not can_transition(current, new_status):
        return {
            "ok": False,
            "error": f"Переход {current} → {new_status} запрещён"
        }

    key = f"{current}→{new_status}"
    allowed = ALLOWED_ROLES.get(key, ["admin"])
    if user_role not in allowed:
        return {
            "ok": False,
            "error": f"Роль «{user_role}» не может выполнить {current} → {new_status}"
        }

    db.update_finance_status(doc_id, new_status, user_id, comment)
    db.audit(user_id, "finance_status", "finance_doc", doc_id,
             f"{current} → {new_status}: {comment}")
    logger.info("Finance doc %d: %s → %s by user %d", doc_id, current, new_status, user_id)
    return {"ok": True}


def export_csv(db, object_name: str = None, status: str = None) -> str:
    """Return CSV string (UTF-8-BOM for Excel) of finance docs."""
    import csv
    import io

    rows = db.list_finance_docs(object_name=object_name, status=status)
    out = io.StringIO()
    out.write("\ufeff")  # BOM for Excel
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["ID", "Объект", "Тип", "Файл", "Сумма", "Контрагент",
                     "Статус", "Создан", "Обновлён"])
    for r in rows:
        writer.writerow([
            r["id"], r["object_name"], r["doc_type"], r["filename"],
            r["amount"] or "", r["counterparty"] or "",
            r["status"], r["created_at"], r["updated_at"],
        ])
    return out.getvalue()
