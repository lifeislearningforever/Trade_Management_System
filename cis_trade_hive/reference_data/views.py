"""
Reference Data Views

Provides list views with filtering, search, and CSV export.
Follows Single Responsibility: Each view handles one entity type.
"""

import csv
import logging
from datetime import datetime
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from core.models import AuditLog
from .services.reference_data_service import (
    currency_service,
    country_service,
    calendar_service,
    counterparty_service
)

logger = logging.getLogger('reference_data')


def get_client_ip(request):
    """Helper to get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


@login_required
def currency_list(request):
    """
    Currency list view with search, filter, and CSV export.
    """
    # Get query parameters
    search = request.GET.get('search', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Fetch data
        currencies = currency_service.list_all(search=search if search else None)

        # Log the read action
        AuditLog.log_action(
            action='READ',
            user=request.user,
            object_type='Currency',
            object_repr=f"Currency List (search: {search if search else 'all'})",
            description=f"Viewed currency list with {len(currencies)} records",
            ip_address=get_client_ip(request),
            request_path=request.path,
        )

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="currencies_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Code', 'Name', 'Full Name', 'Symbol', 'Decimal Places',
                           'Rate Precision', 'Calendar', 'Spot Schedule'])

            for currency in currencies:
                writer.writerow([
                    currency.get('code', ''),
                    currency.get('name', ''),
                    currency.get('full_name', ''),
                    currency.get('symbol', ''),
                    currency.get('decimal_places', ''),
                    currency.get('rate_precision', ''),
                    currency.get('calendar', ''),
                    currency.get('spot_schedule', ''),
                ])

            # Log export
            AuditLog.log_action(
                action='EXPORT',
                user=request.user,
                object_type='Currency',
                object_repr='Currency List CSV Export',
                description=f'Exported {len(currencies)} currencies to CSV',
                ip_address=get_client_ip(request),
            )

            return response

        # Pagination
        paginator = Paginator(currencies, 25)
        page_obj = paginator.get_page(page_number)

        context = {
            'currencies': page_obj,
            'search': search,
            'total_count': len(currencies),
        }

        return render(request, 'reference_data/currency_list.html', context)

    except Exception as e:
        logger.error(f"Error in currency_list: {str(e)}")
        messages.error(request, f"Error loading currencies: {str(e)}")
        return render(request, 'reference_data/currency_list.html', {'currencies': []})


@login_required
def country_list(request):
    """
    Country list view with search, filter, and CSV export.
    """
    search = request.GET.get('search', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Fetch data
        countries = country_service.list_all(search=search if search else None)

        # Log the read action
        AuditLog.log_action(
            action='READ',
            user=request.user,
            object_type='Country',
            object_repr=f"Country List (search: {search if search else 'all'})",
            description=f"Viewed country list with {len(countries)} records",
            ip_address=get_client_ip(request),
            request_path=request.path,
        )

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="countries_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Code', 'Name'])

            for country in countries:
                writer.writerow([
                    country.get('code', ''),
                    country.get('name', ''),
                ])

            # Log export
            AuditLog.log_action(
                action='EXPORT',
                user=request.user,
                object_type='Country',
                object_repr='Country List CSV Export',
                description=f'Exported {len(countries)} countries to CSV',
                ip_address=get_client_ip(request),
            )

            return response

        # Pagination
        paginator = Paginator(countries, 25)
        page_obj = paginator.get_page(page_number)

        context = {
            'countries': page_obj,
            'search': search,
            'total_count': len(countries),
        }

        return render(request, 'reference_data/country_list.html', context)

    except Exception as e:
        logger.error(f"Error in country_list: {str(e)}")
        messages.error(request, f"Error loading countries: {str(e)}")
        return render(request, 'reference_data/country_list.html', {'countries': []})


@login_required
def calendar_list(request):
    """
    Calendar/Holiday list view with filtering and CSV export.
    """
    calendar_label = request.GET.get('calendar', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    search = request.GET.get('search', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Parse dates
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None

        # Fetch data
        calendars = calendar_service.list_all(
            calendar_label=calendar_label if calendar_label else None,
            start_date=start_date_obj,
            end_date=end_date_obj,
            search=search if search else None
        )

        # Get distinct calendar labels for filter dropdown
        calendar_labels = calendar_service.get_distinct_calendars()

        # Log the read action
        AuditLog.log_action(
            action='READ',
            user=request.user,
            object_type='Calendar',
            object_repr=f"Calendar List",
            description=f"Viewed calendar list with {len(calendars)} records",
            ip_address=get_client_ip(request),
            request_path=request.path,
        )

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="calendars_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Calendar Label', 'Description', 'Holiday Date'])

            for cal in calendars:
                writer.writerow([
                    cal.get('calendar_label', ''),
                    cal.get('calendar_description', ''),
                    cal.get('holiday_date', ''),
                ])

            # Log export
            AuditLog.log_action(
                action='EXPORT',
                user=request.user,
                object_type='Calendar',
                object_repr='Calendar List CSV Export',
                description=f'Exported {len(calendars)} calendar entries to CSV',
                ip_address=get_client_ip(request),
            )

            return response

        # Pagination
        paginator = Paginator(calendars, 25)
        page_obj = paginator.get_page(page_number)

        context = {
            'calendars': page_obj,
            'calendar_labels': calendar_labels,
            'selected_calendar': calendar_label,
            'start_date': start_date,
            'end_date': end_date,
            'search': search,
            'total_count': len(calendars),
        }

        return render(request, 'reference_data/calendar_list.html', context)

    except Exception as e:
        logger.error(f"Error in calendar_list: {str(e)}")
        messages.error(request, f"Error loading calendars: {str(e)}")
        return render(request, 'reference_data/calendar_list.html', {
            'calendars': [],
            'calendar_labels': []
        })


@login_required
def counterparty_list(request):
    """
    Counterparty list view with filtering and CSV export.
    """
    search = request.GET.get('search', '').strip()
    counterparty_type = request.GET.get('type', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Fetch data
        counterparties = counterparty_service.list_all(
            search=search if search else None,
            counterparty_type=counterparty_type if counterparty_type else None
        )

        # Log the read action
        AuditLog.log_action(
            action='READ',
            user=request.user,
            object_type='Counterparty',
            object_repr=f"Counterparty List (search: {search if search else 'all'})",
            description=f"Viewed counterparty list with {len(counterparties)} records",
            ip_address=get_client_ip(request),
            request_path=request.path,
        )

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="counterparties_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow(['Code', 'Name', 'Legal Name', 'Type', 'Email',
                           'Phone', 'City', 'Country', 'Status', 'Risk Category'])

            for cp in counterparties:
                writer.writerow([
                    cp.get('code', ''),
                    cp.get('name', ''),
                    cp.get('legal_name', ''),
                    cp.get('counterparty_type', ''),
                    cp.get('email', ''),
                    cp.get('phone', ''),
                    cp.get('city', ''),
                    cp.get('country', ''),
                    cp.get('status', ''),
                    cp.get('risk_category', ''),
                ])

            # Log export
            AuditLog.log_action(
                action='EXPORT',
                user=request.user,
                object_type='Counterparty',
                object_repr='Counterparty List CSV Export',
                description=f'Exported {len(counterparties)} counterparties to CSV',
                ip_address=get_client_ip(request),
            )

            return response

        # Pagination
        paginator = Paginator(counterparties, 25)
        page_obj = paginator.get_page(page_number)

        # Get counterparty types for filter
        counterparty_types = [
            ('BANK', 'Bank'),
            ('BROKER', 'Broker'),
            ('CORPORATE', 'Corporate'),
            ('INDIVIDUAL', 'Individual'),
            ('INSTITUTIONAL', 'Institutional'),
            ('GOVERNMENT', 'Government'),
        ]

        context = {
            'counterparties': page_obj,
            'search': search,
            'counterparty_types': counterparty_types,
            'selected_type': counterparty_type,
            'total_count': len(counterparties),
        }

        return render(request, 'reference_data/counterparty_list.html', context)

    except Exception as e:
        logger.error(f"Error in counterparty_list: {str(e)}")
        messages.error(request, f"Error loading counterparties: {str(e)}")
        return render(request, 'reference_data/counterparty_list.html', {
            'counterparties': [],
            'counterparty_types': []
        })
