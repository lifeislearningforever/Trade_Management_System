#!/usr/bin/env python
"""
Complete Audit Logging Test
Tests the full maker-checker workflow and verifies all audit logs
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

def test_complete_workflow():
    """Test complete order workflow with audit logging"""

    # Initialize client
    client = Client()

    # Count initial audit logs
    initial_count = AuditLog.objects.count()
    print(f"📊 Initial audit log count: {initial_count}")
    print("=" * 70)

    # Get test users
    maker = User.objects.get(username='maker1')
    checker = User.objects.get(username='checker1')
    stock = Stock.objects.first()

    print("\n🧪 TEST 1: Maker Login")
    print("-" * 70)
    response = client.post('/login/', {
        'username': 'maker1',
        'password': 'Test@1234'
    })
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Check LOGIN audit log
    login_logs = AuditLog.objects.filter(action='LOGIN', user=maker).order_by('-timestamp')
    if login_logs.exists():
        print(f"   ✅ LOGIN logged: {login_logs.first().description}")
    else:
        print(f"   ❌ LOGIN not logged!")

    print("\n🧪 TEST 2: Create Order (Maker)")
    print("-" * 70)
    response = client.post('/orders/create/', {
        'stock': stock.id,
        'side': 'BUY',
        'order_type': 'MARKET',
        'quantity': 100,
        'validity': 'DAY',
    })
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Get the created order
    created_order = Order.objects.filter(created_by=maker).order_by('-created_at').first()
    if created_order:
        print(f"   Order created: {created_order.order_id}")

        # Check CREATE audit log
        create_logs = AuditLog.objects.filter(
            action='CREATE',
            user=maker,
            object_type='Order',
            object_id=str(created_order.id)
        )
        if create_logs.exists():
            print(f"   ✅ CREATE logged: {create_logs.first().description}")
        else:
            print(f"   ❌ CREATE not logged!")

    print("\n🧪 TEST 3: Submit Order for Approval (Maker)")
    print("-" * 70)
    response = client.post(f'/orders/{created_order.id}/submit/')
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Refresh order from database
    created_order.refresh_from_db()
    print(f"   Order status: {created_order.status}")

    # Check SUBMIT audit log
    submit_logs = AuditLog.objects.filter(
        action='SUBMIT',
        user=maker,
        object_type='Order',
        object_id=str(created_order.id)
    )
    if submit_logs.exists():
        print(f"   ✅ SUBMIT logged: {submit_logs.first().description}")
    else:
        print(f"   ❌ SUBMIT not logged!")

    print("\n🧪 TEST 4: Maker Logout")
    print("-" * 70)
    response = client.get('/logout/')
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Check LOGOUT audit log
    logout_logs = AuditLog.objects.filter(action='LOGOUT', user=maker).order_by('-timestamp')
    if logout_logs.exists():
        print(f"   ✅ LOGOUT logged: {logout_logs.first().description}")
    else:
        print(f"   ❌ LOGOUT not logged!")

    print("\n🧪 TEST 5: Checker Login")
    print("-" * 70)
    response = client.post('/login/', {
        'username': 'checker1',
        'password': 'Test@1234'
    })
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Check LOGIN audit log
    checker_login_logs = AuditLog.objects.filter(action='LOGIN', user=checker).order_by('-timestamp')
    if checker_login_logs.exists():
        print(f"   ✅ LOGIN logged: {checker_login_logs.first().description}")
    else:
        print(f"   ❌ LOGIN not logged!")

    print("\n🧪 TEST 6: Approve Order (Checker)")
    print("-" * 70)
    response = client.post(f'/orders/{created_order.id}/approve/')
    print(f"   Status: {response.status_code} (expected 302 redirect)")

    # Refresh order from database
    created_order.refresh_from_db()
    print(f"   Order status: {created_order.status}")
    print(f"   Approved by: {created_order.approved_by_name}")

    # Check APPROVE audit log
    approve_logs = AuditLog.objects.filter(
        action='APPROVE',
        user=checker,
        object_type='Order',
        object_id=str(created_order.id)
    )
    if approve_logs.exists():
        print(f"   ✅ APPROVE logged: {approve_logs.first().description}")
    else:
        print(f"   ❌ APPROVE not logged!")

    print("\n" + "=" * 70)
    print("📊 FINAL AUDIT LOG SUMMARY")
    print("=" * 70)

    # Count final audit logs
    final_count = AuditLog.objects.count()
    new_logs_count = final_count - initial_count

    print(f"\n   Initial count: {initial_count}")
    print(f"   Final count: {final_count}")
    print(f"   New logs created: {new_logs_count}")
    print(f"   Expected: 6 (2 LOGIN + 1 CREATE + 1 SUBMIT + 1 LOGOUT + 1 APPROVE)")

    # Display all new audit logs
    print("\n📋 All new audit log entries:")
    print("-" * 70)
    new_logs = AuditLog.objects.order_by('-timestamp')[:new_logs_count]
    for i, log in enumerate(reversed(list(new_logs)), 1):
        print(f"{i}. [{log.action:12}] {log.user.username:10} | {log.description}")

    print("\n" + "=" * 70)

    # Verify expected logs
    expected_actions = ['LOGIN', 'CREATE', 'SUBMIT', 'LOGOUT', 'LOGIN', 'APPROVE']
    actual_actions = [log.action for log in reversed(list(new_logs))]

    if all(action in actual_actions for action in expected_actions):
        print("✅ SUCCESS: All expected audit actions logged correctly!")
    else:
        print("❌ FAILURE: Some audit actions missing!")
        print(f"   Expected: {expected_actions}")
        print(f"   Actual: {actual_actions}")

    print("=" * 70)

if __name__ == '__main__':
    test_complete_workflow()
