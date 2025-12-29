"""
Market Data Views
Handles FX Rate operations with Hive integration and CSV export.

Updated to use gmp_cis.gmp_cis_sta_dly_fx_rates external table.
"""

from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
import csv

from market_data.services import fx_rate_service
from core.audit.audit_kudu_repository import audit_log_kudu_repository


class FXRateWrapper:
    """
    Wrapper to convert Hive dict data to object with attributes for template compatibility.

    Updated for gmp_cis_sta_dly_fx_rates external table structure.
    """
    def __init__(self, data, index=0):
        self.data = data

        # Map fields from external table structure
        self.currency_pair = data.get('currency_pair', '')
        self.base_currency = data.get('base_currency', '')
        self.quote_currency = data.get('quote_currency', '')
        self.bid_rate = data.get('bid_rate', 0)
        self.ask_rate = data.get('ask_rate', 0)
        self.mid_rate = data.get('mid_rate', 0)

        # Use mid_rate as the primary rate
        self.rate = self.mid_rate

        # Trade date fields (YYYYMMDD from table, YYYY-MM-DD display from repository)
        self.trade_date = data.get('trade_date', '')
        self.trade_date_display = data.get('trade_date_display', '')
        self.rate_date = self.trade_date_display or self.trade_date  # For backward compatibility

        # ETL processing date (YYYYMMDD - date when file was loaded)
        self.processing_date = data.get('processing_date', '')
        self.processing_date_display = self._format_date(self.processing_date) if self.processing_date else ''

        # Source and reference
        self.source = data.get('source', '')
        self.reference_id = data.get('reference_id', '')

        # Spread (calculated by repository)
        self.spread = data.get('spread', 0)
        self.spread_bps = data.get('spread_bps', 0)  # Basis points

        # Legacy fields for compatibility
        self.is_active = 'true'  # All records in external table are active
        self.rate_time = ''  # No time field in external table

        # Calculate spread percentage for display
        try:
            mid = float(self.mid_rate) if self.mid_rate else 0
            spread_val = float(self.spread) if self.spread else 0
            self.spread_percentage = (spread_val / mid * 100) if mid > 0 else 0
        except (ValueError, TypeError):
            self.spread_percentage = 0

        # Determine freshness based on trade_date
        self.freshness = self._calculate_freshness()

        # Generate ID from hash
        self.id = abs(hash(self.currency_pair + str(self.trade_date) + str(index))) % 1000000

    def _format_date(self, date_str: str) -> str:
        """Format YYYYMMDD to YYYY-MM-DD"""
        if len(date_str) == 8:
            return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    def _calculate_freshness(self):
        """
        Calculate freshness status based on trade_date.

        Since we only have date (not time), we determine freshness by:
        - Same date as today = fresh
        - 1-2 days old = normal
        - >2 days old = stale
        """
        try:
            if not self.trade_date:
                return 'unknown'

            # Parse trade_date (YYYYMMDD format)
            trade_date_str = str(self.trade_date)
            if len(trade_date_str) == 8:
                year = int(trade_date_str[0:4])
                month = int(trade_date_str[4:6])
                day = int(trade_date_str[6:8])
                rate_date = datetime(year, month, day)
            else:
                return 'unknown'

            # Calculate age in days
            today = datetime.now().date()
            age_days = (today - rate_date.date()).days

            if age_days == 0:
                return 'fresh'
            elif age_days <= 2:
                return 'normal'
            else:
                return 'stale'
        except Exception:
            return 'unknown'

    def get_spread(self):
        """Get bid-ask spread"""
        return self.spread

    def get_spread_bps(self):
        """Get bid-ask spread in basis points"""
        return self.spread_bps

    def get_spread_percentage(self):
        """Get bid-ask spread as percentage"""
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
    List all FX rates with search, filter, and CSV export.

    Uses gmp_cis_sta_dly_fx_rates external table via service layer.
    """
    # Get filters
    currency_pair = request.GET.get('currency_pair', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    base_currency = request.GET.get('base_currency', '').strip()
    source_filter = request.GET.get('source', '').strip()
    export = request.GET.get('export', '').strip()

    # Convert date formats from YYYY-MM-DD to YYYYMMDD if provided
    date_from_fmt = date_from.replace('-', '') if date_from else None
    date_to_fmt = date_to.replace('-', '') if date_to else None

    # Get FX rates from service layer
    try:
        fx_rates_data = fx_rate_service.get_fx_rates(
            limit=1000,
            currency_pair=currency_pair if currency_pair else None,
            date_from=date_from_fmt,
            date_to=date_to_fmt,
            base_currency=base_currency if base_currency else None,
            source=source_filter if source_filter else None
        )
    except ValidationError as e:
        fx_rates_data = []
        # TODO: Show error message to user

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
        user_email = request.session.get('user_email', '')

        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
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

    # Get unique currency pairs, base currencies, and sources for filters
    currency_pairs = fx_rate_service.get_currency_pairs()
    base_currencies = fx_rate_service.get_base_currencies()
    sources = fx_rate_service.get_sources()

    # Log view to Hive - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
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
        'base_currency': base_currency,
        'source_filter': source_filter,
        'currency_pairs': currency_pairs,
        'base_currencies': base_currencies,
        'sources': sources,
        'total_count': len(fx_rates_data),
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_list.html', context)


def fx_rate_dashboard(request):
    """
    FX Rate dashboard with statistics and latest rates.

    Uses service layer to get statistics and latest rates.
    """
    # Get statistics from service
    stats = fx_rate_service.get_statistics()

    # Get latest rates for each currency pair
    latest_rates = fx_rate_service.get_latest_rates(limit=100)
    wrapped_latest = [FXRateWrapper(r, idx) for idx, r in enumerate(latest_rates)]

    # Get unique base currencies
    base_currencies = fx_rate_service.get_base_currencies()

    # Log view to Hive - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
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
        'base_currencies': base_currencies,
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_dashboard.html', context)


def fx_rate_detail(request, currency_pair):
    """
    View FX rate details and history for a specific currency pair.

    Uses service layer to get historical rates and trend analysis.
    """
    # Get rate history (last 30 days) from service
    try:
        history = fx_rate_service.get_rate_history(currency_pair, days=30)
    except ValidationError:
        history = []

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
    user_email = request.session.get('user_email', '')

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
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

    # Convert chart data to JSON for JavaScript
    import json
    chart_data_json = json.dumps(chart_data)

    context = {
        'currency_pair': currency_pair,
        'rate': latest_rate,
        'history': wrapped_history[-10:],  # Show last 10 records
        'chart_data': chart_data_json,
        'using_hive': True,
    }

    return render(request, 'market_data/fx_rate_detail.html', context)
