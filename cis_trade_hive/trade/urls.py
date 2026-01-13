"""
Trade URLs

URL patterns for trade management module.
"""

from django.urls import path
from trade import views

app_name = 'trade'

urlpatterns = [
    # Trade List
    path('', views.trade_list, name='list'),

    # Trade CRUD
    path('create/', views.trade_create, name='create'),
    path('create/<str:trade_type>/', views.trade_create, name='create_type'),
    path('<int:trade_id>/', views.trade_detail, name='detail'),
    path('<int:trade_id>/edit/', views.trade_edit, name='edit'),
    path('<int:trade_id>/delete/', views.trade_delete, name='delete'),

    # Workflow Actions
    path('<int:trade_id>/submit/', views.trade_submit, name='submit'),
    path('<int:trade_id>/validate/', views.trade_validate, name='validate'),
    path('<int:trade_id>/settle/', views.trade_settle, name='settle'),
    path('<int:trade_id>/cancel/', views.trade_cancel, name='cancel'),
    path('<int:trade_id>/reactivate/', views.trade_reactivate, name='reactivate'),

    # Approval Queues
    path('pending-validation/', views.pending_validation, name='pending_validation'),
    path('pending-settlement/', views.pending_settlement, name='pending_settlement'),

    # History
    path('<int:trade_id>/history/', views.trade_history, name='history'),

    # API endpoints for AJAX
    path('api/validate-portfolio/', views.api_validate_portfolio, name='api_validate_portfolio'),
    path('api/validate-security/', views.api_validate_security, name='api_validate_security'),
    path('api/validate-counterparty/', views.api_validate_counterparty, name='api_validate_counterparty'),
    path('api/portfolios/', views.api_portfolios, name='api_portfolios'),
    path('api/securities/', views.api_securities, name='api_securities'),
    path('api/counterparties/', views.api_counterparties, name='api_counterparties'),
    path('api/position/', views.api_get_position, name='api_get_position'),
]
