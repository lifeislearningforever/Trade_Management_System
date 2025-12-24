"""
Portfolio Views
Handles portfolio CRUD operations, Four-Eyes workflow, and CSV export.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q
import csv

from .models import Portfolio
from .services import PortfolioService
from core.models import AuditLog


@login_required
def portfolio_list(request):
    """
    List all portfolios with search, filter, and CSV export.
    """
    # Get filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    currency_filter = request.GET.get('currency', '').strip()
    export = request.GET.get('export', '').strip()

    # Build queryset
    queryset = PortfolioService.list_portfolios(
        status=status_filter if status_filter else None,
        search=search_query if search_query else None,
        currency=currency_filter if currency_filter else None
    )

    # CSV Export
    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="portfolios.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Code', 'Name', 'Currency', 'Manager', 'Cash Balance',
            'Status', 'Created By', 'Created At', 'Approved By'
        ])

        for portfolio in queryset:
            writer.writerow([
                portfolio.code,
                portfolio.name,
                portfolio.currency,
                portfolio.manager,
                portfolio.cash_balance,
                portfolio.status,
                portfolio.created_by.username if portfolio.created_by else '',
                portfolio.created_at.strftime('%Y-%m-%d %H:%M'),
                portfolio.approved_by.username if portfolio.approved_by else ''
            ])

        # Log export
        AuditLog.log_action(
            action='EXPORT',
            user=request.user,
            object_type='Portfolio',
            description=f'Exported {queryset.count()} portfolios to CSV',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Pagination
    paginator = Paginator(queryset, 25)
    page = request.GET.get('page', 1)

    try:
        portfolios = paginator.page(page)
    except PageNotAnInteger:
        portfolios = paginator.page(1)
    except EmptyPage:
        portfolios = paginator.page(paginator.num_pages)

    # Get unique currencies for filter
    currencies = Portfolio.objects.values_list('currency', flat=True).distinct()

    context = {
        'portfolios': portfolios,
        'search_query': search_query,
        'status_filter': status_filter,
        'currency_filter': currency_filter,
        'currencies': sorted(set(currencies)),
    }

    return render(request, 'portfolio/portfolio_list.html', context)


@login_required
def portfolio_detail(request, pk):
    """
    View portfolio details and history.
    """
    portfolio = get_object_or_404(Portfolio, pk=pk)

    # Get change history
    history = PortfolioService.get_portfolio_history(portfolio)

    # Check permissions
    can_edit = PortfolioService.can_user_edit(portfolio, request.user)
    can_approve = PortfolioService.can_user_approve(portfolio, request.user)

    context = {
        'portfolio': portfolio,
        'history': history,
        'can_edit': can_edit,
        'can_approve': can_approve,
    }

    return render(request, 'portfolio/portfolio_detail.html', context)


@login_required
def portfolio_create(request):
    """
    Create a new portfolio.
    """
    if request.method == 'POST':
        try:
            data = {
                'code': request.POST.get('code'),
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
            }

            portfolio = PortfolioService.create_portfolio(request.user, data)
            messages.success(request, f'Portfolio {portfolio.code} created successfully!')
            return redirect('portfolio:detail', pk=portfolio.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating portfolio: {str(e)}')

    # Get currencies for dropdown
    from reference_data.models import Currency
    currencies = Currency.objects.filter(is_active=True).order_by('code')

    context = {
        'currencies': currencies,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


@login_required
def portfolio_edit(request, pk):
    """
    Edit an existing portfolio (DRAFT or REJECTED only).
    """
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
            }

            portfolio = PortfolioService.update_portfolio(portfolio, request.user, data)
            messages.success(request, f'Portfolio {portfolio.code} updated successfully!')
            return redirect('portfolio:detail', pk=portfolio.id)

        except (ValidationError, PermissionDenied) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error updating portfolio: {str(e)}')

    # Get currencies for dropdown
    from reference_data.models import Currency
    currencies = Currency.objects.filter(is_active=True).order_by('code')

    context = {
        'portfolio': portfolio,
        'currencies': currencies,
        'is_edit': True,
    }

    return render(request, 'portfolio/portfolio_form.html', context)


@login_required
def portfolio_submit(request, pk):
    """
    Submit portfolio for approval (Maker action).
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


@login_required
def portfolio_approve(request, pk):
    """
    Approve portfolio (Checker action - Four-Eyes).
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


@login_required
def portfolio_reject(request, pk):
    """
    Reject portfolio (Checker action).
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


@login_required
def pending_approvals(request):
    """
    List portfolios pending approval (for Checkers).
    """
    # Only show to users in Checkers group
    if not request.user.groups.filter(name='Checkers').exists() and not request.user.is_superuser:
        messages.error(request, 'Access denied. Only Checkers can view pending approvals.')
        return redirect('dashboard')

    portfolios = PortfolioService.get_pending_approvals()

    context = {
        'portfolios': portfolios,
    }

    return render(request, 'portfolio/pending_approvals.html', context)
