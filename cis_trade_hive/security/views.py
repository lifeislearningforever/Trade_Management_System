"""
Security Views

HTTP request handlers for security master data.
All data operations use Kudu tables (no Django ORM).
"""

import csv
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse

from core.views.auth_views import require_login, require_permission
from core.services.permission_service import build_permission_context
from security.repositories.security_hive_repository import security_hive_repository
from security.services.security_service import security_service
from security.services.security_dropdown_service import security_dropdown_service
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


@require_login
@require_permission('securities-list', 'READ')
def security_list(request: HttpRequest) -> HttpResponse:
    """
    List all securities with pagination, filters, and CSV export.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Get filters
    status_filter = request.GET.get('status', '')
    search_term = request.GET.get('search', '')
    currency_filter = request.GET.get('currency', '')
    security_type_filter = request.GET.get('security_type', '')
    src_system_filter = request.GET.get('src_system', '')
    export = request.GET.get('export', '').strip()

    # Fetch securities
    securities = security_hive_repository.get_all_securities(
        limit=1000,
        status=status_filter if status_filter else None,
        search=search_term if search_term else None,
        currency=currency_filter if currency_filter else None,
        security_type=security_type_filter if security_type_filter else None,
        src_system=src_system_filter if src_system_filter else None
    )

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="securities.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Security ID', 'Security Name', 'Record Type', 'ISIN', 'Ticker',
            'Description', 'Issuer', 'Industry', 'Security Type', 'Investment Type',
            'Currency', 'Country of Inc.', 'Exchange Code', 'Quoted/Unquoted',
            'Status', 'Source System', 'Created At', 'Created By'
        ])

        for security in securities:
            writer.writerow([
                security.get('security_id', ''),
                security.get('security_name', ''),
                security.get('record_type', ''),
                security.get('isin', ''),
                security.get('ticker', ''),
                security.get('security_description', ''),
                security.get('issuer', ''),
                security.get('industry', ''),
                security.get('security_type', ''),
                security.get('investment_type', ''),
                security.get('currency_code', ''),
                security.get('country_of_incorporation', ''),
                security.get('exchange_code', ''),
                security.get('quoted_unquoted', ''),
                security.get('status', ''),
                security.get('src_system', ''),
                security.get('created_at', ''),
                security.get('created_by', ''),
            ])

        # Log audit for export
        AuditLogKuduRepository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='EXPORT',
            entity_type='SECURITY',
            entity_name='Security List',
            action_description=f'Exported {len(securities)} securities to CSV',
            status='SUCCESS',
            request_method='GET',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Add status color to each security
    for security in securities:
        security['status_color'] = security_service.get_status_display_color(security.get('status', ''))

    # Pagination
    paginator = Paginator(securities, 25)  # 25 per page
    page = request.GET.get('page', 1)

    try:
        securities_page = paginator.page(page)
    except PageNotAnInteger:
        securities_page = paginator.page(1)
    except EmptyPage:
        securities_page = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Build permission context for template
    perms = build_permission_context(request, 'securities')

    # Get pending count for badge
    pending_count = len([s for s in securities if s.get('status') in ('INITIAL', 'MODIFIED') and s.get('src_system', '').upper() == 'CIS'])

    context = {
        'securities': securities_page,
        'page_obj': securities_page,
        'total_count': len(securities),
        'status': status_filter,
        'search': search_term,
        'currency': currency_filter,
        'security_type': security_type_filter,
        'src_system': src_system_filter,
        'pending_count': pending_count,
        # Permission flags
        **perms,
    }

    return render(request, 'security/security_list.html', context)


@require_login
# @check_permission('cis-security', 'READ')  # Commented for demo
def security_detail(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    View security details with history.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Fetch security
    security = security_hive_repository.get_security_by_id(security_id)
    if not security:
        messages.error(request, f'Security {security_id} not found')
        return redirect('security:list')

    # Fetch history
    history = security_hive_repository.get_security_history(security_id, limit=50)

    # Check permissions
    can_edit = security_service.can_user_edit(security, user_id)
    can_validate = security_service.can_user_validate(security, username)
    can_submit = False  # No submit step in simplified flow

    # Get status color
    security['status_color'] = security_service.get_status_display_color(security.get('status', ''))

    # Log audit - Commented out for VIEW actions (only log CREATE, UPDATE, DELETE)
    # AuditLogKuduRepository.log_action(
    #     user_id=user_id,
    #     username=username,
    #     user_email=user_email,
    #     action_type='VIEW',
    #     entity_type='SECURITY',
    #     entity_id=str(security_id),
    #     entity_name=security.get('security_name', ''),
    #     action_description=f'Viewed security detail: {security.get("security_name")}',
    #     status='SUCCESS'
    # )

    context = {
        'security': security,
        'history': history,
        'can_edit': can_edit,
        'can_validate': can_validate,
        'can_submit': can_submit,
    }

    return render(request, 'security/security_detail.html', context)


@require_login
# @check_permission('cis-security', 'CREATE')  # Commented for demo
def security_create(request: HttpRequest) -> HttpResponse:
    """
    Create a new security.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    if request.method == 'POST':
        try:
            def safe_int(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default

            def safe_float(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default

            # Parse all fields directly from POST (flat form, no modals)
            security_data = {
                'record_type': request.POST.get('record_type', '').strip(),
                'security_name': request.POST.get('security_name', '').strip(),
                'isin': request.POST.get('isin', '').strip(),
                'security_description': request.POST.get('security_description', '').strip(),
                'issuer': request.POST.get('issuer', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                'shares_outstanding': safe_int(request.POST.get('shares_outstanding', '')),
                'price': safe_float(request.POST.get('price', '')),
                'country_of_exchange': request.POST.get('country_of_exchange', '').strip(),
                'exchange_code': request.POST.get('exchange_code', '').strip(),
                'currency_code': request.POST.get('currency_code', '').strip(),
                'ticker': request.POST.get('ticker', '').strip(),
                'country_of_issue': request.POST.get('country_of_issue', '').strip(),
                'issuer_type': request.POST.get('issuer_type', '').strip(),
                'quoted_unquoted': request.POST.get('quoted_unquoted', '').strip(),
                'security_type': request.POST.get('security_type', '').strip() or 'COMMON STOCK',  # Default to COMMON STOCK
                'investment_type': request.POST.get('investment_type', '').strip(),
                'market': request.POST.get('market', '').strip(),
                'pct_hld_entity_1': request.POST.get('pct_hld_entity_1', '').strip(),
                'pct_hld_entity_2': request.POST.get('pct_hld_entity_2', '').strip(),
                'pct_hld_entity_3': request.POST.get('pct_hld_entity_3', '').strip(),
                'pct_hld_entity_aggr': request.POST.get('pct_hld_entity_aggr', '').strip(),
                'substantial_10_pct': request.POST.get('substantial_10_pct', '').strip(),
                'cels': request.POST.get('cels', '').strip(),
                'pevc_s32_devest': request.POST.get('pevc_s32_devest', '').strip(),
                's32_representative': request.POST.get('s32_representative', '').strip(),
                'basel_iv_fund': request.POST.get('basel_iv_fund', '').strip(),
                'mas_643_entity_type': request.POST.get('mas_643_entity_type', '').strip(),
                'mas_6d_code': request.POST.get('mas_6d_code', '').strip(),
                'fin_nonfin_ind': request.POST.get('fin_nonfin_ind', '').strip(),
                'beta': safe_float(request.POST.get('beta', '')),
                'par_value': safe_float(request.POST.get('par_value', '')),
                'business_unit_head': request.POST.get('business_unit_head', '').strip(),
                'person_in_charge': request.POST.get('person_in_charge', '').strip(),
                'core_noncore': request.POST.get('core_noncore', '').strip(),
                'fund_index_fund': request.POST.get('fund_index_fund', '').strip(),
                'management_limit_classification': request.POST.get('management_limit_classification', '').strip(),
                'relative_index': request.POST.get('relative_index', '').strip(),
            }

            # Create security (status = INITIAL)
            success, security_id, error = security_service.create_security(
                security_data=security_data,
                user_id=user_id,
                username=username,
                user_email=user_email
            )

            if not success:
                messages.error(request, f'Error creating security: {error}')
                # Re-render form with data
                dropdown_options = security_dropdown_service.get_all_dropdown_options(username)
                context = {
                    'dropdown_options': dropdown_options,
                    'security': security_data,
                }
                return render(request, 'security/security_form.html', context)

            messages.success(request, f'Security "{security_data["security_name"]}" created successfully')

            return redirect('security:detail', security_id=security_id)

        except Exception as e:
            logger.error(f"Error creating security: {str(e)}")
            messages.error(request, f'Error creating security: {str(e)}')

    # GET request - show form
    dropdown_options = security_dropdown_service.get_all_dropdown_options(username)

    context = {
        'dropdown_options': dropdown_options,
    }

    return render(request, 'security/security_form.html', context)


@require_login
# @check_permission('cis-security', 'UPDATE')  # Commented for demo
def security_edit(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    Edit an existing security.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Fetch existing security
    security = security_hive_repository.get_security_by_id(security_id)
    if not security:
        messages.error(request, f'Security {security_id} not found')
        return redirect('security:list')

    # Check if editable (only CIS src_system records)
    if not security_service.can_user_edit(security, user_id):
        messages.error(request, f'Cannot edit security with source system {security.get("src_system")}. Only CIS records can be edited.')
        return redirect('security:detail', security_id=security_id)

    if request.method == 'POST':
        try:
            def safe_int(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default

            def safe_float(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default

            # Parse all fields directly from POST (flat form, no modals)
            security_data = {
                'record_type': request.POST.get('record_type', '').strip(),
                'security_name': request.POST.get('security_name', '').strip(),
                'isin': request.POST.get('isin', '').strip(),
                'security_description': request.POST.get('security_description', '').strip(),
                'issuer': request.POST.get('issuer', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                'shares_outstanding': safe_int(request.POST.get('shares_outstanding', '')),
                'price': safe_float(request.POST.get('price', '')),
                'country_of_exchange': request.POST.get('country_of_exchange', '').strip(),
                'exchange_code': request.POST.get('exchange_code', '').strip(),
                'currency_code': request.POST.get('currency_code', '').strip(),
                'ticker': request.POST.get('ticker', '').strip(),
                'country_of_issue': request.POST.get('country_of_issue', '').strip(),
                'issuer_type': request.POST.get('issuer_type', '').strip(),
                'quoted_unquoted': request.POST.get('quoted_unquoted', '').strip(),
                'security_type': request.POST.get('security_type', '').strip() or 'COMMON STOCK',  # Default to COMMON STOCK
                'investment_type': request.POST.get('investment_type', '').strip(),
                'market': request.POST.get('market', '').strip(),
                'pct_hld_entity_1': request.POST.get('pct_hld_entity_1', '').strip(),
                'pct_hld_entity_2': request.POST.get('pct_hld_entity_2', '').strip(),
                'pct_hld_entity_3': request.POST.get('pct_hld_entity_3', '').strip(),
                'pct_hld_entity_aggr': request.POST.get('pct_hld_entity_aggr', '').strip(),
                'substantial_10_pct': request.POST.get('substantial_10_pct', '').strip(),
                'cels': request.POST.get('cels', '').strip(),
                'pevc_s32_devest': request.POST.get('pevc_s32_devest', '').strip(),
                's32_representative': request.POST.get('s32_representative', '').strip(),
                'basel_iv_fund': request.POST.get('basel_iv_fund', '').strip(),
                'mas_643_entity_type': request.POST.get('mas_643_entity_type', '').strip(),
                'mas_6d_code': request.POST.get('mas_6d_code', '').strip(),
                'fin_nonfin_ind': request.POST.get('fin_nonfin_ind', '').strip(),
                'beta': safe_float(request.POST.get('beta', '')),
                'par_value': safe_float(request.POST.get('par_value', '')),
                'business_unit_head': request.POST.get('business_unit_head', '').strip(),
                'person_in_charge': request.POST.get('person_in_charge', '').strip(),
                'core_noncore': request.POST.get('core_noncore', '').strip(),
                'fund_index_fund': request.POST.get('fund_index_fund', '').strip(),
                'management_limit_classification': request.POST.get('management_limit_classification', '').strip(),
                'relative_index': request.POST.get('relative_index', '').strip(),
            }

            # Update security
            success, error = security_service.update_security(
                security_id=security_id,
                security_data=security_data,
                user_id=user_id,
                username=username,
                user_email=user_email
            )

            if not success:
                messages.error(request, f'Error updating security: {error}')
            else:
                messages.success(request, 'Security updated successfully')
                return redirect('security:detail', security_id=security_id)

        except Exception as e:
            logger.error(f"Error updating security: {str(e)}")
            messages.error(request, f'Error updating security: {str(e)}')

    # GET request - show form with existing data
    dropdown_options = security_dropdown_service.get_all_dropdown_options(username)

    context = {
        'dropdown_options': dropdown_options,
        'security': security,
        'is_edit': True,
    }

    return render(request, 'security/security_form.html', context)


@require_login
@require_http_methods(['POST'])
def security_validate(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    Validate security (Checker action).
    INITIAL/MODIFIED → VALIDATED
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    comments = request.POST.get('comments', '').strip()

    success, error = security_service.validate_security(
        security_id=security_id,
        user_id=user_id,
        username=username,
        user_email=user_email,
        comments=comments
    )

    if success:
        messages.success(request, 'Security validated successfully')
    else:
        messages.error(request, f'Error validating security: {error}')

    return redirect('security:detail', security_id=security_id)


@require_login
@require_permission('securities-approval', 'READ')
def pending_approvals(request: HttpRequest) -> HttpResponse:
    """
    List securities pending approval (only CIS records with INITIAL or MODIFIED status).
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Fetch securities pending validation (INITIAL or MODIFIED)
    initial_securities = security_hive_repository.get_all_securities(
        limit=1000,
        status='INITIAL'
    )
    modified_securities = security_hive_repository.get_all_securities(
        limit=1000,
        status='MODIFIED'
    )

    # Only include CIS records (records created in CIS, not imported from GMP)
    all_securities = initial_securities + modified_securities
    securities = [s for s in all_securities if s.get('src_system', '').upper() == 'CIS']

    # Add status color
    for security in securities:
        security['status_color'] = security_service.get_status_display_color(security.get('status', ''))

    # Pagination
    paginator = Paginator(securities, 25)
    page = request.GET.get('page', 1)

    try:
        securities_page = paginator.page(page)
    except PageNotAnInteger:
        securities_page = paginator.page(1)
    except EmptyPage:
        securities_page = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Build permission context for template
    perms = build_permission_context(request, 'securities')

    context = {
        'securities': securities_page,
        'page_obj': securities_page,
        'total_count': len(securities),
        'is_pending_view': True,
        'pending_count': len(securities),
        # Permission flags
        **perms,
    }

    return render(request, 'security/security_list.html', context)


@require_login
def security_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Security dashboard with statistics.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Fetch statistics
    stats = security_hive_repository.get_statistics()

    # Log audit - Commented out for VIEW actions (only log CREATE, UPDATE, DELETE)
    # AuditLogKuduRepository.log_action(
    #     user_id=user_id,
    #     username=username,
    #     user_email=user_email,
    #     action_type='VIEW',
    #     entity_type='SECURITY',
    #     action_description='Viewed security dashboard',
    #     status='SUCCESS'
    # )

    context = {
        'stats': stats,
    }

    return render(request, 'security/security_dashboard.html', context)
