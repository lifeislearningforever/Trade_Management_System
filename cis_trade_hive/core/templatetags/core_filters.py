"""
Custom template filters for the core app.
"""

from django import template

register = template.Library()


@register.filter(name='split')
def split(value, arg):
    """
    Split a string by the given separator.

    Usage: {{ "hello world"|split:" " }}
    Returns: ['hello', 'world']
    """
    if value is None:
        return []
    return str(value).split(arg)
