#!/usr/bin/env python3
"""
Hive Connection Diagnostic Script for CML

Tests different connection approaches to find what works.
Run: python test_hive_diagnostic.py
"""
import os
import sys

# Force work environment
os.environ['CIS_ENV'] = 'work'

# Hive connection parameters (from DataViz working config)
HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
DATABASE = 'mrw_ima'
KERBEROS_SERVICE = 'hive'

print("=" * 70)
print("HIVE CONNECTION DIAGNOSTIC")
print("=" * 70)
print(f"\nHost: {HIVE_HOST}")
print(f"Port: {HIVE_PORT}")
print(f"Database: {DATABASE}")
print(f"Kerberos Service: {KERBEROS_SERVICE}")

# Check Kerberos ticket
print("\n" + "-" * 70)
print("[1] Kerberos Ticket Check")
print("-" * 70)
import subprocess
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode == 0:
    print("Kerberos ticket: VALID")
    for line in result.stdout.split('\n'):
        if 'principal' in line.lower():
            print(f"  {line.strip()}")
else:
    print("Kerberos ticket: NOT FOUND - Run kinit first!")
    sys.exit(1)

# Test 1: impyla with GSSAPI
print("\n" + "-" * 70)
print("[2] Test impyla with GSSAPI (Binary, No SSL)")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name=KERBEROS_SERVICE,
        use_ssl=False,
        timeout=60,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: impyla with different timeout
print("\n" + "-" * 70)
print("[3] Test impyla with longer timeout (120s)")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name=KERBEROS_SERVICE,
        use_ssl=False,
        timeout=120,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 3: pyhive with KERBEROS
print("\n" + "-" * 70)
print("[4] Test pyhive with KERBEROS auth")
print("-" * 70)
try:
    from pyhive import hive

    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth='KERBEROS',
        kerberos_service_name=KERBEROS_SERVICE,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except ImportError:
    print("pyhive not installed")
except Exception as e:
    print(f"FAILED: {e}")

# Test 4: Try different service names
print("\n" + "-" * 70)
print("[5] Test with 'hiveserver2' service name")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name='hiveserver2',
        use_ssl=False,
        timeout=60,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 5: Test with thrift_transport
print("\n" + "-" * 70)
print("[6] Test with explicit thrift_transport='binary'")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    # Check if thrift_transport is supported
    import inspect
    sig = inspect.signature(impyla_connect)
    if 'thrift_transport' in sig.parameters:
        conn = impyla_connect(
            host=HIVE_HOST,
            port=HIVE_PORT,
            database=DATABASE,
            auth_mechanism='GSSAPI',
            kerberos_service_name=KERBEROS_SERVICE,
            use_ssl=False,
            timeout=60,
            thrift_transport='binary',
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        print(f"SUCCESS! Result: {result}")
    else:
        print("thrift_transport parameter not supported in this impyla version")
except Exception as e:
    print(f"FAILED: {e}")

# Test 6: Try without database
print("\n" + "-" * 70)
print("[7] Test without specifying database")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        auth_mechanism='GSSAPI',
        kerberos_service_name=KERBEROS_SERVICE,
        use_ssl=False,
        timeout=60,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
