"""
Orders Views - Custom Maker-Checker Workflow
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction

from .models import Order
from .forms import OrderForm, OrderRejectForm, OrderFilterForm
from .validators import (
    can_edit_order, can_submit_order, can_approve_order,
    can_reject_order, can_delete_order, get_workflow_error_message
)
from accounts.models import AuditLog


@login_required
def order_list(request):
    """Display list of orders with filters"""
    filter_form = OrderFilterForm(request.GET or None)

    # Base queryset
    orders = Order.objects.select_related(
        'stock', 'client', 'broker', 'created_by', 'approved_by'
    ).all()

    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('status'):
            orders = orders.filter(status=filter_form.cleaned_data['status'])
        if filter_form.cleaned_data.get('side'):
            orders = orders.filter(side=filter_form.cleaned_data['side'])
        if filter_form.cleaned_data.get('order_type'):
            orders = orders.filter(order_type=filter_form.cleaned_data['order_type'])
        if filter_form.cleaned_data.get('stock'):
            orders = orders.filter(stock=filter_form.cleaned_data['stock'])
        if filter_form.cleaned_data.get('client'):
            orders = orders.filter(client=filter_form.cleaned_data['client'])

    # Apply status filter from query params (for dashboard links)
    status_param = request.GET.get('status')
    if status_param and status_param in dict(Order.STATUS_CHOICES):
        orders = orders.filter(status=status_param)

    # Order by most recent first
    orders = orders.order_by('-created_at')

    # Pagination
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_count': orders.count(),
    }

    return render(request, 'orders/order_list_simple.html', context)


@login_required
def order_create(request):
    """Create new order in DRAFT status"""
    if request.method == 'POST':
        form = OrderForm(request.POST, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)

                # Set maker fields
                order.created_by = request.user
                order.created_by_name = request.user.get_full_name()
                order.created_by_employee_id = request.user.employee_id or ''
                order.status = 'DRAFT'

                # Generate order_id
                last_order = Order.objects.order_by('-created_at').first()
                if last_order and last_order.order_id:
                    try:
                        last_num = int(last_order.order_id.split('-')[1])
                        order.order_id = f'ORD-{last_num + 1:06d}'
                    except:
                        order.order_id = f'ORD-{Order.objects.count() + 1:06d}'
                else:
                    order.order_id = 'ORD-000001'

                order.save()

                # Log order creation
                AuditLog.log_action(
                    user=request.user,
                    action='CREATE',
                    description=f'Created order {order.order_id}',
                    category='orders',
                    object_type='Order',
                    object_id=str(order.id),
                    success=True
                )

                messages.success(request, f'Order {order.order_id} created successfully.')
                return redirect('order_detail', pk=order.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = OrderForm(user=request.user)

    return render(request, 'orders/order_form.html', {'form': form, 'action': 'Create'})


@login_required
def order_detail(request, pk):
    """View order details with workflow actions"""
    order = get_object_or_404(
        Order.objects.select_related('stock', 'client', 'broker', 'created_by', 'approved_by'),
        pk=pk
    )

    context = {
        'order': order,
        'can_edit': can_edit_order(request.user, order),
        'can_submit': can_submit_order(request.user, order),
        'can_approve': can_approve_order(request.user, order),
        'can_reject': can_reject_order(request.user, order),
        'can_delete': can_delete_order(request.user, order),
    }

    return render(request, 'orders/order_detail.html', context)


@login_required
def order_edit(request, pk):
    """Edit order (only DRAFT orders by creator)"""
    order = get_object_or_404(Order, pk=pk)

    if not can_edit_order(request.user, order):
        messages.error(request, get_workflow_error_message('edit', request.user, order))
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order, user=request.user)
        if form.is_valid():
            form.save()

            # Log order update
            AuditLog.log_action(
                user=request.user,
                action='UPDATE',
                description=f'Updated order {order.order_id}',
                category='orders',
                object_type='Order',
                object_id=str(order.id),
                success=True
            )

            messages.success(request, f'Order {order.order_id} updated successfully.')
            return redirect('order_detail', pk=pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = OrderForm(instance=order, user=request.user)

    return render(request, 'orders/order_form.html', {'form': form, 'order': order, 'action': 'Edit'})


@login_required
def order_submit(request, pk):
    """Submit order for approval (DRAFT → PENDING_APPROVAL)"""
    order = get_object_or_404(Order, pk=pk)

    if not can_submit_order(request.user, order):
        messages.error(request, get_workflow_error_message('submit', request.user, order))
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            order.status = 'PENDING_APPROVAL'
            order.save(update_fields=['status', 'updated_at'])

            # Log order submission
            AuditLog.log_action(
                user=request.user,
                action='SUBMIT',
                description=f'Submitted order {order.order_id} for approval',
                category='orders',
                object_type='Order',
                object_id=str(order.id),
                success=True
            )

            messages.success(request, f'Order {order.order_id} submitted for approval.')
            return redirect('order_detail', pk=pk)

    return render(request, 'orders/order_submit_confirm.html', {'order': order})


@login_required
def order_approve(request, pk):
    """Approve order (PENDING_APPROVAL → APPROVED)"""
    order = get_object_or_404(Order, pk=pk)

    if not can_approve_order(request.user, order):
        messages.error(request, get_workflow_error_message('approve', request.user, order))
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            order.approved_by = request.user
            order.approved_by_name = request.user.get_full_name()
            order.approved_by_employee_id = request.user.employee_id or ''
            order.approved_at = timezone.now()
            order.status = 'APPROVED'
            order.save()

            # Log order approval
            AuditLog.log_action(
                user=request.user,
                action='APPROVE',
                description=f'Approved order {order.order_id}',
                category='orders',
                object_type='Order',
                object_id=str(order.id),
                success=True
            )

            messages.success(request, f'Order {order.order_id} approved successfully.')
            return redirect('order_detail', pk=pk)

    return render(request, 'orders/order_approve_confirm.html', {'order': order})


@login_required
def order_reject(request, pk):
    """Reject order (PENDING_APPROVAL → REJECTED)"""
    order = get_object_or_404(Order, pk=pk)

    if not can_reject_order(request.user, order):
        messages.error(request, get_workflow_error_message('reject', request.user, order))
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        form = OrderRejectForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                order.approved_by = request.user
                order.approved_by_name = request.user.get_full_name()
                order.approved_by_employee_id = request.user.employee_id or ''
                order.approved_at = timezone.now()
                order.status = 'REJECTED'
                order.rejection_reason = form.cleaned_data['rejection_reason']
                order.save()

                # Log order rejection
                AuditLog.log_action(
                    user=request.user,
                    action='REJECT',
                    description=f'Rejected order {order.order_id}: {order.rejection_reason}',
                    category='orders',
                    object_type='Order',
                    object_id=str(order.id),
                    success=True
                )

                messages.warning(request, f'Order {order.order_id} rejected.')
                return redirect('order_detail', pk=pk)
        else:
            messages.error(request, 'Please provide a valid rejection reason.')
    else:
        form = OrderRejectForm()

    return render(request, 'orders/order_reject.html', {'order': order, 'form': form})


@login_required
def order_delete(request, pk):
    """Delete order (only DRAFT orders by creator)"""
    order = get_object_or_404(Order, pk=pk)

    if not can_delete_order(request.user, order):
        messages.error(request, get_workflow_error_message('delete', request.user, order))
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        order_id = order.order_id
        order_uuid = str(order.id)

        # Log order deletion before deleting
        AuditLog.log_action(
            user=request.user,
            action='DELETE',
            description=f'Deleted order {order_id}',
            category='orders',
            object_type='Order',
            object_id=order_uuid,
            success=True
        )

        order.delete()
        messages.success(request, f'Order {order_id} deleted successfully.')
        return redirect('order_list')

    return render(request, 'orders/order_confirm_delete.html', {'order': order})
