"""
Core Views Package
Contains authentication, dashboard, and RBAC admin views.
"""

from .auth_views import LoginView, LogoutView, auto_login_tmp3rc, require_login, require_permission
from .dashboard_views import dashboard_view
from . import rbac_admin_views

__all__ = [
    'LoginView',
    'LogoutView',
    'auto_login_tmp3rc',
    'require_login',
    'require_permission',
    'dashboard_view',
    'rbac_admin_views',
]
