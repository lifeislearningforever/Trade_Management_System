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


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key.

    Usage: {{ my_dict|get_item:'key_name' }}
    Returns: The value for the key, or None if not found
    """
    if dictionary is None:
        return None
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    # Try to get attribute if not a dict
    try:
        return getattr(dictionary, key, None)
    except (TypeError, AttributeError):
        return None
