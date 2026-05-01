import pprint as py_pprint

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
