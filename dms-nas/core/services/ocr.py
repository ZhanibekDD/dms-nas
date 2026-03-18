"""
Sprint 12: OCR / AI document recognition service.

Strategy (no external API required):
  1. PDF with selectable text  → pdfplumber (fast, accurate)
  2. PDF scanned / image (jpg/png/tiff) → pytesseract (if installed)
  3. Fallback: mark as needs_manual_review

Extracts minimal fields:
  - doc_number   : document number / contract number
  - doc_date     : date of document (ISO)
  - expires_at   : expiry / validity date (ISO)
  - counterparty : company / person name
  - amount       : monetary amount (float)
  - raw_text     : first 2000 chars of extracted text (for audit)
"""

import re
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("core.ocr")


# ──────────────────────────────────────────────────────────────────────────────
# Text extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            parts = []
            for page in pdf.pages[:5]:  # first 5 pages is enough
                t = page.extract_text()
                if t:
                    parts.append(t)
            return "\n".join(parts)
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        return ""


def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from image bytes using pytesseract (if available)."""
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(file_bytes))
        # Try Russian + English
        text = pytesseract.image_to_string(img, lang="rus+eng")
        return text
    except ImportError:
        logger.debug("pytesseract not installed, skipping image OCR")
        return ""
    except Exception as exc:
        logger.warning("pytesseract extraction failed: %s", exc)
        return ""


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Auto-detect file type and extract text."""
    fname_lower = filename.lower()
    if fname_lower.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
        if not text.strip():
            # Scanned PDF — try image OCR on first page
            text = _pdf_to_image_ocr(file_bytes)
        return text
    elif fname_lower.endswith((".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp")):
        return extract_text_from_image(file_bytes)
    else:
        return ""


def _pdf_to_image_ocr(file_bytes: bytes) -> str:
    """Convert first PDF page to image and OCR it (requires pdf2image + poppler)."""
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes, first_page=1, last_page=1, dpi=200)
        if images:
            return extract_text_from_image(_pil_to_bytes(images[0]))
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("pdf2image OCR failed: %s", exc)
    return ""


def _pil_to_bytes(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Field parsers (regex-based, Russian document conventions)
# ──────────────────────────────────────────────────────────────────────────────

# Date patterns: DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD, "12 января 2025"
_MONTHS_RU = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

_DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b"),
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_RU) + r")\s+(20\d{2})\b", re.IGNORECASE),
]

_DOC_NUMBER_PATTERNS = [
    re.compile(r"№\s*([А-ЯA-Z0-9/-]{2,30})", re.IGNORECASE),
    re.compile(r"[Нн]омер[:\s]+([А-ЯA-Z0-9/-]{2,30})", re.IGNORECASE),
    re.compile(r"[Дд]оговор\s+(?:№\s*)?([А-ЯA-Z0-9/-]{2,30})", re.IGNORECASE),
    re.compile(r"[Сс]чет[:\s]+(?:№\s*)?([0-9А-ЯA-Z/-]{4,20})", re.IGNORECASE),
]

_EXPIRY_PATTERNS = [
    re.compile(r"(?:срок[а-я\s]*(?:действия|до)[:\s]*)(\d{1,2}[./]\d{1,2}[./]20\d{2})", re.IGNORECASE),
    re.compile(r"(?:действителен\s+до[:\s]*)(\d{1,2}[./]\d{1,2}[./]20\d{2})", re.IGNORECASE),
    re.compile(r"(?:окончания[:\s]*)(\d{1,2}[./]\d{1,2}[./]20\d{2})", re.IGNORECASE),
    re.compile(r"(?:до\s+)(\d{1,2}[./]\d{1,2}[./]20\d{2})", re.IGNORECASE),
]

_AMOUNT_PATTERNS = [
    re.compile(r"(?:сумм[аыею][:\s]*)(\d[\d\s.,]*(?:руб|грн|USD|EUR)?)", re.IGNORECASE),
    re.compile(r"(?:итого[:\s]*)(\d[\d\s.,]+)", re.IGNORECASE),
    re.compile(r"(\d{1,3}(?:[\s,]\d{3})+(?:[.,]\d{2})?)\s*(?:руб|грн|USD|EUR)", re.IGNORECASE),
]

_COUNTERPARTY_PATTERNS = [
    re.compile(r"(?:заказчик|исполнитель|поставщик|покупатель|продавец)[:\s]+([А-ЯA-Z][^\n,]{3,60})", re.IGNORECASE),
    re.compile(r'(?:ООО|ОАО|ЗАО|ПАО|ИП|АО)\s+"?([^"\n,]{3,50})"?', re.IGNORECASE),
]


def _parse_date_str(ds: str) -> Optional[str]:
    """Convert any recognized date string to ISO YYYY-MM-DD."""
    ds = ds.strip()
    # DD.MM.YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](20\d{2})$", ds)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # YYYY-MM-DD
    m = re.match(r"^(20\d{2})-(\d{2})-(\d{2})$", ds)
    if m:
        return ds
    # DD месяц YYYY
    for word, num in _MONTHS_RU.items():
        m = re.match(rf"^(\d{{1,2}})\s+{word}\s+(20\d{{2}})$", ds, re.IGNORECASE)
        if m:
            return f"{m.group(2)}-{num}-{int(m.group(1)):02d}"
    return None


def _find_first_date(text: str) -> Optional[str]:
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groups()
        # Check which pattern matched
        if re.match(r"^20\d{2}$", g[0]):
            ds = f"{g[0]}-{g[1]}-{g[2]}"
        elif g[1] in _MONTHS_RU:
            ds = f"{g[0]} {g[1]} {g[2]}"
        else:
            ds = f"{g[0]}.{g[1]}.{g[2]}"
        result = _parse_date_str(ds)
        if result:
            return result
    return None


def _find_expiry(text: str) -> Optional[str]:
    for pat in _EXPIRY_PATTERNS:
        m = pat.search(text)
        if m:
            ds = m.group(1)
            result = _parse_date_str(ds)
            if result:
                return result
    return None


def _find_doc_number(text: str) -> Optional[str]:
    for pat in _DOC_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip().rstrip(".")
            if len(val) >= 2:
                return val
    return None


def _find_amount(text: str) -> Optional[float]:
    for pat in _AMOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1).strip()
            # Remove spaces used as thousands separator, replace comma with dot
            cleaned = re.sub(r"[^\d.,]", "", raw).replace(",", ".").rstrip(".")
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _find_counterparty(text: str) -> Optional[str]:
    for pat in _COUNTERPARTY_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip().rstrip(",.")
            if 3 <= len(val) <= 100:
                return val
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_ocr(file_bytes: bytes, filename: str, doc_type: str = "") -> dict:
    """
    Run OCR on a document and return extracted fields.

    Returns dict:
      ok           : bool
      raw_text     : str (first 2000 chars)
      doc_number   : str or None
      doc_date     : str (ISO) or None
      expires_at   : str (ISO) or None
      counterparty : str or None
      amount       : float or None
      confidence   : int (0-100 rough score)
      error        : str (if ok=False)
    """
    result = {
        "ok":           False,
        "raw_text":     "",
        "doc_number":   None,
        "doc_date":     None,
        "expires_at":   None,
        "counterparty": None,
        "amount":       None,
        "confidence":   0,
        "error":        "",
    }

    if not file_bytes:
        result["error"] = "empty file"
        return result

    text = extract_text(file_bytes, filename)
    if not text.strip():
        result["ok"]    = True   # not an error — just no text found
        result["error"] = "no_text_extracted"
        return result

    result["raw_text"]     = text[:2000]
    result["doc_number"]   = _find_doc_number(text)
    result["doc_date"]     = _find_first_date(text)
    result["expires_at"]   = _find_expiry(text)
    result["counterparty"] = _find_counterparty(text)
    result["amount"]       = _find_amount(text)

    # Rough confidence: count how many fields were found
    found = sum(1 for v in [
        result["doc_number"], result["doc_date"],
        result["expires_at"], result["counterparty"],
    ] if v)
    result["confidence"] = found * 25  # 0, 25, 50, 75, 100
    result["ok"]         = True

    logger.info(
        "OCR '%s' → number=%s date=%s expiry=%s confidence=%d%%",
        filename, result["doc_number"], result["doc_date"],
        result["expires_at"], result["confidence"],
    )
    return result
