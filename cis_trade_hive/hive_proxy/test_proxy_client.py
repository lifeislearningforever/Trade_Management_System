#!/usr/bin/env python3
"""
Test Client for Hive REST Proxy

Run this from CML to test connectivity to the REST Proxy on the edge node.

Usage:
    python test_proxy_client.py

Environment Variables:
    HIVE_PROXY_URL: URL of the REST Proxy (e.g., http://edge-node:5000)
    HIVE_PROXY_API_KEY: API key if proxy requires authentication
"""

import os
import sys
import json
import time

# Try to import requests
try:
    import requests
except ImportError:
    print("ERROR: requests library not installed")
    print("Install: pip install requests")
    sys.exit(1)


# Configuration
PROXY_URL = os.environ.get('HIVE_PROXY_URL', 'http://localhost:5000')
API_KEY = os.environ.get('HIVE_PROXY_API_KEY', '')

# Test database - use mrw_ima with Hive ACID tables (not Kudu)
TEST_DATABASE = os.environ.get('HIVE_TEST_DATABASE', 'mrw_ima')
TEST_TABLE = os.environ.get('HIVE_TEST_TABLE', 'portfolio_hive')


def make_request(endpoint: str, method: str = 'GET', data: dict = None, timeout: int = 30):
    """Make a request to the proxy."""
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
    except requests.exceptions.ConnectionError as e:
        return None, {'error': f'Connection failed: {str(e)}'}
    except requests.exceptions.Timeout:
        return None, {'error': 'Request timed out'}
    except Exception as e:
        return None, {'error': str(e)}


def test_health():
    """Test 1: Health check endpoint."""
    print("\n" + "=" * 60)
    print("TEST 1: Health Check")
    print("=" * 60)

    status, result = make_request('/health')

    if status == 200:
        print(f"  Status: OK")
        print(f"  Service: {result.get('service')}")
        print(f"  Version: {result.get('version')}")
        print(f"  Config: {json.dumps(result.get('config', {}), indent=4)}")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_connection():
    """Test 2: Test Hive connection."""
    print("\n" + "=" * 60)
    print("TEST 2: Hive Connection Test")
    print("=" * 60)

    status, result = make_request('/test')

    if status == 200:
        print(f"  Status: Connected")
        print(f"  Result: {result.get('result')}")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_list_databases():
    """Test 3: List databases."""
    print("\n" + "=" * 60)
    print("TEST 3: List Databases")
    print("=" * 60)

    status, result = make_request('/databases')

    if status == 200 and result.get('success'):
        databases = result.get('data', [])
        print(f"  Found {len(databases)} databases")
        for db in databases[:10]:  # Show first 10
            print(f"    - {db}")
        if len(databases) > 10:
            print(f"    ... and {len(databases) - 10} more")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_list_tables():
    """Test 4: List tables in gmp_cis database."""
    print("\n" + "=" * 60)
    print(f"TEST 4: List Tables in {TEST_DATABASE}")
    print("=" * 60)

    status, result = make_request(f'/tables?database={TEST_DATABASE}')

    if status == 200 and result.get('success'):
        tables = result.get('data', [])
        print(f"  Found {len(tables)} tables")
        for table in tables[:15]:  # Show first 15
            print(f"    - {table}")
        if len(tables) > 15:
            print(f"    ... and {len(tables) - 15} more")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_select_query():
    """Test 5: Execute a SELECT query on Hive ACID table."""
    print("\n" + "=" * 60)
    print("TEST 5: SELECT Query (Hive ACID Table)")
    print("=" * 60)

    query = f"SELECT * FROM {TEST_DATABASE}.{TEST_TABLE} LIMIT 5"
    print(f"  Query: {query}")

    status, result = make_request('/query', method='POST', data={
        'sql': query,
        'database': TEST_DATABASE,
        'timeout': 60
    })

    if status == 200 and result.get('success'):
        rows = result.get('rows', 0)
        elapsed = result.get('elapsed_ms', 0)
        print(f"  Rows: {rows}")
        print(f"  Elapsed: {elapsed}ms")
        data = result.get('data', [])
        if data:
            print(f"  Sample: {json.dumps(data[0], indent=4)}")
        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_insert_query():
    """Test 6: Execute an INSERT query (into Hive ACID table)."""
    print("\n" + "=" * 60)
    print("TEST 6: INSERT Query (Hive ACID Table)")
    print("=" * 60)

    # Use timestamp for unique ID
    timestamp = int(time.time() * 1000)

    # Insert into portfolio_hive table (Hive ACID table in mrw_ima)
    # First, let's check the table schema
    print(f"  Checking {TEST_DATABASE}.{TEST_TABLE} schema...")

    # Get table schema first
    schema_status, schema_result = make_request('/query', method='POST', data={
        'sql': f"DESCRIBE {TEST_DATABASE}.{TEST_TABLE}",
        'database': TEST_DATABASE,
        'timeout': 60
    })

    if schema_status == 200 and schema_result.get('success'):
        print(f"  Table columns: {[col.get('col_name', col) for col in schema_result.get('data', [])[:5]]}")

    # Insert a test record - adjust columns based on actual table schema
    query = f"""
    INSERT INTO {TEST_DATABASE}.{TEST_TABLE}
    (portfolio_id, portfolio_name, status, created_by, created_at)
    VALUES
    ('TEST_{timestamp}', 'REST Proxy Test Portfolio', 'DRAFT', 'proxy_test', CURRENT_TIMESTAMP)
    """

    print(f"  Query: INSERT INTO {TEST_TABLE} (test record)")

    status, result = make_request('/execute', method='POST', data={
        'sql': query.strip(),
        'database': TEST_DATABASE,
        'timeout': 120
    })

    if status == 200 and result.get('success'):
        elapsed = result.get('elapsed_ms', 0)
        print(f"  SUCCESS!")
        print(f"  Elapsed: {elapsed}ms")

        # Verify the insert
        verify_query = f"SELECT * FROM {TEST_DATABASE}.{TEST_TABLE} WHERE portfolio_id = 'TEST_{timestamp}'"
        status2, result2 = make_request('/query', method='POST', data={
            'sql': verify_query,
            'database': TEST_DATABASE
        })

        if status2 == 200 and result2.get('rows', 0) > 0:
            print(f"  Verified: Record found in database")

        return True
    else:
        print(f"  FAILED: {result}")
        return False


def test_batch_queries():
    """Test 7: Execute batch queries on Hive ACID tables."""
    print("\n" + "=" * 60)
    print("TEST 7: Batch Queries (Hive ACID Tables)")
    print("=" * 60)

    queries = [
        {'sql': f'SELECT COUNT(*) as cnt FROM {TEST_DATABASE}.{TEST_TABLE}', 'type': 'read'},
        {'sql': f'SHOW TABLES IN {TEST_DATABASE}', 'type': 'read'},
    ]

    print(f"  Executing {len(queries)} queries in batch...")

    status, result = make_request('/batch', method='POST', data={
        'queries': queries,
        'database': TEST_DATABASE,
        'stop_on_error': False
    })

    if status == 200:
        executed = result.get('executed', 0)
        total = result.get('total', 0)
        print(f"  Executed: {executed}/{total}")

        for r in result.get('results', []):
            idx = r.get('index')
            success = r.get('success')
            data = r.get('data', [])
            print(f"    Query {idx + 1}: {'OK' if success else 'FAILED'} - {data}")

        return result.get('success', False)
    else:
        print(f"  FAILED: {result}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("HIVE REST PROXY TEST CLIENT")
    print("=" * 60)
    print(f"Proxy URL: {PROXY_URL}")
    print(f"API Key: {'configured' if API_KEY else 'not set'}")
    print(f"Database: {TEST_DATABASE}")
    print(f"Test Table: {TEST_TABLE} (Hive ACID)")

    results = {
        'health': test_health(),
        'connection': test_connection(),
        'databases': test_list_databases(),
        'tables': test_list_tables(),
        'select': test_select_query(),
        'insert': test_insert_query(),
        'batch': test_batch_queries(),
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
        print("\nAll tests passed! REST Proxy is working correctly.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed. Check the proxy configuration.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
