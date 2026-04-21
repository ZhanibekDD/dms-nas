"""
Синхронизация записей DocumentType с каталогом DOCUMENT_CODE_CATALOG.

Используется management-командой sync_pass_docs_document_types (не трогает UI / builder / extraction).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pass_docs.catalog.document_codes import get_catalog_entry

Status = Literal["would_update", "uncertain", "ok"]


def is_trivial_document_name(code: str, name: str) -> bool:
    """Пустое имя или имя совпадает с кодом (как при первичном импорте без каталога)."""
    c = (code or "").strip()
    n = (name or "").strip()
    if not n:
        return True
    return n.casefold() == c.casefold()


def is_blank_extractor(extractor_kind: str) -> bool:
    return not (extractor_kind or "").strip()


def classify_document_type(dt: Any) -> Status:
    """
    would_update — в каталоге есть запись и есть что поправить (name/extractor_kind).
    uncertain — в каталоге нет записи, а name или extractor_kind всё ещё «сырые».
    ok — либо уже нормализовано, либо без каталога, но поля заполнены вручную.
    """
    code = getattr(dt, "code", "") or ""
    cat = get_catalog_entry(code)
    trivial = is_trivial_document_name(code, getattr(dt, "name", "") or "")
    blank_ek = is_blank_extractor(getattr(dt, "extractor_kind", "") or "")
    if cat and (trivial or blank_ek):
        planned = planned_field_updates(dt, cat)
        if planned:
            return "would_update"
        return "ok"
    if not cat and (trivial or blank_ek):
        return "uncertain"
    return "ok"


@dataclass(frozen=True)
class SyncPreview:
    code: str
    old_name: str
    new_name: str | None
    old_extractor_kind: str
    new_extractor_kind: str | None


def planned_field_updates(dt: Any, cat: dict[str, str] | None = None) -> dict[str, str]:
    """Поля для save(update_fields=...). Пустой dict — менять нечего."""
    code = getattr(dt, "code", "") or ""
    if cat is None:
        cat = get_catalog_entry(code)
    if not cat:
        return {}
    out: dict[str, str] = {}
    name = getattr(dt, "name", "") or ""
    ek = getattr(dt, "extractor_kind", "") or ""
    if is_trivial_document_name(code, name) and (cat.get("name") or "").strip():
        new_name = cat["name"][:255].strip()
        if new_name and name.strip() != new_name:
            out["name"] = new_name
    if is_blank_extractor(ek) and (cat.get("extractor_kind") or "").strip():
        new_ek = cat["extractor_kind"][:64].strip()
        if new_ek and ek.strip() != new_ek:
            out["extractor_kind"] = new_ek
    return out


def preview_sync(dt: Any, updates: dict[str, str]) -> SyncPreview | None:
    if not updates:
        return None
    code = getattr(dt, "code", "") or ""
    return SyncPreview(
        code=code,
        old_name=(getattr(dt, "name", "") or "")[:255],
        new_name=updates.get("name"),
        old_extractor_kind=(getattr(dt, "extractor_kind", "") or "")[:64],
        new_extractor_kind=updates.get("extractor_kind"),
    )
