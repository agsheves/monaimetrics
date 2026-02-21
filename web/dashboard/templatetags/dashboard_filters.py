from django import template

register = template.Library()


@register.filter
def as_pct(value):
    try:
        return f"{float(value) * 100:.0f}"
    except (ValueError, TypeError):
        return value


@register.filter
def as_pct1(value):
    try:
        return f"{float(value) * 100:.1f}"
    except (ValueError, TypeError):
        return value
