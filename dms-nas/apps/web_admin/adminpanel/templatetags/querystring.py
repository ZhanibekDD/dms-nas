from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def qs_replace(context, **kwargs):
    """
    Вернёт querystring с заменой/удалением ключей:
      {% qs_replace page=2 %}
      {% qs_replace q='' %}  -> удалит q
    """
    request = context.get("request")
    if request is None:
        return ""
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, "", False):
            query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else "?"
