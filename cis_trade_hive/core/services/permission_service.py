"""
Permission Service - Helper functions for RBAC permission checks.

This module provides convenient helper functions for checking permissions
in views, templates, and other parts of the application.

Features:
- Simple permission checks from request object
- Bulk permission checks
- Permission info utilities
- Four-eyes principle helpers

Usage:
    from core.services.permission_service import (
        has_permission,
        has_any_permission,
        has_all_permissions,
        get_user_permissions,
        can_approve_entity,
    )

    # In a view
    @require_login
    def trade_list(request):
        if has_permission(request, 'trade-create', 'WRITE'):
            context['can_create'] = True

Author: CIS Trade Hive Team
Version: 1.0
Created: 2026-04-05
"""

import logging
from typing import Optional, List, Dict, Any, Set
from functools import wraps

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# ============================================================================
# Permission Mode Constants
# ============================================================================

class PermissionMode:
    """
    Constants for permission access modes.

    Usage:
        from core.services.permission_service import PermissionMode

        if has_permission(request, 'trade-create', PermissionMode.WRITE):
            # User can create trades
    """
    READ = 'READ'
    WRITE = 'WRITE'
    WRITE = 'WRITE'  # Alias: WRITE means WRITE


# ============================================================================
# Core Permission Check Functions
# ============================================================================

def has_permission(
    request: HttpRequest,
    permission_name: str,
    required_mode: str = 'READ'
) -> bool:
    """
    Check if current user has specified permission.

    This is the primary function for permission checks. It reads the
    permission map from the user's session (populated during login).

    Args:
        request: Django HttpRequest object
        permission_name: Permission name to check (e.g., 'trade-create')
        required_mode: Required access level:
            - 'READ': User needs at least READ access
            - 'WRITE' or 'WRITE': User needs WRITE access

    Returns:
        bool: True if user has permission, False otherwise

    Access Level Rules:
        - WRITE permission satisfies both READ and WRITE requirements
        - READ permission only satisfies READ requirements

    Example:
        >>> # In a view
        >>> if has_permission(request, 'trade-create', 'WRITE'):
        ...     # Show create button
        ...     pass
        >>>
        >>> # Using constants
        >>> if has_permission(request, 'trade-list', PermissionMode.READ):
        ...     # Show trade list
        ...     pass
    """
    try:
        # Get permission map from session
        permission_map = request.session.get('user_permissions', {})

        if not permission_map:
            logger.debug(f"No permissions in session for permission check: {permission_name}")
            return False

        user_mode = permission_map.get(permission_name)

        if user_mode is None:
            logger.debug(f"Permission not found: {permission_name}")
            return False

        # Check access level
        if required_mode == 'READ':
            return user_mode in ('READ', 'WRITE')
        elif required_mode == 'WRITE':
            return user_mode == 'WRITE'

        return False

    except Exception as e:
        logger.error(f"Error checking permission '{permission_name}': {str(e)}")
        return False


def has_any_permission(
    request: HttpRequest,
    permissions: List[str],
    required_mode: str = 'READ'
) -> bool:
    """
    Check if user has ANY of the specified permissions.

    Useful for OR logic where user needs at least one permission.

    Args:
        request: Django HttpRequest object
        permissions: List of permission names to check
        required_mode: Required access level

    Returns:
        bool: True if user has at least one permission

    Example:
        >>> # User can access if they have trade OR portfolio permissions
        >>> if has_any_permission(request, ['trade-list', 'portfolio-list']):
        ...     # Show dashboard
        ...     pass
    """
    if not permissions:
        return False

    return any(
        has_permission(request, perm, required_mode)
        for perm in permissions
    )


def has_all_permissions(
    request: HttpRequest,
    permissions: List[str],
    required_mode: str = 'READ'
) -> bool:
    """
    Check if user has ALL of the specified permissions.

    Useful for AND logic where user needs all permissions.

    Args:
        request: Django HttpRequest object
        permissions: List of permission names to check
        required_mode: Required access level

    Returns:
        bool: True if user has all permissions

    Example:
        >>> # User can bulk approve only if they have both permissions
        >>> if has_all_permissions(request, ['trade-approval', 'trade-edit'], 'WRITE'):
        ...     # Show bulk approve button
        ...     pass
    """
    if not permissions:
        return True  # No permissions required

    return all(
        has_permission(request, perm, required_mode)
        for perm in permissions
    )


def get_user_permissions(request: HttpRequest) -> Dict[str, str]:
    """
    Get all permissions for current user.

    Returns the complete permission map from session.

    Args:
        request: Django HttpRequest object

    Returns:
        Dictionary mapping permission names to access modes.
        Empty dict if no permissions.

    Example:
        >>> perms = get_user_permissions(request)
        >>> for perm_name, mode in perms.items():
        ...     print(f"{perm_name}: {mode}")
    """
    return request.session.get('user_permissions', {})


def get_user_groups(request: HttpRequest) -> List[str]:
    """
    Get list of group names user belongs to.

    Args:
        request: Django HttpRequest object

    Returns:
        List of group names (e.g., ['SG-TRADER', 'CIS-OPS'])

    Example:
        >>> groups = get_user_groups(request)
        >>> if 'CIS-SYSOPS' in groups:
        ...     print("User is a sysop")
    """
    return request.session.get('user_groups', [])


def is_in_group(request: HttpRequest, group_name: str) -> bool:
    """
    Check if user is in a specific group.

    Args:
        request: Django HttpRequest object
        group_name: Group name to check

    Returns:
        bool: True if user is in the group

    Example:
        >>> if is_in_group(request, 'CIS-SYSOPS'):
        ...     print("User has admin access")
    """
    groups = get_user_groups(request)
    return group_name.upper() in [g.upper() for g in groups]


# ============================================================================
# Four-Eyes Principle Helpers
# ============================================================================

def can_approve_entity(
    request: HttpRequest,
    entity_created_by: str,
    approval_permission: str
) -> bool:
    """
    Check if user can approve an entity (Four-Eyes principle).

    The Four-Eyes principle requires that the approver is different
    from the creator. This function checks:
    1. User has approval permission
    2. User is not the creator

    Args:
        request: Django HttpRequest object
        entity_created_by: Login of user who created the entity
        approval_permission: Permission required for approval

    Returns:
        bool: True if user can approve

    Example:
        >>> trade = get_trade(trade_id)
        >>> if can_approve_entity(request, trade['created_by'], 'trade-approval'):
        ...     show_approve_button = True
    """
    # Check permission
    if not has_permission(request, approval_permission, 'WRITE'):
        return False

    # Four-eyes: Cannot approve own entity
    current_user = request.session.get('user_login', '')
    if current_user.upper() == entity_created_by.upper():
        logger.debug(f"Four-eyes violation: {current_user} cannot approve own entity")
        return False

    return True


def get_four_eyes_info(request: HttpRequest, entity_created_by: str) -> Dict[str, Any]:
    """
    Get detailed info about four-eyes approval eligibility.

    Useful for displaying information to users about why they
    can or cannot approve something.

    Args:
        request: Django HttpRequest object
        entity_created_by: Login of entity creator

    Returns:
        Dictionary with:
        - can_approve: bool
        - reason: str explaining the decision
        - is_own_entity: bool

    Example:
        >>> info = get_four_eyes_info(request, trade['created_by'])
        >>> if not info['can_approve']:
        ...     messages.warning(request, info['reason'])
    """
    current_user = request.session.get('user_login', '')
    is_own = current_user.upper() == entity_created_by.upper()

    if is_own:
        return {
            'can_approve': False,
            'reason': 'You cannot approve your own submission (Four-Eyes principle)',
            'is_own_entity': True
        }

    return {
        'can_approve': True,
        'reason': 'Eligible to approve',
        'is_own_entity': False
    }


# ============================================================================
# Permission Context Builder
# ============================================================================

def build_permission_context(
    request: HttpRequest,
    module: str
) -> Dict[str, bool]:
    """
    Build a context dictionary with all standard permissions for a module.

    Automatically generates can_list, can_view, can_create, can_edit,
    can_delete, can_approve, can_download flags for a module.

    When SKIP_PERMISSION_CHECKS is True (dev mode), all permissions return True.

    Args:
        request: Django HttpRequest object
        module: Module name (e.g., 'trade', 'portfolio', 'securities')

    Returns:
        Dictionary with boolean flags for each permission.

    Example:
        >>> # In a view
        >>> context = build_permission_context(request, 'trade')
        >>> # Returns: {
        >>> #     'can_list': True,
        >>> #     'can_view': True,
        >>> #     'can_create': False,
        >>> #     'can_edit': False,
        >>> #     'can_delete': False,
        >>> #     'can_approve': False,
        >>> #     'can_download': True,
        >>> # }
        >>> return render(request, 'trade/list.html', context)
    """
    from django.conf import settings

    # Check if permission checks should be skipped (dev mode)
    skip_checks = getattr(settings, 'SKIP_PERMISSION_CHECKS', False)

    if skip_checks:
        # In dev mode, grant all permissions
        return {
            'can_list': True,
            'can_view': True,
            'can_create': True,
            'can_edit': True,
            'can_delete': True,
            'can_approve': True,
            'can_download': True,
        }

    module_lower = module.lower()

    return {
        'can_list': has_permission(request, f'{module_lower}-list', 'READ'),
        'can_view': has_permission(request, f'{module_lower}-view', 'READ'),
        'can_create': has_permission(request, f'{module_lower}-create', 'WRITE'),
        'can_edit': has_permission(request, f'{module_lower}-edit', 'WRITE'),
        'can_delete': has_permission(request, f'{module_lower}-delete', 'WRITE'),
        'can_approve': has_permission(request, f'{module_lower}-approval', 'WRITE'),
        'can_download': has_permission(request, f'{module_lower}-download', 'READ'),
    }


def build_custom_permission_context(
    request: HttpRequest,
    permissions: Dict[str, str]
) -> Dict[str, bool]:
    """
    Build a custom permission context with specified permissions.

    When SKIP_PERMISSION_CHECKS is True (dev mode), all permissions return True.

    Args:
        request: Django HttpRequest object
        permissions: Dictionary mapping context key to permission spec.
            Format: {'context_key': 'permission-name:MODE'}

    Returns:
        Dictionary with boolean flags.

    Example:
        >>> context = build_custom_permission_context(request, {
        ...     'can_create_trade': 'trade-create:WRITE',
        ...     'can_view_audit': 'audit-logs-read:READ',
        ...     'can_manage_fx': 'fx-rates-edit:WRITE',
        ... })
    """
    from django.conf import settings

    # Check if permission checks should be skipped (dev mode)
    skip_checks = getattr(settings, 'SKIP_PERMISSION_CHECKS', False)

    if skip_checks:
        # In dev mode, grant all permissions
        return {key: True for key in permissions.keys()}

    result = {}

    for key, spec in permissions.items():
        if ':' in spec:
            perm_name, mode = spec.split(':', 1)
        else:
            perm_name, mode = spec, 'READ'

        result[key] = has_permission(request, perm_name, mode)

    return result


# ============================================================================
# Decorators
# ============================================================================

def permission_required(permission: str, mode: str = 'READ'):
    """
    Decorator to require specific permission for a view function.

    Similar to @require_permission in auth_views.py but can be used
    independently.

    Args:
        permission: Permission name required
        mode: Access mode required ('READ' or 'WRITE')

    Returns:
        Decorator function

    Example:
        >>> @permission_required('trade-create', 'WRITE')
        ... def create_trade(request):
        ...     pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            # Check login
            if not request.session.get('user_login'):
                return redirect('login')

            # Check permission
            if not has_permission(request, permission, mode):
                return HttpResponse(
                    f"Access denied: You don't have {mode} permission for {permission}",
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def any_permission_required(permissions: List[str], mode: str = 'READ'):
    """
    Decorator requiring any of the specified permissions.

    Args:
        permissions: List of permission names (any one required)
        mode: Access mode required

    Example:
        >>> @any_permission_required(['trade-list', 'portfolio-list'])
        ... def dashboard(request):
        ...     pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            if not request.session.get('user_login'):
                return redirect('login')

            if not has_any_permission(request, permissions, mode):
                perms_str = ', '.join(permissions)
                return HttpResponse(
                    f"Access denied: You need one of these permissions: {perms_str}",
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def all_permissions_required(permissions: List[str], mode: str = 'READ'):
    """
    Decorator requiring all specified permissions.

    Args:
        permissions: List of permission names (all required)
        mode: Access mode required

    Example:
        >>> @all_permissions_required(['trade-approval', 'trade-edit'], 'WRITE')
        ... def bulk_approve_trades(request):
        ...     pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            if not request.session.get('user_login'):
                return redirect('login')

            if not has_all_permissions(request, permissions, mode):
                perms_str = ', '.join(permissions)
                return HttpResponse(
                    f"Access denied: You need all of these permissions: {perms_str}",
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


# ============================================================================
# Logging and Audit Helpers
# ============================================================================

def log_permission_check(
    request: HttpRequest,
    permission: str,
    result: bool,
    context: str = ''
) -> None:
    """
    Log a permission check for debugging/auditing.

    Args:
        request: Django HttpRequest object
        permission: Permission that was checked
        result: Result of the check
        context: Additional context (e.g., 'trade creation')

    Example:
        >>> result = has_permission(request, 'trade-create', 'WRITE')
        >>> log_permission_check(request, 'trade-create', result, 'creating trade')
    """
    user = request.session.get('user_login', 'anonymous')
    status = 'GRANTED' if result else 'DENIED'

    log_msg = f"Permission check: {permission} for {user} = {status}"
    if context:
        log_msg += f" (context: {context})"

    if result:
        logger.debug(log_msg)
    else:
        logger.info(log_msg)


# ============================================================================
# Module Permission Groups
# ============================================================================

# Pre-defined permission groups for common modules
PERMISSION_GROUPS = {
    'trade': [
        'trade-list', 'trade-view', 'trade-create', 'trade-edit',
        'trade-delete', 'trade-download', 'trade-approval'
    ],
    'portfolio': [
        'portfolio-list', 'portfolio-view', 'portfolio-create', 'portfolio-edit',
        'portfolio-delete', 'portfolio-download', 'portfolio-approval'
    ],
    'position': [
        'position-list', 'position-view', 'position-create', 'position-edit',
        'position-delete', 'position-download', 'position-approval'
    ],
    'securities': [
        'securities-list', 'securities-view', 'securities-create', 'securities-edit',
        'securities-delete', 'securities-download', 'securities-approval'
    ],
    'parties': [
        'parties-list', 'parties-view', 'parties-create', 'parties-edit',
        'parties-delete', 'parties-download'
    ],
    'cash_flow': [
        'cash-flow-list', 'cash-flow-view', 'cash-flow-create', 'cash-flow-edit',
        'cash-flow-approval'
    ],
    'corp_action': [
        'corp-action-list', 'corp-action-view', 'corp-action-create', 'corp-action-edit',
        'corp-action-approval'
    ],
    'udf': [
        'udf-list', 'udf-view', 'udf-create', 'udf-edit',
        'udf-delete', 'udf-download', 'udf-approval'
    ],
    'reference_data': [
        'currencies-list', 'currencies-view',
        'countries-list', 'countries-view',
        'calendars-list', 'calendars-view', 'calendars-edit',
        'counterparties-list', 'counterparties-view',
        'counterparties-create', 'counterparties-edit'
    ],
    'market_data': [
        'equity-prices-list', 'equity-prices-view', 'equity-prices-create', 'equity-prices-edit',
        'fx-rates-list', 'fx-rates-view',
        'market-data-dashboard'
    ],
    'admin': [
        'audit-logs-read',
        'documentation-read',
        'lookup-tables-list', 'lookup-tables-edit', 'lookup-tables-download'
    ]
}


def get_module_permissions(module: str) -> List[str]:
    """
    Get list of permissions for a module.

    Args:
        module: Module name

    Returns:
        List of permission names for the module

    Example:
        >>> perms = get_module_permissions('trade')
        >>> # Returns: ['trade-list', 'trade-view', ...]
    """
    return PERMISSION_GROUPS.get(module.lower(), [])


def get_portfolio_action_permissions(request: HttpRequest, portfolio_data: Any) -> Dict[str, bool]:
    """
    Compute per-portfolio action flags combining RBAC permission + status + src_system.

    This is the single source of truth for what actions a user can take on a
    given portfolio. Both the list view (per-row icons) and the detail view
    (action buttons) must call this function — never duplicate the status/src logic
    inline in views or templates.

    Args:
        request: Django HttpRequest with session permissions
        portfolio_data: Portfolio dict (from Kudu) or PortfolioWrapper instance.
                        Must expose .status and .src_system (attribute or dict key).

    Returns:
        Dict with boolean flags:
            can_edit        — pencil icon / edit page (INITIAL, MODIFIED, PENDING_VALIDATION, CANCELLED)
            can_submit      — send for validation (INITIAL, MODIFIED)
            can_cancel      — cancel action (INITIAL, MODIFIED, PENDING_VALIDATION)
            can_reactivate  — reactivate from CANCELLED
            can_validate    — checker: approve (PENDING_VALIDATION)
            can_reject      — checker: reject  (PENDING_VALIDATION)
            can_settle      — checker: settle  (VALIDATED)

    Example:
        >>> actions = get_portfolio_action_permissions(request, portfolio_data)
        >>> # In view context: context.update(actions)
        >>> # On wrapper:      wrapper.can_edit = actions['can_edit']
    """
    from django.conf import settings

    # Dict or object access
    if hasattr(portfolio_data, 'status'):
        status = portfolio_data.status
        src_system = portfolio_data.src_system or ''
    else:
        status = portfolio_data.get('status', '')
        src_system = portfolio_data.get('src_system', '') or ''

    is_cis = src_system.upper() == 'CIS'

    # Dev bypass — grant all actions (permission check is separate concern)
    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return {
            'can_edit': is_cis,
            'can_submit': is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_cancel': is_cis and status in ('INITIAL', 'MODIFIED', 'PENDING_VALIDATION'),
            'can_reactivate': is_cis and status == 'CANCELLED',
            'can_validate': is_cis and status == 'PENDING_VALIDATION',
            'can_reject': is_cis and status == 'PENDING_VALIDATION',
            'can_settle': is_cis and status == 'VALIDATED',
        }

    has_edit = has_permission(request, 'portfolio-edit', 'WRITE')
    has_approve = has_permission(request, 'portfolio-approval', 'WRITE')

    return {
        'can_edit': has_edit and is_cis and status in (
            'INITIAL', 'MODIFIED', 'PENDING_VALIDATION', 'CANCELLED'
        ),
        'can_submit': has_edit and is_cis and status in ('INITIAL', 'MODIFIED'),
        'can_cancel': has_edit and is_cis and status in (
            'INITIAL', 'MODIFIED', 'PENDING_VALIDATION'
        ),
        'can_reactivate': has_edit and is_cis and status == 'CANCELLED',
        'can_validate': has_approve and is_cis and status == 'PENDING_VALIDATION',
        'can_reject': has_approve and is_cis and status == 'PENDING_VALIDATION',
        'can_settle': has_approve and is_cis and status == 'VALIDATED',
    }


def get_trade_action_permissions(request: HttpRequest, trade_data: Any) -> Dict[str, bool]:
    """
    Compute per-trade action flags: RBAC permission + status + src_system.

    Single source of truth for trade edit/submit/cancel/validate/settle icons.
    Use in trade_detail view (context flags) and trade_list view (annotate wrapper).

    Maker statuses (editable): INITIAL, MODIFIED, VALIDATED, SETTLED
    Checker statuses:          INITIAL, MODIFIED → validate
                               VALIDATED         → settle
    Cancel: available at all live statuses (not CANCELLED, not is_deleted)
    Restore: available on CANCELLED or is_deleted=true (pending-cancel)
    """
    from django.conf import settings

    if hasattr(trade_data, 'status'):
        status = trade_data.status
        src_system = trade_data.src_system or ''
        is_deleted = str(getattr(trade_data, 'is_deleted', False)).lower() in ('true', '1')
    else:
        status = trade_data.get('status', '')
        src_system = trade_data.get('src_system', '') or ''
        is_deleted = str(trade_data.get('is_deleted', False)).lower() in ('true', '1')

    is_cis = src_system.upper() == 'CIS'
    pending_cancel = is_cis and status == 'MODIFIED' and is_deleted

    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return {
            'can_edit':                 is_cis and status in ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED'),
            'can_cancel':               is_cis and status != 'CANCELLED' and not is_deleted,
            'can_restore':              is_cis and (status == 'CANCELLED' or is_deleted),
            'can_validate':             is_cis and status in ('INITIAL', 'MODIFIED') and not is_deleted,
            'can_settle':               is_cis and status == 'VALIDATED',
            'can_approve_cancellation': pending_cancel,
            'can_reject_cancellation':  pending_cancel,
        }

    has_edit = has_permission(request, 'trade-edit', 'WRITE')
    has_approve = has_permission(request, 'trade-approval', 'WRITE')

    return {
        'can_edit':                 has_edit    and is_cis and status in ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED'),
        'can_cancel':               has_edit    and is_cis and status != 'CANCELLED' and not is_deleted,
        'can_restore':              has_edit    and is_cis and (status == 'CANCELLED' or is_deleted),
        'can_validate':             has_approve and is_cis and status in ('INITIAL', 'MODIFIED') and not is_deleted,
        'can_settle':               has_approve and is_cis and status == 'VALIDATED',
        'can_approve_cancellation': has_approve and pending_cancel,
        'can_reject_cancellation':  has_approve and pending_cancel,
    }


def get_security_action_permissions(request: HttpRequest, security_data: Any) -> Dict[str, bool]:
    """
    Compute per-security action flags: RBAC permission + status + src_system.

    Security uses 'securities-create' permission for both create and edit
    (matches URL_PERMISSION_MAP: security:edit → securities-create WRITE).
    Approval is also 'securities-create' WRITE (security:validate).
    """
    from django.conf import settings

    if hasattr(security_data, 'status'):
        status = security_data.status
        src_system = security_data.src_system or ''
    else:
        status = security_data.get('status', '')
        src_system = security_data.get('src_system', '') or ''

    is_cis = src_system.upper() == 'CIS'

    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return {
            'can_edit': is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_validate': is_cis and status in ('INITIAL', 'MODIFIED'),
        }

    has_edit = has_permission(request, 'securities-create', 'WRITE')

    return {
        'can_edit': has_edit and is_cis and status in ('INITIAL', 'MODIFIED'),
        'can_validate': has_edit and is_cis and status in ('INITIAL', 'MODIFIED'),
    }


def get_party_action_permissions(request: HttpRequest, party_data: Any) -> Dict[str, bool]:
    """
    Compute per-party/counterparty action flags: RBAC permission + src_system.

    Parties have no status-based workflow beyond CIS vs GMP ownership.
    'parties-create' WRITE covers both edit and delete (matches URL_PERMISSION_MAP).
    """
    from django.conf import settings

    if hasattr(party_data, 'src_system'):
        src_system = party_data.src_system or ''
    else:
        src_system = party_data.get('src_system', '') or ''

    is_cis = src_system.upper() == 'CIS'

    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return {
            'can_edit': is_cis,
            'can_delete': is_cis,
        }

    has_write = has_permission(request, 'parties-create', 'WRITE')

    return {
        'can_edit': has_write and is_cis,
        'can_delete': has_write and is_cis,
    }


def get_corporate_action_action_permissions(request: HttpRequest, ca_data: Any) -> Dict[str, bool]:
    """
    Compute per-corporate-action flags: RBAC permission + src_system + status.

    'corp-action-create' WRITE covers edit, delete, validate (matches URL_PERMISSION_MAP).
    """
    from django.conf import settings

    if hasattr(ca_data, 'status'):
        status = ca_data.status
        src_system = ca_data.src_system or ''
    else:
        status = ca_data.get('status', '')
        src_system = ca_data.get('src_system', '') or ''

    is_cis = src_system.upper() == 'CIS'

    if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
        return {
            'can_edit': is_cis and status in ('INITIAL', 'MODIFIED'),
            'can_delete': is_cis,
            'can_validate': is_cis and status in ('INITIAL', 'MODIFIED'),
        }

    has_write = has_permission(request, 'corp-action-create', 'WRITE')

    return {
        'can_edit': has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
        'can_delete': has_write and is_cis,
        'can_validate': has_write and is_cis and status in ('INITIAL', 'MODIFIED'),
    }


def get_user_accessible_modules(request: HttpRequest) -> List[str]:
    """
    Get list of modules user has any access to.

    Useful for building navigation menus.

    Args:
        request: Django HttpRequest object

    Returns:
        List of module names user can access

    Example:
        >>> modules = get_user_accessible_modules(request)
        >>> # Returns: ['trade', 'portfolio', 'reference_data']
    """
    accessible = []

    for module, perms in PERMISSION_GROUPS.items():
        if has_any_permission(request, perms, 'READ'):
            accessible.append(module)

    return accessible
