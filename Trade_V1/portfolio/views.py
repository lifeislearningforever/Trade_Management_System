"""
Portfolio Views - Complete CRUD with Maker-Checker Workflow
Implements create, read, update, delete with approval workflow and audit logging
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone
from decimal import Decimal

from .models import Portfolio, Holding, Transaction
from reference_data.models import Client
from accounts.models import AuditLog


@login_required
def portfolio_list(request):
    """Portfolio list view with filtering and pagination"""
    # Base queryset
    portfolios = Portfolio.objects.select_related('created_by', 'approved_by', 'client', 'owner')

    # Apply filters based on user role
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')

    if status_filter:
        portfolios = portfolios.filter(status=status_filter)

    if search_query:
        portfolios = portfolios.filter(
            Q(portfolio_id__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Filter by user permissions
    if request.user.has_permission('approve_portfolio'):
        # Checkers see all portfolios
        pass
    elif request.user.has_permission('create_portfolio'):
        # Makers see only their own portfolios
        portfolios = portfolios.filter(created_by=request.user)
    else:
        # Others see only active portfolios they own
        portfolios = portfolios.filter(owner=request.user, status='ACTIVE')

    # Pagination
    paginator = Paginator(portfolios, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Statistics
    total_portfolios = portfolios.count()
    draft_count = portfolios.filter(status='DRAFT').count()
    pending_count = portfolios.filter(status='PENDING_APPROVAL').count()
    active_count = portfolios.filter(status='ACTIVE').count()

    # Log the view action
    AuditLog.log_action(
        user=request.user,
        action='VIEW',
        description='Viewed portfolio list',
        category='portfolio',
        object_type='Portfolio',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_portfolios': total_portfolios,
        'draft_count': draft_count,
        'pending_count': pending_count,
        'active_count': active_count,
        'STATUS_CHOICES': Portfolio.STATUS_CHOICES,
    }

    return render(request, 'portfolio/portfolio_list.html', context)


@login_required
def portfolio_create(request):
    """Create new portfolio"""
    # Check permission
    if not request.user.has_permission('create_portfolio'):
        messages.error(request, 'You do not have permission to create portfolios.')
        AuditLog.log_action(
            user=request.user,
            action='CREATE',
            description='Portfolio creation denied - insufficient permissions',
            category='portfolio',
            object_type='Portfolio',
            ip_address=request.META.get('REMOTE_ADDR'),
            status='PERMISSION_DENIED'
        )
        return redirect('portfolio_list')

    if request.method == 'POST':
        try:
            # Create portfolio
            portfolio = Portfolio(
                name=request.POST.get('name'),
                description=request.POST.get('description', ''),
                owner=request.user,  # Default owner is the creator
                initial_capital=Decimal(request.POST.get('initial_capital', '0')),
                current_cash=Decimal(request.POST.get('current_cash', '0')),
                base_currency=request.POST.get('base_currency', 'INR'),
                portfolio_group=request.POST.get('portfolio_group', ''),
                portfolio_subgroup=request.POST.get('portfolio_subgroup', ''),
                portfolio_manager=request.POST.get('portfolio_manager', ''),
                strategy=request.POST.get('strategy', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user,
                status='DRAFT'
            )

            # Set client if provided
            client_id = request.POST.get('client')
            if client_id:
                portfolio.client = Client.objects.get(id=client_id)

            portfolio.save()

            # Log success
            AuditLog.log_action(
                user=request.user,
                action='CREATE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name,
                    'initial_capital': str(portfolio.initial_capital)
                }
            )

            messages.success(request, f'Portfolio "{portfolio.name}" created successfully.')
            return redirect('portfolio_detail', pk=portfolio.id)

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='CREATE_PORTFOLIO',
                target_model='Portfolio',
                target_id=None,
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error creating portfolio: {str(e)}')

    # Get clients for dropdown
    clients = Client.objects.filter(is_active=True).order_by('name')

    context = {
        'clients': clients,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


@login_required
def portfolio_detail(request, pk):
    """Portfolio detail view with holdings and transactions"""
    portfolio = get_object_or_404(
        Portfolio.objects.select_related('created_by', 'approved_by', 'client', 'owner'),
        id=pk
    )

    # Check if user can view this portfolio
    can_view = (
        portfolio.owner == request.user or
        portfolio.created_by == request.user or
        request.user.has_permission('approve_portfolio') or
        portfolio.status == 'ACTIVE'
    )

    if not can_view:
        messages.error(request, 'You do not have permission to view this portfolio.')
        return redirect('portfolio_list')

    # Get holdings with stock details
    holdings = portfolio.holdings.select_related('stock').all()

    # Get recent transactions
    transactions = portfolio.transactions.select_related('stock').order_by('-transaction_date')[:10]

    # Calculate aggregates
    total_holdings_value = sum(h.current_value for h in holdings)
    total_holdings_cost = sum(h.total_cost for h in holdings)
    total_unrealized_pnl = total_holdings_value - total_holdings_cost

    # Check permissions for actions
    can_edit = portfolio.status == 'DRAFT' and portfolio.created_by == request.user
    can_submit = portfolio.status == 'DRAFT' and portfolio.created_by == request.user
    can_approve = portfolio.status == 'PENDING_APPROVAL' and portfolio.can_be_approved_by(request.user)
    can_reject = portfolio.status == 'PENDING_APPROVAL' and portfolio.can_be_approved_by(request.user)

    # Log the view action
    AuditLog.log_action(
        user=request.user,
        action='VIEW_PORTFOLIO_DETAIL',
        target_model='Portfolio',
        target_id=str(portfolio.id),
        status='SUCCESS',
        ip_address=request.META.get('REMOTE_ADDR'),
        details={'portfolio_id': portfolio.portfolio_id}
    )

    context = {
        'portfolio': portfolio,
        'holdings': holdings,
        'transactions': transactions,
        'total_holdings_value': total_holdings_value,
        'total_holdings_cost': total_holdings_cost,
        'total_unrealized_pnl': total_unrealized_pnl,
        'can_edit': can_edit,
        'can_submit': can_submit,
        'can_approve': can_approve,
        'can_reject': can_reject,
    }

    return render(request, 'portfolio/portfolio_detail.html', context)


@login_required
def portfolio_edit(request, pk):
    """Edit existing portfolio (only in DRAFT status)"""
    portfolio = get_object_or_404(Portfolio, id=pk)

    # Check permissions
    if portfolio.status != 'DRAFT':
        messages.error(request, 'Only DRAFT portfolios can be edited.')
        return redirect('portfolio_detail', pk=pk)

    if portfolio.created_by != request.user:
        messages.error(request, 'You can only edit portfolios you created.')
        return redirect('portfolio_detail', pk=pk)

    if request.method == 'POST':
        try:
            # Update portfolio fields
            portfolio.name = request.POST.get('name')
            portfolio.description = request.POST.get('description', '')
            portfolio.initial_capital = Decimal(request.POST.get('initial_capital', '0'))
            portfolio.current_cash = Decimal(request.POST.get('current_cash', '0'))
            portfolio.base_currency = request.POST.get('base_currency', 'INR')
            portfolio.portfolio_group = request.POST.get('portfolio_group', '')
            portfolio.portfolio_subgroup = request.POST.get('portfolio_subgroup', '')
            portfolio.portfolio_manager = request.POST.get('portfolio_manager', '')
            portfolio.strategy = request.POST.get('strategy', '')
            portfolio.notes = request.POST.get('notes', '')

            # Update client
            client_id = request.POST.get('client')
            if client_id:
                portfolio.client = Client.objects.get(id=client_id)
            else:
                portfolio.client = None

            portfolio.save()

            # Log success
            AuditLog.log_action(
                user=request.user,
                action='UPDATE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name
                }
            )

            messages.success(request, f'Portfolio "{portfolio.name}" updated successfully.')
            return redirect('portfolio_detail', pk=pk)

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='UPDATE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error updating portfolio: {str(e)}')

    # Get clients for dropdown
    clients = Client.objects.filter(is_active=True).order_by('name')

    context = {
        'portfolio': portfolio,
        'clients': clients,
        'is_edit': True,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


@login_required
def portfolio_submit(request, pk):
    """Submit portfolio for approval"""
    portfolio = get_object_or_404(Portfolio, id=pk)

    # Check permissions
    if portfolio.status != 'DRAFT':
        messages.error(request, 'Only DRAFT portfolios can be submitted.')
        return redirect('portfolio_detail', pk=pk)

    if portfolio.created_by != request.user:
        messages.error(request, 'You can only submit portfolios you created.')
        return redirect('portfolio_detail', pk=pk)

    if request.method == 'POST':
        try:
            # Change status to pending approval
            portfolio.status = 'PENDING_APPROVAL'
            portfolio.save()

            # Log success
            AuditLog.log_action(
                user=request.user,
                action='SUBMIT_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name
                }
            )

            messages.success(request, f'Portfolio "{portfolio.name}" submitted for approval.')
            return redirect('portfolio_detail', pk=pk)

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='SUBMIT_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error submitting portfolio: {str(e)}')

    return redirect('portfolio_detail', pk=pk)


@login_required
def portfolio_approve(request, pk):
    """Approve portfolio (Checker role)"""
    portfolio = get_object_or_404(Portfolio, id=pk)

    # Check permissions
    if portfolio.status != 'PENDING_APPROVAL':
        messages.error(request, 'Only PENDING_APPROVAL portfolios can be approved.')
        return redirect('portfolio_detail', pk=pk)

    if not portfolio.can_be_approved_by(request.user):
        messages.error(request, 'You cannot approve this portfolio (self-approval not allowed or missing permission).')
        AuditLog.log_action(
            user=request.user,
            action='APPROVE_PORTFOLIO',
            target_model='Portfolio',
            target_id=str(portfolio.id),
            status='PERMISSION_DENIED',
            ip_address=request.META.get('REMOTE_ADDR'),
            details={'portfolio_id': portfolio.portfolio_id, 'reason': 'Self-approval not allowed'}
        )
        return redirect('portfolio_detail', pk=pk)

    if request.method == 'POST':
        try:
            approval_notes = request.POST.get('notes', '')

            # Approve the portfolio
            portfolio.approve(request.user, approval_notes)

            # Log success
            AuditLog.log_action(
                user=request.user,
                action='APPROVE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name,
                    'notes': approval_notes
                }
            )

            messages.success(request, f'Portfolio "{portfolio.name}" approved successfully.')
            return redirect('portfolio_detail', pk=pk)

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='APPROVE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error approving portfolio: {str(e)}')

    return redirect('portfolio_detail', pk=pk)


@login_required
def portfolio_reject(request, pk):
    """Reject portfolio (Checker role)"""
    portfolio = get_object_or_404(Portfolio, id=pk)

    # Check permissions
    if portfolio.status != 'PENDING_APPROVAL':
        messages.error(request, 'Only PENDING_APPROVAL portfolios can be rejected.')
        return redirect('portfolio_detail', pk=pk)

    if not portfolio.can_be_approved_by(request.user):
        messages.error(request, 'You cannot reject this portfolio (self-rejection not allowed or missing permission).')
        AuditLog.log_action(
            user=request.user,
            action='REJECT_PORTFOLIO',
            target_model='Portfolio',
            target_id=str(portfolio.id),
            status='PERMISSION_DENIED',
            ip_address=request.META.get('REMOTE_ADDR'),
            details={'portfolio_id': portfolio.portfolio_id, 'reason': 'Self-rejection not allowed'}
        )
        return redirect('portfolio_detail', pk=pk)

    if request.method == 'POST':
        try:
            rejection_reason = request.POST.get('rejection_reason', '')

            if not rejection_reason:
                messages.error(request, 'Rejection reason is required.')
                return redirect('portfolio_detail', pk=pk)

            # Reject the portfolio
            portfolio.reject(request.user, rejection_reason)

            # Log success
            AuditLog.log_action(
                user=request.user,
                action='REJECT_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name,
                    'reason': rejection_reason
                }
            )

            messages.success(request, f'Portfolio "{portfolio.name}" rejected.')
            return redirect('portfolio_detail', pk=pk)

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='REJECT_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error rejecting portfolio: {str(e)}')

    return redirect('portfolio_detail', pk=pk)


@login_required
def portfolio_delete(request, pk):
    """Delete portfolio (only DRAFT or REJECTED)"""
    portfolio = get_object_or_404(Portfolio, id=pk)

    # Check permissions
    if portfolio.status not in ['DRAFT', 'REJECTED']:
        messages.error(request, 'Only DRAFT or REJECTED portfolios can be deleted.')
        return redirect('portfolio_detail', pk=pk)

    if portfolio.created_by != request.user:
        messages.error(request, 'You can only delete portfolios you created.')
        return redirect('portfolio_detail', pk=pk)

    if request.method == 'POST':
        try:
            portfolio_id = portfolio.portfolio_id
            portfolio_name = portfolio.name

            # Log before deletion
            AuditLog.log_action(
                user=request.user,
                action='DELETE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='SUCCESS',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={
                    'portfolio_id': portfolio_id,
                    'name': portfolio_name
                }
            )

            # Delete portfolio
            portfolio.delete()

            messages.success(request, f'Portfolio "{portfolio_name}" deleted successfully.')
            return redirect('portfolio_list')

        except Exception as e:
            # Log failure
            AuditLog.log_action(
                user=request.user,
                action='DELETE_PORTFOLIO',
                target_model='Portfolio',
                target_id=str(portfolio.id),
                status='FAILED',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'error': str(e)}
            )
            messages.error(request, f'Error deleting portfolio: {str(e)}')

    return redirect('portfolio_detail', pk=pk)
