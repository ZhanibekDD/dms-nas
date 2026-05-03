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
    "pending": "В очереди",
    "ok": "Обработан",
    "skipped": "Без обработки",
    "error": "Ошибка",
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
    "building": "Собирается…",
    "ready": "Готов",
    "failed": "Ошибка",
    "sent": "Отправлен",
    "cancelled": "Отменён",
}

# Подписи полей normalized / типичных ключей из extraction
FIELD_LABELS_RU: dict[str, str] = {
    # Паспорт
    "series": "Серия",
    "number": "Номер",
    "full_number": "Номер полностью",
    "last_name": "Фамилия",
    "first_name": "Имя",
    "middle_name": "Отчество",
    "birth_date": "Дата рождения",
    "birth_place": "Место рождения",
    "issue_date": "Дата выдачи",
    "issuer_code": "Код подразделения",
    "issuer": "Кем выдан",
    "registration_address": "Адрес регистрации",
    # Медицина
    "patient_name": "ФИО",
    "organization": "Организация",
    "certificate_number": "Номер документа",
    "valid_until": "Действует до",
    "conclusion": "Заключение",
    # Обучение / протоколы
    "employee_name": "ФИО сотрудника",
    "holder_name": "ФИО владельца",
    "training_topic": "Тема обучения",
    "program_name": "Программа обучения",
    "protocol_number": "Номер протокола",
    "protocol_date": "Дата протокола",
    "expiry_date": "Действует до",
    "document_number": "Номер документа",
}

# Технические ключи, которые никогда не показываются пользователю
_INTERNAL_KEYS: frozenset[str] = frozenset({
    "schema", "source", "extractor", "extractor_kind", "extractor_version",
    "import_key", "legacy", "raw_vision", "e2e_package_mvp", "e2e_test",
    "confidence", "page", "ocr_engine",
})


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


def _normalized_key_is_internal(ks: str) -> bool:
    low = str(ks).strip().lower()
    if not low:
        return True
    if low.startswith("_"):
        return True
    if low in _INTERNAL_KEYS:
        return True
    if low.startswith("e2e_"):
        return True
    if low == "legacy" or low.endswith("_legacy"):
        return True
    compact = re.sub(r"[^a-z0-9]+", "", low)
    if "extractor" in low or "extractor" in compact:
        return True
    return False


def _label_looks_internal(ks: str, label: str) -> bool:
    if _normalized_key_is_internal(ks):
        return True
    ll = (label or "").lower()
    return "extractor" in ll


def _warning_text_is_internal(text: str) -> bool:
    low = (text or "").lower()
    if "extractor_kind" in low or "extractor kind" in low:
        return True
    if re.search(r"\bextractor\b", low):
        return True
    if "e2e_" in low:
        return True
    return False


def normalized_pairs_for_ui(normalized: Any) -> list[tuple[str, str]]:
    """Плоский список (подпись, значение) для блока «Распознанные данные».

    Обходит вложенные dict (часть пайплайнов кладёт поля во внутренние объекты),
    не показывает служебные ключи вроде extractor_kind на любом уровне.
    """
    if not normalized or not isinstance(normalized, dict):
        return []

    def walk(d: dict[str, Any]) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for key, val in d.items():
            ks = str(key)
            if _normalized_key_is_internal(ks):
                continue
            if isinstance(val, dict):
                rows.extend(walk(val))
                continue
            if isinstance(val, list):
                continue
            label = FIELD_LABELS_RU.get(ks, ks.replace("_", " ").strip().title())
            if _label_looks_internal(ks, label):
                continue
            rows.append((label, _format_scalar(val)))
        return rows

    return walk(normalized)


def normalized_warnings(normalized: Any) -> list[str]:
    if not normalized or not isinstance(normalized, dict):
        return []
    w = normalized.get("_warnings")
    out: list[str] = []
    if isinstance(w, list):
        out = [str(x) for x in w if str(x).strip()]
    elif isinstance(w, str) and w.strip():
        out = [w.strip()]
    return [s for s in out if not _warning_text_is_internal(s)]


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


def extracted_text_for_ui(payload: dict) -> str:
    """Возвращает полный текст из результата extraction.

    Приоритет:
      1. full_text  — дословный текст документа, возвращённый vision-моделью
      2. pdf_text   — текст, извлечённый из PDF через pdfplumber
    """
    if not payload or not isinstance(payload, dict):
        return ""

    full_text = (payload.get("full_text") or "").strip()
    if full_text:
        return full_text

    pdf_text = (payload.get("pdf_text") or "").strip()
    if pdf_text:
        return pdf_text

    return ""


def employee_bundle_line(
    *,
    documents_total: int,
    parse_ok: int,
    parse_pending: int,
    parse_err: int,
    doc_ok: int,
) -> str:
    parts = [f"Документов: {documents_total}", f"Распознано: {parse_ok}"]
    if parse_pending:
        parts.append(f"В обработке: {parse_pending}")
    if parse_err:
        parts.append(f"Ошибок: {parse_err}")
    parts.append(f"Принято: {doc_ok}")
    return " · ".join(parts)
