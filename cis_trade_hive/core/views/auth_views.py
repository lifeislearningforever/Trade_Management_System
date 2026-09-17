"""
Authentication views for CIS Trade Hive.

This module provides session-based authentication using ACL from Kudu/Impala.
Supports both legacy (v1) and new (v2) RBAC table structures.

RBAC Version Support:
    v1 (legacy): Uses cis_user, cis_user_group, cis_group_permissions
        - Single group per user
        - Session keys: user_group_id, user_group_name

    v2 (new): Uses cis_user_info, cis_user_group_info, cis_permission_info,
              cis_user_group_mapping_info, cis_group_permission_map
        - Multi-group support (user can belong to multiple groups)
        - Session keys: user_groups (list), user_group_names (list)
        - Backward compatible: also sets user_group_name (first group)

Configuration:
    Set RBAC_VERSION='v1' or 'v2' in environment or settings.py
    Default: 'v1' for backward compatibility

Usage:
    @require_login
    def my_view(request):
        # Access user info
        user_login = request.session.get('user_login')
        permissions = request.session.get('user_permissions', {})

    @require_permission('trade-create', 'WRITE')
    def create_trade(request):
        # Only users with trade-create WRITE permission can access
        pass

Author: CIS Trade Hive Team
Version: 2.0
"""

import logging
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.conf import settings

from ..repositories.acl_repository import get_acl_repository, get_rbac_version
from ..audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)


class LoginView(View):
    """
    Simple login view using ACL from Hive.
    No password required for now - just login ID.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        """Display login form."""
        # If already logged in, redirect to dashboard
        if request.session.get('user_login'):
            return redirect('dashboard')

        return render(request, 'core/login.html')

    def post(self, request: HttpRequest) -> HttpResponse:
        """
        Process login and establish user session.

        Supports both RBAC v1 (legacy) and v2 (new) table structures.
        The session data format is compatible with both versions.

        Session Keys Set:
            Common (both v1 and v2):
            - user_login: User login ID (e.g., 'TMP3RC')
            - user_name: Full name (e.g., 'PRAKASH HOSALLI')
            - user_email: Email address
            - user_permissions: Dict mapping permission_name to access mode

            v1 specific:
            - user_id: from cis_user.cis_user_id
            - user_group_id: from cis_user.cis_user_group_id
            - user_group_name: Group name (single)

            v2 specific (also sets v1 keys for backward compatibility):
            - user_id: from cis_user_info.user_id
            - user_groups: List of group dictionaries
            - user_group_names: List of group names (e.g., ['SG-TRADER', 'CIS-OPS'])
            - user_group_name: First group name (for backward compatibility)
            - user_entity: Default entity (e.g., 'UOBS')
            - rbac_version: 'v2' marker
        """
        login = request.POST.get('login', '').strip()

        if not login:
            return render(request, 'core/login.html', {
                'error': 'Please enter your login ID'
            })

        # Authenticate user using version-appropriate repository
        acl_repo = get_acl_repository()
        rbac_version = get_rbac_version()
        auth_data = acl_repo.authenticate_user(login)

        if not auth_data:
            # Log failed login attempt to Kudu audit
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=login,
                user_email='',
                action_type='LOGIN',
                entity_type='AUTH',
                entity_name='Login',
                entity_id='FAILED_LOGIN',
                action_description=f'Failed login attempt for user: {login} (RBAC {rbac_version})',
                request_method=request.method,
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='FAILURE'
            )

            return render(request, 'core/login.html', {
                'error': f'User {login} not found or not enabled'
            })

        user = auth_data['user']
        permission_map = auth_data['permission_map']

        # Store session data based on RBAC version
        if rbac_version == 'v2':
            # V2: New RBAC tables with multi-group support
            groups = auth_data.get('groups', [])
            group_names = auth_data.get('group_names', [])

            # Common session keys
            request.session['user_login'] = user['login']
            request.session['user_id'] = user['user_id']  # v2 uses user_id
            request.session['user_name'] = user['name']
            request.session['user_email'] = user.get('email', '')
            request.session['user_entity'] = user.get('default_entity', 'UOBS')
            request.session['user_permissions'] = permission_map

            # V2 specific: multi-group data
            request.session['user_groups'] = groups
            request.session['user_group_names'] = group_names

            # Backward compatibility: set single group keys
            first_group = groups[0] if groups else {}
            request.session['user_group_name'] = first_group.get('group_name', 'Unknown')
            request.session['user_group_id'] = first_group.get('mapping_id', '')

            # Mark as v2 session
            request.session['rbac_version'] = 'v2'

            # Log group info
            logger.info(f"V2 Login: {user['name']} belongs to {len(groups)} group(s): {group_names}")

        else:
            # V1: Legacy RBAC tables (single group)
            group = auth_data.get('group')

            request.session['user_login'] = user['login']
            request.session['user_id'] = user['cis_user_id']  # v1 uses cis_user_id
            request.session['user_name'] = user['name']
            request.session['user_email'] = user.get('email', '')
            request.session['user_group_id'] = user.get('cis_user_group_id')
            request.session['user_group_name'] = group['name'] if group else 'Unknown'
            request.session['user_permissions'] = permission_map

            # Mark as v1 session
            request.session['rbac_version'] = 'v1'

        # Persist last_login timestamp to cis_user_info
        acl_repo.update_last_login(login)

        # Rate limiting: Check last login audit timestamp
        import time
        current_time = int(time.time())
        last_login_audit = request.session.get('last_login_audit_time', 0)
        time_since_last_audit = current_time - last_login_audit

        # Get user_id for audit (handle both v1 and v2 key names)
        audit_user_id = str(user.get('user_id') or user.get('cis_user_id', '0'))

        # Only log if more than 60 seconds since last LOGIN audit (prevents flooding)
        if time_since_last_audit > 60:
            # Build description with RBAC version info
            group_info = request.session.get('user_group_names', [request.session.get('user_group_name', 'Unknown')])
            description = f"User {user['name']} ({user['login']}) logged in successfully (RBAC {rbac_version}, groups: {group_info})"

            # Log successful login to Kudu audit
            audit_log_kudu_repository.log_action(
                user_id=audit_user_id,
                username=user['login'],
                user_email=user.get('email') or '',
                action_type='LOGIN',
                entity_type='AUTH',
                entity_name='Login',
                entity_id='SUCCESSFUL_LOGIN',
                action_description=description,
                request_method=request.method,
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            # Update last login audit timestamp
            request.session['last_login_audit_time'] = current_time
            logger.info(f"User {user['name']} ({login}) logged in successfully - LOGIN audit logged")
        else:
            logger.info(f"User {user['name']} ({login}) logged in successfully - LOGIN audit skipped (last audit {time_since_last_audit}s ago)")

        return redirect('dashboard')


class LogoutView(View):
    """Logout view."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Process logout."""
        # Get session data BEFORE flushing
        user_name = request.session.get('user_name', 'Unknown')
        user_login = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', '0'))
        user_email = request.session.get('user_email', '')

        # Log logout to Kudu audit BEFORE clearing session
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=user_login,
            user_email=user_email,
            action_type='LOGOUT',
            entity_type='AUTH',
            entity_name='Logout',
            entity_id='USER_LOGOUT',
            action_description=f'User {user_name} ({user_login}) logged out',
            request_method=request.method,
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        # Clear session
        request.session.flush()

        logger.info(f"User {user_name} logged out")

        return redirect('login')


def require_login(view_func):
    """
    Decorator to require login for a view.
    Creates a mock user object from session data for compatibility.

    Usage:
        @require_login
        def my_view(request):
            ...
    """
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.session.get('user_login'):
            return redirect('login')

        # Create a mock user object from session for compatibility
        class MockUser:
            def __init__(self, session_data):
                self.id = session_data.get('user_id')
                self.username = session_data.get('user_login')
                self.email = session_data.get('user_email', '')
                self.is_authenticated = True
                self._full_name = session_data.get('user_name', '')

            def get_full_name(self):
                return self._full_name or self.username

        request.user = MockUser(request.session)
        return view_func(request, *args, **kwargs)

    return wrapper


def require_permission(permission: str, access_level: str = 'READ'):
    """
    Decorator to require specific permission for a view.
    For development, set SKIP_PERMISSION_CHECKS = True in settings.

    Usage:
        @require_permission('cis-portfolio', 'WRITE')
        def create_portfolio(request):
            ...
    """
    def decorator(view_func):
        def wrapper(request: HttpRequest, *args, **kwargs):
            # First check login
            if not request.session.get('user_login'):
                return redirect('login')

            # Create mock user object for compatibility
            class MockUser:
                def __init__(self, session_data):
                    self.id = session_data.get('user_id')
                    self.username = session_data.get('user_login')
                    self.email = session_data.get('user_email', '')
                    self.is_authenticated = True
                    self._full_name = session_data.get('user_name', '')

                def get_full_name(self):
                    return self._full_name or self.username

            request.user = MockUser(request.session)

            # Skip permission checks for development (set SKIP_PERMISSION_CHECKS = True in settings)
            from django.conf import settings
            if getattr(settings, 'SKIP_PERMISSION_CHECKS', False):
                logger.info(f"DEV MODE: Skipping permission check for {permission}")
                return view_func(request, *args, **kwargs)

            # Check permission
            permission_map = request.session.get('user_permissions', {})
            user_access = permission_map.get(permission)

            has_access = False
            if access_level == 'READ':
                has_access = user_access in ['READ', 'WRITE']
            elif access_level == 'WRITE':
                has_access = user_access == 'WRITE'

            if not has_access:
                # Log permission denial to Kudu audit
                audit_log_kudu_repository.log_action(
                    user_id=str(request.session.get('user_id', '0')),
                    username=request.session.get('user_login', 'anonymous'),
                    user_email=request.session.get('user_email', ''),
                    action_type='ACCESS_DENIED',
                    entity_type='AUTH',
                    entity_name='Permission Check',
                    entity_id=permission,
                    action_description=f"Access denied: User lacks {access_level} permission for {permission}",
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='FAILURE'
                )

                return HttpResponse(
                    f"Access denied: You don't have {access_level} permission for {permission}",
                    status=403
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def auto_login_tmp3rc(request: HttpRequest) -> HttpResponse:
    """
    Auto-login helper for TMP3RC user (for testing/development only).

    This endpoint is only available when DEBUG=True (see config/urls.py).
    Supports both RBAC v1 and v2 table structures.

    Note:
        AUTO_LOGIN events are NOT logged to audit table to prevent flooding.
        Only manual LOGIN/LOGOUT through LoginView are audited.

    Security:
        This endpoint should NEVER be enabled in production.
        It is protected by DEBUG mode check in urls.py.

    Returns:
        HttpResponse: Redirect to dashboard on success, error page on failure
    """
    # If already logged in, just redirect to dashboard
    if request.session.get('user_login'):
        logger.debug(f"User {request.session.get('user_name')} already logged in, redirecting to dashboard")
        return redirect('dashboard')

    try:
        acl_repo = get_acl_repository()
        rbac_version = get_rbac_version()
        logger.info(f"ACL Repository created successfully (RBAC {rbac_version})")

        auth_data = acl_repo.authenticate_user('TMP3RC')
        logger.info(f"Authentication result: {auth_data is not None}")

        if auth_data:
            user = auth_data['user']
            permission_map = auth_data['permission_map']

            # Store session data based on RBAC version
            if rbac_version == 'v2':
                # V2: New RBAC tables with multi-group support
                groups = auth_data.get('groups', [])
                group_names = auth_data.get('group_names', [])

                request.session['user_login'] = user['login']
                request.session['user_id'] = user['user_id']
                request.session['user_name'] = user['name']
                request.session['user_email'] = user.get('email', '')
                request.session['user_entity'] = user.get('default_entity', 'UOBS')
                request.session['user_permissions'] = permission_map
                request.session['user_groups'] = groups
                request.session['user_group_names'] = group_names

                # Backward compatibility
                first_group = groups[0] if groups else {}
                request.session['user_group_name'] = first_group.get('group_name', 'Unknown')
                request.session['user_group_id'] = first_group.get('mapping_id', '')
                request.session['rbac_version'] = 'v2'

                logger.info(f"Auto-login (V2) successful for {user['name']} ({user['login']}) - groups: {group_names}")

            else:
                # V1: Legacy RBAC tables
                group = auth_data.get('group')

                request.session['user_login'] = user['login']
                request.session['user_id'] = user['cis_user_id']
                request.session['user_name'] = user['name']
                request.session['user_email'] = user.get('email', '')
                request.session['user_group_id'] = user.get('cis_user_group_id')
                request.session['user_group_name'] = group['name'] if group else 'Unknown'
                request.session['user_permissions'] = permission_map
                request.session['rbac_version'] = 'v1'

                logger.info(f"Auto-login (V1) successful for {user['name']} ({user['login']}) - no audit entry created")

            return redirect('dashboard')

        logger.error("Auto-login failed: auth_data is None")
        return HttpResponse("Auto-login failed for TMP3RC: User not found or authentication failed", status=500)

    except Exception as e:
        logger.exception(f"Auto-login exception: {str(e)}")
        return HttpResponse(f"Auto-login error: {str(e)}", status=500)
