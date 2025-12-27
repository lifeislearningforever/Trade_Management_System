"""
Market Data Views
Handles FX Rate operations with Hive integration and CSV export.
"""

from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime, timedelta
import csv

from market_data.repositories import fx_rate_hive_repository
from core.audit.audit_hive_repository import audit_log_repository


class FXRateWrapper:
    """Wrapper to convert Hive dict data to object with attributes for template compatibility."""
    def __init__(self, data, index=0):
        self.data = data
        # Map all Hive fields to attributes
        self.currency_pair = data.get('currency_pair', '')
        self.base_currency = data.get('base_currency', '')
        self.quote_currency = data.get('quote_currency', '')
        self.rate = data.get('rate', 0)
        self.bid_rate = data.get('bid_rate', 0)
        self.ask_rate = data.get('ask_rate', 0)
        self.mid_rate = data.get('mid_rate', 0)
        self.rate_date = data.get('rate_date', '')
        self.rate_time = data.get('rate_time', '')
        self.source = data.get('source', '')
        self.is_active = data.get('is_active', 'true')
        self.created_at = data.get('created_at', '')
        self.updated_at = data.get('updated_at', '')

        # Calculate spread
        try:
            bid = float(self.bid_rate) if self.bid_rate else 0
            ask = float(self.ask_rate) if self.ask_rate else 0
            mid = float(self.mid_rate) if self.mid_rate else 0
            self.spread = ask - bid if (bid and ask) else 0
            self.spread_percentage = (self.spread / mid * 100) if (mid and self.spread) else 0
        except (ValueError, TypeError):
            self.spread = 0
            self.spread_percentage = 0

        # Determine freshness
        self.freshness = self._calculate_freshness()

        # Generate a simple numeric ID from hash
        self.id = abs(hash(data.get('currency_pair', '') + str(data.get('rate_date', '')) + str(index))) % 1000000

    def _calculate_freshness(self):
        """Calculate freshness status based on rate_time"""
        try:
            if not self.rate_time:
                return 'stale'

            # Parse rate_time
            if isinstance(self.rate_time, str):
                rate_dt = datetime.strptime(self.rate_time, '%Y-%m-%d %H:%M:%S')
            else:
                rate_dt = self.rate_time

            age = datetime.now() - rate_dt
            hours = age.total_seconds() / 3600

            if hours < 1:
                return 'fresh'
            elif hours > 24:
                return 'stale'
            else:
                return 'normal'
        except:
            return 'unknown'

    def get_spread(self):
        """Calculate bid-ask spread"""
        return self.spread

    def get_spread_percentage(self):
        """Calculate bid-ask spread as percentage"""
        return self.spread_percentage

    def get_freshness_status(self):
        """Get freshness status for display"""
        return self.freshness

    def get_freshness_color(self):
        """Get Bootstrap color class for freshness"""
        colors = {
            'fresh': 'success',
            'normal': 'info',
            'stale': 'warning',
            'unknown': 'secondary'
        }
        return colors.get(self.freshness, 'secondary')


def fx_rate_list(request):
    """
    List all FX rates with search, filter, and CSV export - FROM HIVE.
    """
    # Get filters
    currency_pair = request.GET.get('currency_pair', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    source_filter = request.GET.get('source', '').strip()
    export = request.GET.get('export', '').strip()

    # Get FX rates from Hive
    fx_rates_data = fx_rate_hive_repository.get_all_fx_rates(
        limit=1000,
        currency_pair=currency_pair if currency_pair else None,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None,
        source=source_filter if source_filter else None
    )

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="fx_rates.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Currency Pair', 'Base', 'Quote', 'Rate', 'Bid', 'Ask', 'Mid',
            'Spread', 'Spread %', 'Date', 'Time', 'Source', 'Active'
        ])

        for rate_data in fx_rates_data:
            rate = FXRateWrapper(rate_data)
            writer.writerow([
                rate.currency_pair,
                rate.base_currency,
                rate.quote_currency,
                rate.rate,
                rate.bid_rate,
                rate.ask_rate,
                rate.mid_rate,
                f"{rate.spread:.10f}",
                f"{rate.spread_percentage:.4f}",
                rate.rate_date,
                rate.rate_time,
                rate.source,
                rate.is_active
            ])

        # Log export to Hive - Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))

        audit_log_repository.log_action(
            user_id=user_id,
            username=username,
            action_type='EXPORT',
            entity_type='FX_RATE',
            action_description=f'Exported {len(fx_rates_data)} FX rates to CSV from Hive',
            status='SUCCESS',
            request_method='GET',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Wrap dictionaries in objects for template compatibility
    wrapped_rates = [FXRateWrapper(r, idx) for idx, r in enumerate(fx_rates_data)]

    # Pagination
    paginator = Paginator(wrapped_rates, 25)
    page = request.GET.get('page', 1)

    try:
        fx_rates = paginator.page(page)
    except PageNotAnInteger:
        fx_rates = paginator.page(1)
    except EmptyPage:
        fx_rates = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Get unique currency pairs and sources for filters
    currency_pairs = fx_rate_hive_repository.get_currency_pairs()
    sources = ['BLOOMBERG', 'REUTERS', 'MANUAL', 'API', 'HIVE']

    # Log view to Hive - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))

    audit_log_repository.log_action(
        user_id=user_id,
        username=username,
        action_type='VIEW',
        entity_type='FX_RATE',
        action_description=f'Viewed FX rate list from Hive ({len(fx_rates_data)} rates)',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'page_obj': fx_rates,
        'currency_pair': currency_pair,
        'date_from': date_from,
        'date_to': date_to,
        'source_filter': source_filter,
        'currency_pairs': currency_pairs,
        'sources': sources,
        'total_count': len(fx_rates_data),
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_list.html', context)


def fx_rate_dashboard(request):
    """
    FX Rate dashboard with statistics and latest rates.
    """
    # Get statistics
    stats = fx_rate_hive_repository.get_statistics()

    # Get latest rates for each currency pair
    latest_rates = fx_rate_hive_repository.get_latest_rates()
    wrapped_latest = [FXRateWrapper(r, idx) for idx, r in enumerate(latest_rates)]

    # Get unique currencies for matrix
    currencies = fx_rate_hive_repository.get_currencies()

    # Log view to Hive - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))

    audit_log_repository.log_action(
        user_id=user_id,
        username=username,
        action_type='VIEW',
        entity_type='FX_RATE',
        action_description='Viewed FX rate dashboard',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'stats': stats,
        'latest_rates': wrapped_latest[:10],  # Show top 10
        'currencies': currencies,
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_dashboard.html', context)


def fx_rate_detail(request, currency_pair):
    """
    View FX rate details and history for a specific currency pair.
    """
    # Get rate history (last 30 days)
    history = fx_rate_hive_repository.get_rate_history(currency_pair, days=30)

    if not history:
        # No data found
        context = {
            'currency_pair': currency_pair,
            'rate': None,
            'history': [],
            'chart_data': {'dates': [], 'rates': []},
        }
        return render(request, 'market_data/fx_rate_detail.html', context)

    # Get latest rate
    latest_rate_data = history[-1] if history else None
    latest_rate = FXRateWrapper(latest_rate_data) if latest_rate_data else None

    # Wrap history
    wrapped_history = [FXRateWrapper(r, idx) for idx, r in enumerate(history)]

    # Prepare chart data (JSON for Chart.js)
    chart_data = {
        'dates': [r.rate_date for r in wrapped_history],
        'rates': [float(r.rate) if r.rate else 0 for r in wrapped_history],
        'bid_rates': [float(r.bid_rate) if r.bid_rate else 0 for r in wrapped_history],
        'ask_rates': [float(r.ask_rate) if r.ask_rate else 0 for r in wrapped_history],
    }

    # Log view to Hive - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))

    audit_log_repository.log_action(
        user_id=user_id,
        username=username,
        action_type='VIEW',
        entity_type='FX_RATE',
        entity_id=currency_pair,
        action_description=f'Viewed FX rate detail for {currency_pair}',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'currency_pair': currency_pair,
        'rate': latest_rate,
        'history': wrapped_history[-10:],  # Show last 10 records
        'chart_data': chart_data,
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_detail.html', context)
