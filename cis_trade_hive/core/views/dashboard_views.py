"""
Dashboard views for CIS Trade Hive.
"""

import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from .auth_views import require_login

logger = logging.getLogger(__name__)


@require_login
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view.
    Shows user information and navigation to different modules.
    Requires: User to be logged in via ACL authentication
    """
    # Get user info from session
    user_info = {
        'login': request.session.get('user_login'),
        'name': request.session.get('user_name'),
        'email': request.session.get('user_email'),
        'group': request.session.get('user_group_name'),
    }

    # Get permissions from session
    permissions = request.session.get('user_permissions', {})

    # Organize permissions by module
    permission_modules = {
        'portfolio': {
            'name': 'Portfolio Management',
            'access': permissions.get('cis-portfolio', 'NONE'),
            'icon': 'briefcase',
            'url': '/portfolio/',
        },
        'trade': {
            'name': 'Trade Management',
            'access': permissions.get('cis-trade', 'NONE'),
            'icon': 'exchange-alt',
            'url': '/trade/',
        },
        'udf': {
            'name': 'UDF Management',
            'access': permissions.get('cis-udf', 'NONE'),
            'icon': 'tags',
            'url': '/udf/',
        },
        'report': {
            'name': 'Reports',
            'access': permissions.get('cis-report', 'NONE'),
            'icon': 'file-alt',
            'url': '/reports/',
        },
        'currency': {
            'name': 'Currency Reference',
            'access': permissions.get('cis-currency', 'NONE'),
            'icon': 'dollar-sign',
            'url': '/reference-data/currency/',
        },
        'audit': {
            'name': 'Audit Log',
            'access': permissions.get('cis-audit', 'NONE'),
            'icon': 'history',
            'url': '/audit/',
        },
    }

    context = {
        'user': user_info,
        'permissions': permissions,
        'modules': permission_modules,
        'page_title': 'Dashboard',
    }

    return render(request, 'core/dashboard.html', context)
