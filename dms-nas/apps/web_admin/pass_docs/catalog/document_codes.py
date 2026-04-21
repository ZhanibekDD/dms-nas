"""
Каталог соответствия: код файла (префикс до &) → человекочитаемое имя типа и extractor_kind.

Используется при импорте (DocumentType) и как резерв в resolve_extractor_kind.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class CatalogEntry(TypedDict):
    """extractor_kind можно не указывать — тогда в БД/extraction не подставляется."""

    name: str
    extractor_kind: NotRequired[str]


# Ключи — нормализованный код (как после import_pass_docs._normalize_doc_code: 6, 7, 13, …).
DOCUMENT_CODE_CATALOG: dict[str, CatalogEntry] = {
    # Числовые коды из имён файлов «6&…», «7&…»
    "6": {"name": "Паспорт РФ", "extractor_kind": "ru_passport"},
    "7": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    # Текстовые синонимы (PASSPORT_RF&… и т.п.)
    "PASSPORT_RF": {"name": "Паспорт РФ", "extractor_kind": "ru_passport"},
    "PASPORT_RF": {"name": "Паспорт РФ", "extractor_kind": "ru_passport"},
    "MED": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    "MEDICAL": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    "MEDICAL_CERTIFICATE": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    "MED_SPRAVKA": {"name": "Медицинская справка", "extractor_kind": "medical_certificate"},
    "SPRAVKA086": {"name": "Медицинская справка (086/у)", "extractor_kind": "medical_certificate"},
    "13": {"name": "Охрана труда (программа В)", "extractor_kind": "safety_protocol_v"},
    "14": {"name": "Охрана труда (программы А, Б)", "extractor_kind": "safety_protocol_ab"},
    "15": {"name": "Пожарная безопасность (протокол / удостоверение)", "extractor_kind": "safety_protocol_v"},
    "16": {"name": "Газобезопасность (протокол / удостоверение)", "extractor_kind": "safety_protocol_v"},
    "18": {"name": "Охрана труда (доп. протокол)", "extractor_kind": "safety_protocol_ab"},
    # Частые коды из комплектов: имя по подписи файла; extractor — тот же «протокол/обучение», что и для 13/14/57.
    "17": {"name": "Общие требования промышленной безопасности", "extractor_kind": "safety_protocol_v"},
    "19": {"name": "ОПП (протокол / удостоверение)", "extractor_kind": "umo"},
    "20": {"name": "Подъёмные сооружения (протокол / обучение)", "extractor_kind": "siz_training_protocol"},
    "21": {"name": "Промышленная безопасность (протокол)", "extractor_kind": "safety_protocol_v"},
    "22": {"name": "Обучение по охране труда (протокол)", "extractor_kind": "safety_protocol_ab"},
    "23": {"name": "Специальная оценка условий труда (документ)", "extractor_kind": "umo"},
    "26": {"name": "Электробезопасность", "extractor_kind": "electrical_safety"},
    "31": {"name": "БДД", "extractor_kind": "bdd_protocol"},
    "37": {"name": "Квалификационное удостоверение", "extractor_kind": "umo"},
    "44": {"name": "Трудовой договор"},
    "45": {"name": "Согласие на обработку персональных данных"},
    "46": {"name": "Договор МО"},
    "52": {"name": "Фото сотрудника"},
    "57": {"name": "СИЗ (протокол / обучение)", "extractor_kind": "siz_training_protocol"},
    "59": {"name": "ПТМ (пожарно-технический минимум)", "extractor_kind": "safety_protocol_v"},
    "61": {"name": "ПБ1 (промышленная безопасность)", "extractor_kind": "safety_protocol_v"},
    "74": {"name": "УМО", "extractor_kind": "umo"},
    "78": {"name": "Нефтепромысловые трубопроводы (протокол / обучение)", "extractor_kind": "safety_protocol_v"},
    # Общие документы из каталогов R&/D& (часто без отдельного экстрактора)
    "UNKNOWN": {"name": "Тип документа (не классифицирован)"},
    "RULE01": {"name": "Внутренний регламент (RULE01)", "extractor_kind": "umo"},
    "RULE_01": {"name": "Внутренний регламент (RULE_01)", "extractor_kind": "umo"},
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
    ek = (entry.get("extractor_kind") or "").strip()
    return ek or None


def catalog_defaults_for_import(code: str) -> dict[str, Any]:
    """Поля по умолчанию для DocumentType при импорте (name, extractor_kind)."""
    entry = get_catalog_entry(code)
    if not entry:
        return {}
    out: dict[str, Any] = {"name": entry["name"][:255]}
    ek = (entry.get("extractor_kind") or "").strip()
    if ek:
        out["extractor_kind"] = ek[:64]
    return out
