"""
Hive POC Views

Simple views for demonstrating CRUD operations with Hive Managed Tables.
Supports both traditional form submissions and AJAX requests with progress modal.
"""

import logging
import time
from datetime import datetime, date
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse

from .services.portfolio_hive_service import PortfolioHiveService, PortfolioDTO
from .services.trade_hive_service import TradeHiveService, TradeDTO

logger = logging.getLogger('hive_poc')


def is_ajax(request: HttpRequest) -> bool:
    """Check if request is an AJAX request."""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def json_response(success: bool, message: str, redirect_url: str = None,
                  elapsed_ms: float = None, errors: dict = None) -> JsonResponse:
    """Create a standardized JSON response for AJAX requests."""
    data = {
        'success': success,
        'message': message,
    }
    if redirect_url:
        data['redirect_url'] = redirect_url
    if elapsed_ms is not None:
        data['elapsed_ms'] = elapsed_ms
    if errors:
        data['errors'] = errors
    return JsonResponse(data)


# =============================================================================
# Dashboard
# =============================================================================

def hive_poc_dashboard(request: HttpRequest) -> HttpResponse:
    """POC Dashboard with overview of portfolios and trades."""
    portfolio_service = PortfolioHiveService()
    trade_service = TradeHiveService()

    portfolios = portfolio_service.get_all()
    trades = trade_service.get_all()

    context = {
        'portfolios': portfolios,
        'trades': trades[:10],  # Latest 10
        'portfolio_count': len(portfolios),
        'trade_count': len(trades),
        'deleted_portfolios': len(portfolio_service.get_deleted()),
        'deleted_trades': len(trade_service.get_deleted()),
    }
    return render(request, 'hive_poc/dashboard.html', context)


# =============================================================================
# Portfolio Views
# =============================================================================

def portfolio_list(request: HttpRequest) -> HttpResponse:
    """List all portfolios."""
    service = PortfolioHiveService()
    show_deleted = request.GET.get('show_deleted') == '1'

    portfolios = service.get_all(include_deleted=show_deleted)

    context = {
        'portfolios': portfolios,
        'show_deleted': show_deleted,
    }
    return render(request, 'hive_poc/portfolio_list.html', context)


def portfolio_create(request: HttpRequest) -> HttpResponse:
    """Create a new portfolio."""
    service = PortfolioHiveService()

    if request.method == 'POST':
        start_time = time.time()

        dto = PortfolioDTO(
            portfolio_name=request.POST.get('portfolio_name', ''),
            portfolio_code=request.POST.get('portfolio_code', '').upper(),
            portfolio_type=request.POST.get('portfolio_type', 'EQUITY'),
            currency=request.POST.get('currency', 'USD'),
            manager_name=request.POST.get('manager_name', ''),
            description=request.POST.get('description', ''),
            status=request.POST.get('status', 'DRAFT'),
            created_by='poc_user',
            updated_by='poc_user',
        )

        result = service.create(dto)
        elapsed_ms = (time.time() - start_time) * 1000

        if is_ajax(request):
            if result['success']:
                return json_response(
                    success=True,
                    message=result['message'],
                    redirect_url=reverse('hive_poc:portfolio_list'),
                    elapsed_ms=elapsed_ms
                )
            else:
                return json_response(
                    success=False,
                    message='Validation failed',
                    errors=result.get('errors', {}),
                    elapsed_ms=elapsed_ms
                )

        # Traditional form submission
        if result['success']:
            messages.success(request, result['message'])
            return redirect('hive_poc:portfolio_list')
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, f"{field}: {error}")

    context = {
        'type_choices': service.get_type_choices(),
        'status_choices': service.get_status_choices(),
        'currency_choices': service.get_currency_choices(),
    }
    return render(request, 'hive_poc/portfolio_form.html', context)


def portfolio_edit(request: HttpRequest, portfolio_id: str) -> HttpResponse:
    """Edit an existing portfolio."""
    service = PortfolioHiveService()
    portfolio = service.get_by_id(portfolio_id)

    if not portfolio:
        if is_ajax(request):
            return json_response(success=False, message='Portfolio not found')
        messages.error(request, 'Portfolio not found')
        return redirect('hive_poc:portfolio_list')

    if request.method == 'POST':
        start_time = time.time()

        dto = PortfolioDTO(
            portfolio_name=request.POST.get('portfolio_name', ''),
            portfolio_code=request.POST.get('portfolio_code', '').upper(),
            portfolio_type=request.POST.get('portfolio_type', 'EQUITY'),
            currency=request.POST.get('currency', 'USD'),
            manager_name=request.POST.get('manager_name', ''),
            description=request.POST.get('description', ''),
            status=request.POST.get('status', 'ACTIVE'),
            updated_by='poc_user',
        )

        result = service.update(portfolio_id, dto)
        elapsed_ms = (time.time() - start_time) * 1000

        if is_ajax(request):
            if result['success']:
                return json_response(
                    success=True,
                    message=result['message'],
                    redirect_url=reverse('hive_poc:portfolio_list'),
                    elapsed_ms=elapsed_ms
                )
            else:
                return json_response(
                    success=False,
                    message='Validation failed',
                    errors=result.get('errors', {}),
                    elapsed_ms=elapsed_ms
                )

        # Traditional form submission
        if result['success']:
            messages.success(request, result['message'])
            return redirect('hive_poc:portfolio_list')
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, f"{field}: {error}")

    context = {
        'portfolio': portfolio,
        'type_choices': service.get_type_choices(),
        'status_choices': service.get_status_choices(),
        'currency_choices': service.get_currency_choices(),
        'is_edit': True,
    }
    return render(request, 'hive_poc/portfolio_form.html', context)


def portfolio_delete(request: HttpRequest, portfolio_id: str) -> HttpResponse:
    """Soft delete a portfolio."""
    service = PortfolioHiveService()

    if request.method == 'POST':
        result = service.delete(portfolio_id, deleted_by='poc_user')
        if result['success']:
            messages.success(request, result['message'])
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, error)

    return redirect('hive_poc:portfolio_list')


def portfolio_restore(request: HttpRequest, portfolio_id: str) -> HttpResponse:
    """Restore a soft-deleted portfolio."""
    service = PortfolioHiveService()

    if request.method == 'POST':
        result = service.restore(portfolio_id, restored_by='poc_user')
        if result['success']:
            messages.success(request, result['message'])
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, error)

    return redirect('hive_poc:portfolio_list')


def portfolio_deleted(request: HttpRequest) -> HttpResponse:
    """List soft-deleted portfolios."""
    service = PortfolioHiveService()
    portfolios = service.get_deleted()

    context = {
        'portfolios': portfolios,
    }
    return render(request, 'hive_poc/portfolio_deleted.html', context)


# =============================================================================
# Trade Views
# =============================================================================

def trade_list(request: HttpRequest) -> HttpResponse:
    """List all trades."""
    service = TradeHiveService()
    show_deleted = request.GET.get('show_deleted') == '1'

    trades = service.get_all(include_deleted=show_deleted)

    context = {
        'trades': trades,
        'show_deleted': show_deleted,
    }
    return render(request, 'hive_poc/trade_list.html', context)


def trade_create(request: HttpRequest) -> HttpResponse:
    """Create a new trade."""
    trade_service = TradeHiveService()
    portfolio_service = PortfolioHiveService()

    if request.method == 'POST':
        start_time = time.time()

        # Parse dates
        trade_date_str = request.POST.get('trade_date', '')
        settlement_date_str = request.POST.get('settlement_date', '')

        trade_date = None
        settlement_date = None
        if trade_date_str:
            try:
                trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if settlement_date_str:
            try:
                settlement_date = datetime.strptime(settlement_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Parse numbers
        quantity_str = request.POST.get('quantity', '0')
        price_str = request.POST.get('price', '0')
        try:
            quantity = Decimal(quantity_str) if quantity_str else Decimal('0')
        except:
            quantity = Decimal('0')
        try:
            price = Decimal(price_str) if price_str else Decimal('0')
        except:
            price = Decimal('0')

        dto = TradeDTO(
            portfolio_id=request.POST.get('portfolio_id', ''),
            security_id=request.POST.get('security_id', ''),
            security_name=request.POST.get('security_name', ''),
            trade_type=request.POST.get('trade_type', 'BUY'),
            quantity=quantity,
            price=price,
            currency=request.POST.get('currency', 'USD'),
            trade_date=trade_date,
            settlement_date=settlement_date,
            status=request.POST.get('status', 'PENDING'),
            broker=request.POST.get('broker', ''),
            notes=request.POST.get('notes', ''),
            created_by='poc_user',
            updated_by='poc_user',
        )

        result = trade_service.create(dto)
        elapsed_ms = (time.time() - start_time) * 1000

        if is_ajax(request):
            if result['success']:
                return json_response(
                    success=True,
                    message=result['message'],
                    redirect_url=reverse('hive_poc:trade_list'),
                    elapsed_ms=elapsed_ms
                )
            else:
                return json_response(
                    success=False,
                    message='Validation failed',
                    errors=result.get('errors', {}),
                    elapsed_ms=elapsed_ms
                )

        # Traditional form submission
        if result['success']:
            messages.success(request, result['message'])
            return redirect('hive_poc:trade_list')
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, f"{field}: {error}")

    context = {
        'portfolios': portfolio_service.get_dropdown_options(),
        'type_choices': trade_service.get_type_choices(),
        'status_choices': trade_service.get_status_choices(),
        'currency_choices': trade_service.get_currency_choices(),
    }
    return render(request, 'hive_poc/trade_form.html', context)


def trade_edit(request: HttpRequest, trade_id: str) -> HttpResponse:
    """Edit an existing trade."""
    trade_service = TradeHiveService()
    portfolio_service = PortfolioHiveService()

    trade = trade_service.get_by_id(trade_id)

    if not trade:
        if is_ajax(request):
            return json_response(success=False, message='Trade not found')
        messages.error(request, 'Trade not found')
        return redirect('hive_poc:trade_list')

    if request.method == 'POST':
        start_time = time.time()

        # Parse dates
        trade_date_str = request.POST.get('trade_date', '')
        settlement_date_str = request.POST.get('settlement_date', '')

        trade_date = None
        settlement_date = None
        if trade_date_str:
            try:
                trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if settlement_date_str:
            try:
                settlement_date = datetime.strptime(settlement_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Parse numbers
        quantity_str = request.POST.get('quantity', '0')
        price_str = request.POST.get('price', '0')
        try:
            quantity = Decimal(quantity_str) if quantity_str else Decimal('0')
        except:
            quantity = Decimal('0')
        try:
            price = Decimal(price_str) if price_str else Decimal('0')
        except:
            price = Decimal('0')

        dto = TradeDTO(
            portfolio_id=request.POST.get('portfolio_id', ''),
            security_id=request.POST.get('security_id', ''),
            security_name=request.POST.get('security_name', ''),
            trade_type=request.POST.get('trade_type', 'BUY'),
            quantity=quantity,
            price=price,
            currency=request.POST.get('currency', 'USD'),
            trade_date=trade_date,
            settlement_date=settlement_date,
            status=request.POST.get('status', 'PENDING'),
            broker=request.POST.get('broker', ''),
            notes=request.POST.get('notes', ''),
            updated_by='poc_user',
        )

        result = trade_service.update(trade_id, dto)
        elapsed_ms = (time.time() - start_time) * 1000

        if is_ajax(request):
            if result['success']:
                return json_response(
                    success=True,
                    message=result['message'],
                    redirect_url=reverse('hive_poc:trade_list'),
                    elapsed_ms=elapsed_ms
                )
            else:
                return json_response(
                    success=False,
                    message='Validation failed',
                    errors=result.get('errors', {}),
                    elapsed_ms=elapsed_ms
                )

        # Traditional form submission
        if result['success']:
            messages.success(request, result['message'])
            return redirect('hive_poc:trade_list')
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, f"{field}: {error}")

    context = {
        'trade': trade,
        'portfolios': portfolio_service.get_dropdown_options(),
        'type_choices': trade_service.get_type_choices(),
        'status_choices': trade_service.get_status_choices(),
        'currency_choices': trade_service.get_currency_choices(),
        'is_edit': True,
    }
    return render(request, 'hive_poc/trade_form.html', context)


def trade_delete(request: HttpRequest, trade_id: str) -> HttpResponse:
    """Soft delete a trade."""
    service = TradeHiveService()

    if request.method == 'POST':
        result = service.delete(trade_id, deleted_by='poc_user')
        if result['success']:
            messages.success(request, result['message'])
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, error)

    return redirect('hive_poc:trade_list')


def trade_restore(request: HttpRequest, trade_id: str) -> HttpResponse:
    """Restore a soft-deleted trade."""
    service = TradeHiveService()

    if request.method == 'POST':
        result = service.restore(trade_id, restored_by='poc_user')
        if result['success']:
            messages.success(request, result['message'])
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, error)

    return redirect('hive_poc:trade_list')


def trade_deleted(request: HttpRequest) -> HttpResponse:
    """List soft-deleted trades."""
    service = TradeHiveService()
    trades = service.get_deleted()

    context = {
        'trades': trades,
    }
    return render(request, 'hive_poc/trade_deleted.html', context)


def trade_update_status(request: HttpRequest, trade_id: str) -> HttpResponse:
    """Update trade status."""
    service = TradeHiveService()

    if request.method == 'POST':
        new_status = request.POST.get('status', '')
        result = service.update_status(trade_id, new_status, updated_by='poc_user')

        if result['success']:
            messages.success(request, result['message'])
        else:
            for field, error in result.get('errors', {}).items():
                messages.error(request, error)

    return redirect('hive_poc:trade_list')
