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
from django.http import JsonResponse
from datetime import timedelta
import logging

from .models import AuditLog
from portfolio.models import Portfolio
from core.audit.audit_hive_repository import audit_log_repository
from portfolio.repositories import portfolio_hive_repository

logger = logging.getLogger(__name__)


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
    import csv
    from django.http import HttpResponse
    from core.audit.audit_kudu_repository import audit_log_kudu_repository

    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    action_filter = request.GET.get('action', '').strip()
    entity_filter = request.GET.get('entity_type', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    export = request.GET.get('export') == 'csv'

    # Get audit logs from Kudu/Impala with error handling
    try:
        audit_logs_list = audit_log_kudu_repository.get_all_logs(
            limit=10000 if export else 1000,  # Fetch more for export
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

    # CSV Export
    if export:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="audit_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'User', 'Email', 'Action', 'Entity Type', 'Entity ID',
                        'Entity Name', 'Description', 'Old Value', 'New Value', 'IP Address', 'Status'])

        for log in audit_logs_list:
            writer.writerow([
                log.get('audit_timestamp', ''),
                log.get('username', ''),
                log.get('user_email', ''),
                log.get('action_type', ''),
                log.get('entity_type', ''),
                log.get('entity_id', ''),
                log.get('entity_name', ''),
                log.get('action_description', ''),
                log.get('old_value', ''),
                log.get('new_value', ''),
                log.get('ip_address', ''),
                log.get('status', ''),
            ])

        return response

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

    # Build query string without 'page' so pagination links don't double-append it
    params = request.GET.copy()
    params.pop('page', None)
    filter_query_string = params.urlencode()  # e.g. "search=foo&action=CREATE"

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
        'filter_query_string': filter_query_string,
    }

    return render(request, 'core/audit_log.html', context)


def health_check(request):
    """
    Health check endpoint for monitoring long-running applications.

    Returns JSON with:
    - Application status
    - Connection pool health
    - Performance metrics
    - Queue status

    Use: GET /health/
    """
    from core.repositories.impala_connection import impala_manager
    from core.middleware.performance_middleware import PerformanceMonitoringMiddleware

    health_status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }

    # Check Impala connection pool
    try:
        pool_stats = impala_manager.get_pool_stats()
        health_status['checks']['impala_pool'] = {
            'status': 'healthy',
            'active_connections': pool_stats.get('active_connections', 0),
            'pool_size': pool_stats.get('pool_size', 0),
            'pool_available': pool_stats.get('pool_available', 0),
            'utilization_pct': round(pool_stats.get('pool_utilization_pct', 0), 1),
            'connection_reuse_count': pool_stats.get('connection_reuse_count', 0),
            'validation_skip_count': pool_stats.get('validation_skip_count', 0)
        }

        # Flag if pool utilization is high
        if pool_stats.get('pool_utilization_pct', 0) > 90:
            health_status['checks']['impala_pool']['status'] = 'warning'
            health_status['status'] = 'degraded'

    except Exception as e:
        health_status['checks']['impala_pool'] = {
            'status': 'error',
            'error': str(e)
        }
        health_status['status'] = 'unhealthy'

    # Check async queue status
    try:
        async_queue_size = impala_manager.get_async_queue_size()
        health_status['checks']['async_queue'] = {
            'status': 'healthy' if async_queue_size < 100 else 'warning',
            'queue_size': async_queue_size
        }
        if async_queue_size >= 100:
            health_status['status'] = 'degraded'
    except Exception as e:
        health_status['checks']['async_queue'] = {
            'status': 'error',
            'error': str(e)
        }

    # Get performance stats
    try:
        perf_stats = PerformanceMonitoringMiddleware.get_stats_summary()
        health_status['checks']['performance'] = {
            'status': 'healthy' if perf_stats['slow_request_pct'] < 10 else 'warning',
            'request_count': perf_stats['request_count'],
            'slow_request_count': perf_stats['slow_request_count'],
            'slow_request_pct': perf_stats['slow_request_pct'],
            'avg_request_time_ms': perf_stats['avg_request_time_ms']
        }
        if perf_stats['slow_request_pct'] >= 10:
            health_status['status'] = 'degraded'
    except Exception as e:
        health_status['checks']['performance'] = {
            'status': 'error',
            'error': str(e)
        }

    # Test Impala connectivity with a simple query
    try:
        results = impala_manager.execute_query("SELECT 1 AS health_check", database='gmp_cis')
        if results:
            health_status['checks']['impala_connectivity'] = {'status': 'healthy'}
        else:
            health_status['checks']['impala_connectivity'] = {'status': 'warning', 'message': 'Empty result'}
    except Exception as e:
        health_status['checks']['impala_connectivity'] = {
            'status': 'error',
            'error': str(e)
        }
        health_status['status'] = 'unhealthy'

    # Set HTTP status code based on health
    status_code = 200
    if health_status['status'] == 'degraded':
        status_code = 200  # Still return 200 for degraded (app is running)
    elif health_status['status'] == 'unhealthy':
        status_code = 503  # Service unavailable

    return JsonResponse(health_status, status=status_code)


def pool_stats(request):
    """
    Detailed pool statistics endpoint for debugging.

    Use: GET /pool-stats/
    """
    from core.repositories.impala_connection import impala_manager

    try:
        stats = impala_manager.get_pool_stats()
        return JsonResponse({
            'status': 'ok',
            'timestamp': timezone.now().isoformat(),
            'pool_stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting pool stats: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


def reset_pool_stats(request):
    """
    Reset pool and performance statistics.

    Use: POST /reset-stats/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    from core.repositories.impala_connection import impala_manager
    from core.middleware.performance_middleware import PerformanceMonitoringMiddleware

    try:
        impala_manager.reset_stats()
        PerformanceMonitoringMiddleware.reset_stats()

        return JsonResponse({
            'status': 'ok',
            'message': 'Stats reset successfully',
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error resetting stats: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


# =========================================================================
# SYSTEM DATE API
# =========================================================================

def system_date_api(request):
    """
    API endpoint to get current system date info from GMP file.

    Returns JSON with:
    - system_date: Business date T (YYYYMMDD)
    - report_date: Report date T-1 (YYYYMMDD)
    - processing_date: Processing date (YYYYMMDD)
    - source: 'GMP_FILE' or 'FALLBACK'
    - is_business_day: Whether system_date is a business day
    """
    from core.services.system_date_service import system_date_service

    date_info = system_date_service.get_system_date_info()

    return JsonResponse({
        'system_date': date_info.system_date_str,
        'system_date_display': date_info.system_date_display,
        'report_date': date_info.report_date_str,
        'report_date_display': date_info.report_date_display,
        'processing_date': date_info.processing_date_str,
        'source': date_info.source,
        'is_business_day': date_info.is_business_day,
        'source_file': date_info.source_file,
        'loaded_at': date_info.loaded_at.isoformat() if date_info.loaded_at else None,
    })


# =========================================================================
# WEBSOCKET DIAGNOSTICS
# =========================================================================

def ws_debug(request):
    """
    GET /core/ws-debug/
    JSON dump of the full WebSocket / channel-layer diagnostic state.
    No login required so it works even when session is broken.
    """
    import sys, os
    data = {}

    # 1. Channel layer
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        data['channel_layer'] = {
            'configured': layer is not None,
            'backend': type(layer).__name__ if layer else None,
            'module': type(layer).__module__ if layer else None,
        }
    except Exception as e:
        data['channel_layer'] = {'error': str(e)}

    # 2. ASGI application type
    try:
        from config.asgi import application
        data['asgi_application'] = type(application).__name__
    except Exception as e:
        data['asgi_application'] = f'error: {e}'

    # 3. Session / logged-in user
    username = request.session.get('user_login', '')
    data['session'] = {
        'user_login': username or None,
        'session_key': request.session.session_key,
    }

    # 4. Channel group the user would be in
    if username:
        from core.notifications.constants import user_group
        data['expected_group'] = user_group(username)

    # 5. Server process info
    data['server'] = {
        'pid': os.getpid(),
        'python': sys.executable,
        'workers_env': os.environ.get('WORKERS', 'not set'),
        'redis_url': 'SET' if os.environ.get('REDIS_URL') else 'NOT SET',
    }

    return JsonResponse(data, json_dumps_params={'indent': 2})


def ws_test_notify(request):
    """
    POST /core/ws-test-notify/
    Fires a real AVP_COMPLETED notification to the logged-in user via the
    channel layer so you can verify end-to-end without saving a trade.

    Returns JSON: {ok, username, group, channel_layer_backend, error?}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    username = request.session.get('user_login', '')
    if not username:
        return JsonResponse({'error': 'Not logged in — no user_login in session'}, status=403)

    try:
        from core.notifications import notify_user
        from core.notifications.constants import EVT_AVP_COMPLETED, user_group
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        group = user_group(username)

        ok = notify_user(username, EVT_AVP_COMPLETED, {
            'trade_id': 'TEST-001',
            'message': f'WebSocket test notification for {username} — if you see this, notifications are working!',
        })

        return JsonResponse({
            'ok': ok,
            'username': username,
            'group': group,
            'channel_layer_backend': type(layer).__name__ if layer else None,
            'pid': __import__('os').getpid(),
        })
    except Exception as e:
        import traceback
        return JsonResponse({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}, status=500)
