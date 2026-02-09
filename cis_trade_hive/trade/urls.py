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

    # Dashboard
    path('dashboard/', views.trade_dashboard, name='dashboard'),

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

    # ==========================================================================
    # POSITIONS - DISABLED
    # To re-enable, uncomment the following 3 lines and the sidebar link in
    # templates/components/sidebar.html (lines 97-102)
    # Also uncomment the position views in trade/views.py (lines 1041-1139)
    # See: docs/DISABLED_POSITION_CODE.md for full details
    # ==========================================================================
    # path('positions/', views.position_list, name='position_list'),
    # path('positions/<int:position_id>/', views.position_detail, name='position_detail'),
    # path('positions/refresh/', views.refresh_positions, name='refresh_positions'),

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

    # Detailed API endpoints for modal selection
    path('api/portfolios-detailed/', views.api_portfolios_detailed, name='api_portfolios_detailed'),
    path('api/securities-detailed/', views.api_securities_detailed, name='api_securities_detailed'),

    # Currency-based API endpoints for cascading dropdown
    path('api/currencies/', views.api_currencies, name='api_currencies'),
    path('api/securities-by-currency/', views.api_securities_by_currency, name='api_securities_by_currency'),
    path('api/equity-price/', views.api_get_equity_price, name='api_get_equity_price'),
]
