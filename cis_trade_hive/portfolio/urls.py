"""
Portfolio URL Configuration
"""

from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    # List and Create
    path('', views.portfolio_list, name='list'),
    path('create/', views.portfolio_create, name='create'),

    # Pending Approvals - MUST come before <str:portfolio_name>/ pattern
    path('pending/', views.pending_approvals, name='pending_approvals'),

    # Edit - uses Django ORM pk for now
    path('edit/<int:pk>/', views.portfolio_edit, name='edit'),

    # Workflow Actions - use Django ORM pk
    path('<int:pk>/submit/', views.portfolio_submit, name='submit'),
    path('<int:pk>/approve/', views.portfolio_approve, name='approve'),
    path('<int:pk>/reject/', views.portfolio_reject, name='reject'),

    # Close/Reactivate - use portfolio name from Kudu
    path('<str:portfolio_name>/close/', views.portfolio_close, name='close'),
    path('<str:portfolio_name>/reactivate/', views.portfolio_reactivate, name='reactivate'),

    # Detail - uses portfolio name from Kudu (MUST be last - catch-all pattern)
    path('<str:portfolio_name>/', views.portfolio_detail, name='detail'),
]
