#!/usr/bin/env python3
"""
CDV Hive Connection Test - Without PyHive
==========================================

This script tests Hive connectivity using packages that are typically
available in CDV (Cloudera Data Visualization) without needing to install PyHive.

Methods tested:
1. impyla (usually available in CDV)
2. subprocess + beeline (always works)
3. JayDeBeApi + JDBC (if Java available)
4. requests + REST API (if Knox/Livy available)

CDV Environment:
- venv: /opt/vizapps/venv
- Python: 3.9
- Site packages: /opt/vizapps/venv/lib64/python3.9/site-packages

Usage:
    python cdv_test_hive_no_pyhive.py
    python cdv_test_hive_no_pyhive.py --method beeline
    python cdv_test_hive_no_pyhive.py --method impyla
"""

import os
import sys
import subprocess
import time
import argparse
from datetime import datetime


# CDV/Hive Settings
HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
HIVE_DATABASE = 'mrw_ima'
KERBEROS_PRINCIPAL = 'hive/_HOST@TST.UOBNET.COM'


def print_banner(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_section(text):
    print("\n" + "-" * 40)
    print(text)
    print("-" * 40)


def check_available_packages():
    """Check which packages are available in CDV."""
    print_section("Checking Available Packages")

    packages = {
        'impyla': 'impala.dbapi',
        'jaydebeapi': 'jaydebeapi',
        'pyhive': 'pyhive',
        'thrift': 'thrift',
        'pandas': 'pandas',
        'sqlalchemy': 'sqlalchemy',
        'requests': 'requests',
    }

    available = {}
    for name, module in packages.items():
        try:
            __import__(module)
            print(f"  [OK] {name}")
            available[name] = True
        except ImportError:
            print(f"  [--] {name} (not installed)")
            available[name] = False

    return available


def test_impyla():
    """Test using impyla (Impala Python client)."""
    print_section("Method 1: impyla")

    try:
        from impala.dbapi import connect
        from impala.hive import connect as hive_connect

        print(f"Host: {HIVE_HOST}")
        print(f"Port: {HIVE_PORT}")
        print(f"Auth: GSSAPI (Kerberos)")
        print()

        # impyla can connect to HiveServer2 as well
        print("Connecting to HiveServer2 via impyla...")
        start = time.time()

        conn = connect(
            host=HIVE_HOST,
            port=HIVE_PORT,
            auth_mechanism='GSSAPI',
            kerberos_service_name='hive',
            database=HIVE_DATABASE
        )

        print(f"Connected in {time.time()-start:.2f}s")

        cursor = conn.cursor()

        # Test query
        print("\nRunning: SELECT 1")
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        print(f"Result: {result}")

        # Show tables
        print(f"\nRunning: SHOW TABLES")
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()[:10]]
        print(f"Tables: {tables}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] impyla connection works!")
        return True

    except ImportError:
        print("[ERROR] impyla not installed")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_beeline():
    """Test using beeline subprocess."""
    print_section("Method 2: Beeline (subprocess)")

    # Build JDBC URL
    jdbc_url = (
        f"jdbc:hive2://{HIVE_HOST}:{HIVE_PORT}/{HIVE_DATABASE};"
        f"principal={KERBEROS_PRINCIPAL};"
        f"ssl=true"
    )

    print(f"JDBC URL: {jdbc_url[:80]}...")
    print()

    # Test query
    query = "SELECT 1 AS test"
    cmd = f'beeline -u "{jdbc_url}" -e "{query}" --silent=true --outputformat=csv2'

    print(f"Running: {query}")

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"Completed in {elapsed:.2f}s")

            # Parse output
            output = result.stdout.strip()
            lines = [l for l in output.split('\n')
                    if l.strip() and not l.startswith('INFO') and not l.startswith('WARNING')]

            print(f"Output: {lines[:5]}")
            print("\n[SUCCESS] Beeline works!")
            return True
        else:
            print(f"[ERROR] Return code: {result.returncode}")
            print(f"STDERR: {result.stderr[:300]}")
            return False

    except subprocess.TimeoutExpired:
        print("[ERROR] Timeout after 120s")
        return False
    except FileNotFoundError:
        print("[ERROR] beeline command not found")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_jaydebeapi():
    """Test using JayDeBeApi with JDBC."""
    print_section("Method 3: JayDeBeApi (JDBC)")

    try:
        import jaydebeapi

        # Hive JDBC driver
        jdbc_driver = "org.apache.hive.jdbc.HiveDriver"
        jdbc_url = (
            f"jdbc:hive2://{HIVE_HOST}:{HIVE_PORT}/{HIVE_DATABASE};"
            f"principal={KERBEROS_PRINCIPAL};"
            f"ssl=true"
        )

        # Find Hive JDBC jar
        possible_jars = [
            "/opt/cloudera/parcels/CDH/lib/hive/lib/hive-jdbc-standalone.jar",
            "/usr/lib/hive/lib/hive-jdbc-standalone.jar",
            "/opt/cloudera/parcels/CDH/jars/hive-jdbc-*.jar",
        ]

        jar_path = None
        for path in possible_jars:
            if os.path.exists(path):
                jar_path = path
                break

        if not jar_path:
            print("[ERROR] Hive JDBC jar not found")
            print(f"Searched: {possible_jars}")
            return False

        print(f"JDBC Driver: {jdbc_driver}")
        print(f"JDBC URL: {jdbc_url[:60]}...")
        print(f"JAR: {jar_path}")
        print()

        print("Connecting...")
        start = time.time()

        conn = jaydebeapi.connect(
            jdbc_driver,
            jdbc_url,
            ['', ''],  # Empty user/password for Kerberos
            jar_path
        )

        print(f"Connected in {time.time()-start:.2f}s")

        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        print(f"Result: {result}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] JayDeBeApi works!")
        return True

    except ImportError:
        print("[ERROR] jaydebeapi not installed")
        print("Install: pip install JayDeBeApi")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_sqlalchemy_hive():
    """Test using SQLAlchemy with Hive dialect."""
    print_section("Method 4: SQLAlchemy + Hive")

    try:
        from sqlalchemy import create_engine, text

        # SQLAlchemy Hive connection string
        # Requires: pip install sqlalchemy pyhive
        conn_str = (
            f"hive://{HIVE_HOST}:{HIVE_PORT}/{HIVE_DATABASE}"
            f"?auth=KERBEROS&kerberos_service_name=hive"
        )

        print(f"Connection: {conn_str[:60]}...")
        print()

        print("Creating engine...")
        engine = create_engine(conn_str)

        print("Connecting...")
        start = time.time()

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 AS test"))
            row = result.fetchone()
            print(f"Result: {row}")

        print(f"Completed in {time.time()-start:.2f}s")
        print("\n[SUCCESS] SQLAlchemy works!")
        return True

    except ImportError as e:
        print(f"[ERROR] Missing package: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def run_query_beeline(query: str, database: str = None):
    """Run a query using beeline and return results."""
    db = database or HIVE_DATABASE

    jdbc_url = (
        f"jdbc:hive2://{HIVE_HOST}:{HIVE_PORT}/{db};"
        f"principal={KERBEROS_PRINCIPAL};"
        f"ssl=true"
    )

    cmd = f'beeline -u "{jdbc_url}" -e "{query}" --silent=true --outputformat=csv2 --showHeader=true'

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            # Filter out info/warning lines
            lines = [l for l in output.split('\n')
                    if l.strip() and not l.startswith('INFO') and not l.startswith('WARNING')]
            return True, '\n'.join(lines)
        else:
            return False, result.stderr

    except Exception as e:
        return False, str(e)


def describe_table(table_name: str):
    """Get table columns using beeline."""
    print_section(f"DESCRIBE {HIVE_DATABASE}.{table_name}")

    success, output = run_query_beeline(f"DESCRIBE {HIVE_DATABASE}.{table_name}")

    if success:
        print(output)

        # Parse columns
        lines = output.strip().split('\n')
        if len(lines) > 1:
            columns = []
            for line in lines[1:]:  # Skip header
                parts = line.split(',')
                if parts:
                    columns.append(parts[0].strip())

            print(f"\nPython list format:")
            print(f"columns = {columns}")
    else:
        print(f"[ERROR] {output}")


def main():
    parser = argparse.ArgumentParser(description='CDV Hive Test (No PyHive)')
    parser.add_argument('--method', choices=['all', 'impyla', 'beeline', 'jdbc', 'sqlalchemy'],
                        default='all', help='Test method')
    parser.add_argument('--query', '-q', type=str, help='Custom query to run')
    parser.add_argument('--describe', '-d', type=str, help='Describe a table')

    args = parser.parse_args()

    print_banner("CDV HIVE CONNECTION TEST (No PyHive)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Host: {HIVE_HOST}")
    print(f"Port: {HIVE_PORT}")
    print(f"Database: {HIVE_DATABASE}")

    # Check available packages
    available = check_available_packages()

    results = {}

    # Run tests based on method
    if args.method in ['all', 'impyla']:
        if available.get('impyla'):
            results['impyla'] = test_impyla()
        else:
            print("\n[SKIP] impyla not available")

    if args.method in ['all', 'beeline']:
        results['beeline'] = test_beeline()

    if args.method in ['all', 'jdbc']:
        if available.get('jaydebeapi'):
            results['jaydebeapi'] = test_jaydebeapi()
        else:
            print("\n[SKIP] jaydebeapi not available")

    if args.method in ['all', 'sqlalchemy']:
        if available.get('sqlalchemy') and available.get('pyhive'):
            results['sqlalchemy'] = test_sqlalchemy_hive()
        else:
            print("\n[SKIP] sqlalchemy+pyhive not available")

    # Custom query
    if args.query:
        print_section("Custom Query")
        print(f"Query: {args.query}")
        success, output = run_query_beeline(args.query)
        if success:
            print(f"\nResult:\n{output}")
        else:
            print(f"[ERROR] {output}")

    # Describe table
    if args.describe:
        describe_table(args.describe)

    # Summary
    print_banner("SUMMARY")
    for method, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {method}")

    if any(results.values()):
        print("\nRecommendation: Use the method that passed for your queries.")
    else:
        print("\nAll methods failed. Check:")
        print("  1. Kerberos ticket: klist")
        print("  2. Network access to Hive server")
        print("  3. Firewall rules")


if __name__ == '__main__':
    main()
