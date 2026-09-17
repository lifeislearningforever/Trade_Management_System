"""
Custom template filters and tags for the core app.
"""

from django import template
from django.http import QueryDict

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
# querystring — application-level fix for list-page sort/filter/pagination
# ============================================================================
# Every list page (mascode, calendar, currency, party, ...) needs to preserve
# search/filter/sort state across pagination links and column-sort links.
# Building that query string by hand in each template — e.g.
#   ?page={{ n }}{% if search %}&search={{ search }}{% endif %}...
# — was error-prone (values weren't urlencoded, so filter values containing
# '&' or spaces silently truncated the query string and dropped sort/page
# state) and had to be repeated on every <a> tag on every list page.
#
# This tag replaces all of that: it starts from request.GET, applies the
# given overrides (a value of '' or None removes the key), and returns a
# single properly-encoded query string.
#
# Usage in any list template (no view changes needed — reads request.GET):
#
#   {% load core_filters %}
#
#   <a href="?{% querystring page=1 %}">First</a>
#   <a href="?{% querystring page=mascodes.next_page_number %}">Next</a>
#   <a href="?{% querystring sort='mas_code' order=toggle_order %}">MAS Code</a>
#   <a href="?{% querystring export='csv' %}">Download CSV</a>
#
# Any key not passed as an override is carried over unchanged from the
# current request (e.g. search, industry_group, status, country, ...) —
# so pages don't need to enumerate every filter field they support.
@register.simple_tag(takes_context=True)
def querystring(context, **overrides):
    """
    Build a URL query string from the current request.GET, applying overrides.

    Pass a keyword arg with value '' or None to remove that key entirely
    (e.g. querystring page=None when changing the sort so pagination
    resets to page 1).
    """
    request = context.get('request')
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)

    for key, value in overrides.items():
        if value is None or value == '':
            query.pop(key, None)
        else:
            query[key] = value

    return query.urlencode()


@register.simple_tag(takes_context=True)
def sort_querystring(context, field, sort_param='sort', order_param='order'):
    """
    Build the query string for a sortable column header link.

    Toggles order (asc <-> desc) if the column is already the active sort,
    otherwise starts at 'asc'. Always resets 'page' to 1 since the result
    set order changed. All other current filters (search, industry_group,
    country, status, ...) are preserved automatically from request.GET.

    Usage:
        <a href="?{% sort_querystring 'mas_code' %}">MAS Code</a>
        <a href="?{% sort_querystring 'calendar_label' %}">Calendar</a>
    """
    request = context.get('request')
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)

    current_sort = query.get(sort_param, '')
    current_order = query.get(order_param, 'asc')
    next_order = 'desc' if (current_sort == field and current_order == 'asc') else 'asc'

    query[sort_param] = field
    query[order_param] = next_order
    query.pop('page', None)

    return query.urlencode()


@register.simple_tag(takes_context=True)
def page_querystring(context, page_number):
    """
    Build the query string for a pagination link, preserving every current
    filter/sort param from request.GET and overriding only 'page'.

    Usage:
        <a href="?{% page_querystring 1 %}">First</a>
        <a href="?{% page_querystring mascodes.next_page_number %}">Next</a>
    """
    request = context.get('request')
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)
    query['page'] = page_number
    return query.urlencode()


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
#
# Supported modules and the flags each returns:
#
#   "trade"    → can_edit, can_cancel, can_restore,
#                can_validate, can_settle,
#                can_approve_cancellation, can_reject_cancellation
#   "security" → can_edit, can_validate
#   "party"    → can_edit, can_delete
#   "corp_action" → can_edit, can_delete, can_validate
#   "portfolio" → can_edit, can_cancel, can_restore,
#                 can_validate, can_settle
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
        is_deleted = str(_get_field(record, 'is_deleted')).lower() in ('true', '1')
        pending_cancel = is_cis and status == 'MODIFIED' and is_deleted
        # Four-eyes: hide the checker action from the maker who created/
        # requested it, mirroring the backend guards in trade_validate() and
        # trade_approve_cancellation()/trade_reject_cancellation() in
        # trade/views.py. Without this, this tag (which is what
        # trade_detail.html/trade_list.html actually render from, not the
        # view's can_validate/can_approve_cancellation context) let the maker
        # see the Validate/Approve/Reject buttons and only find out they're
        # blocked after submitting.
        current_user = request.session.get('user_login', '')
        created_by = _get_field(record, 'created_by')
        cancelled_by = _get_field(record, 'cancelled_by')
        is_own_trade = bool(created_by) and created_by == current_user
        is_own_cancellation = bool(cancelled_by) and cancelled_by == current_user
        return {
            'can_edit':                   has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED'),
            'can_cancel':                 has_edit    and is_cis and status != 'CANCELLED' and not is_deleted,
            'can_restore':                has_edit    and is_cis and (status == 'CANCELLED' or is_deleted),
            'can_validate':               has_approve and is_cis and status in ('INITIAL', 'MODIFIED') and not is_deleted and not is_own_trade,
            'can_settle':                 has_approve and is_cis and status == 'VALIDATED',
            'can_approve_cancellation':   has_approve and pending_cancel and not is_own_cancellation,
            'can_reject_cancellation':    has_approve and pending_cancel and not is_own_cancellation,
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
