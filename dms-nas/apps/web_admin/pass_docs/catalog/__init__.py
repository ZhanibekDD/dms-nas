"""Каталог кодов документов (импорт / extraction)."""

from pass_docs.catalog.document_codes import (
    DOCUMENT_CODE_CATALOG,
    catalog_defaults_for_import,
    extractor_kind_for_code,
    get_catalog_entry,
)

__all__ = [
    "DOCUMENT_CODE_CATALOG",
    "catalog_defaults_for_import",
    "extractor_kind_for_code",
    "get_catalog_entry",
]
