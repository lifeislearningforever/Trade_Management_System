#!/usr/bin/env python3
"""
Simple Hive Connection Test Script
===================================

Test PyHive connectivity to HiveServer2 with different auth modes.

Usage:
    # Test with Kerberos (default)
    python test_hive_connection.py

    # Test with NOSASL (no auth)
    python test_hive_connection.py --auth NOSASL

    # Test with LDAP
    python test_hive_connection.py --auth LDAP --user myuser --password mypass

    # Custom host/port
    python test_hive_connection.py --host hive.server.com --port 10000
"""

import sys
import time
import argparse

def test_pyhive_connection(host, port, auth, database, kerberos_service='hive',
                           username=None, password=None):
    """Test PyHive connection."""
    print("\n" + "="*60)
    print("PyHive Connection Test")
    print("="*60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Auth: {auth}")
    print(f"Database: {database}")
    print("="*60 + "\n")

    # Step 1: Check imports
    print("[1/5] Checking PyHive installation...")
    try:
        from pyhive import hive
        print("      ✓ PyHive imported successfully")
    except ImportError as e:
        print(f"      ✗ PyHive not installed: {e}")
        print("      Fix: pip install pyhive thrift thrift-sasl")
        return False

    # Step 2: Check SASL (for Kerberos)
    print("\n[2/5] Checking SASL/Kerberos libraries...")
    sasl_available = False
    try:
        import sasl
        import thrift_sasl
        sasl_available = True
        print("      ✓ SASL libraries available")
    except ImportError as e:
        print(f"      ⚠ SASL not available: {e}")
        print("      Fix: pip install sasl thrift-sasl")
        if auth.upper() in ('KERBEROS', 'GSSAPI'):
            print("      Kerberos auth may fail without SASL")

    # Step 3: Check Kerberos ticket (if using Kerberos)
    if auth.upper() in ('KERBEROS', 'GSSAPI'):
        print("\n[3/5] Checking Kerberos ticket...")
        import subprocess
        try:
            result = subprocess.run(['klist', '-s'], capture_output=True)
            if result.returncode == 0:
                print("      ✓ Valid Kerberos ticket found")
                # Show ticket info
                klist = subprocess.run(['klist'], capture_output=True, text=True)
                for line in klist.stdout.split('\n')[:5]:
                    if line.strip():
                        print(f"        {line}")
            else:
                print("      ✗ No valid Kerberos ticket")
                print("      Fix: kinit -kt /path/to/keytab principal@REALM")
                return False
        except FileNotFoundError:
            print("      ⚠ klist command not found")
    else:
        print("\n[3/5] Skipping Kerberos check (not using Kerberos auth)")

    # Step 4: Create connection
    print(f"\n[4/5] Connecting to HiveServer2...")

    conn_params = {
        'host': host,
        'port': port,
        'database': database,
    }

    auth_upper = auth.upper()
    if auth_upper in ('KERBEROS', 'GSSAPI'):
        conn_params['auth'] = 'KERBEROS'
        conn_params['kerberos_service_name'] = kerberos_service
        print(f"      Using Kerberos auth (service: {kerberos_service})")
    elif auth_upper == 'LDAP':
        conn_params['auth'] = 'LDAP'
        conn_params['username'] = username
        conn_params['password'] = password
        print(f"      Using LDAP auth (user: {username})")
    elif auth_upper == 'CUSTOM':
        conn_params['auth'] = 'CUSTOM'
        conn_params['username'] = username
        conn_params['password'] = password
        print(f"      Using CUSTOM auth (user: {username})")
    else:
        conn_params['auth'] = 'NOSASL'
        print("      Using NOSASL (no authentication)")

    start = time.time()
    try:
        conn = hive.Connection(**conn_params)
        elapsed = time.time() - start
        print(f"      ✓ Connected successfully ({elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.time() - start
        print(f"      ✗ Connection failed ({elapsed:.2f}s): {e}")

        # Suggest fixes
        if 'SASL' in str(e):
            print("\n      Troubleshooting SASL errors:")
            print("        1. Install: pip install sasl thrift-sasl pykerberos")
            print("        2. System: yum install cyrus-sasl-devel cyrus-sasl-gssapi")
            print("        3. Kerberos: kinit -kt keytab principal@REALM")
            print("        4. Or try: python test_hive_connection.py --auth NOSASL")
        return False

    # Step 5: Run test query
    print("\n[5/5] Running test query...")
    try:
        cursor = conn.cursor()

        # Test 1: Simple query
        start = time.time()
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        elapsed = time.time() - start
        print(f"      ✓ SELECT 1: {result} ({elapsed*1000:.1f}ms)")

        # Test 2: Show databases
        start = time.time()
        cursor.execute("SHOW DATABASES")
        databases = [row[0] for row in cursor.fetchall()]
        elapsed = time.time() - start
        print(f"      ✓ SHOW DATABASES: {len(databases)} found ({elapsed*1000:.1f}ms)")
        print(f"        Databases: {', '.join(databases[:5])}{'...' if len(databases) > 5 else ''}")

        # Test 3: Use database
        start = time.time()
        cursor.execute(f"USE {database}")
        elapsed = time.time() - start
        print(f"      ✓ USE {database} ({elapsed*1000:.1f}ms)")

        # Test 4: Show tables
        start = time.time()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        elapsed = time.time() - start
        print(f"      ✓ SHOW TABLES: {len(tables)} found ({elapsed*1000:.1f}ms)")
        if tables:
            print(f"        Tables: {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")

        # Test 5: Check execution engine
        start = time.time()
        cursor.execute("SET hive.execution.engine")
        engine = cursor.fetchone()
        elapsed = time.time() - start
        print(f"      ✓ Execution engine: {engine} ({elapsed*1000:.1f}ms)")

        cursor.close()
        conn.close()
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED - Hive connection working!")
        print("="*60 + "\n")
        return True

    except Exception as e:
        print(f"      ✗ Query failed: {e}")
        return False


def test_beeline_connection(host, port, database):
    """Test beeline connection as fallback."""
    print("\n" + "="*60)
    print("Beeline Connection Test (Fallback)")
    print("="*60)

    import subprocess

    jdbc_url = f"jdbc:hive2://{host}:{port}/{database}"
    cmd = ['beeline', '-u', jdbc_url, '-e', 'SELECT 1']

    print(f"Command: {' '.join(cmd)}")
    print("Running...")

    start = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"✓ Beeline connected successfully ({elapsed:.2f}s)")
            return True
        else:
            print(f"✗ Beeline failed ({elapsed:.2f}s)")
            print(f"STDERR: {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        print("✗ Beeline timed out after 60s")
        return False
    except FileNotFoundError:
        print("✗ beeline command not found")
        return False


def main():
    parser = argparse.ArgumentParser(description='Test Hive Connection')
    parser.add_argument('--host', default='lxmrwtsgv0m1.sg.uobnet.com',
                       help='HiveServer2 host')
    parser.add_argument('--port', type=int, default=10000,
                       help='HiveServer2 port')
    parser.add_argument('--database', default='mrw_ima',
                       help='Default database')
    parser.add_argument('--auth', default='KERBEROS',
                       choices=['KERBEROS', 'GSSAPI', 'LDAP', 'CUSTOM', 'NOSASL', 'NONE'],
                       help='Authentication mode')
    parser.add_argument('--kerberos-service', default='hive',
                       help='Kerberos service name')
    parser.add_argument('--user', default=None,
                       help='Username for LDAP/CUSTOM auth')
    parser.add_argument('--password', default=None,
                       help='Password for LDAP/CUSTOM auth')
    parser.add_argument('--beeline', action='store_true',
                       help='Also test beeline connection')

    args = parser.parse_args()

    print("\n" + "#"*60)
    print("# HIVE CONNECTION TEST")
    print("#"*60)

    # Test PyHive
    success = test_pyhive_connection(
        host=args.host,
        port=args.port,
        auth=args.auth,
        database=args.database,
        kerberos_service=args.kerberos_service,
        username=args.user,
        password=args.password
    )

    # Test beeline if requested or PyHive failed
    if args.beeline or not success:
        beeline_success = test_beeline_connection(
            host=args.host,
            port=args.port,
            database=args.database
        )
        if not success and beeline_success:
            print("\n⚠ PyHive failed but beeline works.")
            print("  Use app_v2.py (beeline) instead of app_v3.py (PyHive)")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
