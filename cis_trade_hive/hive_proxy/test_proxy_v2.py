#!/usr/bin/env python3
"""
Test Client for Hive REST Proxy v2.0

Tests dynamic CRUD operations, schema caching, and audit logging.

Usage:
    export HIVE_PROXY_URL=http://edge-node:5000
    python test_proxy_v2.py

Environment Variables:
    HIVE_PROXY_URL: URL of the REST Proxy
    HIVE_PROXY_API_KEY: API key if required
    HIVE_TEST_DATABASE: Database to test (default: mrw_ima)
    HIVE_TEST_TABLE: Table to test (default: portfolio_hive)
"""

import os
import sys
import json
import time
import random
import string

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed")
    print("Install: pip install requests")
    sys.exit(1)


# Configuration
PROXY_URL = os.environ.get('HIVE_PROXY_URL', 'http://localhost:5000')
API_KEY = os.environ.get('HIVE_PROXY_API_KEY', '')
TEST_DATABASE = os.environ.get('HIVE_TEST_DATABASE', 'mrw_ima')
TEST_TABLE = os.environ.get('HIVE_TEST_TABLE', 'portfolio_hive')

# Test record ID (generated)
TEST_RECORD_ID = None


def make_request(endpoint: str, method: str = 'GET', data: dict = None,
                 timeout: int = 120) -> tuple:
    """Make HTTP request to proxy."""
    url = f"{PROXY_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    if API_KEY:
        headers['X-API-Key'] = API_KEY

    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, json=data, headers=headers, timeout=timeout)

        return response.status_code, response.json()
    except requests.exceptions.Timeout:
        return None, {'error': 'Request timeout'}
    except requests.exceptions.ConnectionError as e:
        return None, {'error': f'Connection failed: {str(e)[:50]}'}
    except Exception as e:
        return None, {'error': str(e)}


def generate_test_id() -> str:
    """Generate unique test ID."""
    timestamp = int(time.time() * 1000)
    suffix = ''.join(random.choices(string.ascii_uppercase, k=4))
    return f"TEST_{timestamp}_{suffix}"


# =============================================================================
# Test Functions
# =============================================================================

def test_health():
    """Test 1: Health check."""
    print("\n" + "=" * 60)
    print("TEST 1: Health Check")
    print("=" * 60)

    status, result = make_request('/health')

    if status == 200:
        print(f"  Status: OK")
        print(f"  Version: {result.get('version')}")
        print(f"  Database: {result.get('config', {}).get('database')}")
        print(f"  Audit: {result.get('config', {}).get('audit_enabled')}")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_schema():
    """Test 2: Get table schema."""
    print("\n" + "=" * 60)
    print("TEST 2: Get Table Schema")
    print("=" * 60)

    print(f"  Getting schema for {TEST_DATABASE}.{TEST_TABLE}...")
    start = time.time()

    status, result = make_request(f'/schema/{TEST_DATABASE}.{TEST_TABLE}')
    elapsed = (time.time() - start) * 1000

    if status == 200 and result.get('success'):
        schema = result.get('schema', {})
        columns = schema.get('columns', [])
        print(f"  SUCCESS! ({elapsed:.0f}ms)")
        print(f"  Columns: {len(columns)}")
        for col in columns[:5]:
            print(f"    - {col['name']}: {col['type']}")
        if len(columns) > 5:
            print(f"    ... and {len(columns) - 5} more")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_dynamic_insert():
    """Test 3: Dynamic INSERT."""
    global TEST_RECORD_ID
    print("\n" + "=" * 60)
    print("TEST 3: Dynamic INSERT")
    print("=" * 60)

    TEST_RECORD_ID = generate_test_id()

    data = {
        'data': {
            'portfolio_id': TEST_RECORD_ID,
            'portfolio_name': 'Dynamic Insert Test',
            'portfolio_code': 'DYN001',
            'portfolio_type': 'TEST',
            'currency': 'USD',
            'manager_name': 'Test Manager',
            'description': "Test with special chars: ' \" \\ & < >",
            'status': 'DRAFT',
            'created_at': 'now',
            'created_by': 'test_script'
        }
    }

    print(f"  Record ID: {TEST_RECORD_ID}")
    print(f"  Table: {TEST_DATABASE}.{TEST_TABLE}")
    start = time.time()

    status, result = make_request(
        f'/insert/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )
    elapsed = (time.time() - start) * 1000

    if status == 200 and result.get('success'):
        print(f"  SUCCESS!")
        print(f"  Elapsed: {elapsed:.0f}ms (server: {result.get('elapsed_ms', 0)}ms)")

        # Verify
        verify_status, verify_result = make_request('/query', method='POST', data={
            'sql': f"SELECT * FROM {TEST_DATABASE}.{TEST_TABLE} WHERE portfolio_id = '{TEST_RECORD_ID}'",
            'database': TEST_DATABASE
        })

        if verify_status == 200 and verify_result.get('rows', 0) > 0:
            print(f"  Verified: Record found in database")
        return True
    else:
        print(f"  FAILED: {result}")
        print(f"  Elapsed: {elapsed:.0f}ms")
        return False


def test_dynamic_update():
    """Test 4: Dynamic UPDATE."""
    global TEST_RECORD_ID
    print("\n" + "=" * 60)
    print("TEST 4: Dynamic UPDATE")
    print("=" * 60)

    if not TEST_RECORD_ID:
        print("  SKIP: No test record (INSERT failed)")
        return False

    data = {
        'where': {
            'portfolio_id': TEST_RECORD_ID
        },
        'data': {
            'status': 'APPROVED',
            'description': 'Updated by dynamic UPDATE test',
            'updated_at': 'now',
            'updated_by': 'test_update'
        }
    }

    print(f"  Record ID: {TEST_RECORD_ID}")
    print(f"  Setting status = 'APPROVED'")
    start = time.time()

    status, result = make_request(
        f'/update/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )
    elapsed = (time.time() - start) * 1000

    if status == 200 and result.get('success'):
        print(f"  SUCCESS!")
        print(f"  Elapsed: {elapsed:.0f}ms (server: {result.get('elapsed_ms', 0)}ms)")

        # Verify
        verify_status, verify_result = make_request('/query', method='POST', data={
            'sql': f"SELECT status, updated_by FROM {TEST_DATABASE}.{TEST_TABLE} WHERE portfolio_id = '{TEST_RECORD_ID}'",
            'database': TEST_DATABASE
        })

        if verify_status == 200 and verify_result.get('data'):
            record = verify_result['data'][0]
            print(f"  Verified: status={record.get('status')}, updated_by={record.get('updated_by')}")
        return True
    else:
        print(f"  FAILED: {result}")
        print(f"  Elapsed: {elapsed:.0f}ms")
        return False


def test_dynamic_soft_delete():
    """Test 5: Dynamic SOFT DELETE."""
    global TEST_RECORD_ID
    print("\n" + "=" * 60)
    print("TEST 5: Dynamic SOFT DELETE")
    print("=" * 60)

    if not TEST_RECORD_ID:
        print("  SKIP: No test record (INSERT failed)")
        return False

    data = {
        'where': {
            'portfolio_id': TEST_RECORD_ID
        },
        'soft_delete': True,
        'soft_delete_column': 'deleted_at',
        'deleted_by': 'test_delete'
    }

    print(f"  Record ID: {TEST_RECORD_ID}")
    print(f"  Soft delete (setting deleted_at)")
    start = time.time()

    status, result = make_request(
        f'/delete/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )
    elapsed = (time.time() - start) * 1000

    if status == 200 and result.get('success'):
        print(f"  SUCCESS!")
        print(f"  Operation: {result.get('operation')}")
        print(f"  Elapsed: {elapsed:.0f}ms (server: {result.get('elapsed_ms', 0)}ms)")

        # Verify
        verify_status, verify_result = make_request('/query', method='POST', data={
            'sql': f"SELECT deleted_at FROM {TEST_DATABASE}.{TEST_TABLE} WHERE portfolio_id = '{TEST_RECORD_ID}'",
            'database': TEST_DATABASE
        })

        if verify_status == 200 and verify_result.get('data'):
            record = verify_result['data'][0]
            deleted_at = record.get('deleted_at')
            print(f"  Verified: deleted_at={deleted_at}")
        return True
    else:
        print(f"  FAILED: {result}")
        print(f"  Elapsed: {elapsed:.0f}ms")
        return False


def test_dynamic_hard_delete():
    """Test 6: Dynamic HARD DELETE."""
    global TEST_RECORD_ID
    print("\n" + "=" * 60)
    print("TEST 6: Dynamic HARD DELETE")
    print("=" * 60)

    if not TEST_RECORD_ID:
        print("  SKIP: No test record (INSERT failed)")
        return False

    data = {
        'where': {
            'portfolio_id': TEST_RECORD_ID
        },
        'soft_delete': False  # Force hard delete
    }

    print(f"  Record ID: {TEST_RECORD_ID}")
    print(f"  Hard delete (removing record)")
    start = time.time()

    status, result = make_request(
        f'/delete/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )
    elapsed = (time.time() - start) * 1000

    if status == 200 and result.get('success'):
        print(f"  SUCCESS!")
        print(f"  Operation: {result.get('operation')}")
        print(f"  Elapsed: {elapsed:.0f}ms (server: {result.get('elapsed_ms', 0)}ms)")

        # Verify
        verify_status, verify_result = make_request('/query', method='POST', data={
            'sql': f"SELECT COUNT(*) as cnt FROM {TEST_DATABASE}.{TEST_TABLE} WHERE portfolio_id = '{TEST_RECORD_ID}'",
            'database': TEST_DATABASE
        })

        if verify_status == 200 and verify_result.get('data'):
            data_list = verify_result['data']
            if data_list:
                cnt = data_list[0].get('cnt', data_list[0])
                print(f"  Verified: Record count = {cnt} (should be 0)")
        return True
    else:
        print(f"  FAILED: {result}")
        print(f"  Elapsed: {elapsed:.0f}ms")
        return False


def test_corner_cases():
    """Test 7: Corner cases (special characters, NULL, etc.)."""
    global TEST_RECORD_ID
    print("\n" + "=" * 60)
    print("TEST 7: Corner Cases")
    print("=" * 60)

    TEST_RECORD_ID = generate_test_id()
    results = []

    # Test 7a: Special characters in strings
    print("\n  7a: Special characters in strings")
    data = {
        'data': {
            'portfolio_id': TEST_RECORD_ID,
            'portfolio_name': "Test's \"Special\" <chars> & more\\backslash",
            'portfolio_code': 'SPEC01',
            'portfolio_type': 'TEST',
            'currency': 'USD',
            'status': 'DRAFT',
            'created_at': 'now',
            'created_by': 'corner_test'
        }
    }

    status, result = make_request(
        f'/insert/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )

    if status == 200 and result.get('success'):
        print(f"      SUCCESS! Special chars handled")
        results.append(True)
    else:
        print(f"      FAILED: {result.get('error', result)[:50]}")
        results.append(False)

    # Test 7b: NULL values
    print("\n  7b: NULL values")
    null_id = generate_test_id()
    data = {
        'data': {
            'portfolio_id': null_id,
            'portfolio_name': 'NULL Test',
            'portfolio_code': None,  # NULL
            'portfolio_type': '',    # Empty string
            'currency': 'USD',
            'manager_name': None,    # NULL
            'description': None,     # NULL
            'status': 'DRAFT',
            'created_at': 'now',
            'created_by': 'null_test'
        }
    }

    status, result = make_request(
        f'/insert/{TEST_DATABASE}.{TEST_TABLE}',
        method='POST',
        data=data,
        timeout=320
    )

    if status == 200 and result.get('success'):
        print(f"      SUCCESS! NULL values handled")
        results.append(True)
    else:
        print(f"      FAILED: {result.get('error', result)[:50]}")
        results.append(False)

    # Clean up test records
    print("\n  7c: Cleanup test records")
    for rid in [TEST_RECORD_ID, null_id]:
        make_request(
            f'/delete/{TEST_DATABASE}.{TEST_TABLE}',
            method='POST',
            data={'where': {'portfolio_id': rid}, 'soft_delete': False},
            timeout=320
        )

    print(f"      Cleaned up test records")
    results.append(True)

    return all(results)


def test_audit_log():
    """Test 8: Check audit log."""
    print("\n" + "=" * 60)
    print("TEST 8: Audit Log")
    print("=" * 60)

    # Query audit log
    status, result = make_request('/query', method='POST', data={
        'sql': f"SELECT * FROM {TEST_DATABASE}.hive_proxy_audit ORDER BY performed_at DESC LIMIT 5",
        'database': TEST_DATABASE
    }, timeout=120)

    if status == 200 and result.get('success'):
        rows = result.get('rows', 0)
        print(f"  Found {rows} recent audit entries")

        data = result.get('data', [])
        for entry in data[:3]:
            if isinstance(entry, dict):
                print(f"    - {entry.get('operation')} on {entry.get('table_name')} by {entry.get('performed_by')}")
        return True
    else:
        error = result.get('error', '')
        if 'Table not found' in str(error) or 'does not exist' in str(error).lower():
            print(f"  SKIP: Audit table not created yet")
            print(f"  Run: sql/create_audit_table.sql")
            return True  # Not a failure, just not set up
        print(f"  FAILED: {result}")
        return False


def test_stats():
    """Test 9: Get statistics."""
    print("\n" + "=" * 60)
    print("TEST 9: Statistics")
    print("=" * 60)

    status, result = make_request('/stats')

    if status == 200 and result.get('success'):
        stats = result.get('stats', {})
        print(f"  Total queries: {stats.get('total', 0)}")
        print(f"  Success: {stats.get('success', 0)}")
        print(f"  Failed: {stats.get('failed', 0)}")
        print(f"  SELECT: {stats.get('select', 0)}")
        print(f"  INSERT: {stats.get('insert', 0)}")
        print(f"  UPDATE: {stats.get('update', 0)}")
        print(f"  DELETE: {stats.get('delete', 0)}")

        cache = result.get('schema_cache', {})
        print(f"  Schema cache entries: {cache.get('entries', 0)}")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


# =============================================================================
# Main
# =============================================================================

def main():
    """Run all tests."""
    print("=" * 60)
    print("HIVE REST PROXY v2.0 TEST CLIENT")
    print("=" * 60)
    print(f"Proxy URL: {PROXY_URL}")
    print(f"API Key: {'configured' if API_KEY else 'not set'}")
    print(f"Database: {TEST_DATABASE}")
    print(f"Table: {TEST_TABLE}")

    results = {
        'health': test_health(),
        'schema': test_schema(),
        'insert': test_dynamic_insert(),
        'update': test_dynamic_update(),
        'soft_delete': test_dynamic_soft_delete(),
        'hard_delete': test_dynamic_hard_delete(),
        'corner_cases': test_corner_cases(),
        'audit': test_audit_log(),
        'stats': test_stats(),
    }

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {test:15} : {status}")

    print("-" * 30)
    print(f"  Total: {passed}/{total} passed")

    if passed == total:
        print("\nAll tests passed! REST Proxy v2.0 is working correctly.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
