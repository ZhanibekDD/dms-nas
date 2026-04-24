"""
Подписи и представление данных pass_docs для операторского UI (без изменения моделей и пайплайнов).
"""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from typing import Any

PARSE_STATUS_RU: dict[str, str] = {
    "pending": "Ожидает распознавания",
    "ok": "Распознано",
    "skipped": "Пропущено",
    "error": "Ошибка распознавания",
}

DOC_STATUS_RU: dict[str, str] = {
    "missing": "Нет в комплекте",
    "pending": "На проверке",
    "ok": "Принят",
    "expired": "Просрочен",
    "rejected": "Отклонён",
}

PACKAGE_STATUS_RU: dict[str, str] = {
    "draft": "Черновик",
    "submitted": "Ожидает сборки",
    "building": "Сборка…",
    "ready": "Готов",
    "failed": "Ошибка сборки",
    "sent": "Отправлен",
    "cancelled": "Отменён",
}

# Подписи полей normalized / типичных ключей из extraction
FIELD_LABELS_RU: dict[str, str] = {
    "series": "Серия",
    "number": "Номер",
    "full_number": "Номер полностью",
    "last_name": "Фамилия",
    "first_name": "Имя",
    "middle_name": "Отчество",
    "birth_date": "Дата рождения",
    "issue_date": "Дата выдачи",
    "issuer_code": "Код подразделения",
    "registration_address": "Адрес регистрации",
    "patient_name": "ФИО",
    "organization": "Организация",
    "certificate_number": "Номер документа",
    "valid_until": "Действует до",
    "conclusion": "Заключение",
    "employee_name": "ФИО сотрудника",
    "training_topic": "Тема обучения",
    "protocol_number": "Номер протокола",
    "protocol_date": "Дата протокола",
}


def ru_parse_status(code: str | None) -> str:
    if not code:
        return "—"
    k = str(code).strip()
    return PARSE_STATUS_RU.get(k, "Уточняется")


def ru_doc_status(code: str | None) -> str:
    if not code:
        return "—"
    k = str(code).strip()
    return DOC_STATUS_RU.get(k, "Уточняется")


def ru_package_status(code: str | None) -> str:
    if not code:
        return "—"
    k = str(code).strip()
    return PACKAGE_STATUS_RU.get(k, "Уточняется")


def _format_scalar(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "Да" if v else "Нет"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    s = str(v).strip()
    return s if s else "—"


def _norm_key_for_rule(raw_key: str) -> str:
    """Ключ для правил скрытия служебных полей (регистр, пробелы)."""
    return re.sub(r"\s+", "_", str(raw_key).strip()).lower()


def _normalized_key_is_internal(nk: str) -> bool:
    if not nk or nk.startswith("_"):
        return True
    if "extractor" in nk:
        return True
    if nk == "legacy" or nk.endswith("_legacy"):
        return True
    if nk in {"import_key", "e2e_package_mvp", "e2e_test"}:
        return True
    if nk.startswith("e2e_"):
        return True
    return False


def _warning_is_internal(text: str) -> bool:
    low = str(text).lower()
    return "extractor" in low or "import_key" in low or "e2e_" in low


def normalized_pairs_for_ui(normalized: Any) -> list[tuple[str, str]]:
    """Плоский список (подпись, значение) для блока «Распознанные данные»."""
    if not normalized or not isinstance(normalized, dict):
        return []
    rows: list[tuple[str, str]] = []

    def consider_leaf(raw_key: str, val: Any) -> None:
        if val is None or isinstance(val, (dict, list)):
            return
        ks = str(raw_key).strip()
        if not ks:
            return
        nk = _norm_key_for_rule(ks)
        if _normalized_key_is_internal(nk):
            return
        label = FIELD_LABELS_RU.get(ks, ks.replace("_", " ").strip().title())
        if "extractor" in label.lower():
            return
        rows.append((label, _format_scalar(val)))

    def walk(d: dict) -> None:
        for raw_key, val in d.items():
            ks = str(raw_key).strip()
            if not ks:
                continue
            if isinstance(val, dict):
                inner_vals = list(val.values())
                if val and all(not isinstance(x, (dict, list)) for x in inner_vals):
                    for ik, iv in val.items():
                        consider_leaf(str(ik).strip(), iv)
                continue
            if isinstance(val, list):
                continue
            consider_leaf(ks, val)

    walk(normalized)
    return rows


def normalized_warnings(normalized: Any) -> list[str]:
    if not normalized or not isinstance(normalized, dict):
        return []
    out: list[str] = []
    w = normalized.get("_warnings")
    if isinstance(w, list):
        for x in w:
            sx = str(x).strip()
            if sx and not _warning_is_internal(sx):
                out.append(sx)
    elif isinstance(w, str) and w.strip():
        sx = w.strip()
        if not _warning_is_internal(sx):
            out.append(sx)
    return out


def viewer_kind_for_document(file_field) -> str:
    """
    pdf | image | none — для встроенного просмотра.
    file_field: FieldFile или None.
    """
    if not file_field or not getattr(file_field, "name", None):
        return "none"
    name = file_field.name
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"):
        return "image"
    return "none"


def guess_mime_for_path(path: str) -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or "application/octet-stream"


def employee_bundle_line(
    *,
    documents_total: int,
    parse_ok: int,
    parse_pending: int,
    parse_err: int,
    doc_ok: int,
) -> str:
    parts = [
        f"документов в деле: {documents_total}",
        f"распознано: {parse_ok}",
    ]
    if parse_pending:
        parts.append(f"в очереди на распознавание: {parse_pending}")
    if parse_err:
        parts.append(f"с ошибкой распознавания: {parse_err}")
    parts.append(f"принято в комплект (проверка): {doc_ok}")
    return ", ".join(parts)
