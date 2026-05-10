import pprint as py_pprint
from datetime import date

from django import template
from django.utils.html import format_html

from adminpanel.pass_docs_display import (
    ru_doc_status,
    ru_package_status,
    ru_parse_status,
)

register = template.Library()


@register.filter
def parse_status_ru(value) -> str:
    return ru_parse_status(value)


@register.filter
def doc_status_ru(value) -> str:
    return ru_doc_status(value)


@register.filter
def package_status_ru(value) -> str:
    return ru_package_status(value)


@register.filter(name="pprint")
def pprint_filter(value) -> str:
    """Человекочитаемый вывод для служебных блоков."""
    try:
        return py_pprint.pformat(value)
    except Exception:
        return str(value)


@register.simple_tag
def expiry_date_cell(expiry) -> str:
    """Ячейка срока действия с цветовым индикатором."""
    if not expiry:
        return format_html('<span class="pd-muted">—</span>')
    today = date.today()
    if hasattr(expiry, "date"):
        expiry = expiry.date()
    delta = (expiry - today).days
    fmt = expiry.strftime("%d.%m.%Y")
    if delta < 0:
        return format_html(
            '<span class="pd-expiry pd-expiry--expired">'
            '<i class="fas fa-exclamation-circle"></i> {}</span>', fmt
        )
    if delta < 7:
        return format_html(
            '<span class="pd-expiry pd-expiry--critical">'
            '<i class="fas fa-exclamation-triangle"></i> {}</span>', fmt
        )
    if delta < 30:
        return format_html(
            '<span class="pd-expiry pd-expiry--warn">'
            '<i class="fas fa-clock"></i> {}</span>', fmt
        )
    return format_html('<span class="pd-expiry pd-expiry--ok">{}</span>', fmt)


@register.simple_tag
def doc_status_badge(doc) -> str:
    """Единый понятный статус документа для оператора."""
    status = getattr(doc, "status", "")
    parse = getattr(doc, "parse_status", "")
    if status == "ok":
        return format_html('<span class="pd-badge pd-badge--ok">Принят</span>')
    if status == "expired":
        return format_html('<span class="pd-badge pd-badge--error">Просрочен</span>')
    if status == "rejected":
        return format_html('<span class="pd-badge pd-badge--error">Отклонён</span>')
    if parse == "error":
        return format_html('<span class="pd-badge pd-badge--warn">Требует внимания</span>')
    if parse == "pending":
        return format_html('<span class="pd-badge pd-badge--pending">Обрабатывается</span>')
    return format_html('<span class="pd-badge pd-badge--pending">На проверке</span>')
