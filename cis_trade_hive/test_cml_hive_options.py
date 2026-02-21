#!/usr/bin/env python3
"""
Test All Hive Connection Options for CML

This script tests all available options for connecting to Hive from CML:
1. REST Proxy (recommended - no native library issues)
2. Direct impyla (usually fails due to glibc/SASL issues)
3. Beeline subprocess (works only on edge node, not in CML Docker)

Run this in CML to identify which option works best.

Usage:
    # Basic test
    python test_cml_hive_options.py

    # With REST Proxy URL
    HIVE_PROXY_URL=http://edge-node:5000 python test_cml_hive_options.py

    # With all options
    HIVE_PROXY_URL=http://edge-node:5000 \
    HIVE_PROXY_API_KEY=your-key \
    python test_cml_hive_options.py
"""

import os
import sys
import time

os.environ.setdefault('CIS_ENV', 'work')

print("=" * 70)
print("CML HIVE CONNECTION OPTIONS TEST")
print("=" * 70)

# Test 1: Environment check
print("\n[1] Environment Check")
print("-" * 50)

env_vars = [
    'CIS_ENV', 'HIVE_PROXY_URL', 'HIVE_PROXY_API_KEY',
    'KRB5CCNAME', 'CDSW_APP_PORT', 'CDSW_DOMAIN'
]
for var in env_vars:
    value = os.environ.get(var, 'not set')
    if 'KEY' in var and value != 'not set':
        value = '***configured***'
    print(f"  {var}: {value}")

# Test 2: Check available libraries
print("\n[2] Available Libraries")
print("-" * 50)

libs = {
    'impyla': False,
    'pyhive': False,
    'requests': False,
    'pure_sasl': False,
    'thrift': False,
}

for lib in libs:
    try:
        __import__(lib.replace('_', '-').replace('-', '_'))
        libs[lib] = True
        print(f"  {lib}: installed")
    except ImportError:
        print(f"  {lib}: NOT installed")

# Test 3: REST Proxy (Option 1 - Recommended)
print("\n[3] REST Proxy Connection (Option 1 - Recommended)")
print("-" * 50)

proxy_url = os.environ.get('HIVE_PROXY_URL', '')
if not proxy_url:
    print("  SKIP: HIVE_PROXY_URL not set")
    print("  To test: export HIVE_PROXY_URL=http://edge-node:5000")
else:
    try:
        import requests
        api_key = os.environ.get('HIVE_PROXY_API_KEY', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['X-API-Key'] = api_key

        # Health check
        start = time.time()
        resp = requests.get(f"{proxy_url}/health", headers=headers, timeout=10)
        elapsed = (time.time() - start) * 1000

        if resp.status_code == 200:
            data = resp.json()
            print(f"  Health: OK ({elapsed:.0f}ms)")
            print(f"  Status: {data.get('status')}")
            print(f"  Version: {data.get('version')}")
        else:
            print(f"  Health: FAILED (status {resp.status_code})")

        # Test query
        start = time.time()
        resp = requests.post(
            f"{proxy_url}/query",
            json={'sql': 'SELECT 1 as test', 'database': 'gmp_cis'},
            headers=headers,
            timeout=30
        )
        elapsed = (time.time() - start) * 1000

        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                print(f"  Query: SUCCESS ({elapsed:.0f}ms)")
                print(f"  Data: {data.get('data')}")
            else:
                print(f"  Query: FAILED - {data.get('error')}")
        else:
            print(f"  Query: FAILED (status {resp.status_code})")

    except requests.exceptions.ConnectionError as e:
        print(f"  ERROR: Connection refused - proxy not running?")
        print(f"  Details: {str(e)[:80]}")
    except Exception as e:
        print(f"  ERROR: {str(e)[:80]}")

# Test 4: Direct Impyla to Impala (Option 2 - for reads)
print("\n[4] Direct Impyla to Impala (Reads)")
print("-" * 50)

if not libs['impyla']:
    print("  SKIP: impyla not installed")
    print("  To install: pip install impyla pure-sasl thrift-sasl")
else:
    try:
        from impala.dbapi import connect

        # Get config from environment or use defaults
        host = os.environ.get('IMPALA_HOST', 'lxmrwsgv0d1.sg.uobnet.com')
        port = int(os.environ.get('IMPALA_PORT', '21050'))

        print(f"  Connecting to {host}:{port}...")
        start = time.time()

        conn = connect(
            host=host,
            port=port,
            database='gmp_cis',
            auth_mechanism='GSSAPI',
            kerberos_service_name='impala',
            use_ssl=True,
            timeout=30
        )

        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        elapsed = (time.time() - start) * 1000

        print(f"  SUCCESS! ({elapsed:.0f}ms)")
        print(f"  Result: {result}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"  FAILED: {str(e)[:80]}")

# Test 5: Direct Impyla to HiveServer2 (Option 3 - usually fails)
print("\n[5] Direct Impyla to HiveServer2 (Writes - usually fails in CML)")
print("-" * 50)

if not libs['impyla']:
    print("  SKIP: impyla not installed")
else:
    try:
        from impala.dbapi import connect

        host = os.environ.get('HIVE_HOST', 'lxmrwtsgv0m2.sg.uobnet.com')
        port = int(os.environ.get('HIVE_PORT', '10000'))

        print(f"  Connecting to {host}:{port}...")
        start = time.time()

        conn = connect(
            host=host,
            port=port,
            database='gmp_cis',
            auth_mechanism='GSSAPI',
            kerberos_service_name='hive',
            use_ssl=False,
            timeout=30
        )

        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        elapsed = (time.time() - start) * 1000

        print(f"  SUCCESS! ({elapsed:.0f}ms)")
        print(f"  Result: {result}")

        cursor.close()
        conn.close()

    except Exception as e:
        error_str = str(e)
        if 'TSocket read 0 bytes' in error_str:
            print(f"  FAILED: TSocket read 0 bytes (expected - SASL/glibc issue)")
        elif 'GLIBC' in error_str:
            print(f"  FAILED: glibc version mismatch (expected in CML)")
        else:
            print(f"  FAILED: {error_str[:80]}")

# Test 6: PyHive (Option 4 - usually fails same as impyla)
print("\n[6] PyHive to HiveServer2 (usually fails same as impyla)")
print("-" * 50)

if not libs['pyhive']:
    print("  SKIP: pyhive not installed")
else:
    try:
        from pyhive import hive

        host = os.environ.get('HIVE_HOST', 'lxmrwtsgv0m2.sg.uobnet.com')
        port = int(os.environ.get('HIVE_PORT', '10000'))

        print(f"  Connecting to {host}:{port}...")
        start = time.time()

        conn = hive.Connection(
            host=host,
            port=port,
            database='gmp_cis',
            auth='KERBEROS',
            kerberos_service_name='hive'
        )

        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        elapsed = (time.time() - start) * 1000

        print(f"  SUCCESS! ({elapsed:.0f}ms)")
        print(f"  Result: {result}")

        cursor.close()
        conn.close()

    except Exception as e:
        error_str = str(e)
        if 'TSocket read 0 bytes' in error_str:
            print(f"  FAILED: TSocket read 0 bytes (expected - SASL/glibc issue)")
        elif 'GLIBC' in error_str:
            print(f"  FAILED: glibc version mismatch (expected in CML)")
        else:
            print(f"  FAILED: {error_str[:80]}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY & RECOMMENDATIONS")
print("=" * 70)

print("""
OPTION 1: REST Proxy (RECOMMENDED for CML)
  - Deploy hive_proxy/app.py on edge node
  - Set HIVE_PROXY_URL=http://edge-node:5000 in CML
  - Works around all glibc/SASL issues
  - ~50-200ms latency per query

OPTION 2: Impala for Reads + Proxy for Writes
  - Use direct impyla connection for SELECT queries (fast)
  - Use REST Proxy for INSERT/UPDATE/DELETE (reliable)
  - Best performance combination

OPTION 3: PySpark (NOT recommended for Django UI)
  - 10-30 second startup time per operation
  - Only suitable for batch jobs, not real-time UI

NEXT STEPS:
1. Deploy REST Proxy on edge node:
   - scp hive_proxy/app.py to edge node
   - pip install flask gunicorn
   - kinit to get Kerberos ticket
   - gunicorn -b 0.0.0.0:5000 -w 4 app:app

2. Test from CML:
   - export HIVE_PROXY_URL=http://edge-node:5000
   - python hive_proxy/test_proxy_client.py

3. Integrate with Django:
   - Set HIVE_PROXY_URL in CML environment
   - HybridConnectionManager will auto-use proxy
""")
