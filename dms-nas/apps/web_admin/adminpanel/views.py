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
from datetime import datetime
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
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
def dashboard(request):
    from .models import UploadLog, ExpiryItem, FinanceDoc, Problem, Document
    from django.db.models import Count
    from datetime import date

    today = date.today().isoformat()

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
