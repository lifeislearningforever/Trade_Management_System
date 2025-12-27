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
        # Generate a simple numeric ID from hash of name (for URLs)
        self.id = abs(hash(data.get('name', '') + str(index))) % 1000000

        # Create mock created_by object
        class MockUser:
            username = '-'
        self.created_by = MockUser()

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

        # Log export to Kudu
        user = getattr(request, 'user', None)
        user_id = str(user.id) if user and hasattr(user, 'id') else 'anonymous'
        username = user.username if user and hasattr(user, 'username') else 'anonymous'
        user_email = user.email if user and hasattr(user, 'email') else ''

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

    # Log view to Kudu
    user = getattr(request, 'user', None)
    user_id = str(user.id) if user and hasattr(user, 'id') else 'anonymous'
    username = user.username if user and hasattr(user, 'username') else 'anonymous'
    user_email = user.email if user and hasattr(user, 'email') else ''

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

    # Get user for permission checks
    user = getattr(request, 'user', None)

    # Check permissions based on status
    can_edit = portfolio.status in ['DRAFT', 'REJECTED']
    can_approve = portfolio.status == 'PENDING_APPROVAL'
    can_close = PortfolioService.can_user_close(portfolio.status, user) if user else False
    can_reactivate = PortfolioService.can_user_reactivate(portfolio.status, user) if user else False

    # Log view to Kudu
    user_id = str(user.id) if user and hasattr(user, 'id') else 'anonymous'
    username = user.username if user and hasattr(user, 'username') else 'anonymous'
    user_email = user.email if user and hasattr(user, 'email') else ''

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
def portfolio_edit(request, pk):
    """
    Edit an existing portfolio (DRAFT or REJECTED only).
    Requires: cis-portfolio WRITE permission
    """
    from portfolio.services.portfolio_dropdown_service import portfolio_dropdown_service

    portfolio = get_object_or_404(Portfolio, pk=pk)

    # Check permissions
    if not PortfolioService.can_user_edit(portfolio, request.user):
        messages.error(request, 'You do not have permission to edit this portfolio.')
        return redirect('portfolio:detail', pk=portfolio.id)

    if request.method == 'POST':
        try:
            data = {
                'name': request.POST.get('name'),
                'description': request.POST.get('description', ''),
                'currency': request.POST.get('currency'),
                'manager': request.POST.get('manager'),
                'portfolio_client': request.POST.get('portfolio_client', ''),
                'cash_balance': float(request.POST.get('cash_balance', 0)),
                'cost_centre_code': request.POST.get('cost_centre_code', ''),
                'corp_code': request.POST.get('corp_code', ''),
                'account_group': request.POST.get('account_group', ''),
                'portfolio_group': request.POST.get('portfolio_group', ''),
                'report_group': request.POST.get('report_group', ''),
                'entity_group': request.POST.get('entity_group', ''),
                'status': request.POST.get('status', 'Active'),
                'revaluation_status': request.POST.get('revaluation_status', ''),
            }

            portfolio = PortfolioService.update_portfolio(portfolio, request.user, data)
            messages.success(request, f'Portfolio {portfolio.code} updated successfully!')
            return redirect('portfolio:detail', pk=portfolio.id)

        except (ValidationError, PermissionDenied) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error updating portfolio: {str(e)}')

    # Get all dropdown options from Kudu tables
    dropdown_options = portfolio_dropdown_service.get_all_dropdown_options()

    context = {
        'portfolio': portfolio,
        'dropdown_options': dropdown_options,
        'is_edit': True,
        'can_close': PortfolioService.can_user_close(portfolio.status, request.user),
    }

    return render(request, 'portfolio/portfolio_form.html', context)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_submit(request, pk):
    """
    Submit portfolio for approval (Maker action).
    Requires: cis-portfolio WRITE permission
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', pk=pk)

    portfolio = get_object_or_404(Portfolio, pk=pk)

    try:
        portfolio = PortfolioService.submit_for_approval(portfolio, request.user)
        messages.success(request, f'Portfolio {portfolio.code} submitted for approval!')
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('portfolio:detail', pk=portfolio.id)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_approve(request, pk):
    """
    Approve portfolio (Checker action - Four-Eyes).
    Requires: cis-portfolio WRITE permission
    Note: Service layer enforces Four-Eyes principle
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', pk=pk)

    portfolio = get_object_or_404(Portfolio, pk=pk)
    comments = request.POST.get('comments', '').strip()

    try:
        portfolio = PortfolioService.approve_portfolio(portfolio, request.user, comments)
        messages.success(request, f'Portfolio {portfolio.code} approved successfully!')
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('portfolio:detail', pk=portfolio.id)

# PRODUCTION NOTE: Uncomment this decorator for production deployment
#@require_permission('cis-portfolio', 'WRITE')
def portfolio_reject(request, pk):
    """
    Reject portfolio (Checker action).
    Requires: cis-portfolio WRITE permission
    Note: Service layer enforces Four-Eyes principle
    """
    if request.method != 'POST':
        return redirect('portfolio:detail', pk=pk)

    portfolio = get_object_or_404(Portfolio, pk=pk)
    comments = request.POST.get('comments', '').strip()

    try:
        portfolio = PortfolioService.reject_portfolio(portfolio, request.user, comments)
        messages.warning(request, f'Portfolio {portfolio.code} rejected.')
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('portfolio:detail', pk=portfolio.id)

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
        # DEV MODE: Permission check bypassed
        # PRODUCTION: Uncomment below to enforce permissions
        # portfolio_status = portfolio_data.get('status', '')
        # if not PortfolioService.can_user_close(portfolio_status, request.user):
        #     raise PermissionDenied('You do not have permission to close this portfolio.')

        # Close portfolio in Kudu
        PortfolioService.close_portfolio(
            portfolio_code=portfolio_name,
            user_id=str(request.user.id),
            username=request.user.username,
            user_email=request.user.email or '',
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
        # DEV MODE: Permission check bypassed
        # PRODUCTION: Uncomment below to enforce permissions
        # portfolio_status = portfolio_data.get('status', '')
        # if not PortfolioService.can_user_reactivate(portfolio_status, request.user):
        #     raise PermissionDenied('You do not have permission to reactivate this portfolio.')

        # Reactivate portfolio in Kudu
        PortfolioService.reactivate_portfolio(
            portfolio_code=portfolio_name,
            user_id=str(request.user.id),
            username=request.user.username,
            user_email=request.user.email or '',
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
    List portfolios pending approval (for Checkers).
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

    portfolios = PortfolioService.get_pending_approvals()

    context = {
        'portfolios': portfolios,
    }

    return render(request, 'portfolio/pending_approvals.html', context)
