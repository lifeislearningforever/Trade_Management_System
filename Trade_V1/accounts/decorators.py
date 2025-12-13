"""
Custom decorators for RBAC (Role-Based Access Control)
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


def permission_required(permission_codes):
    """
    Decorator to check custom RBAC permissions

    Usage:
        @permission_required(['create_order'])
        def my_view(request):
            ...

    Args:
        permission_codes: List of permission codes (e.g., ['create_order', 'view_order'])
    """
    if not isinstance(permission_codes, list):
        permission_codes = [permission_codes]

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            # Check if user has any of the required permissions
            if not request.user.has_any_permission(permission_codes):
                messages.error(
                    request,
                    f'You do not have permission to access this page. '
                    f'Required permissions: {", ".join(permission_codes)}'
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def role_required(role_codes):
    """
    Decorator to check user roles

    Usage:
        @role_required(['MAKER', 'CHECKER'])
        def my_view(request):
            ...

    Args:
        role_codes: List of role codes (e.g., ['MAKER', 'CHECKER'])
    """
    if not isinstance(role_codes, list):
        role_codes = [role_codes]

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user_role_codes = request.user.get_role_codes()
            if not any(code in user_role_codes for code in role_codes):
                messages.error(
                    request,
                    f'You do not have the required role to access this page. '
                    f'Required roles: {", ".join(role_codes)}'
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superuser_required(view_func):
    """
    Decorator to check if user is a superuser

    Usage:
        @superuser_required
        def my_view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(
                request,
                'Only administrators can access this page.'
            )
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def maker_required(view_func):
    """
    Shortcut decorator to check if user has MAKER role

    Usage:
        @maker_required
        def my_view(request):
            ...
    """
    return role_required(['MAKER'])(view_func)


def checker_required(view_func):
    """
    Shortcut decorator to check if user has CHECKER role

    Usage:
        @checker_required
        def my_view(request):
            ...
    """
    return role_required(['CHECKER'])(view_func)
