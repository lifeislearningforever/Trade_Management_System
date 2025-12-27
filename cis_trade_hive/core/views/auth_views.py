"""
Authentication views for CIS Trade Hive.
Simple session-based authentication using ACL from Hive.
"""

import logging
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View

from ..repositories.acl_repository import get_acl_repository
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
        """Process login."""
        login = request.POST.get('login', '').strip()

        if not login:
            return render(request, 'core/login.html', {
                'error': 'Please enter your login ID'
            })

        # Authenticate user
        acl_repo = get_acl_repository()
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
                action_description=f'Failed login attempt for user: {login}',
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
        group = auth_data['group']
        permission_map = auth_data['permission_map']

        # Store in session
        request.session['user_login'] = user['login']
        request.session['user_id'] = user['cis_user_id']
        request.session['user_name'] = user['name']
        request.session['user_email'] = user['email']
        request.session['user_group_id'] = user['cis_user_group_id']
        request.session['user_group_name'] = group['name'] if group else 'Unknown'
        request.session['user_permissions'] = permission_map

        # Update last login (logged only, not persisted to Hive)
        acl_repo.update_last_login(login)

        # Log successful login to Kudu audit
        audit_log_kudu_repository.log_action(
            user_id=str(user['cis_user_id']),
            username=user['login'],
            user_email=user['email'] or '',
            action_type='LOGIN',
            entity_type='AUTH',
            entity_name='Login',
            entity_id='SUCCESSFUL_LOGIN',
            action_description=f"User {user['name']} ({user['login']}) logged in successfully",
            request_method=request.method,
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        logger.info(f"User {user['name']} ({login}) logged in successfully")

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
                has_access = user_access in ['READ', 'WRITE', 'READ_WRITE']
            elif access_level == 'WRITE':
                has_access = user_access in ['WRITE', 'READ_WRITE']
            elif access_level == 'READ_WRITE':
                has_access = user_access == 'READ_WRITE'

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
    Auto-login helper for TMP3RC user (for testing/development).
    """
    try:
        acl_repo = get_acl_repository()
        logger.info("ACL Repository created successfully")

        auth_data = acl_repo.authenticate_user('TMP3RC')
        logger.info(f"Authentication result: {auth_data is not None}")

        if auth_data:
            user = auth_data['user']
            group = auth_data['group']
            permission_map = auth_data['permission_map']

            request.session['user_login'] = user['login']
            request.session['user_id'] = user['cis_user_id']
            request.session['user_name'] = user['name']
            request.session['user_email'] = user['email']
            request.session['user_group_id'] = user['cis_user_group_id']
            request.session['user_group_name'] = group['name'] if group else 'Unknown'
            request.session['user_permissions'] = permission_map

            # Log auto-login to Kudu audit
            audit_log_kudu_repository.log_action(
                user_id=str(user['cis_user_id']),
                username=user['login'],
                user_email=user['email'] or '',
                action_type='LOGIN',
                entity_type='AUTH',
                entity_name='Auto-Login',
                entity_id='AUTO_LOGIN',
                action_description=f"Auto-login successful for {user['name']} ({user['login']})",
                request_method=request.method,
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            logger.info(f"Auto-login successful for {user['name']}")
            return redirect('dashboard')

        logger.error("Auto-login failed: auth_data is None")
        return HttpResponse("Auto-login failed for tmp3rc: User not found or authentication failed", status=500)

    except Exception as e:
        logger.exception(f"Auto-login exception: {str(e)}")
        return HttpResponse(f"Auto-login error: {str(e)}", status=500)
