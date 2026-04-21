"""
Сборка ZIP: manifest.json, summary.xlsx, documents/<doc_code>_<extractor>/...
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from pass_docs.models import EmployeeDocument, PackageRequest
from pass_docs.services.package_validation import PackageDocumentResolution, extractor_kind_for_document, resolve_document_filesystem_path


def _safe_segment(s: str, max_len: int = 96) -> str:
    t = re.sub(r"[^\w\-]+", "_", (s or "").strip(), flags=re.UNICODE)
    t = re.sub(r"_+", "_", t).strip("_") or "x"
    return t[:max_len]


def _zip_root_name(request: PackageRequest) -> str:
    key = _safe_segment(request.employee.import_key, 80)
    return f"package_{request.pk}_{key}"


def build_package_zip_bytes(
    request: PackageRequest,
    resolution: PackageDocumentResolution,
    xlsx_bytes: bytes,
    *,
    built_at: datetime | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """
    Возвращает (zip_bytes, manifest_dict) — manifest для payload_json.build_result.
    """
    bt = built_at or datetime.now(timezone.utc)
    if bt.tzinfo is None:
        bt = bt.replace(tzinfo=timezone.utc)
    built_iso = bt.isoformat()

    root = _zip_root_name(request)
    emp = resolution.employee

    manifest: dict[str, Any] = {
        "request_id": request.pk,
        "employee": {
            "id": emp.pk,
            "import_key": emp.import_key,
            "full_name": emp.full_name,
        },
        "built_at": built_iso,
        "zip_root": root,
        "documents": [],
    }

    buf = BytesIO()
    used_arcnames: set[str] = set()

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/summary.xlsx", xlsx_bytes)

        for doc in resolution.included:
            fs_path = resolve_document_filesystem_path(doc)
            if fs_path is None:
                continue

            code = _safe_segment(doc.document_type.code or "doc", 48)
            ek = _safe_segment(extractor_kind_for_document(doc) or "unknown", 48)
            rel_dir = f"{root}/documents/{code}_{ek}"

            orig_name = fs_path.name or f"document_{doc.pk}"
            arcname = f"{rel_dir}/{orig_name}"
            if arcname in used_arcnames:
                arcname = f"{rel_dir}/{doc.pk}/{orig_name}"
            used_arcnames.add(arcname)

            zf.write(str(fs_path), arcname=arcname)

            manifest["documents"].append(
                {
                    "document_id": doc.pk,
                    "code": doc.document_type.code,
                    "name": doc.document_type.name,
                    "extractor_kind": extractor_kind_for_document(doc),
                    "source_path": doc.source_path,
                    "archive_path": arcname,
                    "parse_status": doc.parse_status,
                    "is_actual": bool(doc.is_actual),
                }
            )

        zf.writestr(
            f"{root}/manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )

    return buf.getvalue(), manifest


def describe_zip_example_structure(request: PackageRequest) -> str:
    """Текстовое описание структуры (для help / логов)."""
    root = _zip_root_name(request)
    return "\n".join(
        [
            f"{root}/",
            "  manifest.json",
            "  summary.xlsx",
            "  documents/",
            "    <doc_code>_<extractor_kind>/",
            "      <original_filename>   # при коллизии: <document_id>_<original_filename>",
        ]
    )
