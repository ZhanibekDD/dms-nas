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
from pass_docs.services import employee_extraction_sync
from pass_docs.services import vision_client
from pass_docs.services.extractors import EXTRACTOR_REGISTRY
from pass_docs.services.passport_image_preprocessing import (
    PIPELINE_VERSION,
    choose_passport_rotation,
    compute_name_mismatch_warning,
)

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}

_TRAINING_KINDS = frozenset(
    {
        "safety_protocol_v",
        "safety_protocol_ab",
        "electrical_safety",
        "bdd_protocol",
        "siz_training_protocol",
        "umo",
    }
)


def resolve_extractor_kind(document_type: DocumentType) -> str | None:
    """Сначала поле DocumentType.extractor_kind, затем каталог кодов, затем эвристики по code."""
    raw = (document_type.extractor_kind or "").strip().lower()
    if raw in EXTRACTOR_REGISTRY:
        return raw
    from pass_docs.catalog.document_codes import extractor_kind_for_code

    ek = extractor_kind_for_code(document_type.code or "")
    if ek and ek in EXTRACTOR_REGISTRY:
        return ek
    code = (document_type.code or "").upper()
    if "PASSPORT" in code or "PASPORT" in code:
        return "ru_passport"
    if "MED" in code or "SPRAV" in code or "091" in code or "MEDICAL" in code:
        return "medical_certificate"
    return None


_FULL_TEXT_INSTRUCTION = (
    "full_text (ОБЯЗАТЕЛЬНО: весь текст документа дословно, слово за словом, "
    "строка за строкой в том же порядке что на документе, ничего не пропуская), "
)


def _vision_prompt(kind: str) -> str:
    if kind == "ru_passport":
        return (
            "Ты анализируешь изображение российского паспорта (разворот). "
            "Верни СТРОГО один JSON-объект без markdown и без пояснений. Ключи: "
            + _FULL_TEXT_INSTRUCTION +
            "series (4 цифры), number (6 цифр), last_name, first_name, middle_name, "
            "birth_date (только YYYY-MM-DD или пустая строка), "
            "issue_date (только YYYY-MM-DD или пустая строка), "
            "issuer (полное наименование органа выдавшего паспорт, напр. 'УМВД России по ЯНАО'), "
            "issuer_code (6 цифр кода подразделения, можно как 123-456), "
            "registration_address (одна строка — адрес регистрации как в документе). "
            "Поле iin не используй. Неизвестные поля — пустая строка или null."
        )
    if kind == "medical_certificate":
        return (
            "Ты анализируешь изображение медицинской справки (форма 086/у или аналог). "
            "Верни СТРОГО один JSON-объект. Ключи: "
            + _FULL_TEXT_INSTRUCTION +
            "certificate_number, issue_date, "
            "valid_until, patient_name, organization, conclusion. Даты в ISO ГГГГ-ММ-ДД или пусто."
        )
    if kind in _TRAINING_KINDS:
        return (
            "Ты анализируешь скан протокола или удостоверения обучения (РФ). "
            f"Тип по схеме extractor_kind: {kind}. "
            "Верни СТРОГО один JSON-объект без markdown. Ключи: "
            + _FULL_TEXT_INSTRUCTION +
            "protocol_number, issue_date, valid_until (только YYYY-MM-DD или пустая строка), "
            "holder_name, organization, program_name, conclusion. "
            "Неизвестные поля — пустая строка или null."
        )
    return (
        "Верни JSON-объект. Ключи: "
        + _FULL_TEXT_INSTRUCTION +
        "и другие поля документа которые видишь на изображении."
    )


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


def _pil_to_png_b64_for_vision(pil: Any, *, max_side: int = 1280) -> str:
    """Уменьшает кадр для vision (меньше трафик и быстрее ответ Ollama), сохраняет PNG → base64."""
    from PIL import Image

    im = pil.convert("RGB")
    w, h = im.size
    if max(w, h) > max_side:
        ratio = max_side / float(max(w, h))
        nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        im = im.resize((nw, nh), resample)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return vision_client.file_to_base64_from_bytes(buf.getvalue())


def _pdf_first_page_pil_pdfplumber(path: Path) -> Any | None:
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
                return pil.convert("RGB")
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                from PIL import Image

                img.save(tmp_path, format="PNG")
                with Image.open(tmp_path) as opened:
                    opened.load()
                    return opened.convert("RGB")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    except Exception as exc:
        logger.debug("pdfplumber first-page render failed for %s — %s", path, exc)
        return None


def _pdf_first_page_pil_pypdfium(path: Path) -> Any | None:
    """Headless-friendly рендер первой страницы (pypdfium2 тянется с pdfplumber)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    pdf = None
    try:
        pdf = pdfium.PdfDocument(str(path))
        if len(pdf) < 1:
            return None
        page = pdf[0]
        bitmap = page.render(scale=144 / 72.0)
        try:
            pil = bitmap.to_pil()
            return pil.convert("RGB")
        finally:
            bitmap.close()
    except Exception as exc:
        logger.debug("pypdfium2 first-page render failed for %s — %s", path, exc)
        return None
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def _pdf_first_page_pil(path: Path) -> Any | None:
    pil = _pdf_first_page_pil_pdfplumber(path)
    if pil is not None:
        return pil
    return _pdf_first_page_pil_pypdfium(path)


_PDF_MAX_PAGES_FOR_VISION = 10


def _pdf_all_pages_pil_pdfplumber(path: Path) -> list[Any]:
    import os, tempfile
    import pdfplumber

    pages: list[Any] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:_PDF_MAX_PAGES_FOR_VISION]:
                try:
                    img = page.to_image(resolution=144)
                    pil = getattr(img, "original", None)
                    if pil is not None and hasattr(pil, "save"):
                        pages.append(pil.convert("RGB"))
                        continue
                    fd, tmp_path = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    try:
                        from PIL import Image
                        img.save(tmp_path, format="PNG")
                        with Image.open(tmp_path) as opened:
                            opened.load()
                            pages.append(opened.convert("RGB"))
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
                except Exception as exc:
                    logger.debug("pdfplumber page render failed: %s", exc)
    except Exception as exc:
        logger.debug("pdfplumber all-pages render failed for %s — %s", path, exc)
    return pages


def _pdf_all_pages_pil_pypdfium(path: Path) -> list[Any]:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []
    pdf = None
    pages: list[Any] = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        for i in range(min(len(pdf), _PDF_MAX_PAGES_FOR_VISION)):
            try:
                page = pdf[i]
                bitmap = page.render(scale=144 / 72.0)
                try:
                    pages.append(bitmap.to_pil().convert("RGB"))
                finally:
                    bitmap.close()
            except Exception as exc:
                logger.debug("pypdfium2 page %d render failed: %s", i, exc)
    except Exception as exc:
        logger.debug("pypdfium2 all-pages render failed for %s — %s", path, exc)
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass
    return pages


def _pdf_all_pages_pil(path: Path) -> list[Any]:
    pages = _pdf_all_pages_pil_pdfplumber(path)
    if pages:
        return pages
    return _pdf_all_pages_pil_pypdfium(path)


def _passport_pre_meta_text_only() -> dict[str, Any]:
    return {
        "rotation_applied": None,
        "variant": "skipped_text_only_pdf",
        "note": "Ориентация по изображению не применялась (извлечение только из текста PDF).",
    }


def _merge_passport_meta(
    doc: EmployeeDocument,
    *,
    normalized: dict[str, Any],
    preprocessing: dict[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    nm = compute_name_mismatch_warning(doc.employee, normalized)
    out = {**base, "pipeline_version": PIPELINE_VERSION, "preprocessing": preprocessing}
    out.update(nm)
    return out


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
                base: dict[str, Any] = {
                    "pipeline": steps,
                    "extractor_kind": kind,
                    "normalized": normalized,
                    "pdf_text": pdf_text,
                }
                if kind == "ru_passport":
                    doc.extracted_json = _merge_passport_meta(
                        doc,
                        normalized=normalized,
                        preprocessing=_passport_pre_meta_text_only(),
                        base=base,
                    )
                else:
                    doc.extracted_json = {**base, "pipeline_version": PIPELINE_VERSION}
                doc.parse_status = EmployeeDocument.ParseStatus.OK
            else:
                steps.append("pdf_text_weak_or_empty_try_vision")
                if kind == "ru_passport":
                    # Паспорт: одна страница + эвристика ориентации
                    pil_page = _pdf_first_page_pil(path)
                    if pil_page is None:
                        doc.extracted_json = {
                            "pipeline": steps,
                            "error": "pdf_first_page_render_failed",
                            "extractor_kind": kind,
                        }
                        doc.parse_status = EmployeeDocument.ParseStatus.ERROR
                    else:
                        pil_for_vision, pre_meta = choose_passport_rotation(pil_page)
                        steps.append("passport_orientation_heuristic")
                        b64 = _pil_to_png_b64_for_vision(pil_for_vision)
                        vision_raw = vision_client.chat_json(
                            _vision_prompt(kind),
                            images_b64=[b64],
                        )
                        steps.append("vision_ok")
                        full_text = vision_raw.pop("full_text", "") if isinstance(vision_raw, dict) else ""
                        normalized = _run_extractor(kind, vision_json=vision_raw, pdf_text=None)
                        doc.extracted_json = _merge_passport_meta(
                            doc,
                            normalized=normalized,
                            preprocessing=pre_meta,
                            base={
                                "pipeline": steps,
                                "extractor_kind": kind,
                                "raw_vision": vision_raw,
                                "normalized": normalized,
                                "full_text": full_text,
                            },
                        )
                        doc.parse_status = EmployeeDocument.ParseStatus.OK
                else:
                    # Все остальные типы: все страницы PDF
                    all_pils = _pdf_all_pages_pil(path)
                    if not all_pils:
                        doc.extracted_json = {
                            "pipeline": steps,
                            "error": "pdf_pages_render_failed",
                            "extractor_kind": kind,
                        }
                        doc.parse_status = EmployeeDocument.ParseStatus.ERROR
                    else:
                        steps.append(f"pdf_pages_rendered:{len(all_pils)}")
                        images_b64 = [_pil_to_png_b64_for_vision(p) for p in all_pils]
                        vision_raw = vision_client.chat_json(
                            _vision_prompt(kind),
                            images_b64=images_b64,
                        )
                        steps.append("vision_ok")
                        full_text = vision_raw.pop("full_text", "") if isinstance(vision_raw, dict) else ""
                        normalized = _run_extractor(kind, vision_json=vision_raw, pdf_text=None)
                        doc.extracted_json = {
                            "pipeline": steps,
                            "extractor_kind": kind,
                            "raw_vision": vision_raw,
                            "normalized": normalized,
                            "full_text": full_text,
                            "pipeline_version": PIPELINE_VERSION,
                        }
                        doc.parse_status = EmployeeDocument.ParseStatus.OK

        elif ext in IMAGE_SUFFIXES:
            steps.append("image_direct_vision")
            from PIL import Image

            with Image.open(path) as im:
                im.load()
                pil_page = im.convert("RGB")
            if kind == "ru_passport":
                pil_for_vision, pre_meta = choose_passport_rotation(pil_page)
                steps.append("passport_orientation_heuristic")
            else:
                pil_for_vision = pil_page
                pre_meta = {
                    "rotation_applied": 0,
                    "variant": "no_passport_skip_orientation",
                    "note": "Только ru_passport проходит выбор ориентации.",
                }
            b64 = _pil_to_png_b64_for_vision(pil_for_vision)
            vision_raw = vision_client.chat_json(
                _vision_prompt(kind),
                images_b64=[b64],
            )
            steps.append("vision_ok")
            full_text = vision_raw.pop("full_text", "") if isinstance(vision_raw, dict) else ""
            normalized = _run_extractor(kind, vision_json=vision_raw, pdf_text=None)
            base = {
                "pipeline": steps,
                "extractor_kind": kind,
                "raw_vision": vision_raw,
                "normalized": normalized,
                "full_text": full_text,
            }
            if kind == "ru_passport":
                doc.extracted_json = _merge_passport_meta(
                    doc,
                    normalized=normalized,
                    preprocessing=pre_meta,
                    base=base,
                )
            else:
                doc.extracted_json = {**base, "pipeline_version": PIPELINE_VERSION}
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
