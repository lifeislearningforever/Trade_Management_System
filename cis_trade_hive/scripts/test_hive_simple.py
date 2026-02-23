#!/usr/bin/env python3
"""
Simple Hive Connection Test - CDV 7.2.9 Settings
=================================================

Quick test script matching Cloudera Data Visualization settings.

CDV Connection Settings:
- Host: lxmrwtsgv0m2.sg.uobnet.com
- Port: 10000
- Connection mode: Binary
- Socket type: SSL
- Authentication: Kerberos
- Kerberos service name: hive

Usage:
    python test_hive_simple.py
"""

import time

# CDV Connection Settings
HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
HIVE_DATABASE = 'mrw_ima'
KERBEROS_SERVICE = 'hive'


def test_pyhive():
    """Test with PyHive (matching CDV Binary + Kerberos)."""
    print("\n" + "="*60)
    print("TEST 1: PyHive Connection (Kerberos)")
    print("="*60)

    try:
        from pyhive import hive

        print(f"Host: {HIVE_HOST}")
        print(f"Port: {HIVE_PORT}")
        print(f"Database: {HIVE_DATABASE}")
        print(f"Auth: KERBEROS")
        print(f"Service: {KERBEROS_SERVICE}")
        print()

        print("Connecting...")
        start = time.time()

        conn = hive.Connection(
            host=HIVE_HOST,
            port=HIVE_PORT,
            database=HIVE_DATABASE,
            auth='KERBEROS',
            kerberos_service_name=KERBEROS_SERVICE
        )

        print(f"Connected in {time.time()-start:.2f}s")

        cursor = conn.cursor()

        # Test 1: Simple query
        print("\nTest: SELECT 1")
        cursor.execute("SELECT 1 AS test")
        print(f"Result: {cursor.fetchone()}")

        # Test 2: Show databases
        print("\nTest: SHOW DATABASES")
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall()]
        print(f"Databases: {dbs[:5]}{'...' if len(dbs) > 5 else ''}")

        # Test 3: Show tables in mrw_ima
        print(f"\nTest: SHOW TABLES IN {HIVE_DATABASE}")
        cursor.execute(f"SHOW TABLES IN {HIVE_DATABASE}")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables: {tables[:10]}{'...' if len(tables) > 10 else ''}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] PyHive connection works!")
        return True

    except ImportError:
        print("[ERROR] PyHive not installed")
        print("Install: pip install pyhive thrift thrift-sasl sasl")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_pyhive_nosasl():
    """Test with PyHive without SASL (fallback)."""
    print("\n" + "="*60)
    print("TEST 2: PyHive Connection (NOSASL)")
    print("="*60)

    try:
        from pyhive import hive

        print(f"Host: {HIVE_HOST}")
        print(f"Port: {HIVE_PORT}")
        print(f"Auth: NOSASL")
        print()

        print("Connecting...")
        start = time.time()

        conn = hive.Connection(
            host=HIVE_HOST,
            port=HIVE_PORT,
            database=HIVE_DATABASE,
            auth='NOSASL'
        )

        print(f"Connected in {time.time()-start:.2f}s")

        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        print(f"Result: {cursor.fetchone()}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] NOSASL connection works!")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_impyla():
    """Test with impyla (Impala client)."""
    print("\n" + "="*60)
    print("TEST 3: impyla Connection")
    print("="*60)

    try:
        from impala.dbapi import connect

        # Note: impyla typically connects to Impala (port 21050)
        # but can also connect to HiveServer2
        IMPALA_PORT = 21050

        print(f"Host: {HIVE_HOST}")
        print(f"Port: {IMPALA_PORT}")
        print(f"Auth: GSSAPI (Kerberos)")
        print()

        print("Connecting...")
        start = time.time()

        conn = connect(
            host=HIVE_HOST,
            port=IMPALA_PORT,
            auth_mechanism='GSSAPI',
            kerberos_service_name='impala'
        )

        print(f"Connected in {time.time()-start:.2f}s")

        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        print(f"Result: {cursor.fetchone()}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] impyla connection works!")
        return True

    except ImportError:
        print("[ERROR] impyla not installed")
        print("Install: pip install impyla")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_describe_table():
    """Test DESCRIBE to get column names."""
    print("\n" + "="*60)
    print("TEST 4: Get Table Columns (DESCRIBE)")
    print("="*60)

    try:
        from pyhive import hive

        conn = hive.Connection(
            host=HIVE_HOST,
            port=HIVE_PORT,
            database=HIVE_DATABASE,
            auth='KERBEROS',
            kerberos_service_name=KERBEROS_SERVICE
        )

        cursor = conn.cursor()

        # Describe a table
        table = 'cis_trade'
        print(f"\nDESCRIBE {HIVE_DATABASE}.{table}")
        print("-" * 40)

        cursor.execute(f"DESCRIBE {HIVE_DATABASE}.{table}")
        columns = cursor.fetchall()

        print(f"{'Column Name':<30} {'Type':<20}")
        print("-" * 50)
        for col in columns[:20]:
            print(f"{col[0]:<30} {col[1]:<20}")

        if len(columns) > 20:
            print(f"... and {len(columns) - 20} more columns")

        print(f"\nTotal columns: {len(columns)}")

        # Print as Python list
        print("\nPython list format:")
        col_names = [col[0] for col in columns]
        print(f"columns = {col_names}")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    print("="*60)
    print("HIVE CONNECTION TEST - CDV 7.2.9 Settings")
    print("="*60)
    print(f"Host: {HIVE_HOST}")
    print(f"Port: {HIVE_PORT}")
    print(f"Database: {HIVE_DATABASE}")

    results = {}

    # Test 1: PyHive with Kerberos
    results['pyhive_kerberos'] = test_pyhive()

    # Test 2: PyHive without SASL (fallback)
    # results['pyhive_nosasl'] = test_pyhive_nosasl()

    # Test 3: impyla
    # results['impyla'] = test_impyla()

    # Test 4: Describe table
    if results.get('pyhive_kerberos'):
        results['describe'] = test_describe_table()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test}")


if __name__ == '__main__':
    main()
