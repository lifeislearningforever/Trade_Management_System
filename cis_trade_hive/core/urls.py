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
]
