#!/usr/bin/env python
"""
Test script for Hybrid Connection Manager.

Run from project root:
    python test_hybrid_connection.py

Or with Django shell:
    python manage.py shell < test_hybrid_connection.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from core.repositories.hybrid_connection import hybrid_manager


def test_connections():
    """Test both Impala and Hive connections."""
    print("=" * 60)
    print("HYBRID CONNECTION TEST")
    print("=" * 60)

    # Test connection status
    print("\n1. Testing connections...")
    status = hybrid_manager.test_connections()
    print(f"   Impala (Kudu): {'OK' if status['impala'] else 'FAILED'}")
    print(f"   Hive (External): {'OK' if status['hive'] else 'FAILED'}")

    # Get pool stats
    print("\n2. Pool statistics:")
    stats = hybrid_manager.get_pool_stats()
    print(f"   Impala connections: {stats['impala']['active_connections']}/{stats['impala']['max_connections']}")
    print(f"   Hive connections: {stats['hive']['active_connections']}/{stats['hive']['max_connections']}")

    return status


def test_kudu_read():
    """Test reading from Kudu table via Impala."""
    print("\n3. Testing Kudu READ (via Impala)...")
    try:
        results = hybrid_manager.kudu_read(
            "SELECT * FROM gmp_cis.cis_file_upload LIMIT 5",
        )
        print(f"   Result: {len(results)} rows")
        if results:
            print(f"   Columns: {list(results[0].keys())}")
        return True
    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def test_hive_read():
    """Test reading from Hive table."""
    print("\n4. Testing Hive READ...")
    try:
        results = hybrid_manager.hive_read(
            "SHOW TABLES IN gmp_cis",
        )
        print(f"   Result: {len(results)} tables found")
        if results:
            tables = [r.get('tab_name', r.get('table_name', str(r))) for r in results[:5]]
            print(f"   Sample tables: {tables}")
        return True
    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def test_describe_formatted():
    """Test DESCRIBE FORMATTED to get table info."""
    print("\n5. Testing DESCRIBE FORMATTED...")
    try:
        from upload.repositories.datasource_repository import datasource_repository

        # Test with external table
        table_name = 'cis_user_sta_adhoc_position_1'
        info = datasource_repository.get_table_info(table_name, 'gmp_cis')

        print(f"   Table: {info.get('table_name')}")
        print(f"   Type: {info.get('table_type')}")
        print(f"   Location: {info.get('location')}")
        print(f"   Columns: {len(info.get('columns', []))}")

        if info.get('columns'):
            print(f"   First 5 columns:")
            for col in info['columns'][:5]:
                print(f"      - {col['name']}: {col['type']}")

        return info.get('location') is not None
    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def test_datasource_config():
    """Test datasource configuration lookup."""
    print("\n6. Testing datasource config lookup...")
    try:
        from upload.repositories.datasource_repository import datasource_repository

        # Get all datasources
        datasources = datasource_repository.get_all_datasources()
        print(f"   Found {len(datasources)} datasource configs")

        if datasources:
            ds = datasources[0]
            print(f"   Sample config:")
            print(f"      source_name: {ds.get('source_name')}")
            print(f"      target_table: {ds.get('target_table')}")
            print(f"      separator: {ds.get('separator')}")

        return len(datasources) > 0
    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def test_hive_write_simple():
    """Test simple Hive DDL command."""
    print("\n7. Testing Hive WRITE (DDL)...")
    try:
        # Simple DDL that shouldn't fail
        success = hybrid_manager.hive_write(
            "SHOW DATABASES",
        )
        print(f"   Result: {'OK' if success else 'FAILED'}")
        return success
    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def main():
    """Run all tests."""
    print("\nStarting Hybrid Connection Tests...")
    print("-" * 60)

    results = {
        'connections': test_connections(),
        'kudu_read': test_kudu_read(),
        'hive_read': test_hive_read(),
        'describe_formatted': test_describe_formatted(),
        'datasource_config': test_datasource_config(),
        'hive_write': test_hive_write_simple(),
    }

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, result in results.items():
        if isinstance(result, dict):
            status = 'PASS' if all(result.values()) else 'FAIL'
        else:
            status = 'PASS' if result else 'FAIL'

        if status == 'FAIL':
            all_passed = False

        print(f"   {test_name}: {status}")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - Check errors above")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
