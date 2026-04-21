"""
Оркестрация сборки PackageRequest: валидация набора документов → Excel → ZIP → сохранение в модель.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from pass_docs.models import PackageRequest
from pass_docs.services.package_excel import build_package_workbook
from pass_docs.services.package_validation import resolve_and_validate_package_documents
from pass_docs.services.package_zip import build_package_zip_bytes, describe_zip_example_structure

logger = logging.getLogger(__name__)


class PackageBuildError(Exception):
    """Ошибка бизнес-логики сборки (сообщение для last_error)."""


def _payload_copy(request: PackageRequest) -> dict[str, Any]:
    raw = request.payload_json
    return dict(raw) if isinstance(raw, dict) else {}


def _ensure_payload_employee_matches(request: PackageRequest, payload: dict[str, Any]) -> None:
    eid = payload.get("employee_id")
    if eid is not None and str(eid).strip() != "":
        try:
            if int(eid) != int(request.employee_id):
                raise PackageBuildError(
                    f"payload_json.employee_id={eid} не совпадает с заявкой employee_id={request.employee_id}."
                )
        except (TypeError, ValueError) as exc:
            raise PackageBuildError(f"Некорректный payload_json.employee_id: {eid!r}.") from exc

    ikey = payload.get("employee_import_key")
    if isinstance(ikey, str) and ikey.strip() and ikey.strip() != request.employee.import_key:
        raise PackageBuildError(
            "payload_json.employee_import_key не совпадает с сотрудником заявки "
            f"({ikey!r} != {request.employee.import_key!r})."
        )


def _fail_request(request: PackageRequest, message: str) -> None:
    payload = _payload_copy(request)
    payload["last_error"] = message
    br = payload.get("build_result")
    if isinstance(br, dict):
        br["failed_at"] = datetime.now(timezone.utc).isoformat()
        br["error"] = message
        payload["build_result"] = br
    request.payload_json = payload
    request.status = PackageRequest.Status.FAILED
    request.save(update_fields=["payload_json", "status", "updated_at"])


def build_package_for_request(
    request_id: int,
    *,
    allow_draft: bool = False,
    allow_ready: bool = False,
) -> dict[str, Any]:
    """
    Полная сборка одной заявки.

    Допустимые старты: ``submitted``; при ``allow_draft=True`` ещё ``draft``;
    при ``allow_ready=True`` ещё ``ready`` (пересборка артефактов).
    В процессе: ``building`` → ``ready`` или ``failed``.
    """
    summary: dict[str, Any] = {"request_id": request_id, "ok": False}

    with transaction.atomic():
        try:
            request = PackageRequest.objects.select_for_update().get(pk=request_id)
        except PackageRequest.DoesNotExist as exc:
            raise PackageBuildError(f"PackageRequest id={request_id} не найдена.") from exc

        allowed = {PackageRequest.Status.SUBMITTED}
        if allow_draft:
            allowed.add(PackageRequest.Status.DRAFT)
        if allow_ready:
            allowed.add(PackageRequest.Status.READY)

        if request.status not in allowed:
            parts = ["submitted"]
            if allow_draft:
                parts.append("draft (--allow-draft)")
            if allow_ready:
                parts.append("ready (--allow-ready)")
            raise PackageBuildError(
                f"Сборка недоступна для status={request.status!r}. "
                f"Допустимо: {', '.join(parts)}."
            )

        payload = _payload_copy(request)
        _ensure_payload_employee_matches(request, payload)

        request.status = PackageRequest.Status.BUILDING
        request.save(update_fields=["status", "updated_at"])

        resolution = resolve_and_validate_package_documents(request)

        if not resolution.included:
            msg = "В пакет не попал ни один документ (проверьте файлы и фильтры). См. лист validation."
            _fail_request(request, msg)
            summary.update(
                {
                    "ok": False,
                    "status": request.status,
                    "last_error": msg,
                    "documents_total": resolution.documents_total,
                    "documents_included": 0,
                }
            )
            return summary

        built_at = datetime.now(timezone.utc)

        try:
            xlsx_bytes = build_package_workbook(request, resolution, built_at=built_at)
            zip_bytes, manifest = build_package_zip_bytes(request, resolution, xlsx_bytes, built_at=built_at)
        except Exception as exc:
            logger.exception("package build failed for request_id=%s", request_id)
            tb = traceback.format_exc()
            msg = f"{exc.__class__.__name__}: {exc}"
            _fail_request(request, msg)
            summary.update(
                {
                    "ok": False,
                    "status": request.status,
                    "last_error": msg,
                    "traceback_tail": tb[-4000:],
                }
            )
            return summary

        build_result: dict[str, Any] = {
            "built_at": built_at.isoformat(),
            "documents_total": resolution.documents_total,
            "documents_included": resolution.documents_included,
            "zip_root": manifest.get("zip_root", ""),
            "manifest": manifest,
            "zip_structure_help": describe_zip_example_structure(request),
        }

        payload["last_error"] = None
        payload["build_result"] = build_result
        request.payload_json = payload

        excel_name = f"package_{request.pk}_summary.xlsx"
        zip_name = f"package_{request.pk}.zip"

        request.excel_file.save(excel_name, ContentFile(xlsx_bytes), save=False)
        request.zip_file.save(zip_name, ContentFile(zip_bytes), save=False)
        request.status = PackageRequest.Status.READY

        request.save(update_fields=["payload_json", "excel_file", "zip_file", "status", "updated_at"])

        summary.update(
            {
                "ok": True,
                "status": request.status,
                "documents_total": resolution.documents_total,
                "documents_included": resolution.documents_included,
                "excel_file": request.excel_file.name,
                "zip_file": request.zip_file.name,
                "zip_root": build_result.get("zip_root"),
            }
        )
        return summary
