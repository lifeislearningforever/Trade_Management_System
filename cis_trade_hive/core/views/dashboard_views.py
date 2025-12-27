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

logger = logging.getLogger(__name__)

# Initialize repositories
udf_repository = UDFDefinitionRepository()
currency_repository = CurrencyRepository()
country_repository = CountryRepository()
counterparty_repository = CounterpartyRepository()
audit_log_kudu_repository = AuditLogKuduRepository()


@require_login
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Main dashboard view.
    Shows user information and navigation to different modules.
    Requires: User to be logged in via ACL authentication
    """
    # Get user info from session
    user_info = {
        'login': request.session.get('user_login'),
        'name': request.session.get('user_name'),
        'email': request.session.get('user_email'),
        'group': request.session.get('user_group_name'),
    }

    # Get permissions from session
    permissions = request.session.get('user_permissions', {})

    # Organize permissions by module
    permission_modules = {
        'portfolio': {
            'name': 'Portfolio Management',
            'access': permissions.get('cis-portfolio', 'NONE'),
            'icon': 'briefcase',
            'url': '/portfolio/',
        },
        'trade': {
            'name': 'Trade Management',
            'access': permissions.get('cis-trade', 'NONE'),
            'icon': 'exchange-alt',
            'url': '/trade/',
        },
        'udf': {
            'name': 'UDF Management',
            'access': permissions.get('cis-udf', 'NONE'),
            'icon': 'tags',
            'url': '/udf/',
        },
        'report': {
            'name': 'Reports',
            'access': permissions.get('cis-report', 'NONE'),
            'icon': 'file-alt',
            'url': '/reports/',
        },
        'currency': {
            'name': 'Currency Reference',
            'access': permissions.get('cis-currency', 'NONE'),
            'icon': 'dollar-sign',
            'url': '/reference-data/currency/',
        },
        'audit': {
            'name': 'Audit Log',
            'access': permissions.get('cis-audit', 'NONE'),
            'icon': 'history',
            'url': '/core/audit-log/',
        },
    }

    # Get portfolio analytics (always show in dev phase)
    portfolio_stats = {}
    try:
        portfolio_stats = portfolio_hive_repository.get_portfolio_statistics()
    except Exception as e:
        logger.error(f"Error fetching portfolio statistics: {str(e)}")
        portfolio_stats = {
            'total_portfolios': 0,
            'active_portfolios': 0,
            'currency_breakdown': []
        }

    context = {
        'user': user_info,
        'permissions': permissions,
        'modules': permission_modules,
        'portfolio_stats': portfolio_stats,
        'page_title': 'Dashboard',
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
    Searches portfolios, UDFs, currencies, countries, and counterparties.
    """
    query = request.GET.get('q', '').strip()

    # Initialize results
    results = {
        'portfolios': [],
        'udfs': [],
        'currencies': [],
        'countries': [],
        'counterparties': [],
    }

    total_results = 0

    if query and len(query) >= 2:  # Minimum 2 characters
        try:
            # Search portfolios (filter by name, description, portfolio_group)
            all_portfolios = portfolio_hive_repository.get_all_portfolios(limit=1000)
            results['portfolios'] = [
                p for p in all_portfolios
                if query.upper() in (p.get('name') or '').upper() or
                   query.upper() in (p.get('description') or '').upper() or
                   query.upper() in (p.get('portfolio_group') or '').upper()
            ][:10]
            total_results += len(results['portfolios'])

        except Exception as e:
            logger.error(f"Error searching portfolios: {str(e)}")

        try:
            # Search UDFs (filter by code or name)
            all_udfs = udf_repository.get_all_definitions()
            results['udfs'] = [
                u for u in all_udfs
                if query.upper() in u.get('field_code', '').upper() or
                   query.lower() in u.get('field_name', '').lower()
            ][:10]
            total_results += len(results['udfs'])

        except Exception as e:
            logger.error(f"Error searching UDFs: {str(e)}")

        try:
            # Search currencies
            all_currencies = currency_repository.list_all()
            results['currencies'] = [
                c for c in all_currencies
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['currencies'])

        except Exception as e:
            logger.error(f"Error searching currencies: {str(e)}")

        try:
            # Search countries
            all_countries = country_repository.list_all()
            results['countries'] = [
                c for c in all_countries
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['countries'])

        except Exception as e:
            logger.error(f"Error searching countries: {str(e)}")

        try:
            # Search counterparties (filter by code or name)
            all_counterparties = counterparty_repository.list_all()
            results['counterparties'] = [
                c for c in all_counterparties
                if query.upper() in c.get('code', '').upper() or
                   query.lower() in c.get('name', '').lower()
            ][:10]
            total_results += len(results['counterparties'])

        except Exception as e:
            logger.error(f"Error searching counterparties: {str(e)}")

        # Log search action to audit
        try:
            user_id = request.session.get('user_id', '')
            username = request.session.get('user_login', '')
            user_email = request.session.get('user_email', '')

            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='SEARCH',
                entity_type='GLOBAL',
                entity_name='Global Search',
                entity_id='GLOBAL_SEARCH',
                action_description=f"Global search: '{query}' ({total_results} results)",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )
        except Exception as e:
            logger.error(f"Error logging search to audit: {str(e)}")

    context = {
        'query': query,
        'results': results,
        'total_results': total_results,
        'page_title': f'Search Results: {query}' if query else 'Search',
    }

    return render(request, 'core/search_results.html', context)
