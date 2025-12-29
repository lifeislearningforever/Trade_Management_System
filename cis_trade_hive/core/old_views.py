"""
Core Views
Handles dashboard, authentication, audit logs, and profile views.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.db import models
from django.utils import timezone
from datetime import timedelta

from .models import AuditLog
from portfolio.models import Portfolio
from core.audit.audit_hive_repository import audit_log_repository
from portfolio.repositories import portfolio_hive_repository


@login_required
def dashboard(request):
    """
    Main dashboard view with statistics and recent activity - FROM HIVE.

    SOLID Principle: Single Responsibility - View handles only presentation logic
    """
    # Get portfolio statistics from Hive
    hive_stats = portfolio_hive_repository.get_portfolio_statistics()

    total_portfolios = hive_stats.get('total_portfolios', 0)
    active_portfolios = hive_stats.get('active_portfolios', 0)

    # Get pending approvals from Django (workflow data still in Django)
    pending_portfolios = Portfolio.objects.filter(status='PENDING_APPROVAL').count()

    # Calculate total portfolio value (mock - would need cash_balance from Hive)
    total_value_millions = 0  # Placeholder - Hive query would sum cash_balance

    # Get recent portfolios from Hive (last 10)
    recent_portfolios_data = portfolio_hive_repository.get_all_portfolios(limit=10)

    # Get pending approvals (for checkers) - from Django
    pending_approvals = []
    if request.user.groups.filter(name='Checkers').exists():
        pending_approvals = Portfolio.objects.filter(
            status='PENDING_APPROVAL'
        ).select_related('created_by', 'submitted_by').order_by('-submitted_for_approval_at')

    # Get recent activities (last 10 audit logs) - from Django for now
    recent_activities = AuditLog.objects.select_related(
        'user'
    ).order_by('-timestamp')[:10]

    # Calculate percentage changes
    portfolios_change = 5.2  # Mock data
    active_percentage = (active_portfolios / total_portfolios * 100) if total_portfolios > 0 else 0
    value_change = 3.8  # Mock data

    # Get currency breakdown from Hive
    currency_breakdown = hive_stats.get('currency_breakdown', [])

    context = {
        'stats': {
            'total_portfolios': total_portfolios,
            'active_portfolios': active_portfolios,
            'pending_portfolios': pending_portfolios,
            'total_value': round(total_value_millions, 1),
            'portfolios_change': portfolios_change,
            'active_percentage': round(active_percentage, 1),
            'value_change': value_change,
        },
        'recent_portfolios': recent_portfolios_data,
        'pending_approvals': pending_approvals,
        'recent_activities': recent_activities,
        'pending_portfolios_count': pending_portfolios,
        'currency_breakdown': currency_breakdown,
        'using_hive': True,  # Flag to indicate Hive data source
    }

    # Log dashboard view to Hive
    audit_log_repository.log_action(
        user_id=str(request.user.id),
        username=request.user.username,
        action_type='VIEW',
        entity_type='DASHBOARD',
        action_description=f'Viewed dashboard - {total_portfolios} portfolios from Hive',
        request_method='GET',
        request_path='/dashboard/',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        status='SUCCESS'
    )

    return render(request, 'dashboard.html', context)


def user_login(request):
    """
    User login view.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Log successful login to Hive
            audit_log_repository.log_action(
                user_id=str(user.id),
                username=user.username,
                action_type='LOGIN',
                entity_type='AUTH',
                action_description='User logged in successfully',
                request_method='POST',
                request_path='/login/',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')

            # Redirect to next parameter or dashboard
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            # Log failed login attempt to Hive
            audit_log_repository.log_action(
                user_id='anonymous',
                username=username or 'unknown',
                action_type='LOGIN',
                entity_type='AUTH',
                action_description=f'Failed login attempt for username: {username}',
                request_method='POST',
                request_path='/login/',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='FAILURE',
                error_message='Invalid credentials'
            )

            messages.error(request, 'Invalid username or password.')

    return render(request, 'auth/login.html')


@login_required
def user_logout(request):
    """
    User logout view.
    """
    # Log logout to Hive
    audit_log_repository.log_action(
        user_id=str(request.user.id),
        username=request.user.username,
        action_type='LOGOUT',
        entity_type='AUTH',
        action_description='User logged out',
        request_method='POST',
        request_path='/logout/',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        status='SUCCESS'
    )

    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


@login_required
def profile(request):
    """
    User profile view.
    """
    # Get user's recent activity
    user_activities = AuditLog.objects.filter(
        user=request.user
    ).order_by('-timestamp')[:20]

    # Get user's portfolios
    user_portfolios = Portfolio.objects.filter(
        created_by=request.user
    ).order_by('-created_at')

    context = {
        'user_activities': user_activities,
        'user_portfolios': user_portfolios,
    }

    return render(request, 'auth/profile.html', context)


# @login_required  # Commented for development
def audit_log(request):
    """
    Audit log list view with filtering and search - KUDU/IMPALA INTEGRATION.
    Fetches audit logs from Kudu cis_audit_log table via Impala.
    """
    from core.audit.audit_kudu_repository import audit_log_kudu_repository

    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    action_filter = request.GET.get('action', '').strip()
    entity_filter = request.GET.get('entity_type', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    # Get audit logs from Kudu/Impala with error handling
    try:
        audit_logs_list = audit_log_kudu_repository.get_all_logs(
            limit=1000,  # Fetch more for client-side pagination
            action_type=action_filter if action_filter else None,
            entity_type=entity_filter if entity_filter else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
            search=search_query if search_query else None
        )
    except Exception as e:
        # If Kudu connection fails, return empty list with error message
        messages.warning(request, f'Unable to connect to Kudu: {str(e)}. Showing empty results.')
        audit_logs_list = []

    # Pagination
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    paginator = Paginator(audit_logs_list, 50)  # 50 items per page
    page = request.GET.get('page', 1)

    try:
        audit_logs = paginator.page(page)
    except PageNotAnInteger:
        audit_logs = paginator.page(1)
    except EmptyPage:
        audit_logs = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Get unique action types for filter dropdown
    action_types = sorted(set([log.get('action_type') for log in audit_logs_list if log.get('action_type')]))

    # Get unique entity types for filter dropdown
    entity_types = sorted(set([log.get('entity_type') for log in audit_logs_list if log.get('entity_type')]))

    # Prepare context for template
    context = {
        'audit_logs': audit_logs,
        'actions': action_types,  # For filter dropdown
        'entity_types': entity_types,
        'search_query': search_query,
        'action_filter': action_filter,
        'entity_filter': entity_filter,
        'date_from': date_from,
        'date_to': date_to,
        'total_count': len(audit_logs_list),
        'using_kudu': True,  # Flag to indicate Kudu integration
    }

    return render(request, 'core/audit_log.html', context)
