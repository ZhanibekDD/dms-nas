"""
Каталог соответствия: код файла (префикс до &) → человекочитаемое имя типа и extractor_kind.

Используется при импорте (DocumentType) и как резерв в resolve_extractor_kind.
"""

from __future__ import annotations

from typing import Any, TypedDict


class CatalogEntry(TypedDict):
    name: str
    extractor_kind: str


# Ключи — нормализованный код (как после import_pass_docs._normalize_doc_code: 6, 7, 13, …).
DOCUMENT_CODE_CATALOG: dict[str, CatalogEntry] = {
    "6": {"name": "Паспорт РФ", "extractor_kind": "ru_passport"},
    "7": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    "13": {"name": "Охрана труда (программа В)", "extractor_kind": "safety_protocol_v"},
    "14": {"name": "Охрана труда (программы А, Б)", "extractor_kind": "safety_protocol_ab"},
    # Частые коды из комплектов: имя по подписи файла; extractor — тот же «протокол/обучение», что и для 13/14/57.
    "17": {"name": "Общие требования промышленной безопасности", "extractor_kind": "safety_protocol_v"},
    "19": {"name": "ОПП (протокол / удостоверение)", "extractor_kind": "umo"},
    "20": {"name": "Подъёмные сооружения (протокол / обучение)", "extractor_kind": "siz_training_protocol"},
    "26": {"name": "Электробезопасность", "extractor_kind": "electrical_safety"},
    "31": {"name": "БДД", "extractor_kind": "bdd_protocol"},
    "57": {"name": "СИЗ (протокол / обучение)", "extractor_kind": "siz_training_protocol"},
    "74": {"name": "УМО", "extractor_kind": "umo"},
}


def get_catalog_entry(code: str) -> CatalogEntry | None:
    """Возвращает запись каталога или None."""
    if not code:
        return None
    key = str(code).strip().upper().replace(" ", "_")
    key = "".join(c for c in key if c.isalnum() or c in "_-")[:64]
    return DOCUMENT_CODE_CATALOG.get(key)


def extractor_kind_for_code(code: str) -> str | None:
    """Только extractor_kind для резолва пайплайна (без создания моделей)."""
    entry = get_catalog_entry(code)
    if not entry:
        return None
    return entry["extractor_kind"]


def catalog_defaults_for_import(code: str) -> dict[str, Any]:
    """Поля по умолчанию для DocumentType при импорте (name, extractor_kind)."""
    entry = get_catalog_entry(code)
    if not entry:
        return {}
    return {
        "name": entry["name"][:255],
        "extractor_kind": entry["extractor_kind"][:64],
    }
