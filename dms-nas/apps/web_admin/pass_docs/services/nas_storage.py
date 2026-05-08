"""
Custom Django Storage backend using Synology NAS (FileStation API).

Files are stored under NAS_DMS_ROOT (default /ДМС) with structure:
  /ДМС/Сотрудники/{ФИО}/{Тип документа}.ext
  /ДМС/Пакеты/{ФИО}/Excel_{...}.xlsx

Set NAS_DMS_ROOT env var to change the root folder.
"""

import io
import logging
import os
import re

from django.core.files.base import File
from django.core.files.storage import Storage

logger = logging.getLogger("nas_storage")

NAS_DMS_ROOT = os.environ.get("NAS_DMS_ROOT", "/ДМС")


def _sanitize(name: str) -> str:
    """Remove characters forbidden in NAS paths."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip(" .")


def _nas_client():
    from core.nas_client import NASClient
    from core.config import NAS_BASE_URL as _URL, NAS_USER as _USER, NAS_PASSWORD as _PASS
    return NASClient(
        os.environ.get("NAS_BASE_URL") or _URL,
        os.environ.get("NAS_USER") or _USER,
        os.environ.get("NAS_PASSWORD") or _PASS,
    )


class NASStorage(Storage):
    """
    Store files on Synology NAS via FileStation API.
    Falls back gracefully if NAS is offline (raises IOError on save).
    """

    def __init__(self, location: str | None = None):
        self._location = (location or NAS_DMS_ROOT).rstrip("/")

    # ── internal helpers ──────────────────────────────────────────────────────

    def _nas_full(self, name: str) -> str:
        name = name.lstrip("/")
        return f"{self._location}/{name}"

    def _ensure_folder(self, folder_path: str) -> None:
        """Create all parent folders on NAS (idempotent)."""
        client = _nas_client()
        parts = folder_path.strip("/").split("/")
        cumul = ""
        for i, part in enumerate(parts):
            if i == 0:
                cumul = "/" + part
                continue
            parent = cumul
            cumul = cumul + "/" + part
            try:
                client.create_folder(parent, part)
            except Exception:
                pass  # 414 = already exists — fine

    # ── Django Storage interface ──────────────────────────────────────────────

    def _open(self, name: str, mode: str = "rb") -> File:
        client = _nas_client()
        data = client.download(self._nas_full(name))
        if data is None:
            raise FileNotFoundError(f"NAS: file not found: {name}")
        return File(io.BytesIO(data), name=name)

    def _save(self, name: str, content) -> str:
        nas_full = self._nas_full(name)
        folder, filename = nas_full.rsplit("/", 1)
        self._ensure_folder(folder)
        client = _nas_client()
        data = content.read() if hasattr(content, "read") else bytes(content)
        ok = client.upload(folder, filename, data)
        if not ok:
            raise IOError(f"NAS upload failed: {nas_full}")
        logger.info("NASStorage saved: %s", nas_full)
        return name

    def delete(self, name: str) -> None:
        if not name:
            return
        try:
            _nas_client().delete(self._nas_full(name))
            logger.info("NASStorage deleted: %s", name)
        except Exception as exc:
            logger.warning("NASStorage delete failed %s: %s", name, exc)

    def exists(self, name: str) -> bool:
        try:
            return _nas_client().path_exists(self._nas_full(name))
        except Exception:
            return False

    def url(self, name: str) -> str:
        # Files are proxied through Django views; URL is only used as fallback
        return f"/__nas_file__/{name}"

    def path(self, name: str) -> str:
        raise NotImplementedError("NASStorage: no local filesystem path")

    def size(self, name: str) -> int | None:
        return None


# ── upload_to callables ───────────────────────────────────────────────────────

def employee_doc_upload_path(instance, filename: str) -> str:
    """
    Generate NAS-relative path for EmployeeDocument.original_file.
    Result: Сотрудники/{ФИО}/{Тип документа}.ext
    """
    emp_name = _sanitize(
        getattr(instance.employee, "full_name", None) or f"emp_{instance.employee_id}"
    )
    doc_type = "документ"
    if getattr(instance, "document_type", None):
        doc_type = _sanitize(instance.document_type.name or "документ")
    ext = os.path.splitext(filename)[1].lower() or ".pdf"
    return f"Сотрудники/{emp_name}/{doc_type}{ext}"


def package_upload_path(instance, filename: str) -> str:
    """
    Generate NAS-relative path for PackageRequest files.
    Result: Пакеты/{ФИО}/{filename}
    """
    emp_name = _sanitize(
        getattr(instance.employee, "full_name", None) or f"emp_{instance.employee_id}"
    )
    return f"Пакеты/{emp_name}/{filename}"
