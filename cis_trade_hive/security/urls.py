"""
Security URL Configuration
"""

from django.urls import path
from . import views

app_name = 'security'

urlpatterns = [
    # List and Dashboard
    path('', views.security_list, name='list'),
    path('dashboard/', views.security_dashboard, name='dashboard'),

    # Create
    path('create/', views.security_create, name='create'),

    # Pending Approvals (must come before <int:security_id>)
    path('pending/', views.pending_approvals, name='pending_approvals'),

    # Detail
    path('<int:security_id>/', views.security_detail, name='detail'),

    # Edit
    path('<int:security_id>/edit/', views.security_edit, name='edit'),

    # Workflow Actions
    path('<int:security_id>/validate/', views.security_validate, name='validate'),
]
