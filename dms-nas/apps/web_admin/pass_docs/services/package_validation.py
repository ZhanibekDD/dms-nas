"""
Разрешение набора документов для PackageRequest и проверки перед сборкой архива.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db.models import QuerySet

from pass_docs.models import Employee, EmployeeDocument, PackageRequest
from pass_docs.services.document_pipeline import resolve_extractor_kind


def resolve_document_filesystem_path(doc: EmployeeDocument) -> Path | None:
    """Путь к файлу на диске: source_path, иначе original_file."""
    raw = (doc.source_path or "").strip()
    if raw:
        p = Path(raw)
        if p.is_file():
            return p
    if doc.original_file:
        try:
            p = Path(doc.original_file.path)
            if p.is_file():
                return p
        except Exception:
            return None
    return None


def extractor_kind_for_document(doc: EmployeeDocument) -> str:
    payload = doc.extracted_json if isinstance(doc.extracted_json, dict) else {}
    k = (payload.get("extractor_kind") or "").strip()
    if k:
        return k
    return (resolve_extractor_kind(doc.document_type) or doc.document_type.extractor_kind or "").strip()


@dataclass
class ValidationEntry:
    """Строка для листа validation в Excel."""

    document_id: int | None
    doc_code: str
    severity: str  # error | warning | info
    message: str
    field: str
    current_value: str


@dataclass
class PackageDocumentResolution:
    """Результат разбора и фильтрации документов."""

    employee: Employee
    candidates: list[EmployeeDocument] = field(default_factory=list)
    included: list[EmployeeDocument] = field(default_factory=list)
    validation_entries: list[ValidationEntry] = field(default_factory=list)

    @property
    def documents_total(self) -> int:
        return len(self.candidates)

    @property
    def documents_included(self) -> int:
        return len(self.included)


def _payload(request: PackageRequest) -> dict[str, Any]:
    raw = request.payload_json
    return raw if isinstance(raw, dict) else {}


def _filters(payload: dict[str, Any]) -> dict[str, Any]:
    f = payload.get("filters")
    return f if isinstance(f, dict) else {}


def _candidate_queryset(request: PackageRequest, payload: dict[str, Any]) -> QuerySet[EmployeeDocument]:
    emp = request.employee
    ids = payload.get("selected_document_ids")
    if ids is not None and isinstance(ids, (list, tuple)) and len(ids) > 0:
        id_list = [int(x) for x in ids if str(x).strip().isdigit() or isinstance(x, int)]
        return (
            EmployeeDocument.objects.filter(employee=emp, pk__in=id_list)
            .select_related("employee", "document_type")
            .order_by("document_type__code", "pk")
        )
    return (
        EmployeeDocument.objects.filter(employee=emp)
        .select_related("employee", "document_type")
        .order_by("document_type__code", "pk")
    )


def resolve_and_validate_package_documents(request: PackageRequest) -> PackageDocumentResolution:
    """
    Собирает кандидатов, применяет фильтры из payload_json, формирует validation_entries.
    Документы с ошибками (нет файла, не прошёл фильтр) не попадают в included.
    """
    payload = _payload(request)
    filters = _filters(payload)
    only_actual = bool(filters.get("only_actual"))
    only_parse_ok = bool(filters.get("only_parse_ok"))

    out = PackageDocumentResolution(employee=request.employee)
    qs = _candidate_queryset(request, payload)
    out.candidates = list(qs)

    raw_ids = payload.get("selected_document_ids")
    has_explicit_ids = raw_ids is not None and isinstance(raw_ids, (list, tuple)) and len(raw_ids) > 0

    if not out.candidates:
        msg = "Нет документов для сборки (у сотрудника нет документов"
        if has_explicit_ids:
            msg += " или ни один selected_document_ids не принадлежит этому сотруднику"
        msg += ")."
        out.validation_entries.append(
            ValidationEntry(
                document_id=None,
                doc_code="",
                severity="error",
                message=msg,
                field="selected_document_ids" if has_explicit_ids else "",
                current_value=str(raw_ids)[:500] if has_explicit_ids else "",
            )
        )
        return out

    for doc in out.candidates:
        doc_code = doc.document_type.code or ""
        fs_path = resolve_document_filesystem_path(doc)
        if fs_path is None:
            out.validation_entries.append(
                ValidationEntry(
                    document_id=doc.pk,
                    doc_code=doc_code,
                    severity="error",
                    message="Файл не найден по source_path и original_file.",
                    field="source_path",
                    current_value=(doc.source_path or "")[:500],
                )
            )
            continue

        if only_actual and not doc.is_actual:
            out.validation_entries.append(
                ValidationEntry(
                    document_id=doc.pk,
                    doc_code=doc_code,
                    severity="error",
                    message="Исключён: фильтр only_actual, документ не актуален.",
                    field="is_actual",
                    current_value="false",
                )
            )
            continue

        if only_parse_ok and doc.parse_status != EmployeeDocument.ParseStatus.OK:
            out.validation_entries.append(
                ValidationEntry(
                    document_id=doc.pk,
                    doc_code=doc_code,
                    severity="error",
                    message="Исключён: фильтр only_parse_ok, parse_status не ok.",
                    field="parse_status",
                    current_value=str(doc.parse_status),
                )
            )
            continue

        if doc.parse_status == EmployeeDocument.ParseStatus.ERROR:
            out.validation_entries.append(
                ValidationEntry(
                    document_id=doc.pk,
                    doc_code=doc_code,
                    severity="warning",
                    message="Документ включён, но parse_status=error.",
                    field="parse_status",
                    current_value=str(doc.parse_status),
                )
            )

        out.included.append(doc)

    return out
