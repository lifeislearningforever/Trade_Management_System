"""
Portfolio Views
Handles portfolio CRUD operations, Four-Eyes workflow, and CSV export.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q
import csv

from .models import Portfolio
from .services import PortfolioService
from core.models import AuditLog
from core.views.auth_views import require_login, require_permission
from core.audit.audit_kudu_repository import audit_log_kudu_repository
from portfolio.repositories import portfolio_hive_repository


class PortfolioWrapper:
    """Wrapper to convert Hive dict data to object with attributes for template compatibility."""
    def __init__(self, data, index=0):
        self.data = data
        # Map all Hive fields to attributes
        self.code = data.get('name', '')[:20]  # Use name as code (truncated)
        self.name = data.get('name', '')
        self.description = data.get('description', '')
        self.currency = data.get('currency', '')
        self.manager = data.get('manager', '')
        self.portfolio_client = data.get('portfolio_client', '')
        self.cash_balance = data.get('cash_balance', 0)
        self.status = data.get('status', 'Active')
        # Handle is_active: if NULL and status is 'Active', default to True
        raw_is_active = data.get('is_active')
        if raw_is_active is None:
            # NULL value - infer from status
            self.is_active = (self.status == 'Active')
        else:
            self.is_active = bool(raw_is_active)
        self.cost_centre_code = data.get('cost_centre_code', '')
        self.corp_code = data.get('corp_code', '')
        self.account_group = data.get('account_group', '')
        self.portfolio_group = data.get('portfolio_group', '')
        self.report_group = data.get('report_group', '')
        self.entity_group = data.get('entity_group', '')
        self.revaluation_status = data.get('revaluation_status', '')
        self.created_at = data.get('created_at', '')
        self.updated_at = data.get('updated_at', '')
        self.updated_by = data.get('updated_by', '-')  # Username from Kudu
        # Generate a simple numeric ID from hash of name (for URLs)
        self.id = abs(hash(data.get('name', '') + str(index))) % 1000000

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'READ')
def portfolio_list(request):
    """
    List all portfolios with search, filter, and CSV export - FROM HIVE.
    Requires: cis-portfolio READ permission
    """
    # Get filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    currency_filter = request.GET.get('currency', '').strip()
    export = request.GET.get('export', '').strip()

    # Get portfolios from Hive
    portfolios_data = portfolio_hive_repository.get_all_portfolios(
        limit=1000,
        status=status_filter if status_filter else None,
        search=search_query if search_query else None,
        currency=currency_filter if currency_filter else None
    )

    # Wrap dictionaries in objects for template compatibility
    wrapped_portfolios = [PortfolioWrapper(p, idx) for idx, p in enumerate(portfolios_data)]

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="portfolios_hive.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Description', 'Currency', 'Manager', 'Cash Balance',
            'Status', 'Account Group', 'Portfolio Group', 'Created At'
        ])

        for portfolio in portfolios_data:
            writer.writerow([
                portfolio.get('name', ''),
                portfolio.get('description', ''),
                portfolio.get('currency', ''),
                portfolio.get('manager', ''),
                portfolio.get('cash_balance', ''),
                portfolio.get('status', ''),
                portfolio.get('account_group', ''),
                portfolio.get('portfolio_group', ''),
                portfolio.get('created_at', '')
            ])

        # Log export to Kudu - Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='EXPORT',
            entity_type='PORTFOLIO',
            entity_name='Portfolio List',
            action_description=f'Exported {len(portfolios_data)} portfolios to CSV from Kudu',
            status='SUCCESS',
            request_method='GET',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Pagination
    paginator = Paginator(wrapped_portfolios, 25)
    page = request.GET.get('page', 1)

    try:
        portfolios = paginator.page(page)
    except PageNotAnInteger:
        portfolios = paginator.page(1)
    except EmptyPage:
        portfolios = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Get unique currencies from Hive
    currencies = portfolio_hive_repository.get_currencies()

    # Log view to Kudu - Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW' if not search_query else 'SEARCH',
        entity_type='PORTFOLIO',
        entity_name='Portfolio List',
        action_description=f'Viewed portfolio list from Kudu ({len(portfolios_data)} portfolios)' + (f' - Search: {search_query}' if search_query else ''),
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'page_obj': portfolios,  # Template expects 'page_obj'
        'search_query': search_query,
        'status_filter': status_filter,
        'currency_filter': currency_filter,
        'currencies': currencies,
        'total_count': len(portfolios_data),
        'using_hive': True,  # Flag to indicate Hive data source
    }

    return render(request, 'portfolio/portfolio_list.html', context)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'READ')
def portfolio_detail(request, portfolio_name):
    """
    View portfolio details and history - fetches from Kudu.
    Requires: cis-portfolio READ permission
    """
    # Get portfolio from Kudu by name
    portfolio_data = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)

    if not portfolio_data:
        raise Http404(f"Portfolio '{portfolio_name}' not found in Kudu")

    # Wrap the Kudu data for template compatibility
    portfolio = PortfolioWrapper(portfolio_data)

    # For now, history is not available from Kudu (would need to query cis_portfolio_history)
    history = []

    # Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    # Check permissions based on status
    can_edit = portfolio.status in ['DRAFT', 'REJECTED']
    can_approve = portfolio.status == 'PENDING_APPROVAL'
    # DEV MODE: Permission checks bypassed for close/reactivate
    can_close = portfolio.status == 'Active'  # Simple status check
    can_reactivate = portfolio.status == 'Inactive'  # Simple status check

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='PORTFOLIO',
        entity_name=portfolio_name,
        action_description=f'Viewed portfolio detail from Kudu: {portfolio_name}',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'portfolio': portfolio,
        'history': history,
        'can_edit': can_edit,
        'can_approve': can_approve,
        'can_close': can_close,
        'can_reactivate': can_reactivate,
    }

    return render(request, 'portfolio/portfolio_detail.html', context)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_create(request):
    """
    Create a new portfolio - Inserts directly into Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    """
    from portfolio.services.portfolio_dropdown_service import portfolio_dropdown_service

    if request.method == 'POST':
        try:
            # Get user info from session (ACL authentication)
            username = request.session.get('user_login', 'anonymous')
            user_id = str(request.session.get('user_id', ''))
            user_email = request.session.get('user_email', '')

            # Prepare portfolio data
            portfolio_name = request.POST.get('name', '').strip()

            if not portfolio_name:
                raise ValidationError("Portfolio name is required")

            # Check if portfolio already exists
            existing = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
            if existing:
                raise ValidationError(f"Portfolio '{portfolio_name}' already exists")

            data = {
                'name': portfolio_name,
                'description': request.POST.get('description', ''),
                'currency': request.POST.get('currency'),
                'manager': request.POST.get('manager'),
                'portfolio_client': request.POST.get('portfolio_client', ''),
                'cash_balance': float(request.POST.get('cash_balance', 0)) if request.POST.get('cash_balance') else 0,
                'cost_centre_code': request.POST.get('cost_centre_code', ''),
                'corp_code': request.POST.get('corp_code', ''),
                'account_group': request.POST.get('account_group', ''),
                'portfolio_group': request.POST.get('portfolio_group', ''),
                'report_group': request.POST.get('report_group', ''),
                'entity_group': request.POST.get('entity_group', ''),
                'revaluation_status': request.POST.get('revaluation_status', ''),
            }

            # Validate required fields
            if not data.get('currency'):
                raise ValidationError("Currency is required")
            if not data.get('manager'):
                raise ValidationError("Manager is required")

            # Insert into Kudu
            success = portfolio_hive_repository.insert_portfolio(data, created_by=username)

            if not success:
                raise Exception("Failed to create portfolio in Kudu")

            # Log to audit
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_name,
                entity_name=portfolio_name,
                action_description=f"Created portfolio: {portfolio_name}",
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Portfolio "{portfolio_name}" created in DRAFT status. Submit for approval to activate.')
            return redirect('portfolio:detail', portfolio_name=portfolio_name)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating portfolio: {str(e)}')

    # Get all dropdown options from Kudu tables
    dropdown_options = portfolio_dropdown_service.get_all_dropdown_options()

    context = {
        'dropdown_options': dropdown_options,
    }

    return render(request, 'portfolio/portfolio_form.html', context)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_edit(request, portfolio_name):
    """
    Edit an existing portfolio (DRAFT or REJECTED only) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    """
    from portfolio.services.portfolio_dropdown_service import portfolio_dropdown_service

    # Get portfolio from Kudu
    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    # Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    # Check if portfolio can be edited (only DRAFT or REJECTED)
    current_status = portfolio.get('status', '')
    if current_status not in ['DRAFT', 'REJECTED']:
        messages.error(request, f'Cannot edit portfolio with status "{current_status}". Only DRAFT or REJECTED portfolios can be edited.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    if request.method == 'POST':
        try:
            # Build UPDATE query for Kudu
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Escape single quotes
            def escape_value(val):
                if val is None:
                    return 'NULL'
                if isinstance(val, str):
                    return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
                return str(val)

            cash_balance_str = str(request.POST.get('cash_balance', '0'))

            update_query = f"""
            UPDATE gmp_cis.cis_portfolio
            SET description = {escape_value(request.POST.get('description', ''))},
                currency = {escape_value(request.POST.get('currency'))},
                manager = {escape_value(request.POST.get('manager'))},
                portfolio_client = {escape_value(request.POST.get('portfolio_client', ''))},
                cash_balance = {escape_value(cash_balance_str)},
                cost_centre_code = {escape_value(request.POST.get('cost_centre_code', ''))},
                corp_code = {escape_value(request.POST.get('corp_code', ''))},
                account_group = {escape_value(request.POST.get('account_group', ''))},
                portfolio_group = {escape_value(request.POST.get('portfolio_group', ''))},
                report_group = {escape_value(request.POST.get('report_group', ''))},
                entity_group = {escape_value(request.POST.get('entity_group', ''))},
                revaluation_status = {escape_value(request.POST.get('revaluation_status', ''))},
                updated_by = {escape_value(username)},
                updated_at = '{timestamp}'
            WHERE name = {escape_value(portfolio_name)}
            """

            from core.repositories.impala_connection import impala_manager
            success = impala_manager.execute_write(update_query, database='gmp_cis')

            if not success:
                raise Exception('Failed to update portfolio in Kudu')

            # Log to audit
            audit_log_kudu_repository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='UPDATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_name,
                entity_name=portfolio_name,
                action_description=f'Updated portfolio: {portfolio_name}',
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Portfolio "{portfolio_name}" updated successfully!')
            return redirect('portfolio:detail', portfolio_name=portfolio_name)

        except Exception as e:
            messages.error(request, f'Error updating portfolio: {str(e)}')

    # Get all dropdown options from Kudu tables
    dropdown_options = portfolio_dropdown_service.get_all_dropdown_options()

    context = {
        'portfolio': portfolio,
        'dropdown_options': dropdown_options,
        'is_edit': True,
        'can_close': current_status == 'APPROVED',  # Can only close APPROVED portfolios
    }

    return render(request, 'portfolio/portfolio_form.html', context)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_submit(request, portfolio_name):
    """
    Submit portfolio for approval (Maker action) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Get portfolio from Kudu
    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    # Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    # Validate portfolio status
    current_status = portfolio.get('status', '')
    if current_status not in ['DRAFT', 'REJECTED']:
        messages.error(request, f'Cannot submit portfolio with status "{current_status}". Only DRAFT or REJECTED portfolios can be submitted.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        # Update status to PENDING_APPROVAL in Kudu
        success = portfolio_hive_repository.update_portfolio_status(
            portfolio_code=portfolio_name,
            status='PENDING_APPROVAL',
            is_active=False,  # Still not active until approved
            updated_by=username
        )

        if not success:
            raise Exception('Failed to update portfolio status in Kudu')

        # Log to audit
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='SUBMIT',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Submitted portfolio for approval: {portfolio_name}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Portfolio "{portfolio_name}" submitted for approval!')
    except Exception as e:
        messages.error(request, f'Error submitting portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_approve(request, portfolio_name):
    """
    Approve portfolio (Checker action - Four-Eyes) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    Note: Should enforce Four-Eyes principle (different user than creator)
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Get portfolio from Kudu
    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    # Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')
    comments = request.POST.get('comments', '').strip()

    # Validate portfolio status
    current_status = portfolio.get('status', '')
    if current_status != 'PENDING_APPROVAL':
        messages.error(request, f'Cannot approve portfolio with status "{current_status}". Only PENDING_APPROVAL portfolios can be approved.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        # Update status to APPROVED (ACTIVE) in Kudu
        success = portfolio_hive_repository.update_portfolio_status(
            portfolio_code=portfolio_name,
            status='APPROVED',
            is_active=True,  # Now active!
            updated_by=username
        )

        if not success:
            raise Exception('Failed to approve portfolio in Kudu')

        # Log to audit
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='APPROVE',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Approved portfolio: {portfolio_name}. Comments: {comments}' if comments else f'Approved portfolio: {portfolio_name}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Portfolio "{portfolio_name}" approved successfully and is now ACTIVE!')
    except Exception as e:
        messages.error(request, f'Error approving portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_reject(request, portfolio_name):
    """
    Reject portfolio (Checker action) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    Note: Should enforce Four-Eyes principle (different user than creator)
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Get portfolio from Kudu
    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    # Get user info from session (ACL authentication)
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')
    comments = request.POST.get('comments', '').strip()

    # Validate portfolio status
    current_status = portfolio.get('status', '')
    if current_status != 'PENDING_APPROVAL':
        messages.error(request, f'Cannot reject portfolio with status "{current_status}". Only PENDING_APPROVAL portfolios can be rejected.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        # Update status to REJECTED in Kudu
        success = portfolio_hive_repository.update_portfolio_status(
            portfolio_code=portfolio_name,
            status='REJECTED',
            is_active=False,  # Not active
            updated_by=username
        )

        if not success:
            raise Exception('Failed to reject portfolio in Kudu')

        # Log to audit
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='REJECT',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Rejected portfolio: {portfolio_name}. Comments: {comments}' if comments else f'Rejected portfolio: {portfolio_name}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.warning(request, f'Portfolio "{portfolio_name}" rejected. It can be edited and resubmitted.')
    except Exception as e:
        messages.error(request, f'Error rejecting portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_close(request, portfolio_name):
    """
    Close portfolio (soft delete) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Get portfolio from Kudu to validate status
    portfolio_data = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio_data:
        messages.error(request, f'Portfolio {portfolio_name} not found.')
        return redirect('portfolio:list')

    reason = request.POST.get('reason', '').strip()

    try:
        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # DEV MODE: Permission check bypassed
        # PRODUCTION: Uncomment below to enforce permissions
        # portfolio_status = portfolio_data.get('status', '')
        # if not PortfolioService.can_user_close(portfolio_status, request.user):
        #     raise PermissionDenied('You do not have permission to close this portfolio.')

        # Close portfolio in Kudu
        PortfolioService.close_portfolio(
            portfolio_code=portfolio_name,
            user_id=user_id,
            username=username,
            user_email=user_email,
            reason=reason
        )

        messages.success(request, f'Portfolio {portfolio_name} has been closed successfully.')
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('portfolio:detail', portfolio_name=portfolio_name)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_reactivate(request, portfolio_name):
    """
    Reactivate closed portfolio - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Get portfolio from Kudu to validate status
    portfolio_data = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio_data:
        messages.error(request, f'Portfolio {portfolio_name} not found.')
        return redirect('portfolio:list')

    comments = request.POST.get('comments', '').strip()

    try:
        # Get user info from session (ACL authentication)
        username = request.session.get('user_login', 'anonymous')
        user_id = str(request.session.get('user_id', ''))
        user_email = request.session.get('user_email', '')

        # DEV MODE: Permission check bypassed
        # PRODUCTION: Uncomment below to enforce permissions
        # portfolio_status = portfolio_data.get('status', '')
        # if not PortfolioService.can_user_reactivate(portfolio_status, request.user):
        #     raise PermissionDenied('You do not have permission to reactivate this portfolio.')

        # Reactivate portfolio in Kudu
        PortfolioService.reactivate_portfolio(
            portfolio_code=portfolio_name,
            user_id=user_id,
            username=username,
            user_email=user_email,
            comments=comments
        )

        messages.success(request, f'Portfolio {portfolio_name} has been reactivated successfully.')
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('portfolio:detail', portfolio_name=portfolio_name)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def pending_approvals(request):
    """
    List portfolios pending approval (for Checkers) - Uses Kudu/Impala.
    Requires: cis-portfolio WRITE permission
    Note: Additional group check remains for Checkers-only access
    """
    # DEV MODE: Permission check bypassed
    # PRODUCTION: Uncomment below to enforce Checker group access
    # user = getattr(request, 'user', None)
    # if user and hasattr(user, 'groups'):
    #     if not user.groups.filter(name='Checkers').exists() and not user.is_superuser:
    #         messages.error(request, 'Access denied. Only Checkers can view pending approvals.')
    #         return redirect('dashboard')

    # Get portfolios with PENDING_APPROVAL status from Kudu
    portfolios_data = portfolio_hive_repository.get_all_portfolios(
        limit=1000,
        status='PENDING_APPROVAL'
    )

    # Wrap dictionaries in objects for template compatibility
    wrapped_portfolios = [PortfolioWrapper(p, idx) for idx, p in enumerate(portfolios_data)]

    # Log view to audit
    username = request.session.get('user_login', 'anonymous')
    user_id = str(request.session.get('user_id', ''))
    user_email = request.session.get('user_email', '')

    audit_log_kudu_repository.log_action(
        user_id=user_id,
        username=username,
        user_email=user_email,
        action_type='VIEW',
        entity_type='PORTFOLIO',
        entity_id='PENDING_APPROVALS',
        entity_name='Pending Approvals List',
        action_description=f'Viewed pending approvals list from Kudu ({len(portfolios_data)} portfolios)',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        status='SUCCESS'
    )

    context = {
        'portfolios': wrapped_portfolios,
        'pending_count': len(portfolios_data),
    }

    return render(request, 'portfolio/pending_approvals.html', context)
