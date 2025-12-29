"""
Core Views Package
Contains authentication and dashboard views.
"""

from .auth_views import LoginView, LogoutView, auto_login_tmp3rc, require_login, require_permission
from .dashboard_views import dashboard_view

__all__ = [
    'LoginView',
    'LogoutView',
    'auto_login_tmp3rc',
    'require_login',
    'require_permission',
    'dashboard_view',
]
