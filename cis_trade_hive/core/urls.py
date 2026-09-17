"""
Core URL Configuration
"""

from django.urls import path
from . import old_views
from .views import rbac_admin_views
from .views import notification_views

app_name = 'core'

urlpatterns = [
    path('audit-log/', old_views.audit_log, name='audit_log'),
    # Health check endpoints for monitoring long-running applications
    path('health/', old_views.health_check, name='health_check'),
    path('pool-stats/', old_views.pool_stats, name='pool_stats'),
    path('reset-stats/', old_views.reset_pool_stats, name='reset_stats'),

    # System Date API (from GMP file)
    path('system-date/api/', old_views.system_date_api, name='system_date_api'),

    # =========================================================================
    # RBAC Admin (superuser only — rbac-admin WRITE permission required)
    # =========================================================================
    path('rbac/', rbac_admin_views.rbac_dashboard, name='rbac_dashboard'),

    # Users
    path('rbac/users/', rbac_admin_views.user_list, name='rbac_user_list'),
    path('rbac/users/create/', rbac_admin_views.user_create, name='rbac_user_create'),
    path('rbac/users/<str:user_id>/edit/', rbac_admin_views.user_edit, name='rbac_user_edit'),
    path('rbac/users/<str:user_id>/deactivate/', rbac_admin_views.user_deactivate, name='rbac_user_deactivate'),
    path('rbac/users/<str:user_id>/groups/', rbac_admin_views.user_groups, name='rbac_user_groups'),

    # Groups
    path('rbac/groups/', rbac_admin_views.group_list, name='rbac_group_list'),
    path('rbac/groups/create/', rbac_admin_views.group_create, name='rbac_group_create'),
    path('rbac/groups/<str:group_id>/edit/', rbac_admin_views.group_edit, name='rbac_group_edit'),
    path('rbac/groups/<str:group_id>/permissions/', rbac_admin_views.group_permissions, name='rbac_group_permissions'),

    # Permissions
    path('rbac/permissions/', rbac_admin_views.permission_list, name='rbac_permission_list'),
    path('rbac/permissions/create/', rbac_admin_views.permission_create, name='rbac_permission_create'),

    # Audit
    path('rbac/audit/', rbac_admin_views.rbac_audit, name='rbac_audit'),

    # Notification poll endpoint — cross-worker fallback (no Redis / InMemory layer)
    path('api/notifications/poll/', notification_views.poll_notifications, name='notifications_poll'),

    # WebSocket diagnostics (dev/debug — no auth so it works with broken sessions)
    path('ws-debug/', old_views.ws_debug, name='ws_debug'),
    path('ws-test-notify/', old_views.ws_test_notify, name='ws_test_notify'),
]
