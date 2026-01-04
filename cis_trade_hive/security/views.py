"""
Security Views

HTTP request handlers for security master data.
All data operations use Kudu tables (no Django ORM).
"""

import logging
import json
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse

from core.views.auth_views import require_login
# from core.decorators import check_permission  # Commented for demo
from security.repositories.security_hive_repository import security_hive_repository
from security.services.security_service import security_service
from security.services.security_dropdown_service import security_dropdown_service
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


@require_login
# @check_permission('cis-security', 'READ')  # Commented for demo
def security_list(request: HttpRequest) -> HttpResponse:
    """
    List all securities with pagination and filters.
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

    # Fetch securities
    securities = security_hive_repository.get_all_securities(
        limit=1000,
        status=status_filter if status_filter else None,
        search=search_term if search_term else None,
        currency=currency_filter if currency_filter else None,
        security_type=security_type_filter if security_type_filter else None
    )

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

    # Log audit
    AuditLogKuduRepository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='SECURITY',
        action_description=f'Viewed security list ({len(securities)} securities)',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'securities': securities_page,
        'page_obj': securities_page,
        'total_count': len(securities),
        'status_filter': status_filter,
        'search_term': search_term,
        'currency_filter': currency_filter,
        'security_type_filter': security_type_filter,
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
    can_approve = security_service.can_user_approve(security, username)
    can_submit = security.get('status') in ['DRAFT', 'REJECTED']

    # Get status color
    security['status_color'] = security_service.get_status_display_color(security.get('status', ''))

    # Log audit
    AuditLogKuduRepository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='SECURITY',
        entity_id=str(security_id),
        entity_name=security.get('security_name', ''),
        action_description=f'Viewed security detail: {security.get("security_name")}',
        status='SUCCESS'
    )

    context = {
        'security': security,
        'history': history,
        'can_edit': can_edit,
        'can_approve': can_approve,
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
            # Helper function to safely convert to int
            def safe_int(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default

            # Helper function to safely convert to float
            def safe_float(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default

            # Parse main form fields with proper type conversions
            security_data = {
                'security_name': request.POST.get('security_name', '').strip(),
                'isin': request.POST.get('isin', '').strip(),
                'security_description': request.POST.get('security_description', '').strip(),
                'issuer': request.POST.get('issuer', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                'shares_outstanding': safe_int(request.POST.get('shares_outstanding', '')),
                'country_of_exchange': request.POST.get('country_of_exchange', '').strip(),
                'exchange_code': request.POST.get('exchange_code', '').strip(),
                'currency_code': request.POST.get('currency_code', '').strip(),
                'ticker': request.POST.get('ticker', '').strip(),
                'quoted_unquoted': request.POST.get('quoted_unquoted', '').strip(),
                'security_type': request.POST.get('security_type', '').strip(),
                'investment_type': request.POST.get('investment_type', '').strip(),
            }

            # Parse modal data (trading & pricing) with type conversions
            trading_data_json = request.POST.get('trading_data', '{}')
            if trading_data_json:
                try:
                    trading_data = json.loads(trading_data_json)
                    # Type conversions for trading fields
                    if 'price' in trading_data:
                        trading_data['price'] = safe_float(trading_data['price'])
                    if 'beta' in trading_data:
                        trading_data['beta'] = safe_float(trading_data['beta'])
                    if 'par_value' in trading_data:
                        trading_data['par_value'] = safe_float(trading_data['par_value'])
                    security_data.update(trading_data)
                except json.JSONDecodeError:
                    pass

            # Parse modal data (regulatory & management) with type conversions
            regulatory_data_json = request.POST.get('regulatory_data', '{}')
            if regulatory_data_json:
                try:
                    regulatory_data = json.loads(regulatory_data_json)
                    # Type conversions for regulatory fields
                    if 'shareholding_entity_1' in regulatory_data:
                        regulatory_data['shareholding_entity_1'] = safe_float(regulatory_data['shareholding_entity_1'])
                    if 'shareholding_entity_2' in regulatory_data:
                        regulatory_data['shareholding_entity_2'] = safe_float(regulatory_data['shareholding_entity_2'])
                    if 'shareholding_entity_3' in regulatory_data:
                        regulatory_data['shareholding_entity_3'] = safe_float(regulatory_data['shareholding_entity_3'])
                    if 'shareholding_aggregated' in regulatory_data:
                        regulatory_data['shareholding_aggregated'] = safe_float(regulatory_data['shareholding_aggregated'])
                    if 'bwciif' in regulatory_data:
                        regulatory_data['bwciif'] = safe_int(regulatory_data['bwciif'])
                    if 'bwciif_others' in regulatory_data:
                        regulatory_data['bwciif_others'] = safe_int(regulatory_data['bwciif_others'])
                    security_data.update(regulatory_data)
                except json.JSONDecodeError:
                    pass

            # Determine action
            action = request.POST.get('action', 'save_draft')

            # Create security
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

            # If action is submit, submit for approval
            if action == 'submit' and security_id:
                submit_success, submit_error = security_service.submit_for_approval(
                    security_id=security_id,
                    user_id=user_id,
                    username=username,
                    user_email=user_email
                )
                if submit_success:
                    messages.success(request, f'Security "{security_data["security_name"]}" created and submitted for approval')
                else:
                    messages.warning(request, f'Security created but submission failed: {submit_error}')
            else:
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

    # Check if editable
    if not security_service.can_user_edit(security, user_id):
        messages.error(request, f'Cannot edit security with status {security.get("status")}')
        return redirect('security:detail', security_id=security_id)

    if request.method == 'POST':
        try:
            # Helper function to safely convert to int
            def safe_int(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default

            # Helper function to safely convert to float
            def safe_float(value, default=None):
                if not value or value == '':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default

            # Parse all fields with proper type conversions
            security_data = {
                'security_name': request.POST.get('security_name', '').strip(),
                'isin': request.POST.get('isin', '').strip(),
                'security_description': request.POST.get('security_description', '').strip(),
                'issuer': request.POST.get('issuer', '').strip(),
                'industry': request.POST.get('industry', '').strip(),
                'country_of_incorporation': request.POST.get('country_of_incorporation', '').strip(),
                'shares_outstanding': safe_int(request.POST.get('shares_outstanding', '')),
                'country_of_exchange': request.POST.get('country_of_exchange', '').strip(),
                'exchange_code': request.POST.get('exchange_code', '').strip(),
                'currency_code': request.POST.get('currency_code', '').strip(),
                'ticker': request.POST.get('ticker', '').strip(),
                'quoted_unquoted': request.POST.get('quoted_unquoted', '').strip(),
                'security_type': request.POST.get('security_type', '').strip(),
                'investment_type': request.POST.get('investment_type', '').strip(),
            }

            # Parse modal data with type conversions
            trading_data_json = request.POST.get('trading_data', '{}')
            if trading_data_json:
                try:
                    trading_data = json.loads(trading_data_json)
                    # Type conversions for trading fields
                    if 'price' in trading_data:
                        trading_data['price'] = safe_float(trading_data['price'])
                    if 'beta' in trading_data:
                        trading_data['beta'] = safe_float(trading_data['beta'])
                    if 'par_value' in trading_data:
                        trading_data['par_value'] = safe_float(trading_data['par_value'])
                    security_data.update(trading_data)
                except json.JSONDecodeError:
                    pass

            regulatory_data_json = request.POST.get('regulatory_data', '{}')
            if regulatory_data_json:
                try:
                    regulatory_data = json.loads(regulatory_data_json)
                    # Type conversions for regulatory fields
                    if 'shareholding_entity_1' in regulatory_data:
                        regulatory_data['shareholding_entity_1'] = safe_float(regulatory_data['shareholding_entity_1'])
                    if 'shareholding_entity_2' in regulatory_data:
                        regulatory_data['shareholding_entity_2'] = safe_float(regulatory_data['shareholding_entity_2'])
                    if 'shareholding_entity_3' in regulatory_data:
                        regulatory_data['shareholding_entity_3'] = safe_float(regulatory_data['shareholding_entity_3'])
                    if 'shareholding_aggregated' in regulatory_data:
                        regulatory_data['shareholding_aggregated'] = safe_float(regulatory_data['shareholding_aggregated'])
                    if 'bwciif' in regulatory_data:
                        regulatory_data['bwciif'] = safe_int(regulatory_data['bwciif'])
                    if 'bwciif_others' in regulatory_data:
                        regulatory_data['bwciif_others'] = safe_int(regulatory_data['bwciif_others'])
                    security_data.update(regulatory_data)
                except json.JSONDecodeError:
                    pass

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
def security_submit(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    Submit security for approval.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    success, error = security_service.submit_for_approval(
        security_id=security_id,
        user_id=user_id,
        username=username,
        user_email=user_email
    )

    if success:
        messages.success(request, 'Security submitted for approval')
    else:
        messages.error(request, f'Error submitting security: {error}')

    return redirect('security:detail', security_id=security_id)


@require_login
# @check_permission('cis-security', 'APPROVE')  # Commented for demo
@require_http_methods(['POST'])
def security_approve(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    Approve security (Checker action).
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    comments = request.POST.get('comments', '').strip()

    success, error = security_service.approve_security(
        security_id=security_id,
        user_id=user_id,
        username=username,
        user_email=user_email,
        comments=comments
    )

    if success:
        messages.success(request, 'Security approved successfully')
    else:
        messages.error(request, f'Error approving security: {error}')

    return redirect('security:detail', security_id=security_id)


@require_login
# @check_permission('cis-security', 'APPROVE')  # Commented for demo
@require_http_methods(['POST'])
def security_reject(request: HttpRequest, security_id: int) -> HttpResponse:
    """
    Reject security (Checker action).
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    comments = request.POST.get('comments', '').strip()

    if not comments:
        messages.error(request, 'Rejection comments are required')
        return redirect('security:detail', security_id=security_id)

    success, error = security_service.reject_security(
        security_id=security_id,
        user_id=user_id,
        username=username,
        user_email=user_email,
        comments=comments
    )

    if success:
        messages.success(request, 'Security rejected')
    else:
        messages.error(request, f'Error rejecting security: {error}')

    return redirect('security:detail', security_id=security_id)


@require_login
# @check_permission('cis-security', 'READ')  # Commented for demo
def pending_approvals(request: HttpRequest) -> HttpResponse:
    """
    List securities pending approval.
    """
    # Get user session info
    user_id = str(request.session.get('user_id', ''))
    username = request.session.get('user_login', 'anonymous')
    user_email = request.session.get('user_email', '')

    # Fetch pending securities
    securities = security_hive_repository.get_all_securities(
        limit=1000,
        status='PENDING_APPROVAL'
    )

    # Add status color
    for security in securities:
        security['status_color'] = 'warning'

    # Pagination
    paginator = Paginator(securities, 25)
    page = request.GET.get('page', 1)

    try:
        securities_page = paginator.page(page)
    except PageNotAnInteger:
        securities_page = paginator.page(1)
    except EmptyPage:
        securities_page = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Log audit
    AuditLogKuduRepository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='SECURITY',
        action_description=f'Viewed pending approvals ({len(securities)} securities)',
        status='SUCCESS'
    )

    context = {
        'securities': securities_page,
        'page_obj': securities_page,
        'total_count': len(securities),
        'is_pending_view': True,
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

    # Log audit
    AuditLogKuduRepository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='SECURITY',
        action_description='Viewed security dashboard',
        status='SUCCESS'
    )

    context = {
        'stats': stats,
    }

    return render(request, 'security/security_dashboard.html', context)
