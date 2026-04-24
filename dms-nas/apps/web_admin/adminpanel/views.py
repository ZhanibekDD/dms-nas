"""
Web admin custom views: dashboard KPI + NAS download proxy + health.
Sprint 8: health endpoint, packages from web.
Sprint 9: object summary, packages UI.
"""

import io
import json
import os
import sys
import logging
from typing import Optional
from datetime import datetime
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("web_views")

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _db():
    import apps.bot.bot_db as db
    return db


def _nas():
    from apps.bot.bot_nas import get_nas
    return get_nas()


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────


@staff_member_required
def root_pass_docs_redirect(request):
    """GET / → список сотрудников (основной сценарий оператора)."""
    return redirect("pass_docs_employees")


def _dashboard_missing_schema_redirect(request, exc) -> Optional[HttpResponse]:
    """Если схема adminpanel не прогнана (нет таблиц) — не даём 500 на `/`."""
    from django.db.utils import OperationalError

    if not isinstance(exc, OperationalError):
        return None
    msg = str(exc).lower()
    if "no such table" not in msg and "does not exist" not in msg:
        return None
    logger.warning("dashboard: incomplete DB schema (%s) — redirect to pass_docs", exc)
    messages.info(
        request,
        "Главный дашборд сейчас недоступен: в базе нет нужных таблиц. "
        "Открыт список сотрудников. Для полного дашборда выполните migrate.",
    )
    return redirect("pass_docs_employees")


@staff_member_required
def dashboard(request):
    from .models import UploadLog, ExpiryItem, FinanceDoc, Problem, Document
    from django.db.models import Count
    from datetime import date

    today = date.today().isoformat()

    from django.db.utils import OperationalError

    try:
        # ── Загрузки ──
        total_docs    = UploadLog.objects.count()
        pending_docs  = UploadLog.objects.filter(review_status="pending").count()
        approved      = UploadLog.objects.filter(review_status="approved").count()
        rejected      = UploadLog.objects.filter(review_status="rejected").count()
        today_uploads = UploadLog.objects.filter(uploaded_at__startswith=today).count()

        # ── Сроки ──
        expiry_active  = ExpiryItem.objects.filter(status="active").count()
        expiry_overdue = sum(
            1 for e in ExpiryItem.objects.filter(status="active")
            if e.expires_at < today
        )
        expiry_soon = sum(
            1 for e in ExpiryItem.objects.filter(status="active")
            if today <= e.expires_at <= (date.today().replace(day=date.today().day)).isoformat()
            or 0 <= (
                (date.fromisoformat(e.expires_at) - date.today()).days
            ) <= 7
        )

        # ── Финансы ──
        fin_total    = FinanceDoc.objects.count()
        fin_draft    = FinanceDoc.objects.filter(status="черновик").count()
        fin_review   = FinanceDoc.objects.filter(status="на_проверке").count()
        fin_approved = FinanceDoc.objects.filter(status="утверждён").count()
        fin_paid     = FinanceDoc.objects.filter(status="оплачен").count()

        # ── Проблемы ──
        open_problems = Problem.objects.filter(status="open").count()

        # ── Sprint 11: Document Registry ──
        registry_total   = Document.objects.count()
        registry_pending = Document.objects.filter(status="pending").count()
        registry_approved = Document.objects.filter(status="approved").count()
        # дубликаты — файлы с одинаковым хэшем
        try:
            dupes = (
                Document.objects
                .exclude(file_hash__isnull=True)
                .exclude(file_hash="")
                .values("file_hash")
                .annotate(cnt=Count("id"))
                .filter(cnt__gt=1)
                .count()
            )
        except Exception:
            dupes = 0

        # ── Топ объектов по активности ──
        top_objects = (
            UploadLog.objects
            .exclude(object_name="")
            .values("object_name")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:5]
        )

        recent_uploads = UploadLog.objects.order_by("-id")[:10]

        context = {
            "total_docs":       total_docs,
            "pending_docs":     pending_docs,
            "approved":         approved,
            "rejected":         rejected,
            "today_uploads":    today_uploads,
            "expiry_active":    expiry_active,
            "expiry_overdue":   expiry_overdue,
            "expiry_soon":      expiry_soon,
            "fin_total":        fin_total,
            "fin_draft":        fin_draft,
            "fin_review":       fin_review,
            "fin_approved":     fin_approved,
            "fin_paid":         fin_paid,
            "open_problems":    open_problems,
            # Registry
            "registry_total":   registry_total,
            "registry_pending": registry_pending,
            "registry_approved": registry_approved,
            "registry_dupes":   dupes,
            # Top objects
            "top_objects":      top_objects,
            "recent_uploads":   recent_uploads,
        }
        return render(request, "adminpanel/dashboard.html", context)
    except OperationalError as exc:
        redir = _dashboard_missing_schema_redirect(request, exc)
        if redir is not None:
            return redir
        raise


def _workspace_ctx(active: str):
    return {"workspace_active": active}


def _pass_docs_shell_ctx(active: str) -> dict:
    return {"pass_docs_active": active}


@staff_member_required
def workspace_dashboard(request):
    return render(
        request,
        "adminpanel/workspace_dashboard.html",
        _workspace_ctx("dashboard"),
    )


@staff_member_required
def workspace_employees(request):
    return redirect("pass_docs_employees")


@staff_member_required
def workspace_documents(request):
    return redirect("pass_docs_documents")


@staff_member_required
def pass_docs_home(request):
    return redirect("pass_docs_employees")


def _pass_docs_safe_local_redirect(request, target: str):
    """Только относительные пути внутри workspace — после POST сборки пакета."""
    if target.startswith("/workspace/"):
        return redirect(target)
    return redirect("pass_docs_package_requests")


@staff_member_required
def pass_docs_employees(request):
    from django.db.models import Count, Q
    from pass_docs.models import Employee

    q = (request.GET.get("q") or "").strip()
    company = (request.GET.get("company") or "").strip()
    active = (request.GET.get("active") or "").strip()

    qs = Employee.objects.annotate(
        documents_count=Count("documents"),
        documents_ok_count=Count("documents", filter=Q(documents__parse_status="ok")),
    )
    if q:
        qs = qs.filter(
            Q(import_key__icontains=q)
            | Q(full_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(source_folder_name__icontains=q)
            | Q(company__icontains=q)
        )
    if company:
        qs = qs.filter(company__icontains=company)
    if active in ("1", "0"):
        qs = qs.filter(is_active=(active == "1"))

    employees_qs = qs.order_by("full_name", "import_key")
    paginator = Paginator(employees_qs, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    employees_with_docs = employees_qs.filter(documents_count__gt=0).count()
    employees_active = employees_qs.filter(is_active=True).count()

    context = {
        **_pass_docs_shell_ctx("employees"),
        "employees": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "company": company,
        "active": active,
        "employees_total": employees_qs.count(),
        "employees_active": employees_active,
        "employees_with_docs": employees_with_docs,
    }
    return render(request, "adminpanel/pass_docs_employees.html", context)


@staff_member_required
def pass_docs_employee_detail(request, employee_id: int):
    from django.db.models import Count
    from pass_docs.models import Employee, EmployeeDocument, PackageRequest

    from adminpanel.pass_docs_display import employee_bundle_line

    emp = (
        Employee.objects.filter(pk=employee_id)
        .annotate(
            documents_count=Count("documents", distinct=True),
        )
        .first()
    )
    if not emp:
        raise Http404("Сотрудник не найден")

    docs = (
        EmployeeDocument.objects.filter(employee=emp)
        .select_related("document_type")
        .order_by("document_type__code", "id")
    )
    dtot = docs.count()
    parse_ok = docs.filter(parse_status=EmployeeDocument.ParseStatus.OK).count()
    parse_pending = docs.filter(parse_status=EmployeeDocument.ParseStatus.PENDING).count()
    parse_err = docs.filter(parse_status=EmployeeDocument.ParseStatus.ERROR).count()
    doc_ok = docs.filter(status=EmployeeDocument.Status.OK).count()

    package_qs = (
        PackageRequest.objects.filter(employee=emp)
        .order_by("-created_at", "-id")[:20]
    )
    ready_with_files = None
    for pr in package_qs:
        if pr.status == PackageRequest.Status.READY and (pr.excel_file or pr.zip_file):
            ready_with_files = pr
            break

    context = {
        **_pass_docs_shell_ctx("employees"),
        "employee": emp,
        "documents": docs,
        "package_requests": package_qs,
        "ready_package": ready_with_files,
        "bundle_summary": employee_bundle_line(
            documents_total=dtot,
            parse_ok=parse_ok,
            parse_pending=parse_pending,
            parse_err=parse_err,
            doc_ok=doc_ok,
        ),
    }
    return render(request, "adminpanel/pass_docs_employee_detail.html", context)


@staff_member_required
@require_POST
def pass_docs_employee_quick_build(request, employee_id: int):
    from pass_docs.models import Employee, PackageRequest
    from pass_docs.services.package_builder import PackageBuildError, build_package_for_request

    emp = Employee.objects.filter(pk=employee_id).first()
    if not emp:
        raise Http404("Сотрудник не найден")

    pr = PackageRequest.objects.create(
        employee=emp,
        package_kind="",
        status=PackageRequest.Status.SUBMITTED,
        payload_json={
            "employee_id": emp.pk,
            "employee_import_key": emp.import_key,
        },
    )
    try:
        summary = build_package_for_request(pr.pk, allow_draft=False, allow_ready=False)
    except PackageBuildError as exc:
        messages.error(request, str(exc))
        return redirect("pass_docs_employee_detail", employee_id=emp.pk)

    if summary.get("ok"):
        messages.success(
            request,
            f"Пакет собран (заявка №{pr.pk}). Документов в архиве: {summary.get('documents_included')}.",
        )
    else:
        messages.error(request, summary.get("last_error") or "Не удалось собрать пакет.")
    return redirect("pass_docs_employee_detail", employee_id=emp.pk)


def _pass_docs_document_file_response(request, doc_id: int, *, attachment: bool):
    from adminpanel.pass_docs_display import guess_mime_for_path

    from pass_docs.models import EmployeeDocument

    doc = EmployeeDocument.objects.filter(pk=doc_id).first()
    if not doc:
        raise Http404("Документ не найден")
    f = doc.original_file
    if not f or not f.name:
        raise Http404("Файл не загружен")

    fh = f.open("rb")
    download_name = os.path.basename(f.name)
    ctype = guess_mime_for_path(download_name)
    resp = FileResponse(fh, content_type=ctype or "application/octet-stream")
    disp_type = "attachment" if attachment else "inline"
    resp["Content-Disposition"] = f'{disp_type}; filename="{download_name}"'
    return resp


@staff_member_required
@xframe_options_sameorigin
@require_GET
def pass_docs_document_file_inline(request, doc_id: int):
    """Встроенный просмотр (PDF / изображение)."""
    return _pass_docs_document_file_response(request, doc_id, attachment=False)


@staff_member_required
@require_GET
def pass_docs_document_download(request, doc_id: int):
    """Скачать исходный файл."""
    return _pass_docs_document_file_response(request, doc_id, attachment=True)


@staff_member_required
def pass_docs_documents(request):
    from django.db.models import Q
    from pass_docs.models import EmployeeDocument

    q = (request.GET.get("q") or "").strip()
    parse_status = (request.GET.get("parse_status") or "").strip()
    status = (request.GET.get("status") or "").strip()
    actual = (request.GET.get("actual") or "").strip()

    qs = EmployeeDocument.objects.select_related("employee", "document_type")
    if q:
        qs = qs.filter(
            Q(employee__full_name__icontains=q)
            | Q(employee__import_key__icontains=q)
            | Q(document_type__code__icontains=q)
            | Q(document_type__name__icontains=q)
            | Q(source_path__icontains=q)
        )
    if parse_status:
        qs = qs.filter(parse_status=parse_status)
    if status:
        qs = qs.filter(status=status)
    if actual in ("1", "0"):
        qs = qs.filter(is_actual=(actual == "1"))

    documents_qs = qs.order_by("-updated_at", "-id")
    paginator = Paginator(documents_qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    documents_ok = documents_qs.filter(parse_status=EmployeeDocument.ParseStatus.OK).count()
    documents_error = documents_qs.filter(parse_status=EmployeeDocument.ParseStatus.ERROR).count()
    documents_pending = documents_qs.filter(parse_status=EmployeeDocument.ParseStatus.PENDING).count()

    context = {
        **_pass_docs_shell_ctx("documents"),
        "documents": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "parse_status": parse_status,
        "status": status,
        "actual": actual,
        "parse_status_choices": EmployeeDocument.ParseStatus.choices,
        "status_choices": EmployeeDocument.Status.choices,
        "documents_total": documents_qs.count(),
        "documents_ok": documents_ok,
        "documents_error": documents_error,
        "documents_pending": documents_pending,
    }
    return render(request, "adminpanel/pass_docs_documents.html", context)


@staff_member_required
def pass_docs_document_types(request):
    from django.db.models import Q
    from pass_docs.models import DocumentType

    q = (request.GET.get("q") or "").strip()
    is_common = (request.GET.get("is_common") or "").strip()

    qs = DocumentType.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))
    if is_common in ("1", "0"):
        qs = qs.filter(is_common_document=(is_common == "1"))

    types_qs = qs.order_by("sort_order", "code")
    paginator = Paginator(types_qs, 40)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **_pass_docs_shell_ctx("types"),
        "document_types": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "is_common": is_common,
        "types_total": types_qs.count(),
    }
    return render(request, "adminpanel/pass_docs_document_types.html", context)


@staff_member_required
def pass_docs_package_requests(request):
    from django.db.models import Q
    from pass_docs.models import PackageRequest

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    employee_pk = (request.GET.get("employee") or "").strip()

    qs = PackageRequest.objects.select_related("employee")
    if employee_pk.isdigit():
        qs = qs.filter(employee_id=int(employee_pk))
    if q:
        qs = qs.filter(
            Q(employee__full_name__icontains=q)
            | Q(employee__import_key__icontains=q)
            | Q(email_to__icontains=q)
            | Q(package_kind__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    requests_qs = qs.order_by("-created_at", "-id")
    paginator = Paginator(requests_qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **_pass_docs_shell_ctx("packages"),
        "package_requests": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "employee_filter": employee_pk,
        "status_choices": PackageRequest.Status.choices,
        "requests_total": requests_qs.count(),
    }
    return render(request, "adminpanel/pass_docs_package_requests.html", context)


@staff_member_required
@require_POST
def pass_docs_package_request_build(request, request_id: int):
    """Запуск сборки Excel+ZIP для одной заявки (draft / submitted), без нового UI-слоя."""
    from pass_docs.models import PackageRequest
    from pass_docs.services.package_builder import PackageBuildError, build_package_for_request

    pr = PackageRequest.objects.filter(pk=request_id).first()
    if not pr:
        raise Http404("Заявка не найдена")
    allow_draft = pr.status == PackageRequest.Status.DRAFT
    allow_ready = pr.status == PackageRequest.Status.READY
    try:
        summary = build_package_for_request(
            pr.pk, allow_draft=allow_draft, allow_ready=allow_ready
        )
    except PackageBuildError as exc:
        messages.error(request, str(exc))
        return _pass_docs_safe_local_redirect(
            request, (request.POST.get("next") or "").strip()
        )
    if summary.get("ok"):
        messages.success(
            request,
            f"Пакет №{pr.pk}: готово. Документов в архиве: {summary.get('documents_included')}.",
        )
    else:
        messages.error(
            request,
            summary.get("last_error") or "Сборка завершилась с ошибкой.",
        )
    next_path = (request.POST.get("next") or "").strip()
    return _pass_docs_safe_local_redirect(request, next_path)


@staff_member_required
@require_GET
def pass_docs_package_request_download(request, request_id: int, kind: str):
    """Скачивание Excel или ZIP для заявки в статусе ready (только staff)."""
    import mimetypes

    from pass_docs.models import PackageRequest

    kind = (kind or "").strip().lower()
    if kind not in ("excel", "zip"):
        raise Http404("Неизвестный тип файла")
    pr = PackageRequest.objects.filter(pk=request_id).first()
    if not pr:
        raise Http404("Заявка не найдена")
    if pr.status != PackageRequest.Status.READY:
        raise Http404("Скачивание доступно только для заявок в статусе «Готов»")
    if kind == "excel":
        f = pr.excel_file
        fallback = f"package_{pr.pk}_summary.xlsx"
        ctype_default = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        f = pr.zip_file
        fallback = f"package_{pr.pk}.zip"
        ctype_default = "application/zip"
    if not f or not f.name:
        raise Http404("Файл ещё не сформирован")
    download_name = os.path.basename(f.name) if f.name else fallback
    ctype, _ = mimetypes.guess_type(download_name)
    if not ctype:
        ctype = ctype_default
    return FileResponse(
        f.open("rb"),
        as_attachment=True,
        filename=download_name,
        content_type=ctype,
    )


@staff_member_required
def pass_docs_document_detail(request, doc_id: int):
    from adminpanel.pass_docs_display import (
        normalized_pairs_for_ui,
        normalized_warnings,
        viewer_kind_for_document,
    )

    from pass_docs.models import EmployeeDocument

    doc = (
        EmployeeDocument.objects.select_related("employee", "document_type")
        .filter(pk=doc_id)
        .first()
    )
    if not doc:
        raise Http404(f"Документ не найден")

    payload = doc.extracted_json or {}
    normalized = payload.get("normalized") if isinstance(payload.get("normalized"), dict) else {}
    vk = viewer_kind_for_document(doc.original_file)
    has_file = bool(doc.original_file and doc.original_file.name)

    context = {
        **_pass_docs_shell_ctx("documents"),
        "doc": doc,
        "payload": payload,
        "normalized": normalized,
        "normalized_rows": normalized_pairs_for_ui(normalized),
        "warnings": normalized_warnings(normalized),
        "raw_vision": payload.get("raw_vision"),
        "viewer_kind": vk,
        "viewer_has_file": has_file,
    }
    return render(request, "adminpanel/pass_docs_document_detail.html", context)


@staff_member_required
def workspace_packages(request):
    return render(
        request,
        "adminpanel/packages_hub.html",
        _workspace_ctx("packages"),
    )


@staff_member_required
def ai_assistant_page(request):
    return render(
        request,
        "adminpanel/ai_assistant.html",
        _workspace_ctx("ai"),
    )


@staff_member_required
def scan_document_page(request):
    return render(
        request,
        "adminpanel/scan_document.html",
        _workspace_ctx("scan"),
    )


# ──────────────────────────────────────────────────────────────────────────────
# NAS Download Proxy — browser never connects to NAS directly
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
def nas_proxy(request):
    """
    GET /nas-proxy/?path=/Объект/_INBOX/Тип/file.pdf
    Downloads file from NAS and streams it back to browser.
    """
    path = request.GET.get("path", "").strip()
    if not path or ".." in path:
        raise Http404("Invalid path")

    logger.info("NAS proxy download: user=%s path=%s", request.user.username, path)

    try:
        nas = _nas()
        content = nas.download(path)
    except Exception as exc:
        logger.error("NAS proxy error: %s", exc)
        return HttpResponse(f"Ошибка NAS: {exc}", status=502)

    if content is None:
        raise Http404("File not found on NAS")

    filename = path.rsplit("/", 1)[-1]
    # Guess content type
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_map = {
        "pdf": "application/pdf",
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "zip": "application/zip",
        "mp4": "video/mp4",
    }
    content_type = mime_map.get(ext, "application/octet-stream")

    resp = HttpResponse(content, content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["Content-Length"] = len(content)
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 8 — Health endpoint (public, no auth needed)
# GET /health → {"status":"ok","db":"ok","timestamp":"..."}
# ──────────────────────────────────────────────────────────────────────────────

@require_GET
def health(request):
    status = {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

    # Check DB
    try:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        status["db"] = "ok"
    except Exception as exc:
        status["db"] = f"error: {exc}"
        status["status"] = "degraded"

    # Check NAS (non-blocking: skip if NAS is slow)
    try:
        nas = _nas()
        shares = nas.list_shares()
        status["nas"] = f"ok ({len(shares)} shares)"
    except Exception as exc:
        status["nas"] = f"error: {exc}"
        status["status"] = "degraded"

    http_status = 200 if status["status"] == "ok" else 503
    return JsonResponse(status, status=http_status)


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 9 — Packages from Web UI
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
def packages_ui(request):
    """
    GET  /packages/   — form to build a package
    POST /packages/   — submit and stream ZIP
    """
    from .models import PackageLog

    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if root not in sys.path:
        sys.path.insert(0, root)

    from apps.bot.bot_config import DOC_TYPES, NAS_ROOT_SHARES
    from apps.bot.bot_nas import nas_list_folder

    # Collect available objects
    objects: list[str] = []
    for share in NAS_ROOT_SHARES:
        for item in nas_list_folder(share):
            if item.get("isdir"):
                objects.append(item["name"])

    if request.method == "GET":
        history = PackageLog.objects.order_by("-id")[:20]
        return render(request, "adminpanel/packages.html", {
            "objects": objects or ["Днепр", "Обмен"],
            "doc_types": DOC_TYPES,
            "history": history,
        })

    # POST — build package
    object_name = request.POST.get("object_name", "").strip()
    period      = request.POST.get("period", "").strip()
    doc_types   = request.POST.getlist("doc_types")

    if not object_name or not doc_types:
        return render(request, "adminpanel/packages.html", {
            "objects": objects,
            "doc_types": DOC_TYPES,
            "error": "Укажите объект и хотя бы один тип документа",
            "history": PackageLog.objects.order_by("-id")[:20],
        })

    import apps.bot.bot_db as db
    from core.services.packages import build_package

    user_id = request.user.id or 0
    result = build_package(_nas(), db, user_id, object_name, period, doc_types)

    if not result["ok"]:
        return render(request, "adminpanel/packages.html", {
            "objects": objects,
            "doc_types": DOC_TYPES,
            "error": result["error"],
            "history": PackageLog.objects.order_by("-id")[:20],
        })

    # Stream ZIP to browser
    resp = HttpResponse(result["zip_bytes"], content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{result["zip_name"]}"'
    resp["Content-Length"] = len(result["zip_bytes"])
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 9 — Object Summary page
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
def object_summary(request, object_name: str):
    from .models import UploadLog, ExpiryItem, FinanceDoc, Problem, Report
    from datetime import date

    today = date.today().isoformat()

    docs_total    = UploadLog.objects.filter(object_name=object_name).count()
    docs_pending  = UploadLog.objects.filter(object_name=object_name, review_status="pending").count()
    docs_approved = UploadLog.objects.filter(object_name=object_name, review_status="approved").count()
    docs_rejected = UploadLog.objects.filter(object_name=object_name, review_status="rejected").count()

    expiry_active  = ExpiryItem.objects.filter(object_name=object_name, status="active")
    expiry_overdue = sum(1 for e in expiry_active if e.expires_at < today)

    open_problems = Problem.objects.filter(status="open").count()

    fin_docs = FinanceDoc.objects.filter(object_name=object_name).order_by("-id")[:10]

    last_report = Report.objects.filter(object_name=object_name).order_by("-id").first()

    recent_uploads = UploadLog.objects.filter(object_name=object_name).order_by("-id")[:10]

    # NAS folder listing
    try:
        nas_items = _nas().list_folder(f"/{object_name}")
    except Exception:
        nas_items = []

    context = {
        "object_name": object_name,
        "docs_total": docs_total,
        "docs_pending": docs_pending,
        "docs_approved": docs_approved,
        "docs_rejected": docs_rejected,
        "expiry_active": expiry_active.count(),
        "expiry_overdue": expiry_overdue,
        "open_problems": open_problems,
        "fin_docs": fin_docs,
        "last_report": last_report,
        "recent_uploads": recent_uploads,
        "nas_items": nas_items[:30],
    }
    return render(request, "adminpanel/object_summary.html", context)


@staff_member_required
def objects_list(request):
    """List all known objects (from NAS shares + DB)."""
    from apps.bot.bot_config import NAS_ROOT_SHARES
    from apps.bot.bot_nas import nas_list_folder
    from .models import UploadLog

    objects: dict[str, dict] = {}
    for share in NAS_ROOT_SHARES:
        for item in nas_list_folder(share):
            if item.get("isdir"):
                name = item["name"]
                objects[name] = {"name": name, "source": "nas"}

    # Also from DB
    for row in UploadLog.objects.values("object_name").distinct():
        name = row["object_name"]
        if name and name not in objects:
            objects[name] = {"name": name, "source": "db"}

    return render(request, "adminpanel/objects_list.html", {
        "objects": sorted(objects.values(), key=lambda x: x["name"])
    })


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 14: PDF Reports
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
@require_GET
def pdf_dashboard(request):
    """GET /pdf/dashboard/ → Management summary PDF."""
    from .models import UploadLog, ExpiryItem, FinanceDoc, Problem, Document
    from django.db.models import Count
    from datetime import date

    today = date.today().isoformat()

    expiry_rows = list(ExpiryItem.objects.filter(status="active"))
    expiry_overdue = sum(1 for e in expiry_rows if e.expires_at < today)
    expiry_soon    = sum(1 for e in expiry_rows
                         if 0 <= (date.fromisoformat(e.expires_at) - date.today()).days <= 7)
    try:
        dupes = (Document.objects.exclude(file_hash__isnull=True).exclude(file_hash="")
                 .values("file_hash").annotate(cnt=Count("id")).filter(cnt__gt=1).count())
    except Exception:
        dupes = 0

    top_objects = (UploadLog.objects.exclude(object_name="")
                   .values("object_name").annotate(cnt=Count("id"))
                   .order_by("-cnt")[:8])

    stats = {
        "total_docs":        UploadLog.objects.count(),
        "pending_docs":      UploadLog.objects.filter(review_status="pending").count(),
        "approved":          UploadLog.objects.filter(review_status="approved").count(),
        "rejected":          UploadLog.objects.filter(review_status="rejected").count(),
        "today_uploads":     UploadLog.objects.filter(uploaded_at__startswith=today).count(),
        "expiry_active":     len(expiry_rows),
        "expiry_overdue":    expiry_overdue,
        "expiry_soon":       expiry_soon,
        "fin_total":         FinanceDoc.objects.count(),
        "fin_draft":         FinanceDoc.objects.filter(status="черновик").count(),
        "fin_review":        FinanceDoc.objects.filter(status="на_проверке").count(),
        "fin_approved":      FinanceDoc.objects.filter(status="утверждён").count(),
        "fin_paid":          FinanceDoc.objects.filter(status="оплачен").count(),
        "open_problems":     Problem.objects.filter(status="open").count(),
        "registry_total":    Document.objects.count(),
        "registry_pending":  Document.objects.filter(status="pending").count(),
        "registry_approved": Document.objects.filter(status="approved").count(),
        "registry_dupes":    dupes,
        "top_objects":       list(top_objects),
        "recent_uploads":    list(UploadLog.objects.order_by("-id")[:20]),
    }

    try:
        from core.services.pdf_report import build_dashboard_pdf
        pdf_bytes = build_dashboard_pdf(stats)
    except Exception as exc:
        logger.error("PDF dashboard error: %s", exc)
        return HttpResponse(f"Ошибка генерации PDF: {exc}", status=500)

    from datetime import date as _date
    fname = f"dashboard_{_date.today().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response


@staff_member_required
@require_GET
def pdf_object(request, object_name: str):
    """GET /pdf/object/<object_name>/ → Per-object PDF report."""
    from .models import UploadLog, ExpiryItem, FinanceDoc, Problem
    from datetime import date

    today = date.today().isoformat()
    uploads  = list(UploadLog.objects.filter(object_name=object_name).order_by("-id")[:100])
    expiry   = list(ExpiryItem.objects.filter(object_name=object_name))
    finance  = list(FinanceDoc.objects.filter(object_name=object_name).order_by("-id")[:50])
    problems = list(Problem.objects.filter(object_name=object_name, status="open"))

    expiry_overdue = sum(1 for e in expiry if e.status == "active" and e.expires_at < today)

    data = {
        "uploads":       uploads,
        "expiry_items":  expiry,
        "finance_docs":  finance,
        "problems":      problems,
        "stats": {
            "total_docs":     len(uploads),
            "approved":       sum(1 for u in uploads if u.review_status == "approved"),
            "expiry_total":   len(expiry),
            "expiry_overdue": expiry_overdue,
            "problems_open":  len(problems),
        },
    }

    try:
        from core.services.pdf_report import build_object_pdf
        pdf_bytes = build_object_pdf(object_name, data)
    except Exception as exc:
        logger.error("PDF object error: %s", exc)
        return HttpResponse(f"Ошибка генерации PDF: {exc}", status=500)

    safe_name = object_name.replace(" ", "_").replace("/", "-")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="object_{safe_name}.pdf"'
    return response


@staff_member_required
@require_GET
def pdf_registry(request):
    """GET /pdf/registry/ → Full document registry PDF."""
    from .models import Document

    obj_filter = request.GET.get("object", "")
    qs = Document.objects.all().order_by("object_name", "-id")
    if obj_filter:
        qs = qs.filter(object_name=obj_filter)

    try:
        from core.services.pdf_report import build_registry_pdf
        pdf_bytes = build_registry_pdf(list(qs[:500]))
    except Exception as exc:
        logger.error("PDF registry error: %s", exc)
        return HttpResponse(f"Ошибка генерации PDF: {exc}", status=500)

    from datetime import date as _date
    fname = f"registry_{_date.today().strftime('%Y%m%d')}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 13.2 — Quality dashboard
# GET /quality/ → страница с 4 блоками контроля качества данных
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
@require_GET
def quality_dashboard(request):
    from .models import UploadLog, FinanceDoc, ExpiryItem, Problem, Document
    from django.db.models import Count, Q
    from datetime import date

    today = date.today().isoformat()

    # ── 1. Документы без объекта ──
    uploads_no_object = (
        UploadLog.objects
        .filter(Q(object_name="") | Q(object_name__isnull=True))
        .order_by("-id")[:50]
    )

    # ── 2. Финдоки без суммы или контрагента ──
    finance_incomplete = (
        FinanceDoc.objects
        .filter(
            Q(amount__isnull=True) | Q(amount=0) |
            Q(counterparty="") | Q(counterparty__isnull=True)
        )
        .order_by("-id")[:50]
    )

    # ── 3. Сроки без документа-основания (doc_path пустой) ──
    expiry_no_doc = (
        ExpiryItem.objects
        .filter(status="active")
        .filter(Q(doc_path="") | Q(doc_path__isnull=True))
        .order_by("expires_at")[:50]
    )

    # ── 4. Топ-10 объектов по открытым проблемам ──
    top_problems_objects = (
        Problem.objects
        .filter(status="open")
        .exclude(Q(label="") | Q(label__isnull=True))
        .values("label")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")[:10]
    )

    # ── 5. Документы-дубликаты (одинаковый hash) ──
    try:
        dupe_hashes = (
            Document.objects
            .exclude(file_hash__isnull=True)
            .exclude(file_hash="")
            .values("file_hash")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .order_by("-cnt")[:20]
        )
        dupe_docs = []
        for dh in dupe_hashes:
            docs = Document.objects.filter(file_hash=dh["file_hash"]).order_by("id")
            dupe_docs.append({
                "hash": dh["file_hash"][:12] + "…",
                "count": dh["cnt"],
                "docs": list(docs),
            })
    except Exception:
        dupe_docs = []

    # ── Счётчики для KPI-плашек ──
    total_issues = (
        uploads_no_object.count() +
        finance_incomplete.count() +
        expiry_no_doc.count() +
        Problem.objects.filter(status="open").count()
    )

    context = {
        "uploads_no_object":   uploads_no_object,
        "finance_incomplete":  finance_incomplete,
        "expiry_no_doc":       expiry_no_doc,
        "top_problems_objects": top_problems_objects,
        "dupe_docs":           dupe_docs,
        "total_issues":        total_issues,
        "cnt_no_object":       uploads_no_object.count(),
        "cnt_no_finance":      finance_incomplete.count(),
        "cnt_no_expiry_doc":   expiry_no_doc.count(),
        "cnt_open_problems":   Problem.objects.filter(status="open").count(),
        "cnt_dupes":           len(dupe_docs),
    }
    return render(request, "adminpanel/quality_dashboard.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 11 — Document Card
# GET /doc/<doc_id>/ → карточка документа со всеми связанными сущностями
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
@require_GET
def document_card(request, doc_id: int):
    from .models import Document, UploadLog, FinanceDoc, ExpiryItem, DocLink, AuditLog, OcrResult
    from django.db.models import Q

    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        raise Http404(f"Документ #{doc_id} не найден")

    # Загрузка по doc_id или по nas_path
    uploads = UploadLog.objects.filter(
        Q(doc_id=doc_id) | Q(nas_path=doc.nas_path)
    ).order_by("-id")

    # Финдоки по doc_id или по nas_path
    finance = FinanceDoc.objects.filter(
        Q(doc_id=doc_id) | Q(nas_path=doc.nas_path)
    ).order_by("-id")

    # Сроки по doc_path (nas_path документа)
    expiry = ExpiryItem.objects.filter(
        Q(doc_path=doc.nas_path)
    ).order_by("expires_at")

    # doc_links — ищем со стороны doc_id
    links_from = DocLink.objects.filter(from_type="document", from_id=doc_id)
    links_to   = DocLink.objects.filter(to_type="document", to_id=doc_id)

    # upload_id-ы из uploads для поиска links по upload
    upload_ids = list(uploads.values_list("id", flat=True))
    links_upload = DocLink.objects.filter(
        Q(from_type="upload", from_id__in=upload_ids) |
        Q(to_type="upload",   to_id__in=upload_ids)
    )

    # OCR результаты
    ocr_results = OcrResult.objects.filter(
        Q(doc_id=doc_id) | Q(upload_id__in=upload_ids)
    ).order_by("-id")

    # Аудит
    audit = AuditLog.objects.filter(
        Q(entity_type="document", entity_id=doc_id) |
        Q(entity_type="upload", entity_id__in=upload_ids)
    ).order_by("-id")[:30]

    # Дубликаты по хэшу
    duplicates = []
    if doc.file_hash:
        duplicates = list(
            Document.objects.filter(file_hash=doc.file_hash)
            .exclude(pk=doc_id)
            .order_by("id")
        )

    context = {
        "doc":          doc,
        "uploads":      uploads,
        "finance":      finance,
        "expiry":       expiry,
        "links_from":   links_from,
        "links_to":     links_to,
        "links_upload": links_upload,
        "ocr_results":  ocr_results,
        "audit":        audit,
        "duplicates":   duplicates,
    }
    return render(request, "adminpanel/document_card.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 13.1 — Reject with reason (AJAX endpoint)
# POST /reject-with-reason/  body: {ids: [1,2,3], reason: "..."}
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
@csrf_exempt
def reject_with_reason(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST only"}, status=405)

    try:
        data   = json.loads(request.body)
        ids    = [int(i) for i in data.get("ids", [])]
        reason = data.get("reason", "").strip()
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    if not ids:
        return JsonResponse({"ok": False, "error": "No ids provided"}, status=400)
    if not reason:
        return JsonResponse({"ok": False, "error": "Reason required"}, status=400)

    import apps.bot.bot_db as db
    from core.services.approvals import reject_doc
    from core.services.notify import notify_doc_rejected

    reviewer = request.user.get_full_name() or request.user.username
    ok_count = err_count = 0

    for upload_id in ids:
        try:
            result = reject_doc(
                db, _nas(), upload_id,
                request.user.id or 0,
                reason,
            )
            if result.get("ok"):
                ok_count += 1
                try:
                    row = db.get_upload(upload_id)
                    if row and row.get("telegram_id"):
                        notify_doc_rejected(
                            telegram_id=int(row["telegram_id"]),
                            filename=row.get("filename", f"#{upload_id}"),
                            doc_id=upload_id,
                            reviewer=reviewer,
                            reason=reason,
                        )
                except Exception:
                    pass
            else:
                err_count += 1
        except Exception as exc:
            logger.error("reject_with_reason id=%s: %s", upload_id, exc)
            err_count += 1

    return JsonResponse({
        "ok": True,
        "rejected": ok_count,
        "errors":   err_count,
    })
