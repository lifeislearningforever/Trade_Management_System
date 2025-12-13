#!/usr/bin/env python
"""
Test Audit Logging for Order Rejection
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trade_management.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from accounts.models import AuditLog
from orders.models import Order, Stock

User = get_user_model()

def test_rejection_workflow():
    """Test order rejection with audit logging"""

    client = Client()
    initial_count = AuditLog.objects.count()

    maker = User.objects.get(username='maker1')
    checker = User.objects.get(username='checker1')
    stock = Stock.objects.first()

    print("🧪 Testing Order Rejection Workflow")
    print("=" * 70)

    # Login as maker
    print("\n1. Maker creates and submits order...")
    client.post('/login/', {'username': 'maker1', 'password': 'Test@1234'})

    # Create order
    client.post('/orders/create/', {
        'stock': stock.id,
        'side': 'SELL',
        'order_type': 'LIMIT',
        'quantity': 50,
        'price': 2500.00,
        'validity': 'DAY',
    })

    # Get the created order
    order = Order.objects.filter(created_by=maker).order_by('-created_at').first()
    print(f"   Created order: {order.order_id}")

    # Submit order
    client.post(f'/orders/{order.id}/submit/')
    order.refresh_from_db()
    print(f"   Order status: {order.status}")

    # Logout
    client.get('/logout/')

    # Login as checker
    print("\n2. Checker rejects order...")
    client.post('/login/', {'username': 'checker1', 'password': 'Test@1234'})

    # Reject order
    client.post(f'/orders/{order.id}/reject/', {
        'rejection_reason': 'Price too high - market rate is lower'
    })

    order.refresh_from_db()
    print(f"   Order status: {order.status}")
    print(f"   Rejection reason: {order.rejection_reason}")

    # Check REJECT audit log
    print("\n3. Verifying audit logs...")
    reject_logs = AuditLog.objects.filter(
        action='REJECT',
        user=checker,
        object_type='Order',
        object_id=str(order.id)
    )

    if reject_logs.exists():
        log = reject_logs.first()
        print(f"   ✅ REJECT logged: {log.description}")
        print(f"   ✅ User: {log.user.username}")
        print(f"   ✅ Category: {log.category}")
        print(f"   ✅ Success: {log.success}")
    else:
        print(f"   ❌ REJECT not logged!")

    # Summary
    final_count = AuditLog.objects.count()
    new_logs = final_count - initial_count

    print("\n" + "=" * 70)
    print(f"📊 New audit logs created: {new_logs}")
    print(f"   Expected: 5 (LOGIN, CREATE, SUBMIT, LOGOUT, LOGIN, REJECT)")

    # Show recent logs
    print("\n📋 Recent audit entries:")
    recent = AuditLog.objects.order_by('-timestamp')[:new_logs]
    for log in reversed(list(recent)):
        print(f"   [{log.action:12}] {log.user.username:10} | {log.description}")

    print("=" * 70)

if __name__ == '__main__':
    test_rejection_workflow()
