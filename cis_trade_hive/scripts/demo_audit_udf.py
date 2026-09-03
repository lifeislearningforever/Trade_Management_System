#!/usr/bin/env python
"""
Demo Script: Audit Log and UDF Integration with Hive
Shows how to use audit logging and UDF systems with Hive backend.

Usage:
    cd /path/to/cis_trade_hive
    python scripts/demo_audit_udf.py
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()


def demo_audit_log():
    """Demonstrate Audit Log Hive integration."""
    print("\n" + "="*60)
    print("AUDIT LOG DEMO - Hive Integration")
    print("="*60)

    from core.audit.audit_hive_repository import audit_log_repository

    # 1. Log a portfolio creation action
    print("\n1. Logging Portfolio Creation...")
    success = audit_log_repository.log_action(
        user_id='demo_user',
        username='Demo User',
        action_type='CREATE',
        entity_type='PORTFOLIO',
        entity_id='999',
        entity_name='Demo Portfolio',
        action_description='Created demo portfolio for testing',
        request_method='POST',
        request_path='/portfolio/create/',
        ip_address='127.0.0.1',
        user_agent='Python Demo Script',
        status='SUCCESS',
        module_name='demo',
        function_name='demo_audit_log'
    )
    print(f"   ✓ Logged: {success}")

    # 2. Log a UDF update action
    print("\n2. Logging UDF Update...")
    success = audit_log_repository.log_action(
        user_id='demo_user',
        username='Demo User',
        action_type='UPDATE',
        entity_type='UDF',
        entity_id='portfolio-999-account_group',
        entity_name='account_group',
        action_description='Updated account_group UDF',
        field_name='account_group',
        old_value=None,
        new_value='TRADING',
        request_method='POST',
        request_path='/udf/values/portfolio/999/',
        ip_address='127.0.0.1',
        user_agent='Python Demo Script',
        status='SUCCESS'
    )
    print(f"   ✓ Logged: {success}")

    # 3. Retrieve recent logs
    print("\n3. Retrieving Recent Logs (last 10)...")
    logs = audit_log_repository.get_all_logs(limit=10)
    print(f"   Found {len(logs)} log entries")

    if logs:
        print("\n   Recent Actions:")
        for log in logs[:5]:
            print(f"   - [{log.get('audit_timestamp')}] {log.get('username')}: "
                  f"{log.get('action_type')} {log.get('entity_type')} - "
                  f"{log.get('action_description')}")

    # 4. Get statistics
    print("\n4. Getting Audit Statistics (last 30 days)...")
    stats = audit_log_repository.get_statistics(days=30)
    print(f"   Total logs: {stats['total_count']}")
    print(f"   Period: {stats['days']} days")

    if stats.get('action_breakdown'):
        print("\n   Action Type Breakdown:")
        for item in stats['action_breakdown'][:5]:
            print(f"   - {item.get('action_type')}: {item.get('count')}")

    # 5. Get entity history
    print("\n5. Getting Entity History...")
    history = audit_log_repository.get_entity_history('PORTFOLIO', '999')
    print(f"   Found {len(history)} history entries for Portfolio 999")

    if history:
        print("\n   History:")
        for entry in history:
            print(f"   - [{entry.get('audit_timestamp')}] {entry.get('action_type')}: "
                  f"{entry.get('action_description')}")


def demo_udf_system():
    """Demonstrate UDF System Hive integration."""
    print("\n" + "="*60)
    print("UDF SYSTEM DEMO - Hive Integration")
    print("="*60)

    from udf.services.udf_service import UDFService
    from udf.repositories import reference_data_repository

    # 1. Get account group options
    print("\n1. Getting Account Group Options from Hive...")
    options = UDFService.get_account_group_options()
    print(f"   Found {len(options)} options:")
    for opt in options:
        print(f"   - {opt['value']}: {opt['label']}")

    # 2. Get entity group options
    print("\n2. Getting Entity Group Options from Hive...")
    options = UDFService.get_entity_group_options()
    print(f"   Found {len(options)} options:")
    for opt in options:
        print(f"   - {opt['value']}: {opt['label']}")

    # 3. Get currency options
    print("\n3. Getting Currency Options from Hive...")
    currencies = reference_data_repository.get_currencies()
    print(f"   Found {len(currencies)} currencies")
    if currencies:
        print("   Sample currencies:")
        for curr in currencies[:5]:
            print(f"   - {curr.get('iso_code')}: {curr.get('name')} ({curr.get('symbol')})")

    # 4. Get countries
    print("\n4. Getting Countries from Hive...")
    countries = reference_data_repository.get_countries()
    print(f"   Found {len(countries)} countries")
    if countries:
        print("   Sample countries:")
        for country in countries[:5]:
            print(f"   - {country.get('code')}: {country.get('name')}")

    # 5. Dynamic dropdown option routing
    print("\n5. Testing Dynamic Dropdown Routing...")
    test_fields = ['account_group', 'entity_group', 'currency']

    for field in test_fields:
        options = UDFService.get_udf_dropdown_options(field)
        print(f"   {field}: {len(options)} options")


def demo_combined_workflow():
    """Demonstrate combined Audit + UDF workflow."""
    print("\n" + "="*60)
    print("COMBINED WORKFLOW DEMO")
    print("="*60)

    from core.audit.audit_hive_repository import audit_log_repository
    from udf.services.udf_service import UDFService

    print("\n1. Simulating Portfolio UDF Management Workflow...")

    # Step 1: Log viewing UDF management page
    print("\n   Step 1: User views UDF management page")
    audit_log_repository.log_action(
        user_id='demo_user',
        username='Demo User',
        action_type='VIEW',
        entity_type='UDF',
        action_description='Viewed UDF management page',
        request_method='GET',
        request_path='/udf/',
        ip_address='127.0.0.1',
        status='SUCCESS'
    )
    print("   ✓ Audit logged: VIEW UDF management page")

    # Step 2: Get available options
    print("\n   Step 2: Load dropdown options")
    account_groups = UDFService.get_account_group_options()
    print(f"   ✓ Loaded {len(account_groups)} account group options from Hive")

    # Step 3: Log dropdown options loaded
    audit_log_repository.log_action(
        user_id='demo_user',
        username='Demo User',
        action_type='READ',
        entity_type='UDF',
        action_description=f'Loaded account_group dropdown options: {len(account_groups)} items',
        request_method='GET',
        request_path='/udf/ajax/dropdown-options/account_group/',
        ip_address='127.0.0.1',
        status='SUCCESS',
        metadata=f'{{"count":{len(account_groups)}}}'
    )
    print("   ✓ Audit logged: Dropdown options loaded")

    # Step 4: Simulate UDF value change
    print("\n   Step 3: User changes account_group from TRADING to INVESTMENT")
    audit_log_repository.log_action(
        user_id='demo_user',
        username='Demo User',
        action_type='UPDATE',
        entity_type='UDF',
        entity_id='portfolio-999-account_group',
        field_name='account_group',
        old_value='TRADING',
        new_value='INVESTMENT',
        action_description='Changed account_group from TRADING to INVESTMENT',
        request_method='POST',
        request_path='/udf/values/portfolio/999/',
        ip_address='127.0.0.1',
        status='SUCCESS'
    )
    print("   ✓ Audit logged: UDF value updated")

    print("\n2. Workflow Complete!")
    print("   All actions logged to Hive audit log table")
    print("   UDF options fetched from Hive reference tables")


def main():
    """Main demo function."""
    print("\n" + "="*60)
    print("CIS TRADE HIVE - AUDIT LOG & UDF DEMO")
    print("="*60)
    print("\nThis demo shows:")
    print("1. Audit Log integration with Hive")
    print("2. UDF System integration with Hive")
    print("3. Combined workflow example")

    try:
        # Run demos
        demo_audit_log()
        demo_udf_system()
        demo_combined_workflow()

        print("\n" + "="*60)
        print("DEMO COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nNext Steps:")
        print("1. Check audit logs in Hive:")
        print("   beeline -u jdbc:hive2://localhost:10000/cis")
        print("   SELECT * FROM cis_audit_log ORDER BY audit_timestamp DESC LIMIT 10;")
        print("\n2. Check UDF values:")
        print("   SELECT * FROM cis_udf_value WHERE entity_id = 999;")
        print("\n3. View in web interface:")
        print("   http://localhost:8000/core/audit-log/")
        print("   http://localhost:8000/udf/")
        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
