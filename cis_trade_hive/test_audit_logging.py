#!/usr/bin/env python
"""
Test Script for Audit Logging

Tests CREATE, UPDATE, DELETE operations on equity price
and verifies audit entries are written to cis_audit_log.

Usage:
    source .venv/bin/activate
    python test_audit_logging.py
"""

import os
import sys
import time
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from datetime import datetime
from core.repositories.impala_connection import impala_manager
from market_data.repositories.equity_price_hive_repository import EquityPriceHiveRepository


def get_audit_logs(entity_type: str = 'EQUITY_PRICE', limit: int = 10) -> list:
    """Retrieve recent audit logs for the given entity type."""
    query = f"""
    SELECT
        audit_id,
        audit_timestamp,
        username,
        action_type,
        entity_type,
        entity_id,
        entity_name,
        old_value,
        new_value,
        status,
        duration_ms
    FROM gmp_cis.cis_audit_log
    WHERE entity_type = '{entity_type}'
    ORDER BY audit_timestamp DESC
    LIMIT {limit}
    """
    return impala_manager.execute_query(query, database='gmp_cis')


def test_create_operation():
    """Test CREATE operation with audit logging."""
    print("\n" + "="*60)
    print("TEST 1: CREATE EQUITY PRICE")
    print("="*60)

    test_data = {
        'currency_code': 'USD',
        'security_label': 'TEST_AUDIT_SECURITY',
        'isin': 'US0000TEST01',
        'price_date': '2026-01-25',
        'main_closing_price': 123.45,
        'market': 'TEST',
        'price_timestamp': int(time.time() * 1000),
        'group_name': 'TEST_GROUP'
    }

    print(f"Creating equity price: {test_data['security_label']}")

    success = EquityPriceHiveRepository.upsert_equity_price(
        equity_price_data=test_data,
        username='TEST_USER'
    )

    if success:
        print("✓ CREATE operation successful")
    else:
        print("✗ CREATE operation failed")

    return success


def test_update_operation():
    """Test UPDATE operation with audit logging."""
    print("\n" + "="*60)
    print("TEST 2: UPDATE EQUITY PRICE")
    print("="*60)

    # First, find the record we just created
    records = EquityPriceHiveRepository.get_all_equity_prices(
        security_label='TEST_AUDIT_SECURITY',
        limit=1
    )

    if not records:
        print("✗ Could not find test record to update")
        return False

    record = records[0]
    equity_price_id = record['equity_price_id']
    print(f"Found record ID: {equity_price_id}")

    # Update the record
    update_data = {
        'main_closing_price': 150.00,
        'market': 'UPDATED_TEST'
    }

    print(f"Updating price to: {update_data['main_closing_price']}")

    success = EquityPriceHiveRepository.update_equity_price(
        equity_price_id=equity_price_id,
        equity_price_data=update_data,
        username='TEST_USER'
    )

    if success:
        print("✓ UPDATE operation successful")
    else:
        print("✗ UPDATE operation failed")

    return success


def test_delete_operation():
    """Test DELETE (soft delete) operation with audit logging."""
    print("\n" + "="*60)
    print("TEST 3: DELETE EQUITY PRICE")
    print("="*60)

    # Find the record we created
    records = EquityPriceHiveRepository.get_all_equity_prices(
        security_label='TEST_AUDIT_SECURITY',
        limit=1
    )

    if not records:
        print("✗ Could not find test record to delete")
        return False

    record = records[0]
    equity_price_id = record['equity_price_id']
    print(f"Deleting record ID: {equity_price_id}")

    success = EquityPriceHiveRepository.delete_equity_price(
        equity_price_id=equity_price_id,
        deleted_by='TEST_USER'
    )

    if success:
        print("✓ DELETE operation successful")
    else:
        print("✗ DELETE operation failed")

    return success


def verify_audit_logs():
    """Verify audit logs were created."""
    print("\n" + "="*60)
    print("VERIFY AUDIT LOGS")
    print("="*60)

    # Give the async queue time to process
    print("Waiting 5 seconds for async audit queue to process...")
    time.sleep(5)

    logs = get_audit_logs('EQUITY_PRICE', limit=20)

    if not logs:
        print("✗ No audit logs found!")
        return False

    print(f"\nFound {len(logs)} recent EQUITY_PRICE audit entries:\n")

    # Look for our test entries
    test_logs = [log for log in logs if 'TEST_AUDIT_SECURITY' in str(log.get('entity_name', ''))]

    if test_logs:
        print("TEST AUDIT ENTRIES:")
        print("-" * 60)
        for log in test_logs:
            print(f"  Action: {log.get('action_type')}")
            print(f"  Entity: {log.get('entity_name')}")
            print(f"  User: {log.get('username')}")
            print(f"  Status: {log.get('status')}")
            print(f"  Duration: {log.get('duration_ms')}ms")
            print(f"  Timestamp: {log.get('audit_timestamp')}")
            print("-" * 60)

        # Check for all three operations
        actions = [log.get('action_type') for log in test_logs]

        if 'CREATE' in actions:
            print("✓ CREATE audit entry found")
        else:
            print("✗ CREATE audit entry NOT found")

        if 'UPDATE' in actions:
            print("✓ UPDATE audit entry found")
        else:
            print("✗ UPDATE audit entry NOT found")

        if 'DELETE' in actions:
            print("✓ DELETE audit entry found")
        else:
            print("✗ DELETE audit entry NOT found")

        return True
    else:
        print("No test audit entries found. Checking all recent entries...")
        for log in logs[:5]:
            print(f"  {log.get('action_type')} | {log.get('entity_name')} | {log.get('username')}")
        return False


def cleanup_test_data():
    """Clean up test data (permanently delete from table)."""
    print("\n" + "="*60)
    print("CLEANUP TEST DATA")
    print("="*60)

    # Hard delete test records (for cleanup)
    delete_query = """
    DELETE FROM gmp_cis.cis_equity_price
    WHERE security_label = 'TEST_AUDIT_SECURITY'
    """

    try:
        success = impala_manager.execute_write(delete_query, database='gmp_cis')
        if success:
            print("✓ Test data cleaned up")
        return success
    except Exception as e:
        print(f"Note: Could not clean up test data: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("AUDIT LOGGING TEST SUITE")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run tests
    create_ok = test_create_operation()

    if create_ok:
        update_ok = test_update_operation()
        delete_ok = test_delete_operation()
    else:
        print("\nSkipping UPDATE and DELETE tests due to CREATE failure")
        update_ok = False
        delete_ok = False

    # Verify audit logs
    audit_ok = verify_audit_logs()

    # Cleanup
    cleanup_test_data()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"  CREATE operation: {'PASS' if create_ok else 'FAIL'}")
    print(f"  UPDATE operation: {'PASS' if update_ok else 'FAIL'}")
    print(f"  DELETE operation: {'PASS' if delete_ok else 'FAIL'}")
    print(f"  Audit logging:    {'PASS' if audit_ok else 'FAIL'}")
    print("="*60)

    all_passed = create_ok and update_ok and delete_ok and audit_ok

    if all_passed:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
