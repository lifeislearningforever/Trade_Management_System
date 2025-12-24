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

    # Detail, Edit
    path('<int:pk>/', views.portfolio_detail, name='detail'),
    path('<int:pk>/edit/', views.portfolio_edit, name='edit'),

    # Workflow Actions
    path('<int:pk>/submit/', views.portfolio_submit, name='submit'),
    path('<int:pk>/approve/', views.portfolio_approve, name='approve'),
    path('<int:pk>/reject/', views.portfolio_reject, name='reject'),

    # Pending Approvals
    path('pending/', views.pending_approvals, name='pending_approvals'),
]
