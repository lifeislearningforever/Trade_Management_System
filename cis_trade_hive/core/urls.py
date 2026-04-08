"""
Core URL Configuration
"""

from django.urls import path
from . import old_views

app_name = 'core'

urlpatterns = [
    path('audit-log/', old_views.audit_log, name='audit_log'),
    # Health check endpoints for monitoring long-running applications
    path('health/', old_views.health_check, name='health_check'),
    path('pool-stats/', old_views.pool_stats, name='pool_stats'),
    path('reset-stats/', old_views.reset_pool_stats, name='reset_stats'),

    # System Date Management
    path('system-date/', old_views.system_date_dashboard, name='system_date_dashboard'),
    path('system-date/api/', old_views.system_date_api, name='system_date_api'),
    path('system-date/user-override/set/', old_views.system_date_set_user_override, name='system_date_set_user_override'),
    path('system-date/user-override/clear/', old_views.system_date_clear_user_override, name='system_date_clear_user_override'),
    path('system-date/global-override/set/', old_views.system_date_set_global_override, name='system_date_set_global_override'),
    path('system-date/global-override/clear/', old_views.system_date_clear_global_override, name='system_date_clear_global_override'),
    path('system-date/eod-lock/', old_views.system_date_eod_lock, name='system_date_eod_lock'),
]
