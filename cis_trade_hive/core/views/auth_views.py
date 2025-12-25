"""
Authentication views for CIS Trade Hive.
Simple session-based authentication using ACL from Hive.
"""

import logging
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View

from ..repositories.acl_repository import get_acl_repository

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

        logger.info(f"User {user['name']} ({login}) logged in successfully")

        return redirect('dashboard')


class LogoutView(View):
    """Logout view."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Process logout."""
        user_name = request.session.get('user_name', 'Unknown')

        # Clear session
        request.session.flush()

        logger.info(f"User {user_name} logged out")

        return redirect('login')


def require_login(view_func):
    """
    Decorator to require login for a view.

    Usage:
        @require_login
        def my_view(request):
            ...
    """
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.session.get('user_login'):
            return redirect('login')
        return view_func(request, *args, **kwargs)

    return wrapper


def require_permission(permission: str, access_level: str = 'READ'):
    """
    Decorator to require specific permission for a view.

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

            logger.info(f"Auto-login successful for {user['name']}")
            return redirect('dashboard')

        logger.error("Auto-login failed: auth_data is None")
        return HttpResponse("Auto-login failed for tmp3rc: User not found or authentication failed", status=500)

    except Exception as e:
        logger.exception(f"Auto-login exception: {str(e)}")
        return HttpResponse(f"Auto-login error: {str(e)}", status=500)
