"""Нормализация дат в YYYY-MM-DD для extractors."""

from __future__ import annotations

import re
from datetime import datetime


def normalize_date_iso(value: object) -> str:
    """
    Принимает строку/число от vision или PDF; возвращает YYYY-MM-DD или пустую строку.
    Поддержка: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "-", "—"):
        return ""

    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    m = re.search(
        r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b",
        s,
    )
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    m = re.search(
        r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{2})\b(?!\d)",
        s,
    )
    if m:
        d, mo, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + y2 if y2 <= 39 else 1900 + y2
        if _valid_ymd(y, mo, d):
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    return ""


def _valid_ymd(y: int, m: int, d: int) -> bool:
    if y < 1900 or y > 2100 or m < 1 or m > 12 or d < 1 or d > 31:
        return False
    try:
        datetime(y, m, d)
    except ValueError:
        return False
    return True
