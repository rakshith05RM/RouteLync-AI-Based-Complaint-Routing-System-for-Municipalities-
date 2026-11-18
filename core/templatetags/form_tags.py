from django import template

register = template.Library()


@register.filter
def add_class(bound_field, css):
    """Render a form field with extra CSS classes, e.g. {{ field|add_class:"form-control" }}."""
    attrs = dict(bound_field.field.widget.attrs)
    attrs["class"] = f'{attrs.get("class", "")} {css}'.strip()
    return bound_field.as_widget(attrs=attrs)
