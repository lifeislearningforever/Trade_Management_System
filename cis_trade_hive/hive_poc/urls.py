"""
Hive POC URL Configuration

URL patterns for Hive Managed Tables POC.
"""

from django.urls import path
from . import views

app_name = 'hive_poc'

urlpatterns = [
    # Dashboard
    path('', views.hive_poc_dashboard, name='dashboard'),

    # Portfolio URLs
    path('portfolios/', views.portfolio_list, name='portfolio_list'),
    path('portfolios/create/', views.portfolio_create, name='portfolio_create'),
    path('portfolios/deleted/', views.portfolio_deleted, name='portfolio_deleted'),
    path('portfolios/<str:portfolio_id>/edit/', views.portfolio_edit, name='portfolio_edit'),
    path('portfolios/<str:portfolio_id>/delete/', views.portfolio_delete, name='portfolio_delete'),
    path('portfolios/<str:portfolio_id>/restore/', views.portfolio_restore, name='portfolio_restore'),

    # Trade URLs
    path('trades/', views.trade_list, name='trade_list'),
    path('trades/create/', views.trade_create, name='trade_create'),
    path('trades/deleted/', views.trade_deleted, name='trade_deleted'),
    path('trades/<str:trade_id>/edit/', views.trade_edit, name='trade_edit'),
    path('trades/<str:trade_id>/delete/', views.trade_delete, name='trade_delete'),
    path('trades/<str:trade_id>/restore/', views.trade_restore, name='trade_restore'),
    path('trades/<str:trade_id>/status/', views.trade_update_status, name='trade_update_status'),
]
