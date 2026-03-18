"""
Sprint 14: PDF report generation using ReportLab.

Provides:
  - build_dashboard_pdf(stats)     → bytes  (management summary)
  - build_object_pdf(object_name, data) → bytes  (per-object report)
  - build_registry_pdf(documents)  → bytes  (document registry table)
"""

import io
import os
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger("core.pdf_report")

# ── Brand colours ──────────────────────────────────────────────────────────────
COLOR_SLATE  = (0.239, 0.318, 0.400)   # #3D5166
COLOR_YELLOW = (1.000, 0.800, 0.114)   # #FFCC1D
COLOR_WHITE  = (1.000, 1.000, 1.000)
COLOR_LIGHT  = (0.941, 0.945, 0.961)   # #F0F2F5
COLOR_GREEN  = (0.153, 0.682, 0.376)
COLOR_RED    = (0.906, 0.298, 0.235)
COLOR_ORANGE = (0.902, 0.494, 0.133)
COLOR_GRAY   = (0.596, 0.620, 0.643)

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.jpg")

# ── Page setup ─────────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

PAGE_W, PAGE_H = A4


def _rl_color(r, g, b):
    return colors.Color(r, g, b)


BRAND_SLATE  = _rl_color(*COLOR_SLATE)
BRAND_YELLOW = _rl_color(*COLOR_YELLOW)
BRAND_WHITE  = _rl_color(*COLOR_WHITE)
BRAND_LIGHT  = _rl_color(*COLOR_LIGHT)
BRAND_GREEN  = _rl_color(*COLOR_GREEN)
BRAND_RED    = _rl_color(*COLOR_RED)
BRAND_ORANGE = _rl_color(*COLOR_ORANGE)
BRAND_GRAY   = _rl_color(*COLOR_GRAY)


# ── Styles ─────────────────────────────────────────────────────────────────────

def _make_styles():
    styles = getSampleStyleSheet()

    def _add(name, **kwargs):
        if name not in styles:
            styles.add(ParagraphStyle(name=name, **kwargs))
        return styles[name]

    h1 = _add("BrandH1",
        fontSize=20, leading=24, textColor=BRAND_SLATE,
        spaceAfter=4, spaceBefore=0, fontName="Helvetica-Bold",
    )
    h2 = _add("BrandH2",
        fontSize=14, leading=18, textColor=BRAND_SLATE,
        spaceAfter=4, spaceBefore=10, fontName="Helvetica-Bold",
    )
    h3 = _add("BrandH3",
        fontSize=11, leading=14, textColor=BRAND_SLATE,
        spaceAfter=2, spaceBefore=6, fontName="Helvetica-Bold",
    )
    body = _add("BrandBody",
        fontSize=9, leading=13, textColor=BRAND_SLATE,
        fontName="Helvetica",
    )
    small = _add("BrandSmall",
        fontSize=8, leading=11, textColor=BRAND_GRAY,
        fontName="Helvetica",
    )
    label = _add("BrandLabel",
        fontSize=8, leading=10, textColor=BRAND_GRAY,
        fontName="Helvetica", spaceAfter=1,
    )
    value = _add("BrandValue",
        fontSize=22, leading=26, textColor=BRAND_SLATE,
        fontName="Helvetica-Bold", spaceBefore=0,
    )
    center = _add("BrandCenter",
        fontSize=9, leading=13, textColor=BRAND_SLATE,
        fontName="Helvetica", alignment=TA_CENTER,
    )
    footer = _add("BrandFooter",
        fontSize=7.5, leading=10, textColor=BRAND_GRAY,
        fontName="Helvetica", alignment=TA_CENTER,
    )
    return styles


STYLES = _make_styles()


# ── Header / Footer callbacks ──────────────────────────────────────────────────

class _BrandCanvas:
    """Mixin to draw branded header/footer on every page."""

    def __init__(self, *args, report_title="Отчёт", **kwargs):
        from reportlab.pdfgen.canvas import Canvas
        self._report_title = report_title
        super().__init__(*args, **kwargs)

    def showPage(self):
        self._draw_brand()
        super().showPage()

    def save(self):
        self._draw_brand()
        super().save()

    def _draw_brand(self):
        c = self
        # ── Top bar ──
        c.setFillColor(BRAND_SLATE)
        c.rect(0, PAGE_H - 2.0 * cm, PAGE_W, 2.0 * cm, fill=1, stroke=0)

        # Logo
        if os.path.exists(LOGO_PATH):
            try:
                c.drawImage(LOGO_PATH,
                    0.6 * cm, PAGE_H - 1.85 * cm,
                    width=1.4 * cm, height=1.4 * cm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                pass

        # Company name
        c.setFillColor(BRAND_YELLOW)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2.4 * cm, PAGE_H - 0.85 * cm, "ДнепрНАС")

        # Report title
        c.setFillColor(BRAND_WHITE)
        c.setFont("Helvetica", 9)
        c.drawString(2.4 * cm, PAGE_H - 1.5 * cm, self._report_title)

        # Date top right
        c.setFillColor(BRAND_WHITE)
        c.setFont("Helvetica", 8)
        date_str = datetime.now().strftime("%d.%m.%Y")
        c.drawRightString(PAGE_W - 0.8 * cm, PAGE_H - 1.1 * cm, date_str)

        # ── Footer ──
        c.setFillColor(BRAND_LIGHT)
        c.rect(0, 0, PAGE_W, 1.0 * cm, fill=1, stroke=0)
        c.setFillColor(BRAND_GRAY)
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(
            PAGE_W / 2, 0.35 * cm,
            "Строительная компания Днепр — DMS-NAS — Система управления документами"
        )
        c.setFont("Helvetica", 7.5)
        c.drawRightString(PAGE_W - 0.8 * cm, 0.35 * cm, f"Стр. {self._pageNumber}")


def _make_canvas_cls(title: str):
    """Create a canvas class with the given report title."""
    import reportlab.pdfgen.canvas as _c

    class BrandedCanvas(_BrandCanvas, _c.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, report_title=title, **kwargs)

    return BrandedCanvas


# ── Utility builders ───────────────────────────────────────────────────────────

def _section_title(text: str):
    return [
        Spacer(1, 0.3 * cm),
        HRFlowable(width="100%", thickness=2, color=BRAND_YELLOW, spaceAfter=4),
        Paragraph(text, STYLES["BrandH2"]),
    ]


def _kpi_table(items: list) -> Table:
    """
    items: list of (label, value, color) tuples.
    Renders a row of KPI boxes.
    """
    col_w = (PAGE_W - 2.4 * cm) / max(len(items), 1)
    data = [[
        Table(
            [[Paragraph(str(val), STYLES["BrandValue"])],
             [Paragraph(lbl,      STYLES["BrandLabel"])]],
            colWidths=[col_w - 0.4 * cm],
            style=TableStyle([
                ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND",  (0, 0), (-1, -1), BRAND_WHITE),
                ("ROUNDEDCORNERS", [6]),
                ("BOX",         (0, 0), (-1, -1), 0.5, _rl_color(0.85, 0.87, 0.90)),
                ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING",   (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
                ("LINEBELOW",    (0, 0), (-1, 0), 3, color),
            ]),
        )
        for lbl, val, color in items
    ]]
    t = Table(data, colWidths=[col_w] * len(items))
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return t


def _data_table(headers: list, rows: list, col_widths: list = None) -> Table:
    """Build a styled data table."""
    usable_w = PAGE_W - 2.4 * cm
    if col_widths is None:
        col_widths = [usable_w / len(headers)] * len(headers)

    header_row = [Paragraph(f"<b>{h}</b>", STYLES["BrandSmall"]) for h in headers]
    data_rows  = []
    for i, row in enumerate(rows):
        data_rows.append([
            Paragraph(str(cell) if cell is not None else "—", STYLES["BrandSmall"])
            for cell in row
        ])

    table_data = [header_row] + data_rows

    ts = TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0),  BRAND_SLATE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  BRAND_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  8),
        ("ALIGN",        (0, 0), (-1, 0),  "CENTER"),
        ("TOPPADDING",   (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  6),
        # Data rows
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",         (0, 0), (-1, -1), 0.3, _rl_color(0.85, 0.87, 0.90)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRAND_WHITE, BRAND_LIGHT]),
    ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(ts)
    return t


# ── Public API ─────────────────────────────────────────────────────────────────

def build_dashboard_pdf(stats: dict) -> bytes:
    """
    Generate management dashboard PDF.
    stats keys: total_docs, pending_docs, approved, rejected, today_uploads,
                expiry_active, expiry_overdue, expiry_soon,
                fin_total, fin_draft, fin_review, fin_approved, fin_paid,
                open_problems, registry_total, registry_dupes,
                recent_uploads (list of dicts), top_objects (list of dicts)
    """
    buf = io.BytesIO()
    title = "Управленческий дашборд"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=2.4 * cm, bottomMargin=1.4 * cm,
        title=title, author="DMS-NAS",
    )

    story = []

    # ── Title block ──
    today_fmt = datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(title, STYLES["BrandH1"]))
    story.append(Paragraph(
        f"Строительная компания Днепр  |  Сформирован: {today_fmt}",
        STYLES["BrandSmall"],
    ))
    story.append(Spacer(1, 0.4 * cm))

    # ── Документы ──
    story += _section_title("📄 Документы")
    story.append(_kpi_table([
        ("Всего",       stats.get("total_docs", 0),    BRAND_SLATE),
        ("На проверке", stats.get("pending_docs", 0),  BRAND_ORANGE),
        ("Утверждено",  stats.get("approved", 0),      BRAND_GREEN),
        ("Отклонено",   stats.get("rejected", 0),      BRAND_RED),
        ("Сегодня",     stats.get("today_uploads", 0), BRAND_YELLOW),
    ]))

    # ── Реестр ──
    story += _section_title("📋 Реестр документов")
    story.append(_kpi_table([
        ("В реестре",   stats.get("registry_total", 0),   BRAND_SLATE),
        ("На проверке", stats.get("registry_pending", 0), BRAND_ORANGE),
        ("Утверждено",  stats.get("registry_approved", 0),BRAND_GREEN),
        ("Дубликатов",  stats.get("registry_dupes", 0),   BRAND_RED if stats.get("registry_dupes") else BRAND_GREEN),
    ]))

    # ── Сроки и проблемы ──
    story += _section_title("⏰ Сроки и проблемы")
    story.append(_kpi_table([
        ("Активных сроков",   stats.get("expiry_active", 0),  BRAND_SLATE),
        ("Истекает (7 дней)", stats.get("expiry_soon", 0),    BRAND_ORANGE),
        ("Просрочено",        stats.get("expiry_overdue", 0), BRAND_RED),
        ("Открытых проблем",  stats.get("open_problems", 0),  BRAND_RED if stats.get("open_problems") else BRAND_GREEN),
    ]))

    # ── Финансы ──
    story += _section_title("💰 Финансовые документы")
    story.append(_kpi_table([
        ("Всего",       stats.get("fin_total", 0),    BRAND_SLATE),
        ("Черновики",   stats.get("fin_draft", 0),    BRAND_GRAY),
        ("На проверке", stats.get("fin_review", 0),   BRAND_ORANGE),
        ("Утверждено",  stats.get("fin_approved", 0), BRAND_GREEN),
        ("Оплачено",    stats.get("fin_paid", 0),     BRAND_GREEN),
    ]))

    # ── Топ объектов ──
    top_objects = stats.get("top_objects", [])
    if top_objects:
        story += _section_title("🏗️ Топ активных объектов")
        rows = [[obj.get("object_name", "—"), str(obj.get("cnt", 0))]
                for obj in top_objects]
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Объект", "Документов"],
            rows,
            col_widths=[usable * 0.8, usable * 0.2],
        ))

    # ── Последние 20 загрузок ──
    recent = stats.get("recent_uploads", [])
    if recent:
        story += _section_title("📤 Последние загрузки")
        rows = []
        for d in recent[:20]:
            status = getattr(d, "review_status", None) or (d.get("review_status") if isinstance(d, dict) else "—")
            fname  = getattr(d, "filename",      None) or (d.get("filename")      if isinstance(d, dict) else "—")
            obj_n  = getattr(d, "object_name",   None) or (d.get("object_name")   if isinstance(d, dict) else "—")
            doc_t  = getattr(d, "doc_type",      None) or (d.get("doc_type")      if isinstance(d, dict) else "—")
            upl_at = getattr(d, "uploaded_at",   None) or (d.get("uploaded_at")   if isinstance(d, dict) else "—")
            rows.append([
                str(fname)[:40],
                str(obj_n)[:20],
                str(doc_t)[:18],
                str(status),
                str(upl_at)[:16] if upl_at else "—",
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Файл", "Объект", "Тип", "Статус", "Дата"],
            rows,
            col_widths=[
                usable * 0.35, usable * 0.20,
                usable * 0.18, usable * 0.12, usable * 0.15,
            ],
        ))

    doc.build(story, canvasmaker=_make_canvas_cls(title))
    return buf.getvalue()


def build_object_pdf(object_name: str, data: dict) -> bytes:
    """
    Per-object report.
    data keys: uploads (list), expiry_items (list), finance_docs (list),
               problems (list), stats (dict)
    """
    buf = io.BytesIO()
    title = f"Отчёт по объекту: {object_name}"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=2.4 * cm, bottomMargin=1.4 * cm,
        title=title, author="DMS-NAS",
    )
    story = []

    today_fmt = datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f"Объект: {object_name}", STYLES["BrandH1"]))
    story.append(Paragraph(f"Сформирован: {today_fmt}", STYLES["BrandSmall"]))
    story.append(Spacer(1, 0.4 * cm))

    stats = data.get("stats", {})
    story += _section_title("📊 Сводка")
    story.append(_kpi_table([
        ("Документов",  stats.get("total_docs", 0),  BRAND_SLATE),
        ("Утверждено",  stats.get("approved", 0),    BRAND_GREEN),
        ("Сроков",      stats.get("expiry_total", 0),BRAND_ORANGE),
        ("Просрочено",  stats.get("expiry_overdue", 0), BRAND_RED),
        ("Проблем",     stats.get("problems_open", 0),  BRAND_RED if stats.get("problems_open") else BRAND_GREEN),
    ]))

    # Uploads
    uploads = data.get("uploads", [])
    if uploads:
        story += _section_title("📄 Документы объекта")
        rows = []
        for d in uploads[:50]:
            def _g(d, attr, key):
                return getattr(d, attr, None) or (d.get(key) if isinstance(d, dict) else "—") or "—"
            rows.append([
                str(_g(d, "filename", "filename"))[:38],
                str(_g(d, "doc_type", "doc_type"))[:18],
                str(_g(d, "review_status", "review_status")),
                str(_g(d, "uploaded_at", "uploaded_at"))[:16],
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Файл", "Тип", "Статус", "Дата"],
            rows,
            col_widths=[usable * 0.45, usable * 0.22, usable * 0.13, usable * 0.20],
        ))

    # Expiry
    expiry = data.get("expiry_items", [])
    if expiry:
        story += _section_title("⏰ Сроки документов")
        rows = []
        today_s = date.today().isoformat()
        for e in expiry:
            exp_at = getattr(e, "expires_at", None) or (e.get("expires_at") if isinstance(e, dict) else "—") or "—"
            overdue = "🔴 Просрочено" if str(exp_at) < today_s else ""
            rows.append([
                str(getattr(e, "doc_type", None) or (e.get("doc_type") if isinstance(e, dict) else "—") or "—")[:30],
                str(exp_at),
                str(getattr(e, "status", None)  or (e.get("status")   if isinstance(e, dict) else "—") or "—"),
                overdue,
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Документ", "Срок", "Статус", ""],
            rows,
            col_widths=[usable * 0.45, usable * 0.20, usable * 0.17, usable * 0.18],
        ))

    # Finance
    fin = data.get("finance_docs", [])
    if fin:
        story += _section_title("💰 Финансовые документы")
        rows = []
        for f in fin[:30]:
            def _gf(f, attr, key):
                return getattr(f, attr, None) or (f.get(key) if isinstance(f, dict) else "—") or "—"
            amt = _gf(f, "amount", "amount")
            amt_str = f"{float(amt):,.2f}" if amt and str(amt).replace(".", "").isdigit() else str(amt)
            rows.append([
                str(_gf(f, "counterparty", "counterparty"))[:28],
                amt_str,
                str(_gf(f, "status", "status")),
                str(_gf(f, "created_at", "created_at"))[:16],
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Контрагент", "Сумма", "Статус", "Дата"],
            rows,
            col_widths=[usable * 0.38, usable * 0.22, usable * 0.18, usable * 0.22],
        ))

    # Problems
    problems = data.get("problems", [])
    if problems:
        story += _section_title("⚠️ Проблемы")
        rows = []
        for p in problems:
            def _gp(p, attr, key):
                return getattr(p, attr, None) or (p.get(key) if isinstance(p, dict) else "—") or "—"
            rows.append([
                str(_gp(p, "label", "label"))[:25],
                str(_gp(p, "description", "description"))[:50],
                str(_gp(p, "status", "status")),
                str(_gp(p, "created_at", "created_at"))[:16],
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["Метка", "Описание", "Статус", "Дата"],
            rows,
            col_widths=[usable * 0.20, usable * 0.45, usable * 0.13, usable * 0.22],
        ))

    doc.build(story, canvasmaker=_make_canvas_cls(title))
    return buf.getvalue()


def build_registry_pdf(documents: list) -> bytes:
    """Generate document registry PDF (all documents table)."""
    buf = io.BytesIO()
    title = f"Реестр документов — {datetime.now().strftime('%d.%m.%Y')}"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=2.4 * cm, bottomMargin=1.4 * cm,
        title=title, author="DMS-NAS",
    )
    story = []

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Реестр документов", STYLES["BrandH1"]))
    story.append(Paragraph(
        f"Строительная компания Днепр  |  {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  "
        f"Документов: {len(documents)}",
        STYLES["BrandSmall"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    if not documents:
        story.append(Paragraph("Реестр пуст", STYLES["BrandBody"]))
    else:
        rows = []
        cat_labels = {
            "build": "Строительство", "finance": "Финансы",
            "safety": "ТБ/ОТ", "photo": "Фото", "other": "Прочее",
        }
        for d in documents:
            def _gd(d, attr, key):
                return getattr(d, attr, None) or (d.get(key) if isinstance(d, dict) else "—") or "—"
            cat = str(_gd(d, "category", "category"))
            size = getattr(d, "file_size", None) or (d.get("file_size") if isinstance(d, dict) else None)
            size_str = f"{int(size)//1024} KB" if size else "—"
            rows.append([
                str(getattr(d, "id", "") or d.get("id", "")),
                str(_gd(d, "object_name", "object_name"))[:20],
                cat_labels.get(cat, cat)[:12],
                str(_gd(d, "original_filename", "original_filename"))[:32],
                str(_gd(d, "status", "status")),
                size_str,
                str(_gd(d, "created_at", "created_at"))[:10],
            ])
        usable = PAGE_W - 2.4 * cm
        story.append(_data_table(
            ["#", "Объект", "Категория", "Файл", "Статус", "Размер", "Дата"],
            rows,
            col_widths=[
                usable * 0.05, usable * 0.18, usable * 0.10,
                usable * 0.35, usable * 0.10, usable * 0.08, usable * 0.14,
            ],
        ))

    doc.build(story, canvasmaker=_make_canvas_cls(title))
    return buf.getvalue()
