"""
Portfolio URL Configuration

Maker-Checker Workflow URLs:
  MAKER Actions:
    - /create/                    : Create new portfolio (-> INITIAL)
    - /<name>/edit/               : Edit portfolio (-> MODIFIED)
    - /<name>/submit/             : Submit for validation (-> PENDING_VALIDATION)
    - /<name>/cancel/             : Cancel portfolio (-> CANCELLED)
    - /<name>/reactivate/         : Reactivate cancelled portfolio (-> INITIAL)

  CHECKER Actions:
    - /pending-validation/        : List portfolios pending validation
    - /pending-settlement/        : List validated portfolios ready for settlement
    - /<name>/validate/           : Validate portfolio (-> VALIDATED)
    - /<name>/settle/             : Settle portfolio (-> SETTLED)
"""

from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    # List and Create
    path('', views.portfolio_list, name='list'),
    path('create/', views.portfolio_create, name='create'),
    path('dashboard/', views.portfolio_dashboard, name='dashboard'),

    # Checker Lists - MUST come before <str:portfolio_name>/ pattern
    path('pending-validation/', views.pending_validation, name='pending_validation'),
    path('pending-settlement/', views.pending_settlement, name='pending_settlement'),

    # Legacy URL for backward compatibility
    path('pending/', views.pending_approvals, name='pending_approvals'),

    # Maker Actions
    path('<str:portfolio_name>/edit/', views.portfolio_edit, name='edit'),
    path('<str:portfolio_name>/submit/', views.portfolio_submit, name='submit'),
    path('<str:portfolio_name>/cancel/', views.portfolio_cancel, name='cancel'),
    path('<str:portfolio_name>/reactivate/', views.portfolio_reactivate, name='reactivate'),

    # Checker Actions
    path('<str:portfolio_name>/validate/', views.portfolio_validate, name='validate'),
    path('<str:portfolio_name>/settle/', views.portfolio_settle, name='settle'),

    # Legacy URLs for backward compatibility
    path('<str:portfolio_name>/approve/', views.portfolio_approve, name='approve'),
    path('<str:portfolio_name>/reject/', views.portfolio_reject, name='reject'),
    path('<str:portfolio_name>/close/', views.portfolio_close, name='close'),

    # Detail - MUST be last (catch-all pattern)
    path('<str:portfolio_name>/', views.portfolio_detail, name='detail'),
]
