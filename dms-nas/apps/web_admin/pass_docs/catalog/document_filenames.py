"""Safe parsing and canonical display names for Pass Docs files.

The source filename is not authoritative metadata. It can carry the legacy
<code>&<label>.<ext> convention, but files without that prefix must remain
visible and explicitly marked for review instead of being silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
import re
import unicodedata
from typing import Literal

MISSING_DOCUMENT_CODE = "UNKNOWN"

# Uncoded files are accepted only for known document formats. Coded legacy
# files keep the historic "accept any extension" behaviour.
SUPPORTED_UNCODED_SUFFIXES = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
    }
)

# Deliberately small and exact. Add an alias only after the business owner has
# confirmed the mapping. Fuzzy guesses would attach documents to a wrong type.
EXACT_FILENAME_CODE_ALIASES = {
    "ВУ": "11",
    "ВОДИТЕЛЬСКОЕ УДОСТОВЕРЕНИЕ": "11",
}


@dataclass(frozen=True)
class ParsedDocumentFilename:
    basename: str
    code: str
    label: str
    status: Literal["coded", "inferred", "missing"]


def safe_basename(filename: str) -> str:
    """Return a basename for POSIX or Windows-like input without traversal."""
    text = unicodedata.normalize("NFKC", str(filename or ""))
    return re.split(r"[\\/]", text)[-1].strip()


def normalize_document_code(raw: str) -> str:
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = text.strip().upper().replace(" ", "_")
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in "_-")
    return cleaned[:64] if cleaned else MISSING_DOCUMENT_CODE


def _alias_key(filename: str) -> str:
    basename = safe_basename(filename)
    stem = PurePath(basename).stem
    text = unicodedata.normalize("NFKC", stem).upper()
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def infer_exact_document_code(filename: str) -> str | None:
    """Infer only business-confirmed exact aliases; never use fuzzy matching."""
    return EXACT_FILENAME_CODE_ALIASES.get(_alias_key(filename))


def parse_document_filename(filename: str) -> ParsedDocumentFilename:
    basename = safe_basename(filename)
    if "&" in basename:
        raw_code, label = basename.split("&", 1)
        code = normalize_document_code(raw_code)
        if code != MISSING_DOCUMENT_CODE:
            return ParsedDocumentFilename(
                basename=basename,
                code=code,
                label=label.strip() or basename,
                status="coded",
            )

    inferred = infer_exact_document_code(basename)
    if inferred:
        return ParsedDocumentFilename(
            basename=basename,
            code=inferred,
            label=basename,
            status="inferred",
        )

    return ParsedDocumentFilename(
        basename=basename,
        code=MISSING_DOCUMENT_CODE,
        label=basename,
        status="missing",
    )


def is_supported_uncoded_document(filename: str) -> bool:
    return PurePath(safe_basename(filename)).suffix.casefold() in SUPPORTED_UNCODED_SUFFIXES


def canonical_document_filename(code: str, filename: str) -> str:
    """Build a non-destructive display/archive name using authoritative code."""
    basename = safe_basename(filename) or "document"
    normalized_code = normalize_document_code(code)
    tail = basename.split("&", 1)[1] if "&" in basename else basename
    tail = re.sub(r"[\x00-\x1f\x7f]+", "_", tail).strip(" .") or "document"
    return f"{normalized_code}&{tail}"
