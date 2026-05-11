"""
Dashboard views for CIS Trade Hive.
"""

import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

from .auth_views import require_login
from portfolio.repositories import portfolio_hive_repository
from udf.repositories.udf_hive_repository import UDFDefinitionRepository
from reference_data.repositories.reference_data_repository import (
    CurrencyRepository,
    CountryRepository,
    CounterpartyRepository,
)
from core.audit.audit_kudu_repository import AuditLogKuduRepository
from market_data.repositories.fx_rate_hive_repository import fx_rate_hive_repository
from market_data.repositories.equity_price_hive_repository import EquityPriceHiveRepository
from security.repositories.security_hive_repository import security_hive_repository
from trade.repositories.trade_kudu_repository import trade_kudu_repository
from core.repositories.impala_connection import query_cache

logger = logging.getLogger(__name__)

_DASHBOARD_CACHE_TTL = 60

# Initialize repositories
udf_repository = UDFDefinitionRepository()
currency_repository = CurrencyRepository()
country_repository = CountryRepository()
counterparty_repository = CounterpartyRepository()
audit_log_kudu_repository = AuditLogKuduRepository()


def _has_perm(permissions: dict, perm_name: str, mode: str = 'READ') -> bool:
    """Return True if the session permission map grants perm_name at mode."""
    user_mode = permissions.get(perm_name)
    if user_mode is None:
        return False
    if mode == 'READ':
        return user_mode in ('READ', 'WRITE')
    return user_mode == 'WRITE'


def _build_sections(permissions: dict) -> dict:
    """
    Return a dict of boolean flags — one per dashboard section.
    Each flag gates both the stat query and the template block.
    Uses the same permission keys as URL_PERMISSION_MAP / sidebar_permissions.
    """
    return {
        'portfolio':    _has_perm(permissions, 'portfolio-list',          'READ'),
        'trade':        _has_perm(permissions, 'trade-list',              'READ'),
        'trade_create': _has_perm(permissions, 'trade-create',            'WRITE'),
        'trade_approve':_has_perm(permissions, 'trade-approval',          'READ'),
        'position':     _has_perm(permissions, 'position-list',           'READ'),
        'cash_flow':    _has_perm(permissions, 'cash-flow-list',          'READ'),
        'market_data':  _has_perm(permissions, 'fx-rates-list',           'READ') or _has_perm(permissions, 'market-data-dashboard', 'READ'),
        'securities':   _has_perm(permissions, 'securities-list',         'READ'),
        'corp_actions': _has_perm(permissions, 'corp-action-list',        'READ'),
        'parties':      _has_perm(permissions, 'parties-list',            'READ'),
        'upload':       _has_perm(permissions, 'upload-list',             'READ'),
        'rbac_admin':   _has_perm(permissions, 'rbac-admin',              'WRITE'),
        'audit':        _has_perm(permissions, 'audit-logs-read',         'READ'),
        'udf':          _has_perm(permissions, 'udf-list',                'READ'),
        'lookup':       _has_perm(permissions, 'lookup-tables-list',      'READ'),
        'currencies':   _has_perm(permissions, 'currencies-list',         'READ'),
    }


def _build_quick_actions(permissions: dict) -> list:
    """
    Return ordered list of quick-action button dicts for modules the user
    has WRITE access to.  Read-only users see no action buttons.
    """
    actions = []
    if _has_perm(permissions, 'trade-create', 'WRITE'):
        actions.append({'label': 'New Trade',       'url': '/trade/create/',                        'icon': 'plus-circle',      'color': 'primary'})
    if _has_perm(permissions, 'portfolio-create', 'WRITE'):
        actions.append({'label': 'New Portfolio',   'url': '/portfolio/create/',                    'icon': 'plus-circle',      'color': 'success'})
    if _has_perm(permissions, 'securities-create', 'WRITE'):
        actions.append({'label': 'New Security',    'url': '/security/create/',                     'icon': 'plus-circle',      'color': 'info'})
    if _has_perm(permissions, 'corp-action-create', 'WRITE'):
        actions.append({'label': 'New Corp. Action','url': '/reference-data/corporate-action/create/', 'icon': 'building',      'color': 'warning'})
    if _has_perm(permissions, 'upload-list', 'WRITE'):
        actions.append({'label': 'Upload File',     'url': '/upload/create/',                       'icon': 'cloud-upload',     'color': 'secondary'})
    return actions


def _build_pending_actions(permissions: dict, trade_stats: dict, portfolio_stats: dict) -> list:
    """
    Return list of pending-action items (things needing the user's attention).
    Only shown if the user has approval READ access for that module.
    """
    items = []
    if _has_perm(permissions, 'trade-approval', 'READ'):
        pv = trade_stats.get('pending_validation', 0)
        ps = trade_stats.get('pending_settlement', 0)
        if pv:
            items.append({'label': f'{pv} trade{"s" if pv != 1 else ""} pending validation',
                          'url': '/trade/pending-validation/', 'icon': 'hourglass-split', 'color': 'warning'})
        if ps:
            items.append({'label': f'{ps} trade{"s" if ps != 1 else ""} pending settlement',
                          'url': '/trade/pending-settlement/', 'icon': 'clock-history', 'color': 'info'})
    if _has_perm(permissions, 'portfolio-approval', 'READ'):
        pp = portfolio_stats.get('pending_approvals', 0) if portfolio_stats else 0
        if pp:
            items.append({'label': f'{pp} portfolio{"s" if pp != 1 else ""} pending approval',
                          'url': '/portfolio/pending-validation/', 'icon': 'briefcase', 'color': 'primary'})
    return items


@require_login
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    UAM-aware dashboard.
    Stats and quick-links are scoped to the logged-in user's permissions.
    Only sections the user has READ access to are queried and rendered.
    """
    permissions = request.session.get('user_permissions', {})
    sections = _build_sections(permissions)

    # ── User info ─────────────────────────────────────────────────────────────
    user_info = {
        'login':   request.session.get('user_login'),
        'name':    request.session.get('user_name'),
        'email':   request.session.get('user_email'),
        'group':   request.session.get('user_group_name'),
        'groups':  request.session.get('user_group_names') or [request.session.get('user_group_name')] or [],
    }

    # ── Scoped stat queries — only fetch what the user can see ────────────────
    portfolio_stats = {}
    if sections['portfolio']:
        portfolio_stats = query_cache.get('dashboard_portfolio_stats')
        if portfolio_stats is None:
            try:
                portfolio_stats = portfolio_hive_repository.get_portfolio_statistics()
            except Exception as e:
                logger.error(f"Error fetching portfolio statistics: {e}")
                portfolio_stats = {'total_portfolios': 0, 'active_portfolios': 0,
                                   'currency_breakdown': [], 'pending_approvals': 0}
            query_cache.set('dashboard_portfolio_stats', portfolio_stats, _DASHBOARD_CACHE_TTL)

    trade_stats = {}
    if sections['trade']:
        try:
            trade_stats = trade_kudu_repository.get_trade_statistics()
        except Exception as e:
            logger.error(f"Error fetching trade statistics: {e}")
            trade_stats = {'total_trades': 0, 'pending_validation': 0,
                           'pending_settlement': 0, 'settled': 0,
                           'status_breakdown': {}, 'type_breakdown': {}}

    fx_stats = {}
    if sections['market_data']:
        fx_stats = query_cache.get('dashboard_fx_stats')
        if fx_stats is None:
            try:
                fx_stats = fx_rate_hive_repository.get_statistics()
            except Exception as e:
                logger.error(f"Error fetching FX rate statistics: {e}")
                fx_stats = {'total_records': 0, 'unique_pairs': 0,
                            'latest_processing_date': 'N/A', 'processing_date_breakdown': []}
            query_cache.set('dashboard_fx_stats', fx_stats, _DASHBOARD_CACHE_TTL)

    security_stats = {}
    if sections['securities']:
        security_stats = query_cache.get('dashboard_security_stats')
        if security_stats is None:
            try:
                security_stats = security_hive_repository.get_statistics()
            except Exception as e:
                logger.error(f"Error fetching security statistics: {e}")
                security_stats = {'total_securities': 0, 'active_securities': 0, 'pending_approvals': 0}
            query_cache.set('dashboard_security_stats', security_stats, _DASHBOARD_CACHE_TTL)

    # ── Action helpers ────────────────────────────────────────────────────────
    quick_actions   = _build_quick_actions(permissions)
    pending_actions = _build_pending_actions(permissions, trade_stats, portfolio_stats)

    context = {
        'user':            user_info,
        'sections':        sections,
        'quick_actions':   quick_actions,
        'pending_actions': pending_actions,
        'portfolio_stats': portfolio_stats,
        'trade_stats':     trade_stats,
        'fx_stats':        fx_stats,
        'security_stats':  security_stats,
        'page_title':      'Dashboard',
    }

    return render(request, 'core/dashboard.html', context)


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@require_login
def global_search_view(request: HttpRequest) -> HttpResponse:
    """
    Global search across all modules.
    """
    query = request.GET.get('q', '').strip()

    results = {
        'portfolios': [],
        'udfs': [],
        'currencies': [],
        'countries': [],
        'counterparties': [],
        'fx_rates': [],
    }

    total_results = 0

    if query and len(query) >= 2:
        try:
            all_portfolios = portfolio_hive_repository.get_all_portfolios(limit=1000)
            results['portfolios'] = [
                p for p in all_portfolios
                if query.upper() in (p.get('name') or '').upper() or
                   query.upper() in (p.get('description') or '').upper() or
                   query.upper() in (p.get('portfolio_group') or '').upper()
            ][:10]
            total_results += len(results['portfolios'])
        except Exception as e:
            logger.error(f"Error searching portfolios: {e}")

        try:
            all_udfs = udf_repository.get_all_definitions()
            results['udfs'] = [
                u for u in all_udfs
                if query.upper() in u.get('field_code', '').upper() or
                   query.lower() in u.get('field_name', '').lower()
            ][:10]
            total_results += len(results['udfs'])
        except Exception as e:
            logger.error(f"Error searching UDFs: {e}")

        try:
            all_currencies = currency_repository.list_all()
            results['currencies'] = [
                c for c in all_currencies
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['currencies'])
        except Exception as e:
            logger.error(f"Error searching currencies: {e}")

        try:
            all_countries = country_repository.list_all()
            results['countries'] = [
                c for c in all_countries
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['countries'])
        except Exception as e:
            logger.error(f"Error searching countries: {e}")

        try:
            all_counterparties = counterparty_repository.list_all()
            results['counterparties'] = [
                c for c in all_counterparties
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['counterparties'])
        except Exception as e:
            logger.error(f"Error searching counterparties: {e}")

        try:
            all_fx_rates = fx_rate_hive_repository.get_all_fx_rates(limit=1000)
            results['fx_rates'] = [
                fx for fx in all_fx_rates
                if query.upper() in fx.get('currency_pair', '').upper() or
                   query.upper() in fx.get('base_currency', '').upper() or
                   query.upper() in fx.get('quote_currency', '').upper() or
                   query.upper() in fx.get('source', '').upper()
            ][:10]
            total_results += len(results['fx_rates'])
        except Exception as e:
            logger.error(f"Error searching FX rates: {e}")

        try:
            user_id    = request.session.get('user_id', '')
            username   = request.session.get('user_login', '')
            user_email = request.session.get('user_email', '')
            audit_log_kudu_repository.log_action(
                user_id=user_id, username=username, user_email=user_email,
                action_type='SEARCH', entity_type='GLOBAL',
                entity_name='Global Search', entity_id='GLOBAL_SEARCH',
                action_description=f"Global search: '{query}' ({total_results} results)",
                request_method=request.method, request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS',
            )
        except Exception as e:
            logger.error(f"Error logging search to audit: {e}")

    context = {
        'query': query,
        'results': results,
        'total_results': total_results,
        'page_title': f'Search Results: {query}' if query else 'Search',
    }

    return render(request, 'core/search_results.html', context)
