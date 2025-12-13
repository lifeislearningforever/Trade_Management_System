"""
Views for accounts app - Authentication and Dashboard
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .models import AuditLog


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    """Handle user login"""

    # If user is already logged in, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Check if user is active
            if user.is_active:
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_display_name()}!')

                # Log successful login
                AuditLog.log_action(
                    user=user,
                    action='LOGIN',
                    description=f'User {user.get_display_name()} logged in successfully',
                    category='accounts',
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    request_method='POST',
                    request_path='/login/',
                    success=True
                )

                # Redirect to next page or dashboard
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Your account has been deactivated. Please contact administrator.')

                # Log failed login (inactive account)
                AuditLog.log_action(
                    user=user,
                    action='LOGIN_FAILED',
                    description=f'Login failed: Account inactive for {username}',
                    category='accounts',
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    success=False,
                    error_message='Account is inactive'
                )
        else:
            messages.error(request, 'Invalid username or password.')

            # Log failed login attempt (invalid credentials)
            # Note: We don't log username for security reasons
            AuditLog.objects.create(
                action='LOGIN_FAILED',
                description='Login failed: Invalid credentials',
                category='accounts',
                username='anonymous',
                ip_address=request.META.get('REMOTE_ADDR', ''),
                success=False,
                error_message='Invalid username or password'
            )

    return render(request, 'accounts/login.html')


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Handle user logout"""
    if request.user.is_authenticated:
        username = request.user.get_display_name()
        user = request.user

        # Log logout before logging out
        AuditLog.log_action(
            user=user,
            action='LOGOUT',
            description=f'User {username} logged out',
            category='accounts',
            ip_address=request.META.get('REMOTE_ADDR', ''),
            request_path='/logout/',
            success=True
        )

        logout(request)
        messages.info(request, f'You have been logged out successfully. Goodbye, {username}!')

    return redirect('login')


@login_required
def dashboard_view(request):
    """Main dashboard for logged in users with role-based sections"""
    from orders.models import Order
    from portfolio.models import Portfolio

    # Get all active user roles with primary flag
    user_roles_data = []
    user_role_codes = []
    for user_role_obj in request.user.user_roles.filter(role__is_active=True).select_related('role'):
        user_roles_data.append({
            'role': user_role_obj.role,
            'is_primary': user_role_obj.is_primary,
        })
        user_role_codes.append(user_role_obj.role.code)

    # Determine user type
    is_maker = 'MAKER' in user_role_codes
    is_checker = 'CHECKER' in user_role_codes
    is_admin = request.user.is_superuser

    context = {
        'user': request.user,
        'user_roles_data': user_roles_data,
        'is_maker': is_maker,
        'is_checker': is_checker,
        'is_admin': is_admin,
    }

    # For Makers: Show their draft items, pending approvals, rejected items
    if is_maker:
        context['my_draft_orders'] = Order.objects.filter(
            created_by=request.user,
            status='DRAFT'
        ).count()
        context['my_draft_portfolios'] = Portfolio.objects.filter(
            created_by=request.user,
            status='DRAFT'
        ).count()
        context['my_pending_orders'] = Order.objects.filter(
            created_by=request.user,
            status='PENDING_APPROVAL'
        ).count()
        context['my_pending_portfolios'] = Portfolio.objects.filter(
            created_by=request.user,
            status='PENDING_APPROVAL'
        ).count()
        context['my_rejected_orders'] = Order.objects.filter(
            created_by=request.user,
            status='REJECTED'
        ).order_by('-updated_at')[:5]
        context['my_rejected_portfolios'] = Portfolio.objects.filter(
            created_by=request.user,
            status='REJECTED'
        ).order_by('-updated_at')[:5]

    # For Checkers: Show pending approvals, approval history
    if is_checker:
        context['pending_approval_orders'] = Order.objects.filter(
            status='PENDING_APPROVAL'
        ).exclude(created_by=request.user).count()
        context['pending_approval_portfolios'] = Portfolio.objects.filter(
            status='PENDING_APPROVAL'
        ).exclude(created_by=request.user).count()
        context['recently_approved_orders'] = Order.objects.filter(
            approved_by=request.user,
            status='APPROVED'
        ).order_by('-approved_at')[:5]
        context['recently_approved_portfolios'] = Portfolio.objects.filter(
            approved_by=request.user,
            status__in=['ACTIVE']
        ).order_by('-approved_at')[:5]
        context['recently_rejected_orders'] = Order.objects.filter(
            approved_by=request.user,
            status='REJECTED'
        ).order_by('-approved_at')[:5]
        context['recently_rejected_portfolios'] = Portfolio.objects.filter(
            approved_by=request.user,
            status='REJECTED'
        ).order_by('-approved_at')[:5]

    # For Admins: System overview
    if is_admin:
        context['total_orders'] = Order.objects.count()
        context['total_portfolios'] = Portfolio.objects.count()
        context['total_users'] = request.user.__class__.objects.filter(is_active=True).count()
        context['pending_approvals_all'] = (
            Order.objects.filter(status='PENDING_APPROVAL').count() +
            Portfolio.objects.filter(status='PENDING_APPROVAL').count()
        )

    return render(request, 'accounts/dashboard.html', context)
