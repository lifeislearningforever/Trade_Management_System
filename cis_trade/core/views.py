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


@login_required
def dashboard(request):
    """
    Main dashboard view with statistics and recent activity.

    SOLID Principle: Single Responsibility - View handles only presentation logic
    """
    # Calculate statistics
    total_portfolios = Portfolio.objects.count()
    active_portfolios = Portfolio.objects.filter(status='ACTIVE', is_active=True).count()
    pending_portfolios = Portfolio.objects.filter(status='PENDING_APPROVAL').count()

    # Calculate total portfolio value (sum of cash balances)
    total_value = Portfolio.objects.filter(
        status='ACTIVE',
        is_active=True
    ).aggregate(
        total=models.Sum('cash_balance')
    )['total'] or 0

    # Convert to millions for display
    total_value_millions = total_value / 1_000_000

    # Get recent portfolios (last 10)
    recent_portfolios = Portfolio.objects.select_related(
        'created_by'
    ).order_by('-created_at')[:10]

    # Get pending approvals (for checkers)
    pending_approvals = []
    if request.user.groups.filter(name='Checkers').exists():
        pending_approvals = Portfolio.objects.filter(
            status='PENDING_APPROVAL'
        ).select_related('created_by', 'submitted_by').order_by('-submitted_for_approval_at')

    # Get recent activities (last 10 audit logs)
    recent_activities = AuditLog.objects.select_related(
        'user'
    ).order_by('-timestamp')[:10]

    # Calculate percentage changes (mock data - in production, compare with last month)
    portfolios_change = 5.2
    active_percentage = (active_portfolios / total_portfolios * 100) if total_portfolios > 0 else 0
    value_change = 3.8

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
        'recent_portfolios': recent_portfolios,
        'pending_approvals': pending_approvals,
        'recent_activities': recent_activities,
        'pending_portfolios_count': pending_portfolios,
    }

    # Log dashboard view
    AuditLog.log_action(
        action='VIEW',
        user=request.user,
        object_type='Dashboard',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
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

            # Log successful login
            AuditLog.log_action(
                action='LOGIN',
                user=user,
                object_type='Auth',
                description='User logged in successfully',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')

            # Redirect to next parameter or dashboard
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            # Log failed login attempt
            AuditLog.objects.create(
                action='LOGIN_FAILED',
                object_type='Auth',
                description=f'Failed login attempt for username: {username}',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            messages.error(request, 'Invalid username or password.')

    return render(request, 'auth/login.html')


@login_required
def user_logout(request):
    """
    User logout view.
    """
    # Log logout
    AuditLog.log_action(
        action='LOGOUT',
        user=request.user,
        object_type='Auth',
        description='User logged out',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
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


@login_required
def audit_log(request):
    """
    Audit log list view with filtering and search.
    """
    # Base queryset
    queryset = AuditLog.objects.select_related('user').order_by('-timestamp')

    # Search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(user__username__icontains=search_query) |
            Q(object_type__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(changes_summary__icontains=search_query)
        )

    # Filter by action
    action_filter = request.GET.get('action', '').strip()
    if action_filter:
        queryset = queryset.filter(action=action_filter)

    # Filter by date range
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)

    # Pagination
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    paginator = Paginator(queryset, 50)  # 50 items per page
    page = request.GET.get('page', 1)

    try:
        audit_logs = paginator.page(page)
    except PageNotAnInteger:
        audit_logs = paginator.page(1)
    except EmptyPage:
        audit_logs = paginator.page(paginator.num_pages)

    # Log audit log view
    AuditLog.log_action(
        action='VIEW',
        user=request.user,
        object_type='AuditLog',
        description='Viewed audit logs',
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    # Get unique actions for filter dropdown
    actions = AuditLog.objects.values_list('action', flat=True).distinct()

    context = {
        'audit_logs': audit_logs,
        'actions': sorted(set(actions)),
        'search_query': search_query,
        'action_filter': action_filter,
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(request, 'core/audit_log.html', context)
