"""
Core URL Configuration
"""

from django.urls import path
from . import old_views

app_name = 'core'

urlpatterns = [
    path('audit-log/', old_views.audit_log, name='audit_log'),
]
