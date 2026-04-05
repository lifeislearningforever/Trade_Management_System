"""
Context Processors

Make common variables available to all templates.
"""

from django.conf import settings


def acl_context(request):
    """
    Add ACL-related context to templates.

    Makes user permissions available as template variables.
    """
    context = {
        'user_permissions': getattr(request, 'user_permissions', {}),
        'acl_enabled': settings.ACL_ENABLED,
    }
    return context


def app_context(request):
    """
    Add application-wide context to templates.

    Makes app name, version, and other metadata available.
    """
    context = {
        'app_name': settings.APP_NAME,
        'app_version': settings.APP_VERSION,
        'app_description': settings.APP_DESCRIPTION,
        'maker_checker_enabled': settings.MAKER_CHECKER_ENABLED,
    }
    return context


def sidebar_permissions(request):
    """
    Add permission flags for sidebar navigation.

    These flags control which menu items are visible based on user permissions.
    Uses session-stored permissions from RBAC v2 login.
    """
    # Get permission map from session
    permission_map = request.session.get('user_permissions', {})

    def has_perm(perm_name, mode='READ'):
        """Check if user has permission."""
        user_mode = permission_map.get(perm_name)
        if user_mode is None:
            return False
        if mode == 'READ':
            return user_mode in ('READ', 'READ_WRITE')
        return user_mode == 'READ_WRITE'

    # Build sidebar permission context
    # Each module gets: can_view (list access), can_create, can_approve
    return {
        # Portfolio permissions
        'sidebar_portfolio_view': has_perm('portfolio-list', 'READ'),
        'sidebar_portfolio_create': has_perm('portfolio-create', 'READ_WRITE'),
        'sidebar_portfolio_approve': has_perm('portfolio-approval', 'READ'),

        # Trade permissions
        'sidebar_trade_view': has_perm('trade-list', 'READ'),
        'sidebar_trade_create': has_perm('trade-create', 'READ_WRITE'),
        'sidebar_trade_approve': has_perm('trade-approval', 'READ'),

        # Cash Flow permissions
        'sidebar_cash_flow_view': has_perm('cash-flow-list', 'READ'),
        'sidebar_cash_flow_create': has_perm('cash-flow-create', 'READ_WRITE'),
        'sidebar_cash_flow_approve': has_perm('cash-flow-approval', 'READ'),

        # Position permissions
        'sidebar_position_view': has_perm('position-list', 'READ'),

        # Market Data permissions
        'sidebar_market_data_view': has_perm('market-data-dashboard', 'READ') or has_perm('fx-rates-list', 'READ') or has_perm('equity-prices-list', 'READ'),
        'sidebar_fx_rates_view': has_perm('fx-rates-list', 'READ'),
        'sidebar_equity_prices_view': has_perm('equity-prices-list', 'READ'),
        'sidebar_equity_prices_create': has_perm('equity-prices-create', 'READ_WRITE'),

        # Reference Data permissions
        'sidebar_currencies_view': has_perm('currencies-list', 'READ'),
        'sidebar_countries_view': has_perm('countries-list', 'READ'),
        'sidebar_calendars_view': has_perm('calendars-list', 'READ'),
        'sidebar_parties_view': has_perm('parties-list', 'READ'),
        'sidebar_parties_create': has_perm('parties-create', 'READ_WRITE'),
        'sidebar_securities_view': has_perm('securities-list', 'READ'),
        'sidebar_securities_create': has_perm('securities-create', 'READ_WRITE'),
        'sidebar_corp_actions_view': has_perm('corp-action-list', 'READ'),
        'sidebar_corp_actions_create': has_perm('corp-action-create', 'READ_WRITE'),

        # Configuration permissions
        'sidebar_lookup_view': has_perm('lookup-tables-list', 'READ'),
        'sidebar_lookup_edit': has_perm('lookup-tables-edit', 'READ_WRITE'),
        'sidebar_udf_view': has_perm('udf-list', 'READ'),
        'sidebar_udf_create': has_perm('udf-create', 'READ_WRITE'),
        'sidebar_upload_view': has_perm('upload-list', 'READ') or True,  # Allow upload for now

        # System permissions
        'sidebar_audit_view': has_perm('audit-logs-read', 'READ'),
        'sidebar_docs_view': has_perm('documentation-read', 'READ') or True,  # Always allow docs
    }
