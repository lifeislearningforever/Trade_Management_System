"""
Custom template filters and tags for the core app.
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
    try:
        return getattr(dictionary, key, None)
    except (TypeError, AttributeError):
        return None


# ============================================================================
# RBAC action-permission tag
# ============================================================================
# Central place for: "can user X perform action Y on record Z?"
# Combines RBAC permission (from session) + src_system (CIS vs GMP) + status.
#
# Usage in any template (no view changes needed):
#
#   {% load core_filters %}
#
#   {% can_act trade "trade" request as actions %}
#   {% if actions.can_edit %} ... {% endif %}
#   {% if actions.can_submit %} ... {% endif %}
#
# Supported modules and the flags each returns:
#
#   "trade"    → can_edit, can_submit, can_cancel, can_reactivate,
#                can_validate, can_reject, can_settle
#   "security" → can_edit, can_validate
#   "party"    → can_edit, can_delete
#   "corp_action" → can_edit, can_delete, can_validate
#   "portfolio" → can_edit, can_submit, can_cancel, can_reactivate,
#                 can_validate, can_reject, can_settle
#
# All flags are False when:
#   - src_system != 'CIS'
#   - User lacks WRITE permission for that module
#   - Status doesn't permit the action
#
# When SKIP_PERMISSION_CHECKS=True (dev mode) only src_system and status are
# enforced (RBAC is bypassed, same as the rest of the app in dev).

_EMPTY = {}


def _get_field(record, field):
    """Get a field from a dict or object."""
    if isinstance(record, dict):
        return record.get(field, '') or ''
    return getattr(record, field, '') or ''


def _has_perm(request, perm_name, mode='WRITE'):
    """
    Check RBAC permission from session.
    Returns True unconditionally when SKIP_PERMISSION_CHECKS is enabled.
    """
    from django.conf import settings
    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return True
    perm_map = request.session.get('user_permissions', {})
    user_mode = perm_map.get(perm_name)
    if user_mode is None:
        return False
    if mode == 'READ':
        return user_mode in ('READ', 'WRITE')
    return user_mode == 'WRITE'


@register.simple_tag(takes_context=True)
def can_act(context, record, module):
    """
    Return a dict of boolean action flags for a record, based on:
      1. RBAC session permissions (from RBAC v2 login)
      2. src_system == 'CIS'  (GMP records are always read-only)
      3. Status rules per module

    Args:
        record : dict or model/wrapper object with .status, .src_system
        module : one of 'trade', 'security', 'party', 'corp_action', 'portfolio'

    Returns dict with relevant boolean flags (all False if no access).

    Usage:
        {% can_act trade "trade" as actions %}
        {% if actions.can_edit %}<a href="...">Edit</a>{% endif %}
    """
    request = context.get('request')
    if request is None:
        return _EMPTY

    src_system = _get_field(record, 'src_system')
    is_cis = src_system.upper() == 'CIS'
    status = _get_field(record, 'status')

    if module == 'trade':
        has_edit = _has_perm(request, 'trade-edit')
        has_approve = _has_perm(request, 'trade-approval')
        return {
            'can_edit':       has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'CANCELLED'),
            'can_submit':     has_edit    and is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_cancel':     has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'PENDING_VALIDATION'),
            'can_reactivate': has_edit    and is_cis and status == 'CANCELLED',
            'can_validate':   has_approve and is_cis and status == 'PENDING_VALIDATION',
            'can_reject':     has_approve and is_cis and status == 'PENDING_VALIDATION',
            'can_settle':     has_approve and is_cis and status == 'VALIDATED',
        }

    if module == 'portfolio':
        has_edit = _has_perm(request, 'portfolio-edit')
        has_approve = _has_perm(request, 'portfolio-approval')
        return {
            'can_edit':       has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'PENDING_VALIDATION', 'CANCELLED'),
            'can_submit':     has_edit    and is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_cancel':     has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'PENDING_VALIDATION'),
            'can_reactivate': has_edit    and is_cis and status == 'CANCELLED',
            'can_validate':   has_approve and is_cis and status == 'PENDING_VALIDATION',
            'can_reject':     has_approve and is_cis and status == 'PENDING_VALIDATION',
            'can_settle':     has_approve and is_cis and status == 'VALIDATED',
        }

    if module == 'security':
        has_write = _has_perm(request, 'securities-create')
        return {
            'can_edit':     has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_validate': has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
        }

    if module == 'party':
        has_write = _has_perm(request, 'parties-create')
        return {
            'can_edit':   has_write and is_cis,
            'can_delete': has_write and is_cis,
        }

    if module == 'corp_action':
        has_write = _has_perm(request, 'corp-action-create')
        return {
            'can_edit':     has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_delete':   has_write and is_cis,
            'can_validate': has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
        }

    return _EMPTY
