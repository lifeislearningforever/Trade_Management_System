"""
Trade URLs

URL patterns for trade management module.
"""

from django.urls import path
from trade import views
from trade import views_cash_flow

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
    path('api/validate-settlement-date/', views.api_validate_settlement_date, name='api_validate_settlement_date'),
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
    path('api/fx-rate/', views.api_get_fx_rate, name='api_get_fx_rate'),

    # Trade charge API endpoints
    path('api/broker-charges/', views.api_get_broker_charges, name='api_get_broker_charges'),
    path('api/calculate-charges/', views.api_calculate_charges, name='api_calculate_charges'),
    path('api/exchanges/', views.api_get_exchanges, name='api_get_exchanges'),
    path('api/debug-charge-lut/', views.api_debug_charge_lut, name='api_debug_charge_lut'),

    # Position Queue Health Check (for CML monitoring)
    path('api/worker-health/', views.api_worker_health, name='api_worker_health'),

    # =========================================================================
    # Trade Event Queue Management APIs (for async processing recovery)
    # =========================================================================
    path('api/event-queue/health/', views.api_trade_event_queue_health, name='api_trade_event_queue_health'),
    path('api/event-queue/failed/', views.api_trade_event_queue_failed, name='api_trade_event_queue_failed'),
    path('api/event-queue/reprocess/<int:event_id>/', views.api_trade_event_reprocess, name='api_trade_event_reprocess'),
    path('api/event-queue/reprocess-all-failed/', views.api_trade_event_reprocess_all_failed, name='api_trade_event_reprocess_all_failed'),
    path('api/event-queue/worker/start/', views.api_trade_event_worker_start, name='api_trade_event_worker_start'),
    path('api/event-queue/worker/stop/', views.api_trade_event_worker_stop, name='api_trade_event_worker_stop'),

    # =========================================================================
    # Cash Flow URLs
    # =========================================================================
    path('cash-flow/', views_cash_flow.cash_flow_list, name='cash_flow_list'),
    path('cash-flow/create/', views_cash_flow.cash_flow_create, name='cash_flow_create'),
    path('cash-flow/pending/', views_cash_flow.cash_flow_pending_approvals, name='cash_flow_pending_approvals'),
    path('cash-flow/<int:cash_flow_id>/', views_cash_flow.cash_flow_detail, name='cash_flow_detail'),
    path('cash-flow/<int:cash_flow_id>/edit/', views_cash_flow.cash_flow_edit, name='cash_flow_edit'),
    path('cash-flow/<int:cash_flow_id>/delete/', views_cash_flow.cash_flow_delete, name='cash_flow_delete'),
    path('cash-flow/<int:cash_flow_id>/restore/', views_cash_flow.cash_flow_restore, name='cash_flow_restore'),
    path('cash-flow/<int:cash_flow_id>/approve/', views_cash_flow.cash_flow_approve, name='cash_flow_approve'),

    # Cash Flow API endpoints
    path('api/cash-flow/validate-portfolio/', views_cash_flow.api_validate_cf_portfolio, name='api_validate_cf_portfolio'),
    path('api/cash-flow/validate-security/', views_cash_flow.api_validate_cf_security, name='api_validate_cf_security'),
]
