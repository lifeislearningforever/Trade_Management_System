"""
Reference Data Views

Provides list views with filtering, search, and CSV export.
Follows Single Responsibility: Each view handles one entity type.
"""

import csv
import json
import logging
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from core.models import AuditLog
from core.audit.audit_kudu_repository import audit_log_kudu_repository
from core.views.auth_views import require_login, require_permission
from .services.reference_data_service import (
    currency_service,
    country_service,
    calendar_service,
    counterparty_service
)
from .services.counterparty_cif_service import counterparty_cif_service
from .services.party_service import party_service, party_cif_service

logger = logging.getLogger('reference_data')


def get_client_ip(request):
    """Helper to get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


@require_login
def currency_list(request):
    """
    Currency list view with search, filter, and CSV export.
    Requires: Authentication
    """
    # Get query parameters
    search = request.GET.get('search', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Fetch data
        currencies = currency_service.list_all(search=search if search else None)

        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')
        user_full_name = username  # ACL doesn't have full name

        # Commented out VIEW/SEARCH audit logging (only log CREATE, UPDATE, DELETE)
        # audit_log_kudu_repository.log_action(
        #     user_id=user_id,
        #     username=username,
        #     user_email=user_email,
        #     action_type='VIEW' if not search else 'SEARCH',
        #     entity_type='REFERENCE_DATA',
        #     entity_name='Currency',
        #     entity_id='CURRENCY_LIST',
        #     action_description=f"Viewed currency list ({len(currencies)} records)" + (f" - Search: {search}" if search else ""),
        #     request_method=request.method,
        #     request_path=request.path,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        #     status='SUCCESS'
        # )

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

            # Log EXPORT action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='REFERENCE_DATA',
                entity_name='Currency',
                entity_id='CURRENCY_EXPORT',
                action_description=f'Exported {len(currencies)} currencies to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
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


@require_login
def country_list(request):
    """
    Country list view with search, filter, and CSV export.
    Requires: Authentication
    """
    search = request.GET.get('search', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Fetch data
        countries = country_service.list_all(search=search if search else None)

        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')
        user_full_name = username  # ACL doesn't have full name

        # Commented out VIEW/SEARCH audit logging (only log CREATE, UPDATE, DELETE)
        # audit_log_kudu_repository.log_action(
        #     user_id=user_id,
        #     username=username,
        #     user_email=user_email,
        #     action_type='VIEW' if not search else 'SEARCH',
        #     entity_type='REFERENCE_DATA',
        #     entity_name='Country',
        #     entity_id='COUNTRY_LIST',
        #     action_description=f"Viewed country list ({len(countries)} records)" + (f" - Search: {search}" if search else ""),
        #     request_method=request.method,
        #     request_path=request.path,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        #     status='SUCCESS'
        # )

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

            # Log EXPORT action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='REFERENCE_DATA',
                entity_name='Country',
                entity_id='COUNTRY_EXPORT',
                action_description=f'Exported {len(countries)} countries to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
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


@require_login
def calendar_list(request):
    """
    Calendar/Holiday list view with filtering and CSV export.
    Requires: Authentication
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

        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')
        user_full_name = username  # ACL doesn't have full name

        # Commented out VIEW/SEARCH audit logging (only log CREATE, UPDATE, DELETE)
        # audit_log_kudu_repository.log_action(
        #     user_id=user_id,
        #     username=username,
        #     user_email=user_email,
        #     action_type='VIEW' if not search else 'SEARCH',
        #     entity_type='REFERENCE_DATA',
        #     entity_name='Calendar',
        #     entity_id='CALENDAR_LIST',
        #     action_description=f"Viewed calendar list ({len(calendars)} records)" + (f" - Search: {search}" if search else ""),
        #     request_method=request.method,
        #     request_path=request.path,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        #     status='SUCCESS'
        # )

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

            # Log EXPORT action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='REFERENCE_DATA',
                entity_name='Calendar',
                entity_id='CALENDAR_EXPORT',
                action_description=f'Exported {len(calendars)} calendar entries to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
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


@require_login
def counterparty_list(request):
    """
    Counterparty list view with filtering and CSV export - Now using cis_counterparty_kudu table
    Requires: Authentication
    """
    search = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    status_filter = request.GET.get('status', 'active').strip()
    cif_filter = request.GET.get('cif_filter', '').strip()  # New: Filter for multiple CIFs
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Determine is_active filter
        is_active = None
        if status_filter == 'active':
            is_active = True
        elif status_filter == 'inactive':
            is_active = False

        # Filter for counterparties with multiple CIFs (optimized - database-level filtering)
        if cif_filter == 'multiple':
            # Get list of counterparty names with multiple CIFs in a single optimized query
            multi_cif_names = counterparty_cif_service.get_counterparties_with_multiple_cifs(is_active=True)

            # Fetch all counterparties first
            counterparties = counterparty_service.list_all(
                search=search if search else None,
                country=country_filter if country_filter else None,
                is_active=is_active
            )

            # Filter to only those with multiple CIFs
            multi_cif_names_set = set(multi_cif_names)  # Convert to set for O(1) lookup
            counterparties = [cp for cp in counterparties if cp.get('counterparty_short_name') in multi_cif_names_set]
        else:
            # Fetch data from new Kudu table
            counterparties = counterparty_service.list_all(
                search=search if search else None,
                country=country_filter if country_filter else None,
                is_active=is_active
            )

        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Log VIEW/SEARCH action to Kudu - Commented out (only log CREATE, UPDATE, DELETE)
        # audit_log_kudu_repository.log_action(
        #     user_id=user_id,
        #     username=username,
        #     user_email=user_email,
        #     action_type='VIEW' if not search else 'SEARCH',
        #     entity_type='REFERENCE_DATA',
        #     entity_name='Counterparty',
        #     entity_id='COUNTERPARTY_LIST',
        #     action_description=f"Viewed counterparty list ({len(counterparties)} records)" + (f" - Search: {search}" if search else ""),
        #     request_method=request.method,
        #     request_path=request.path,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        #     status='SUCCESS'
        # )

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="counterparties_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow([
                'Short Name', 'Full Name', 'M-Label (CIF)', 'City', 'Country',
                'Is Bank', 'Is Broker', 'Is Custodian', 'Is Issuer', 'Status'
            ])

            for cp in counterparties:
                writer.writerow([
                    cp.get('counterparty_short_name', ''),
                    cp.get('counterparty_full_name', ''),
                    cp.get('m_label', ''),
                    cp.get('city', ''),
                    cp.get('country', ''),
                    'Yes' if cp.get('is_bank') else 'No',
                    'Yes' if cp.get('is_broker') else 'No',
                    'Yes' if cp.get('is_custodian') else 'No',
                    'Yes' if cp.get('is_issuer') else 'No',
                    'Active' if cp.get('is_active') else 'Inactive',
                ])

            # Log EXPORT action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='REFERENCE_DATA',
                entity_name='Counterparty',
                entity_id='COUNTERPARTY_EXPORT',
                action_description=f'Exported {len(counterparties)} counterparties to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return response

        # Pagination
        paginator = Paginator(counterparties, 25)
        page_obj = paginator.get_page(page_number)

        # Get distinct countries for filter dropdown
        countries = counterparty_service.get_distinct_countries()

        context = {
            'counterparties': page_obj,
            'search': search,
            'countries': countries,
            'selected_country': country_filter,
            'selected_status': status_filter,
            'cif_filter': cif_filter,  # New: Pass CIF filter to template
            'total_count': len(counterparties),
        }

        return render(request, 'reference_data/counterparty_list.html', context)

    except Exception as e:
        logger.error(f"Error in counterparty_list: {str(e)}")
        messages.error(request, f"Error loading counterparties: {str(e)}")
        return render(request, 'reference_data/counterparty_list.html', {
            'counterparties': [],
            'countries': []
        })


@require_login
def counterparty_detail(request, short_name):
    """
    View counterparty details including all fields and CIFs
    Requires: Authentication
    """
    try:
        # Get counterparty from Kudu by short name
        counterparty = counterparty_service.get_by_short_name(short_name)

        if not counterparty:
            messages.error(request, f"Counterparty '{short_name}' not found")
            return redirect('reference_data:counterparty_list')

        # Get all CIFs for this counterparty
        cifs = counterparty_cif_service.list_cifs_for_counterparty(short_name, is_active=None)

        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Log VIEW action to Kudu - Commented out (only log CREATE, UPDATE, DELETE)
        # audit_log_kudu_repository.log_action(
        #     user_id=user_id,
        #     username=username,
        #     user_email=user_email,
        #     action_type='VIEW',
        #     entity_type='REFERENCE_DATA',
        #     entity_name='Counterparty Detail',
        #     entity_id=short_name,
        #     action_description=f"Viewed counterparty details: {short_name}",
        #     request_method=request.method,
        #     request_path=request.path,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        #     status='SUCCESS'
        # )

        context = {
            'counterparty': counterparty,
            'cifs': cifs,
            'cif_count': len(cifs),
        }

        return render(request, 'reference_data/counterparty_details.html', context)

    except Exception as e:
        logger.error(f"Error in counterparty_detail: {str(e)}")
        messages.error(request, f"Error loading counterparty details: {str(e)}")
        return redirect('reference_data:counterparty_list')


@require_login
def counterparty_create(request):
    """
    Create new counterparty
    Requires: Authentication
    """
    if request.method == 'POST':
        try:
            # Get user info from session
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            # Extract form data
            # Note: m_label is auto-generated from counterparty_short_name in service
            # Note: src_system is automatically set to 'cis' in service
            counterparty_data = {
                'counterparty_short_name': request.POST.get('counterparty_short_name', '').strip(),
                'counterparty_full_name': request.POST.get('counterparty_full_name', '').strip(),
                'record_type': request.POST.get('record_type', '').strip(),
                'city': request.POST.get('city', '').strip(),
                'country': request.POST.get('country', '').strip(),
                'postal_code': request.POST.get('postal_code', '').strip(),
                'primary_contact': request.POST.get('primary_contact', '').strip(),
                'primary_number': request.POST.get('primary_number', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'is_bank': request.POST.get('is_bank') == 'on',
                'is_broker': request.POST.get('is_broker') == 'on',
                'is_custodian': request.POST.get('is_custodian') == 'on',
                'is_issuer': request.POST.get('is_issuer') == 'on',
            }

            user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

            # Create counterparty
            success, error_msg = counterparty_service.create_counterparty(counterparty_data, user_info)

            if success:
                # Handle CIF data
                # Note: m_label for CIFs is auto-generated in the service
                cif_countries = request.POST.getlist('cif_country[]')
                cif_isins = request.POST.getlist('cif_isin[]')
                cif_descriptions = request.POST.getlist('cif_description[]')

                # Create CIFs
                counterparty_short_name = counterparty_data['counterparty_short_name']
                cif_count = 0
                for i in range(len(cif_countries)):
                    if cif_countries[i]:  # Country is required
                        cif_data = {
                            'counterparty_short_name': counterparty_short_name,
                            'country': cif_countries[i],
                            'isin': cif_isins[i] if i < len(cif_isins) else '',
                            'description': cif_descriptions[i] if i < len(cif_descriptions) else '',
                            'created_by': username,
                            'updated_by': username,
                        }
                        try:
                            counterparty_cif_service.create_cif(cif_data, user_info)
                            cif_count += 1
                        except Exception as cif_error:
                            logger.error(f"Error creating CIF: {str(cif_error)}")

                # Log CREATE action to Kudu
                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='CREATE',
                    entity_type='REFERENCE_DATA',
                    entity_name='Counterparty',
                    entity_id=counterparty_data['counterparty_short_name'],
                    action_description=f"Created counterparty: {counterparty_data['counterparty_short_name']}" + (f" with {cif_count} CIF(s)" if cif_count > 0 else ""),
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, f"Counterparty '{counterparty_data['counterparty_short_name']}' created successfully" + (f" with {cif_count} CIF(s)" if cif_count > 0 else ""))
                return redirect('reference_data:counterparty_list')
            else:
                messages.error(request, error_msg)

        except Exception as e:
            logger.error(f"Error creating counterparty: {str(e)}")
            messages.error(request, f"Error creating counterparty: {str(e)}")

    # GET request - show form with countries
    countries = country_service.list_all()
    context = {
        'countries': countries,
    }
    return render(request, 'reference_data/counterparty_form.html', context)


@require_login
def counterparty_edit(request, short_name):
    """
    Edit existing counterparty
    Requires: Authentication
    """
    try:
        # Get existing counterparty
        counterparty = counterparty_service.get_by_short_name(short_name)
        if not counterparty:
            messages.error(request, f"Counterparty '{short_name}' not found")
            return redirect('reference_data:counterparty_list')

        # Check if counterparty is editable (only src_system='cis')
        if not counterparty_service.can_edit_counterparty(counterparty):
            src_system = counterparty.get('src_system', 'unknown')
            messages.warning(request, f"Cannot edit counterparty from source system '{src_system}'. Only CIS records are editable.")
            return redirect('reference_data:counterparty_list')

        if request.method == 'POST':
            # Get user info from session
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            # Extract form data
            # Note: m_label and src_system are preserved from existing record in service
            counterparty_data = {
                'counterparty_full_name': request.POST.get('counterparty_full_name', '').strip(),
                'record_type': request.POST.get('record_type', '').strip(),
                'city': request.POST.get('city', '').strip(),
                'country': request.POST.get('country', '').strip(),
                'postal_code': request.POST.get('postal_code', '').strip(),
                'primary_contact': request.POST.get('primary_contact', '').strip(),
                'primary_number': request.POST.get('primary_number', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'is_bank': request.POST.get('is_bank') == 'on',
                'is_broker': request.POST.get('is_broker') == 'on',
                'is_custodian': request.POST.get('is_custodian') == 'on',
                'is_issuer': request.POST.get('is_issuer') == 'on',
            }

            user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

            # Update counterparty
            success, error_msg = counterparty_service.update_counterparty(short_name, counterparty_data, user_info)

            if success:
                # Handle CIF data
                # Note: m_label for CIFs is auto-generated in the service
                cif_countries = request.POST.getlist('cif_country[]')
                cif_isins = request.POST.getlist('cif_isin[]')
                cif_descriptions = request.POST.getlist('cif_description[]')

                # Create new CIFs
                cif_count = 0
                for i in range(len(cif_countries)):
                    if cif_countries[i]:  # Country is required
                        cif_data = {
                            'counterparty_short_name': short_name,
                            'country': cif_countries[i],
                            'isin': cif_isins[i] if i < len(cif_isins) else '',
                            'description': cif_descriptions[i] if i < len(cif_descriptions) else '',
                            'created_by': username,
                            'updated_by': username,
                        }
                        try:
                            counterparty_cif_service.create_cif(cif_data, user_info)
                            cif_count += 1
                        except Exception as cif_error:
                            logger.error(f"Error creating CIF: {str(cif_error)}")

                # Track changes for audit
                old_values = {}
                new_values = {}
                changed_fields = []

                trackable_fields = ['counterparty_full_name', 'record_type', 'city', 'country',
                                   'postal_code', 'primary_contact', 'primary_number', 'industry',
                                   'is_bank', 'is_broker', 'is_custodian', 'is_issuer']

                for field in trackable_fields:
                    old_val = counterparty.get(field, '')
                    new_val = counterparty_data.get(field, '')
                    if str(old_val) != str(new_val):
                        old_values[field] = old_val
                        new_values[field] = new_val
                        changed_fields.append(field)

                # Log UPDATE action to Kudu with old_value and new_value
                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='UPDATE',
                    entity_type='REFERENCE_DATA',
                    entity_name='Counterparty',
                    entity_id=short_name,
                    action_description=f"Updated counterparty: {short_name} - Changed fields: {', '.join(changed_fields) if changed_fields else 'No changes'}" + (f" and added {cif_count} CIF(s)" if cif_count > 0 else ""),
                    old_value=json.dumps(old_values, default=str) if old_values else None,
                    new_value=json.dumps(new_values, default=str) if new_values else None,
                    field_name=', '.join(changed_fields) if changed_fields else None,
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, f"Counterparty '{short_name}' updated successfully" + (f" and added {cif_count} CIF(s)" if cif_count > 0 else ""))

                # Redirect back to the page with filters preserved
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('reference_data:counterparty_list')
            else:
                messages.error(request, error_msg)

        # GET request - show form with existing data, countries, and existing CIFs
        countries = country_service.list_all()
        existing_cifs = counterparty_cif_service.list_cifs_for_counterparty(short_name, is_active=True)

        context = {
            'counterparty': counterparty,
            'countries': countries,
            'existing_cifs': existing_cifs,
            'next_url': request.GET.get('next', ''),
            'is_edit': True
        }
        return render(request, 'reference_data/counterparty_form.html', context)

    except Exception as e:
        logger.error(f"Error editing counterparty: {str(e)}")
        messages.error(request, f"Error editing counterparty: {str(e)}")
        return redirect('reference_data:counterparty_list')


@require_login
def counterparty_delete(request, short_name):
    """
    Soft delete counterparty (POST only)
    Requires: Authentication
    """
    if request.method != 'POST':
        return redirect('reference_data:counterparty_list')

    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        # Delete counterparty
        success, error_msg = counterparty_service.delete_counterparty(short_name, user_info)

        if success:
            # Log DELETE action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='DELETE',
                entity_type='REFERENCE_DATA',
                entity_name='Counterparty',
                entity_id=short_name,
                action_description=f"Deleted counterparty: {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f"Counterparty '{short_name}' deleted successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error deleting counterparty: {str(e)}")
        messages.error(request, f"Error deleting counterparty: {str(e)}")

    return redirect('reference_data:counterparty_list')


@require_login
def counterparty_restore(request, short_name):
    """
    Restore soft-deleted counterparty (POST only)
    Requires: Authentication
    """
    if request.method != 'POST':
        return redirect('reference_data:counterparty_list')

    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        # Restore counterparty
        success, error_msg = counterparty_service.restore_counterparty(short_name, user_info)

        if success:
            # Log RESTORE action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='RESTORE',
                entity_type='REFERENCE_DATA',
                entity_name='Counterparty',
                entity_id=short_name,
                action_description=f"Restored counterparty: {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f"Counterparty '{short_name}' restored successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error restoring counterparty: {str(e)}")
        messages.error(request, f"Error restoring counterparty: {str(e)}")

    return redirect('reference_data:counterparty_list')


# ============================================================================
# Counterparty CIF Views (AJAX API)
# ============================================================================

@require_login
@require_http_methods(["GET"])
def counterparty_cif_list(request, short_name):
    """
    Get all CIFs for a counterparty (AJAX endpoint)
    Returns: JSON response with CIF list
    """
    try:
        cifs = counterparty_cif_service.list_cifs_for_counterparty(short_name, is_active=True)

        return JsonResponse({
            'success': True,
            'cifs': cifs,
            'count': len(cifs)
        })

    except Exception as e:
        logger.error(f"Error fetching CIFs for {short_name}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def counterparty_cif_create(request, short_name):
    """
    Create new CIF for a counterparty (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Parse JSON body
        data = json.loads(request.body)

        # Build CIF data
        cif_data = {
            'counterparty_short_name': short_name,
            'm_label': data.get('m_label', '').strip(),
            'country': data.get('country', '').strip(),
            'isin': data.get('isin', '').strip(),
            'description': data.get('description', '').strip(),
        }

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        # Create CIF
        success, error_msg = counterparty_cif_service.create_cif(cif_data, user_info)

        if success:
            # Log CREATE action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='COUNTERPARTY_CIF',
                entity_name='Counterparty CIF',
                entity_id=f"{short_name}:{cif_data['m_label']}",
                action_description=f"Created CIF {cif_data['m_label']} for counterparty {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF '{cif_data['m_label']}' created successfully"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def counterparty_cif_update(request, short_name, m_label):
    """
    Update existing CIF (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Get existing CIF for change tracking
        existing_cif = counterparty_cif_service.get_cif(short_name, m_label)

        # Parse JSON body
        data = json.loads(request.body)

        # Build CIF data
        cif_data = {
            'country': data.get('country', '').strip(),
            'isin': data.get('isin', '').strip(),
            'description': data.get('description', '').strip(),
        }

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        # Update CIF
        success, error_msg = counterparty_cif_service.update_cif(short_name, m_label, cif_data, user_info)

        if success:
            # Track changes for audit
            old_values = {}
            new_values = {}
            changed_fields = []

            if existing_cif:
                trackable_fields = ['country', 'isin', 'description']
                for field in trackable_fields:
                    old_val = existing_cif.get(field, '')
                    new_val = cif_data.get(field, '')
                    if str(old_val) != str(new_val):
                        old_values[field] = old_val
                        new_values[field] = new_val
                        changed_fields.append(field)

            # Log UPDATE action to Kudu with old_value and new_value
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='UPDATE',
                entity_type='COUNTERPARTY_CIF',
                entity_name='Counterparty CIF',
                entity_id=f"{short_name}:{m_label}",
                action_description=f"Updated CIF {m_label} for counterparty {short_name} - Changed fields: {', '.join(changed_fields) if changed_fields else 'No changes'}",
                old_value=json.dumps(old_values, default=str) if old_values else None,
                new_value=json.dumps(new_values, default=str) if new_values else None,
                field_name=', '.join(changed_fields) if changed_fields else None,
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF '{m_label}' updated successfully"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def counterparty_cif_delete(request, short_name, m_label):
    """
    Soft delete CIF (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        # Delete CIF
        success, error_msg = counterparty_cif_service.delete_cif(short_name, m_label, user_info)

        if success:
            # Log DELETE action to Kudu
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='DELETE',
                entity_type='COUNTERPARTY_CIF',
                entity_name='Counterparty CIF',
                entity_id=f"{short_name}:{m_label}",
                action_description=f"Deleted CIF {m_label} for counterparty {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF '{m_label}' deleted successfully"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except Exception as e:
        logger.error(f"Error deleting CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ============================================================================
# Party Views (New naming - uses cis_party and cis_party_cif tables)
# ============================================================================

@require_login
def party_list(request):
    """
    Party list view with filtering and CSV export - Uses cis_party table
    Requires: Authentication
    """
    search = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    status_filter = request.GET.get('status', 'active').strip()
    cif_filter = request.GET.get('cif_filter', '').strip()
    export = request.GET.get('export') == 'csv'
    page_number = request.GET.get('page', 1)

    try:
        # Determine is_active filter
        is_active = None
        if status_filter == 'active':
            is_active = True
        elif status_filter == 'inactive':
            is_active = False

        # Filter for parties with multiple CIFs
        if cif_filter == 'multiple':
            multi_cif_names = party_cif_service.get_parties_with_multiple_cifs(is_active=True)
            parties = party_service.list_all(
                search=search if search else None,
                country=country_filter if country_filter else None,
                is_active=is_active
            )
            multi_cif_names_set = set(multi_cif_names)
            parties = [p for p in parties if p.get('party_short_name') in multi_cif_names_set]
        else:
            parties = party_service.list_all(
                search=search if search else None,
                country=country_filter if country_filter else None,
                is_active=is_active
            )

        # Get user info from session
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # CSV Export
        if export:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="parties_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

            writer = csv.writer(response)
            writer.writerow([
                'Short Name', 'Full Name', 'GICS Code', 'Industry', 'Industry Group',
                'MAS Industry Code', 'Resident Y/N', 'Subsidiary Level',
                'Party Grandparent', 'Party Parent',
                'Address Line 1', 'Address Line 2', 'Address Line 3', 'Address Line 4',
                'City', 'Country', 'Postal Code', 'Country of Incorporation',
                'Primary Contact', 'Primary Number', 'Other Contact', 'Other Number',
                'Fax Number', 'Telex Number',
                'Is Bank', 'Is Broker', 'Is Custodian', 'Is Issuer', 'Is Corporate', 'Is Subsidiary',
                'Status', 'Source System'
            ])

            for party in parties:
                writer.writerow([
                    party.get('party_short_name', ''),
                    party.get('party_full_name', ''),
                    party.get('gics_code', ''),
                    party.get('industry', ''),
                    party.get('industry_group', ''),
                    party.get('mas_industry_code', ''),
                    party.get('resident_y_n', ''),
                    party.get('subsidiary_level', ''),
                    party.get('party_grandparent', ''),
                    party.get('party_parent', ''),
                    party.get('address_line_0', ''),
                    party.get('address_line_1', ''),
                    party.get('address_line_2', ''),
                    party.get('address_line_3', ''),
                    party.get('city', ''),
                    party.get('country', ''),
                    party.get('postal_code', ''),
                    party.get('country_of_incorporation', ''),
                    party.get('primary_contact', ''),
                    party.get('primary_number', ''),
                    party.get('other_contact', ''),
                    party.get('other_number', ''),
                    party.get('fax_number', ''),
                    party.get('telex_number', ''),
                    'Yes' if party.get('is_bank') else 'No',
                    'Yes' if party.get('is_broker') else 'No',
                    'Yes' if party.get('is_custodian') else 'No',
                    'Yes' if party.get('is_issuer') else 'No',
                    'Yes' if party.get('is_corporate') else 'No',
                    'Yes' if party.get('is_subsidiary') else 'No',
                    'Active' if party.get('is_active') else 'Inactive',
                    party.get('src_system', ''),
                ])

            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='EXPORT',
                entity_type='REFERENCE_DATA',
                entity_name='Party',
                entity_id='PARTY_EXPORT',
                action_description=f'Exported {len(parties)} parties to CSV',
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return response

        # Pagination
        paginator = Paginator(parties, 25)
        page_obj = paginator.get_page(page_number)

        # Get distinct countries for filter dropdown
        countries = party_service.get_distinct_countries()

        context = {
            'parties': page_obj,
            'search': search,
            'countries': countries,
            'selected_country': country_filter,
            'selected_status': status_filter,
            'cif_filter': cif_filter,
            'total_count': len(parties),
        }

        return render(request, 'reference_data/party_list.html', context)

    except Exception as e:
        logger.error(f"Error in party_list: {str(e)}")
        messages.error(request, f"Error loading parties: {str(e)}")
        return render(request, 'reference_data/party_list.html', {
            'parties': [],
            'countries': []
        })


@require_login
def party_detail(request, short_name):
    """
    View party details including all fields and CIFs
    Requires: Authentication
    """
    try:
        party = party_service.get_by_short_name(short_name)

        if not party:
            messages.error(request, f"Party '{short_name}' not found")
            return redirect('reference_data:party_list')

        # Get all CIFs for this party
        cifs = party_cif_service.list_cifs_for_party(short_name, is_active=None)

        context = {
            'party': party,
            'cifs': cifs,
            'cif_count': len(cifs),
        }

        return render(request, 'reference_data/party_details.html', context)

    except Exception as e:
        logger.error(f"Error in party_detail: {str(e)}")
        messages.error(request, f"Error loading party details: {str(e)}")
        return redirect('reference_data:party_list')


@require_login
def party_create(request):
    """
    Create new party
    Requires: Authentication
    """
    if request.method == 'POST':
        try:
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            party_data = {
                # Basic Information
                'party_short_name': request.POST.get('party_short_name', '').strip(),
                'party_full_name': request.POST.get('party_full_name', '').strip(),
                'gics_code': request.POST.get('gics_code', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'industry_group': request.POST.get('industry_group', '').strip(),
                'mas_industry_code': request.POST.get('mas_industry_code', '').strip(),
                'resident_y_n': request.POST.get('resident_y_n', '').strip(),
                'subsidiary_level': request.POST.get('subsidiary_level', '').strip(),
                # Hierarchy
                'party_grandparent': request.POST.get('party_grandparent', '').strip(),
                'party_parent': request.POST.get('party_parent', '').strip(),
                # Address
                'address_line_0': request.POST.get('address_line_0', '').strip(),
                'address_line_1': request.POST.get('address_line_1', '').strip(),
                'address_line_2': request.POST.get('address_line_2', '').strip(),
                'address_line_3': request.POST.get('address_line_3', '').strip(),
                'city': request.POST.get('city', '').strip(),
                'country': request.POST.get('country', '').strip(),
                'postal_code': request.POST.get('postal_code', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                # Contact
                'primary_contact': request.POST.get('primary_contact', '').strip(),
                'primary_number': request.POST.get('primary_number', '').strip(),
                'other_contact': request.POST.get('other_contact', '').strip(),
                'other_number': request.POST.get('other_number', '').strip(),
                'fax_number': request.POST.get('fax_number', '').strip(),
                'telex_number': request.POST.get('telex_number', '').strip(),
                # Classification flags
                'is_bank': request.POST.get('is_bank') == 'on',
                'is_broker': request.POST.get('is_broker') == 'on',
                'is_custodian': request.POST.get('is_custodian') == 'on',
                'is_issuer': request.POST.get('is_issuer') == 'on',
                'is_corporate': request.POST.get('is_corporate') == 'on',
                'is_subsidiary': request.POST.get('is_subsidiary') == 'on',
            }

            user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

            success, error_msg = party_service.create_party(party_data, user_info)

            if success:
                # Handle CIF data
                cif_countries = request.POST.getlist('cif_country[]')
                cif_isins = request.POST.getlist('cif_isin[]')
                cif_descriptions = request.POST.getlist('cif_description[]')

                party_short_name = party_data['party_short_name']
                cif_count = 0
                for i in range(len(cif_countries)):
                    if cif_countries[i]:
                        cif_data = {
                            'party_name': party_short_name,
                            'country': cif_countries[i],
                            'isin': cif_isins[i] if i < len(cif_isins) else '',
                            'description': cif_descriptions[i] if i < len(cif_descriptions) else '',
                        }
                        try:
                            party_cif_service.create_cif(cif_data, user_info)
                            cif_count += 1
                        except Exception as cif_error:
                            logger.error(f"Error creating CIF: {str(cif_error)}")

                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='CREATE',
                    entity_type='REFERENCE_DATA',
                    entity_name='Party',
                    entity_id=party_data['party_short_name'],
                    action_description=f"Created party: {party_data['party_short_name']}" + (f" with {cif_count} CIF(s)" if cif_count > 0 else ""),
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, f"Party '{party_data['party_short_name']}' created successfully" + (f" with {cif_count} CIF(s)" if cif_count > 0 else ""))
                return redirect('reference_data:party_list')
            else:
                messages.error(request, error_msg)

        except Exception as e:
            logger.error(f"Error creating party: {str(e)}")
            messages.error(request, f"Error creating party: {str(e)}")

    countries = country_service.list_all()
    context = {
        'countries': countries,
    }
    return render(request, 'reference_data/party_form.html', context)


@require_login
def party_edit(request, short_name):
    """
    Edit existing party
    Requires: Authentication
    """
    try:
        party = party_service.get_by_short_name(short_name)
        if not party:
            messages.error(request, f"Party '{short_name}' not found")
            return redirect('reference_data:party_list')

        if not party_service.can_edit_party(party):
            src_system = party.get('src_system', 'unknown')
            messages.warning(request, f"Cannot edit party from source system '{src_system}'. Only CIS records are editable.")
            return redirect('reference_data:party_list')

        if request.method == 'POST':
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            party_data = {
                # Basic Information
                'party_full_name': request.POST.get('party_full_name', '').strip(),
                'gics_code': request.POST.get('gics_code', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'industry_group': request.POST.get('industry_group', '').strip(),
                'mas_industry_code': request.POST.get('mas_industry_code', '').strip(),
                'resident_y_n': request.POST.get('resident_y_n', '').strip(),
                'subsidiary_level': request.POST.get('subsidiary_level', '').strip(),
                # Hierarchy
                'party_grandparent': request.POST.get('party_grandparent', '').strip(),
                'party_parent': request.POST.get('party_parent', '').strip(),
                # Address
                'address_line_0': request.POST.get('address_line_0', '').strip(),
                'address_line_1': request.POST.get('address_line_1', '').strip(),
                'address_line_2': request.POST.get('address_line_2', '').strip(),
                'address_line_3': request.POST.get('address_line_3', '').strip(),
                'city': request.POST.get('city', '').strip(),
                'country': request.POST.get('country', '').strip(),
                'postal_code': request.POST.get('postal_code', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                # Contact
                'primary_contact': request.POST.get('primary_contact', '').strip(),
                'primary_number': request.POST.get('primary_number', '').strip(),
                'other_contact': request.POST.get('other_contact', '').strip(),
                'other_number': request.POST.get('other_number', '').strip(),
                'fax_number': request.POST.get('fax_number', '').strip(),
                'telex_number': request.POST.get('telex_number', '').strip(),
                # Classification flags
                'is_bank': request.POST.get('is_bank') == 'on',
                'is_broker': request.POST.get('is_broker') == 'on',
                'is_custodian': request.POST.get('is_custodian') == 'on',
                'is_issuer': request.POST.get('is_issuer') == 'on',
                'is_corporate': request.POST.get('is_corporate') == 'on',
                'is_subsidiary': request.POST.get('is_subsidiary') == 'on',
            }

            user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

            success, error_msg = party_service.update_party(short_name, party_data, user_info)

            if success:
                # Handle CIF data
                cif_countries = request.POST.getlist('cif_country[]')
                cif_isins = request.POST.getlist('cif_isin[]')
                cif_descriptions = request.POST.getlist('cif_description[]')

                cif_count = 0
                for i in range(len(cif_countries)):
                    if cif_countries[i]:
                        cif_data = {
                            'party_name': short_name,
                            'country': cif_countries[i],
                            'isin': cif_isins[i] if i < len(cif_isins) else '',
                            'description': cif_descriptions[i] if i < len(cif_descriptions) else '',
                        }
                        try:
                            party_cif_service.create_cif(cif_data, user_info)
                            cif_count += 1
                        except Exception as cif_error:
                            logger.error(f"Error creating CIF: {str(cif_error)}")

                # Track changes for audit
                old_values = {}
                new_values = {}
                changed_fields = []

                trackable_fields = ['party_full_name', 'record_type', 'city', 'country',
                                   'postal_code', 'primary_contact', 'primary_number', 'industry',
                                   'gics_code', 'party_grandparent', 'party_parent',
                                   'is_bank', 'is_broker', 'is_custodian', 'is_issuer',
                                   'is_corporate', 'is_subsidiary']

                for field in trackable_fields:
                    old_val = party.get(field, '')
                    new_val = party_data.get(field, '')
                    if str(old_val) != str(new_val):
                        old_values[field] = old_val
                        new_values[field] = new_val
                        changed_fields.append(field)

                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='UPDATE',
                    entity_type='REFERENCE_DATA',
                    entity_name='Party',
                    entity_id=short_name,
                    action_description=f"Updated party: {short_name} - Changed fields: {', '.join(changed_fields) if changed_fields else 'No changes'}" + (f" and added {cif_count} CIF(s)" if cif_count > 0 else ""),
                    old_value=json.dumps(old_values, default=str) if old_values else None,
                    new_value=json.dumps(new_values, default=str) if new_values else None,
                    field_name=', '.join(changed_fields) if changed_fields else None,
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, f"Party '{short_name}' updated successfully" + (f" and added {cif_count} CIF(s)" if cif_count > 0 else ""))

                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('reference_data:party_list')
            else:
                messages.error(request, error_msg)

        countries = country_service.list_all()
        existing_cifs = party_cif_service.list_cifs_for_party(short_name, is_active=True)

        context = {
            'party': party,
            'countries': countries,
            'existing_cifs': existing_cifs,
            'next_url': request.GET.get('next', ''),
            'is_edit': True
        }
        return render(request, 'reference_data/party_form.html', context)

    except Exception as e:
        logger.error(f"Error editing party: {str(e)}")
        messages.error(request, f"Error editing party: {str(e)}")
        return redirect('reference_data:party_list')


@require_login
def party_delete(request, short_name):
    """
    Soft delete party (POST only)
    Requires: Authentication
    """
    if request.method != 'POST':
        return redirect('reference_data:party_list')

    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        success, error_msg = party_service.delete_party(short_name, user_info)

        if success:
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='DELETE',
                entity_type='REFERENCE_DATA',
                entity_name='Party',
                entity_id=short_name,
                action_description=f"Deleted party: {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f"Party '{short_name}' deleted successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error deleting party: {str(e)}")
        messages.error(request, f"Error deleting party: {str(e)}")

    return redirect('reference_data:party_list')


@require_login
def party_restore(request, short_name):
    """
    Restore soft-deleted party (POST only)
    Requires: Authentication
    """
    if request.method != 'POST':
        return redirect('reference_data:party_list')

    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        success, error_msg = party_service.restore_party(short_name, user_info)

        if success:
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='RESTORE',
                entity_type='REFERENCE_DATA',
                entity_name='Party',
                entity_id=short_name,
                action_description=f"Restored party: {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f"Party '{short_name}' restored successfully")
        else:
            messages.error(request, error_msg)

    except Exception as e:
        logger.error(f"Error restoring party: {str(e)}")
        messages.error(request, f"Error restoring party: {str(e)}")

    return redirect('reference_data:party_list')


# ============================================================================
# Party CIF Views (AJAX API)
# ============================================================================

@require_login
@require_http_methods(["GET"])
def party_cif_list(request, short_name):
    """
    Get all CIFs for a party (AJAX endpoint)
    Returns: JSON response with CIF list
    """
    try:
        cifs = party_cif_service.list_cifs_for_party(short_name, is_active=True)

        return JsonResponse({
            'success': True,
            'cifs': cifs,
            'count': len(cifs)
        })

    except Exception as e:
        logger.error(f"Error fetching CIFs for party {short_name}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def party_cif_create(request, short_name):
    """
    Create new CIF for a party (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        data = json.loads(request.body)

        cif_data = {
            'party_name': short_name,
            'country': data.get('country', '').strip(),
            'isin': data.get('isin', '').strip(),
            'description': data.get('description', '').strip(),
        }

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        success, error_msg = party_cif_service.create_cif(cif_data, user_info)

        if success:
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='PARTY_CIF',
                entity_name='Party CIF',
                entity_id=f"{short_name}:{cif_data.get('country', '')}",
                action_description=f"Created CIF for party {short_name} in country {cif_data.get('country', '')}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF created successfully for party {short_name}"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating party CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def party_cif_update(request, short_name, m_label):
    """
    Update existing party CIF (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        existing_cif = party_cif_service.get_cif(short_name, m_label)

        data = json.loads(request.body)
        country = data.get('country', '').strip()

        cif_data = {
            'isin': data.get('isin', '').strip(),
            'description': data.get('description', '').strip(),
        }

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        success, error_msg = party_cif_service.update_cif(short_name, m_label, country, cif_data, user_info)

        if success:
            old_values = {}
            new_values = {}
            changed_fields = []

            if existing_cif:
                trackable_fields = ['isin', 'description']
                for field in trackable_fields:
                    old_val = existing_cif.get(field, '')
                    new_val = cif_data.get(field, '')
                    if str(old_val) != str(new_val):
                        old_values[field] = old_val
                        new_values[field] = new_val
                        changed_fields.append(field)

            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='UPDATE',
                entity_type='PARTY_CIF',
                entity_name='Party CIF',
                entity_id=f"{short_name}:{m_label}",
                action_description=f"Updated CIF {m_label} for party {short_name} - Changed fields: {', '.join(changed_fields) if changed_fields else 'No changes'}",
                old_value=json.dumps(old_values, default=str) if old_values else None,
                new_value=json.dumps(new_values, default=str) if new_values else None,
                field_name=', '.join(changed_fields) if changed_fields else None,
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF '{m_label}' updated successfully"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating party CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_login
@require_http_methods(["POST"])
def party_cif_delete(request, short_name, m_label):
    """
    Soft delete party CIF (AJAX endpoint)
    Returns: JSON response with success/error
    """
    try:
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # Get country from request body
        data = json.loads(request.body) if request.body else {}
        country = data.get('country', '')

        user_info = {'username': username, 'user_id': user_id, 'user_email': user_email}

        success, error_msg = party_cif_service.delete_cif(short_name, m_label, country, user_info)

        if success:
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='DELETE',
                entity_type='PARTY_CIF',
                entity_name='Party CIF',
                entity_id=f"{short_name}:{m_label}",
                action_description=f"Deleted CIF {m_label} for party {short_name}",
                request_method=request.method,
                request_path=request.path,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            return JsonResponse({
                'success': True,
                'message': f"CIF '{m_label}' deleted successfully"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error deleting party CIF: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
