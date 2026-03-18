"""
Shared helpers: file hashing, size formatting, date utils.
"""

import hashlib
from datetime import date, datetime
from typing import Optional


def file_hash(data: bytes) -> str:
    """Return SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def human_size(n: Optional[int]) -> str:
    """Format bytes as human-readable string."""
    if n is None:
        return "—"
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} ГБ"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} МБ"
    if n >= 1024:
        return f"{n / 1024:.0f} КБ"
    return f"{n} Б"


def days_until(iso_date: str) -> Optional[int]:
    """Return days until ISO date string, negative = overdue."""
    try:
        return (date.fromisoformat(iso_date) - date.today()).days
    except (ValueError, TypeError):
        return None


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def category_from_doc_type(doc_type: str) -> str:
    """Map document type label to Document.category value."""
    _map = {
        "Счета":     "finance",
        "ТТН":       "finance",
        "Акты":      "finance",
        "Договоры":  "finance",
        "Прочее":    "other",
        "ФотоОтчет": "photo",
        "Протокол":  "safety",
    }
    return _map.get(doc_type, "build")
