"""
Одиночный extraction pipeline для EmployeeDocument.

PDF: сначала текст (pdfplumber); если текста нет или он «мусорный» — первая страница в PNG → vision.
Изображения: сразу vision.
Результат пишется в extracted_json, parse_status обновляется.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from pass_docs.models import DocumentType, EmployeeDocument
from pass_docs.services import vision_client
from pass_docs.services import employee_extraction_sync
from pass_docs.services.extractors import EXTRACTOR_REGISTRY

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


def resolve_extractor_kind(document_type: DocumentType) -> str | None:
    raw = (document_type.extractor_kind or "").strip().lower()
    if raw in EXTRACTOR_REGISTRY:
        return raw
    code = (document_type.code or "").upper()
    if "PASSPORT" in code or "PASPORT" in code:
        return "ru_passport"
    if "MED" in code or "SPRAV" in code or "091" in code or "MEDICAL" in code:
        return "medical_certificate"
    return None


def _vision_prompt(kind: str) -> str:
    if kind == "ru_passport":
        return (
            "Ты анализируешь изображение российского паспорта (разворот). "
            "Верни СТРОГО один JSON-объект без markdown и без пояснений. Ключи: "
            "series (4 цифры), number (6 цифр), last_name, first_name, middle_name, "
            "birth_date (только YYYY-MM-DD или пустая строка), "
            "issue_date (только YYYY-MM-DD или пустая строка), "
            "issuer_code (6 цифр кода подразделения, можно как 123-456), "
            "registration_address (одна строка — адрес регистрации как в документе). "
            "Поле iin не используй. Неизвестные поля — пустая строка или null."
        )
    if kind == "medical_certificate":
        return (
            "Ты анализируешь изображение медицинской справки (форма 086/у или аналог). "
            "Верни СТРОГО один JSON-объект. Ключи: certificate_number, issue_date, "
            "valid_until, patient_name, organization, conclusion. Даты в ISO ГГГГ-ММ-ДД или пусто."
        )
    return "Верни JSON-объект с полями документа, которые видишь на изображении."


def _extract_pdf_text(path: Path) -> str:
    import pdfplumber

    try:
        chunks: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        return "\n".join(chunks).strip()
    except Exception as exc:
        logger.debug("Не удалось прочитать PDF как текст: %s — %s", path, exc)
        return ""


def _is_garbage_text(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 40:
        return True
    letters = sum(1 for c in t if c.isalpha())
    if letters / max(len(t), 1) < 0.12:
        return True
    return False


def _pdf_first_page_png_b64(path: Path) -> str | None:
    import os
    import tempfile

    import pdfplumber

    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            img = page.to_image(resolution=144)
            pil = getattr(img, "original", None)
            if pil is not None and hasattr(pil, "save"):
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                return vision_client.file_to_base64_from_bytes(buf.getvalue())
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                img.save(tmp_path, format="PNG")
                return vision_client.file_to_base64(Path(tmp_path))
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    except Exception as exc:
        logger.debug("PDF first page render failed for %s — %s", path, exc)
        return None


def _run_extractor(kind: str, *, vision_json: dict | None, pdf_text: str | None) -> dict[str, Any]:
    fn = EXTRACTOR_REGISTRY.get(kind)
    if not fn:
        raise ValueError(f"unknown extractor kind: {kind}")
    return fn(vision_json=vision_json, pdf_text=pdf_text)


def run_extraction(doc: EmployeeDocument) -> dict[str, Any]:
    """
    Прогоняет pipeline и сохраняет doc.extracted_json / doc.parse_status.
    Возвращает краткий словарь для консоли (без полного дублирования БД).
    """
    path = Path(doc.source_path)
    kind = resolve_extractor_kind(doc.document_type)

    if not path.is_file():
        doc.extracted_json = {"error": "file_not_found", "path": str(path)}
        doc.parse_status = EmployeeDocument.ParseStatus.ERROR
        doc.save(update_fields=["extracted_json", "parse_status", "updated_at"])
        return {
            "parse_status": doc.parse_status,
            "error": "file_not_found",
            "employee_sync": {"applied": False, "reason": "file_not_found"},
        }

    if not kind:
        doc.extracted_json = {
            "skipped": True,
            "reason": "no_extractor_kind",
            "document_type_code": doc.document_type.code,
        }
        doc.parse_status = EmployeeDocument.ParseStatus.SKIPPED
        doc.save(update_fields=["extracted_json", "parse_status", "updated_at"])
        return {
            "parse_status": doc.parse_status,
            "skipped": True,
            "employee_sync": {"applied": False, "reason": "skipped_no_extractor"},
        }

    ext = path.suffix.lower()
    steps: list[str] = []
    vision_raw: dict[str, Any] | None = None
    pdf_text = ""

    try:
        if ext == ".pdf":
            pdf_text = _extract_pdf_text(path)
            steps.append("pdf_text_extracted")
            if pdf_text and not _is_garbage_text(pdf_text):
                steps.append("text_only_path")
                normalized = _run_extractor(kind, vision_json=None, pdf_text=pdf_text)
                doc.extracted_json = {
                    "pipeline": steps,
                    "extractor_kind": kind,
                    "normalized": normalized,
                    "pdf_text_preview": pdf_text[:500],
                }
                doc.parse_status = EmployeeDocument.ParseStatus.OK
            else:
                steps.append("pdf_text_weak_or_empty_try_vision")
                b64 = _pdf_first_page_png_b64(path)
                if not b64:
                    doc.extracted_json = {
                        "pipeline": steps,
                        "error": "pdf_first_page_render_failed",
                        "extractor_kind": kind,
                    }
                    doc.parse_status = EmployeeDocument.ParseStatus.ERROR
                else:
                    vision_raw = vision_client.chat_json(
                        _vision_prompt(kind),
                        images_b64=[b64],
                    )
                    steps.append("vision_ok")
                    normalized = _run_extractor(kind, vision_json=vision_raw, pdf_text=None)
                    doc.extracted_json = {
                        "pipeline": steps,
                        "extractor_kind": kind,
                        "raw_vision": vision_raw,
                        "normalized": normalized,
                    }
                    doc.parse_status = EmployeeDocument.ParseStatus.OK

        elif ext in IMAGE_SUFFIXES:
            steps.append("image_direct_vision")
            b64 = vision_client.file_to_base64(path)
            vision_raw = vision_client.chat_json(
                _vision_prompt(kind),
                images_b64=[b64],
            )
            steps.append("vision_ok")
            normalized = _run_extractor(kind, vision_json=vision_raw, pdf_text=None)
            doc.extracted_json = {
                "pipeline": steps,
                "extractor_kind": kind,
                "raw_vision": vision_raw,
                "normalized": normalized,
            }
            doc.parse_status = EmployeeDocument.ParseStatus.OK
        else:
            doc.extracted_json = {
                "skipped": True,
                "reason": "unsupported_file_suffix",
                "suffix": ext,
                "extractor_kind": kind,
            }
            doc.parse_status = EmployeeDocument.ParseStatus.SKIPPED

    except Exception as exc:
        logger.debug("Extraction failed for document id=%s: %s", doc.pk, exc)
        doc.extracted_json = {
            "pipeline": steps,
            "error": str(exc),
            "extractor_kind": kind,
        }
        doc.parse_status = EmployeeDocument.ParseStatus.ERROR

    doc.save(update_fields=["extracted_json", "parse_status", "updated_at"])

    employee_sync = employee_extraction_sync.apply_extracted_normalized_to_employee(doc)

    out: dict[str, Any] = {
        "id": doc.pk,
        "parse_status": doc.parse_status,
        "extractor_kind": kind,
        "keys": list((doc.extracted_json or {}).keys()),
        "employee_sync": employee_sync,
    }
    return out
