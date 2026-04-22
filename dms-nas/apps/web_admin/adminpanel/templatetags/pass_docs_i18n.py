import pprint as py_pprint

from django import template

from adminpanel.pass_docs_display import (
    human_package_kind,
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


@register.filter
def package_kind_ru(value) -> str:
    return human_package_kind(value)


@register.filter(name="pprint")
def pprint_filter(value) -> str:
    """Человекочитаемый вывод для служебных блоков."""
    try:
        return py_pprint.pformat(value)
    except Exception:
        return str(value)
