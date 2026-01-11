"""
Portfolio Views
Implements Maker-Checker workflow for portfolio management.

Workflow:
  MAKER Side:
    - Create Portfolio -> INITIAL
    - Update Portfolio -> MODIFIED
    - Cancel Portfolio -> CANCELLED
    - Submit for Validation -> PENDING_VALIDATION

  CHECKER Side:
    - Validate -> VALIDATED (or CANCELLED if rejected)
    - Settle -> SETTLED (final active state)
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404
from django.core.exceptions import ValidationError
import csv

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from portfolio.repositories.portfolio_hive_repository import (
    portfolio_hive_repository,
    PortfolioHiveRepository
)


class PortfolioWrapper:
    """Wrapper to convert Kudu dict data to object with attributes for template compatibility."""
    def __init__(self, data, index=0):
        self.data = data
        self.code = data.get('name', '')[:20]
        self.name = data.get('name', '')
        self.description = data.get('description', '')
        self.currency = data.get('currency', '')
        self.manager = data.get('manager', '')
        self.portfolio_client = data.get('portfolio_client', '')
        self.cash_balance = data.get('cash_balance', 0)
        self.status = data.get('status', 'INITIAL')
        self.src_system = data.get('src_system', 'GMP')

        # Handle is_active
        raw_is_active = data.get('is_active')
        if raw_is_active is None:
            self.is_active = (self.status == PortfolioHiveRepository.STATUS_SETTLED)
        else:
            self.is_active = bool(raw_is_active)

        # Classification fields
        self.cost_centre_code = data.get('cost_centre_code', '')
        self.corp_code = data.get('corp_code', '')
        self.account_group = data.get('account_group', '')
        self.portfolio_group = data.get('portfolio_group', '')
        self.report_group = data.get('report_group', '')
        self.entity_group = data.get('entity_group', '')
        self.revaluation_status = data.get('revaluation_status', '')

        # Audit fields
        self.created_by = data.get('created_by', '-')
        self.created_at = data.get('created_at', '')
        self.updated_at = data.get('updated_at', '')
        self.updated_by = data.get('updated_by', '-')

        # Workflow fields
        self.submitted_by = data.get('submitted_by', '')
        self.submitted_at = data.get('submitted_at', '')
        self.validated_by = data.get('validated_by', '')
        self.validated_at = data.get('validated_at', '')
        self.validation_comments = data.get('validation_comments', '')
        self.settled_by = data.get('settled_by', '')
        self.settled_at = data.get('settled_at', '')
        self.settlement_comments = data.get('settlement_comments', '')
        self.cancelled_by = data.get('cancelled_by', '')
        self.cancelled_at = data.get('cancelled_at', '')
        self.cancel_reason = data.get('cancel_reason', '')

        # Generate ID for URLs
        self.id = abs(hash(data.get('name', '') + str(index))) % 1000000


def get_user_info(request):
    """Get user info from session."""
    return {
        'username': request.session.get('user_login', 'anonymous'),
        'user_id': str(request.session.get('user_id', '')),
        'user_email': request.session.get('user_email', '')
    }


def portfolio_list(request):
    """List all portfolios with search, filter, and CSV export."""
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    currency_filter = request.GET.get('currency', '').strip()
    export = request.GET.get('export', '').strip()

    portfolios_data = portfolio_hive_repository.get_all_portfolios(
        limit=1000,
        status=status_filter if status_filter else None,
        search=search_query if search_query else None,
        currency=currency_filter if currency_filter else None
    )

    wrapped_portfolios = [PortfolioWrapper(p, idx) for idx, p in enumerate(portfolios_data)]

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="portfolios.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Description', 'Currency', 'Manager', 'Cash Balance',
            'Status', 'Source', 'Account Group', 'Created At'
        ])

        for portfolio in portfolios_data:
            writer.writerow([
                portfolio.get('name', ''),
                portfolio.get('description', ''),
                portfolio.get('currency', ''),
                portfolio.get('manager', ''),
                portfolio.get('cash_balance', ''),
                portfolio.get('status', ''),
                portfolio.get('src_system', ''),
                portfolio.get('account_group', ''),
                portfolio.get('created_at', '')
            ])

        user_info = get_user_info(request)
        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='EXPORT',
            entity_type='PORTFOLIO',
            entity_name='Portfolio List',
            action_description=f'Exported {len(portfolios_data)} portfolios to CSV',
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

    currencies = portfolio_hive_repository.get_currencies()

    # Get workflow status counts
    stats = portfolio_hive_repository.get_portfolio_statistics()

    # Commented out VIEW/SEARCH audit logging (only log CREATE, UPDATE, DELETE)
    # user_info = get_user_info(request)
    # audit_log_kudu_repository.log_action(
    #     user_id=user_info['user_id'],
    #     username=user_info['username'],
    #     user_email=user_info['user_email'],
    #     action_type='VIEW' if not search_query else 'SEARCH',
    #     entity_type='PORTFOLIO',
    #     entity_name='Portfolio List',
    #     action_description=f'Viewed portfolio list ({len(portfolios_data)} portfolios)' + (f' - Search: {search_query}' if search_query else ''),
    #     status='SUCCESS',
    #     request_method='GET',
    #     request_path=request.path,
    #     ip_address=request.META.get('REMOTE_ADDR'),
    #     user_agent=request.META.get('HTTP_USER_AGENT', '')
    # )

    # Status options for filter dropdown
    status_options = [
        ('', 'All Statuses'),
        (PortfolioHiveRepository.STATUS_INITIAL, 'Initial'),
        (PortfolioHiveRepository.STATUS_MODIFIED, 'Modified'),
        (PortfolioHiveRepository.STATUS_PENDING_VALIDATION, 'Pending Validation'),
        (PortfolioHiveRepository.STATUS_VALIDATED, 'Validated'),
        (PortfolioHiveRepository.STATUS_SETTLED, 'Settled'),
        (PortfolioHiveRepository.STATUS_CANCELLED, 'Cancelled'),
    ]

    # Get pending validation and settlement counts for navigation buttons
    pending_validation_data = portfolio_hive_repository.get_pending_validation_portfolios()
    pending_validation_count = len(pending_validation_data) if pending_validation_data else 0
    pending_settlement_data = portfolio_hive_repository.get_validated_portfolios()
    pending_settlement_count = len(pending_settlement_data) if pending_settlement_data else 0

    context = {
        'page_obj': portfolios,
        'search_query': search_query,
        'status_filter': status_filter,
        'currency_filter': currency_filter,
        'currencies': currencies,
        'total_count': len(portfolios_data),
        'status_options': status_options,
        'stats': stats,
        'pending_validation_count': pending_validation_count,
        'pending_settlement_count': pending_settlement_count,
    }

    return render(request, 'portfolio/portfolio_list.html', context)


def portfolio_detail(request, portfolio_name):
    """View portfolio details."""
    portfolio_data = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)

    if not portfolio_data:
        raise Http404(f"Portfolio '{portfolio_name}' not found")

    portfolio = PortfolioWrapper(portfolio_data)
    status = portfolio.status
    src_system = portfolio.src_system

    # Determine allowed actions based on status and source system
    is_cis_record = src_system and src_system.upper() == 'CIS'

    # Maker actions (only for CIS records)
    can_edit = is_cis_record and status in [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED,
        PortfolioHiveRepository.STATUS_CANCELLED
    ]
    can_submit = is_cis_record and status in [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED
    ]
    can_cancel = is_cis_record and status in [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED,
        PortfolioHiveRepository.STATUS_PENDING_VALIDATION
    ]
    can_reactivate = is_cis_record and status == PortfolioHiveRepository.STATUS_CANCELLED

    # Checker actions (only for CIS records)
    can_validate = is_cis_record and status == PortfolioHiveRepository.STATUS_PENDING_VALIDATION
    can_reject = is_cis_record and status == PortfolioHiveRepository.STATUS_PENDING_VALIDATION
    can_settle = is_cis_record and status == PortfolioHiveRepository.STATUS_VALIDATED

    # Commented out VIEW audit logging (only log CREATE, UPDATE, DELETE)
    # user_info = get_user_info(request)
    # audit_log_kudu_repository.log_action(
    #     user_id=user_info['user_id'],
    #     username=user_info['username'],
    #     user_email=user_info['user_email'],
    #     action_type='VIEW',
    #     entity_type='PORTFOLIO',
    #     entity_id=portfolio_name,
    #     entity_name=portfolio_name,
    #     action_description=f'Viewed portfolio detail: {portfolio_name}',
    #     status='SUCCESS',
    #     request_method='GET',
    #     request_path=request.path,
    #     ip_address=request.META.get('REMOTE_ADDR'),
    #     user_agent=request.META.get('HTTP_USER_AGENT', '')
    # )

    context = {
        'portfolio': portfolio,
        'can_edit': can_edit,
        'can_submit': can_submit,
        'can_cancel': can_cancel,
        'can_reactivate': can_reactivate,
        'can_validate': can_validate,
        'can_reject': can_reject,
        'can_settle': can_settle,
        'is_cis_record': is_cis_record,
    }

    return render(request, 'portfolio/portfolio_detail.html', context)


def portfolio_create(request):
    """Create a new portfolio (Maker action: Create -> INITIAL)."""
    from portfolio.services.portfolio_dropdown_service import portfolio_dropdown_service

    if request.method == 'POST':
        try:
            user_info = get_user_info(request)
            portfolio_name = request.POST.get('name', '').strip()

            if not portfolio_name:
                raise ValidationError("Portfolio name is required")

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

            if not data.get('currency'):
                raise ValidationError("Currency is required")
            if not data.get('manager'):
                raise ValidationError("Manager is required")

            success = portfolio_hive_repository.insert_portfolio(data, created_by=user_info['username'])

            if not success:
                raise Exception("Failed to create portfolio")

            audit_log_kudu_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='CREATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_name,
                entity_name=portfolio_name,
                action_description=f"Created portfolio: {portfolio_name} (INITIAL status)",
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Portfolio "{portfolio_name}" created with INITIAL status. Submit for validation when ready.')
            return redirect('portfolio:detail', portfolio_name=portfolio_name)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating portfolio: {str(e)}')

    dropdown_options = portfolio_dropdown_service.get_all_dropdown_options()

    context = {
        'dropdown_options': dropdown_options,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


def portfolio_edit(request, portfolio_name):
    """Edit portfolio (Maker action: Update -> MODIFIED)."""
    from portfolio.services.portfolio_dropdown_service import portfolio_dropdown_service

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    current_status = portfolio.get('status', '')
    src_system = portfolio.get('src_system', '')

    # Only CIS records in INITIAL, MODIFIED, or CANCELLED status can be edited
    if src_system and src_system.upper() != 'CIS':
        messages.error(request, f'Cannot edit GMP records. Only CIS records can be edited.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    editable_statuses = [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED,
        PortfolioHiveRepository.STATUS_CANCELLED
    ]
    if current_status not in editable_statuses:
        messages.error(request, f'Cannot edit portfolio with status "{current_status}". Only INITIAL, MODIFIED, or CANCELLED portfolios can be edited.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    if request.method == 'POST':
        try:
            data = {
                'description': request.POST.get('description', ''),
                'currency': request.POST.get('currency'),
                'manager': request.POST.get('manager'),
                'portfolio_client': request.POST.get('portfolio_client', ''),
                'cash_balance': request.POST.get('cash_balance', '0'),
                'cost_centre_code': request.POST.get('cost_centre_code', ''),
                'corp_code': request.POST.get('corp_code', ''),
                'account_group': request.POST.get('account_group', ''),
                'portfolio_group': request.POST.get('portfolio_group', ''),
                'report_group': request.POST.get('report_group', ''),
                'entity_group': request.POST.get('entity_group', ''),
                'revaluation_status': request.POST.get('revaluation_status', ''),
            }

            success = portfolio_hive_repository.update_portfolio(
                portfolio_name, data, user_info['username']
            )

            if not success:
                raise Exception('Failed to update portfolio')

            audit_log_kudu_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='UPDATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_name,
                entity_name=portfolio_name,
                action_description=f'Updated portfolio: {portfolio_name} (status set to MODIFIED)',
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Portfolio "{portfolio_name}" updated. Status set to MODIFIED.')
            return redirect('portfolio:detail', portfolio_name=portfolio_name)

        except Exception as e:
            messages.error(request, f'Error updating portfolio: {str(e)}')

    dropdown_options = portfolio_dropdown_service.get_all_dropdown_options()

    context = {
        'portfolio': portfolio,
        'dropdown_options': dropdown_options,
        'is_edit': True,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


def portfolio_submit(request, portfolio_name):
    """Submit portfolio for validation (Maker action: Submit -> PENDING_VALIDATION)."""
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    current_status = portfolio.get('status', '')

    submittable_statuses = [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED
    ]
    if current_status not in submittable_statuses:
        messages.error(request, f'Cannot submit portfolio with status "{current_status}".')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        success = portfolio_hive_repository.submit_for_validation(
            portfolio_name, user_info['username']
        )

        if not success:
            raise Exception('Failed to submit portfolio for validation')

        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='SUBMIT',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Submitted portfolio for validation: {portfolio_name}',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Portfolio "{portfolio_name}" submitted for validation.')
    except Exception as e:
        messages.error(request, f'Error submitting portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)


def portfolio_validate(request, portfolio_name):
    """Validate or reject portfolio (Checker action: Validate -> VALIDATED or Reject -> CANCELLED)."""
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    comments = request.POST.get('comments', '').strip()
    action = request.POST.get('action', 'approve')
    current_status = portfolio.get('status', '')

    if current_status != PortfolioHiveRepository.STATUS_PENDING_VALIDATION:
        messages.error(request, f'Cannot validate portfolio with status "{current_status}".')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    # Four-eyes check: Validator should be different from submitter
    submitted_by = portfolio.get('submitted_by', '')
    if submitted_by and submitted_by == user_info['username']:
        messages.error(request, 'Four-eyes principle: You cannot validate your own submission.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        if action == 'reject':
            # Reject -> Cancel the portfolio
            success = portfolio_hive_repository.cancel_portfolio(
                portfolio_name, user_info['username'], comments
            )
            action_type = 'REJECT'
            action_desc = f'Rejected portfolio: {portfolio_name}' + (f'. Reason: {comments}' if comments else '')
            success_msg = f'Portfolio "{portfolio_name}" has been rejected.'
        else:
            # Approve -> Validate
            success = portfolio_hive_repository.validate_portfolio(
                portfolio_name, user_info['username'], comments
            )
            action_type = 'VALIDATE'
            action_desc = f'Validated portfolio: {portfolio_name}' + (f'. Comments: {comments}' if comments else '')
            success_msg = f'Portfolio "{portfolio_name}" validated. Ready for settlement.'

        if not success:
            raise Exception(f'Failed to {action} portfolio')

        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type=action_type,
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=action_desc,
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        if action == 'reject':
            messages.warning(request, success_msg)
        else:
            messages.success(request, success_msg)
    except Exception as e:
        messages.error(request, f'Error processing portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)


def portfolio_settle(request, portfolio_name):
    """Settle portfolio (Checker action: Settle -> SETTLED)."""
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    comments = request.POST.get('comments', '').strip()
    current_status = portfolio.get('status', '')

    if current_status != PortfolioHiveRepository.STATUS_VALIDATED:
        messages.error(request, f'Cannot settle portfolio with status "{current_status}". Only VALIDATED portfolios can be settled.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        success = portfolio_hive_repository.settle_portfolio(
            portfolio_name, user_info['username'], comments
        )

        if not success:
            raise Exception('Failed to settle portfolio')

        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='SETTLE',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Settled portfolio: {portfolio_name}' + (f'. Comments: {comments}' if comments else ''),
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Portfolio "{portfolio_name}" settled and is now ACTIVE!')
    except Exception as e:
        messages.error(request, f'Error settling portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)


def portfolio_cancel(request, portfolio_name):
    """Cancel portfolio (Maker/Checker action: Cancel -> CANCELLED)."""
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    reason = request.POST.get('reason', '').strip()
    current_status = portfolio.get('status', '')

    cancellable_statuses = [
        PortfolioHiveRepository.STATUS_INITIAL,
        PortfolioHiveRepository.STATUS_MODIFIED,
        PortfolioHiveRepository.STATUS_PENDING_VALIDATION
    ]
    if current_status not in cancellable_statuses:
        messages.error(request, f'Cannot cancel portfolio with status "{current_status}".')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        success = portfolio_hive_repository.cancel_portfolio(
            portfolio_name, user_info['username'], reason
        )

        if not success:
            raise Exception('Failed to cancel portfolio')

        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='CANCEL',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Cancelled portfolio: {portfolio_name}' + (f'. Reason: {reason}' if reason else ''),
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.warning(request, f'Portfolio "{portfolio_name}" has been cancelled.')
    except Exception as e:
        messages.error(request, f'Error cancelling portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)


def portfolio_reactivate(request, portfolio_name):
    """Reactivate cancelled portfolio (sets back to INITIAL)."""
    if request.method != 'POST':
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_name)
    if not portfolio:
        messages.error(request, f'Portfolio "{portfolio_name}" not found')
        return redirect('portfolio:list')

    user_info = get_user_info(request)
    comments = request.POST.get('comments', '').strip()
    current_status = portfolio.get('status', '')

    if current_status != PortfolioHiveRepository.STATUS_CANCELLED:
        messages.error(request, f'Cannot reactivate portfolio with status "{current_status}". Only CANCELLED portfolios can be reactivated.')
        return redirect('portfolio:detail', portfolio_name=portfolio_name)

    try:
        success = portfolio_hive_repository.reactivate_portfolio(
            portfolio_name, user_info['username'], comments
        )

        if not success:
            raise Exception('Failed to reactivate portfolio')

        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='REACTIVATE',
            entity_type='PORTFOLIO',
            entity_id=portfolio_name,
            entity_name=portfolio_name,
            action_description=f'Reactivated portfolio: {portfolio_name}' + (f'. Comments: {comments}' if comments else ''),
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='SUCCESS'
        )

        messages.success(request, f'Portfolio "{portfolio_name}" reactivated. Status set to INITIAL.')
    except Exception as e:
        messages.error(request, f'Error reactivating portfolio: {str(e)}')

    return redirect('portfolio:detail', portfolio_name=portfolio_name)


def pending_validation(request):
    """List portfolios pending validation (for Checkers)."""
    portfolios_data = portfolio_hive_repository.get_pending_validation_portfolios()
    wrapped_portfolios = [PortfolioWrapper(p, idx) for idx, p in enumerate(portfolios_data)]

    # Commented out VIEW audit logging (only log CREATE, UPDATE, DELETE)
    # user_info = get_user_info(request)
    # audit_log_kudu_repository.log_action(
    #     user_id=user_info['user_id'],
    #     username=user_info['username'],
    #     user_email=user_info['user_email'],
    #     action_type='VIEW',
    #     entity_type='PORTFOLIO',
    #     entity_id='PENDING_VALIDATION',
    #     entity_name='Pending Validation List',
    #     action_description=f'Viewed pending validation list ({len(portfolios_data)} portfolios)',
    #     request_method='GET',
    #     request_path=request.path,
    #     ip_address=request.META.get('REMOTE_ADDR'),
    #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
    #     status='SUCCESS'
    # )

    # Get counts for both tabs
    validation_count = len(portfolios_data)
    settlement_data = portfolio_hive_repository.get_validated_portfolios()
    settlement_count = len(settlement_data) if settlement_data else 0

    context = {
        'portfolios': wrapped_portfolios,
        'pending_count': len(portfolios_data),
        'view_type': 'validation',
        'pending_validation_count': validation_count,
        'pending_settlement_count': settlement_count,
    }

    return render(request, 'portfolio/pending_approvals.html', context)


def pending_settlement(request):
    """List validated portfolios ready for settlement (for Checkers)."""
    portfolios_data = portfolio_hive_repository.get_validated_portfolios()
    wrapped_portfolios = [PortfolioWrapper(p, idx) for idx, p in enumerate(portfolios_data)]

    # Commented out VIEW audit logging (only log CREATE, UPDATE, DELETE)
    # user_info = get_user_info(request)
    # audit_log_kudu_repository.log_action(
    #     user_id=user_info['user_id'],
    #     username=user_info['username'],
    #     user_email=user_info['user_email'],
    #     action_type='VIEW',
    #     entity_type='PORTFOLIO',
    #     entity_id='PENDING_SETTLEMENT',
    #     entity_name='Pending Settlement List',
    #     action_description=f'Viewed pending settlement list ({len(portfolios_data)} portfolios)',
    #     request_method='GET',
    #     request_path=request.path,
    #     ip_address=request.META.get('REMOTE_ADDR'),
    #     user_agent=request.META.get('HTTP_USER_AGENT', ''),
    #     status='SUCCESS'
    # )

    # Get counts for both tabs
    settlement_count = len(portfolios_data)
    validation_data = portfolio_hive_repository.get_pending_validation_portfolios()
    validation_count = len(validation_data) if validation_data else 0

    context = {
        'portfolios': wrapped_portfolios,
        'pending_count': len(portfolios_data),
        'view_type': 'settlement',
        'pending_validation_count': validation_count,
        'pending_settlement_count': settlement_count,
    }

    return render(request, 'portfolio/pending_approvals.html', context)


# Legacy views for backward compatibility
def pending_approvals(request):
    """Redirect to pending_validation for backward compatibility."""
    return pending_validation(request)


def portfolio_approve(request, portfolio_name):
    """Legacy: Redirect to validate."""
    return portfolio_validate(request, portfolio_name)


def portfolio_reject(request, portfolio_name):
    """Legacy: Redirect to cancel."""
    return portfolio_cancel(request, portfolio_name)


def portfolio_close(request, portfolio_name):
    """Legacy: Redirect to cancel."""
    return portfolio_cancel(request, portfolio_name)
