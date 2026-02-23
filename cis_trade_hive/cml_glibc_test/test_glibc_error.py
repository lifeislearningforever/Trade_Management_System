#!/usr/bin/env python3
"""
Test Script to Replicate glibc/SASL Exception in CML
====================================================

This script demonstrates the glibc compatibility issue when connecting
to HiveServer2 from CML Docker containers.

EXPECTED ERRORS IN CML:
-----------------------
1. GLIBC version mismatch:
   "version `GLIBC_2.29' not found (required by /path/to/libsasl2.so)"

2. SASL mechanism failure:
   "Could not start SASL: None of the mechanisms listed meet all required properties"

3. Kerberos/GSSAPI errors:
   "GSS failure. GSSAPI Error: Unspecified GSS failure"

SOLUTION:
---------
Use REST Proxy (app_v2.py) deployed on edge node instead of direct connection.

Usage:
------
    # Run in CML environment to replicate error
    python test_glibc_error.py --direct

    # Run with REST Proxy solution
    python test_glibc_error.py --proxy http://edge-node:5000
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hybrid_connection import (
    HybridConnectionManager,
    CMLConfig,
    attempt_direct_pyhive_connection,
    attempt_direct_impyla_connection,
    GlibcCompatibilityError,
    SASlAuthenticationError,
    RestProxyError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner(text: str):
    """Print a banner."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_section(text: str):
    """Print a section header."""
    print("\n" + "-" * 50)
    print(text)
    print("-" * 50)


def check_environment():
    """Check and print environment information."""
    print_section("Environment Check")

    # Check CML indicators
    cml_vars = ['CDSW_PROJECT', 'CDSW_DOMAIN', 'CDSW_APP_PORT', 'ML_RUNTIME_EDITION']
    is_cml = False

    for var in cml_vars:
        value = os.environ.get(var)
        if value:
            print(f"  {var}: {value}")
            is_cml = True

    if is_cml:
        print("\n  [!] Running in CML environment")
        print("  [!] Direct Hive connections will likely FAIL due to glibc issues")
    else:
        print("\n  [i] Not running in CML environment")
        print("  [i] Direct connections may work if libraries are installed")

    # Check for Docker
    if os.path.exists('/.dockerenv'):
        print("  [!] Running in Docker container")

    # Check glibc version
    try:
        import subprocess
        result = subprocess.run(['ldd', '--version'], capture_output=True, text=True)
        glibc_line = result.stdout.split('\n')[0]
        print(f"\n  glibc version: {glibc_line}")
    except:
        print("  [!] Could not determine glibc version")

    # Check Python version
    print(f"  Python version: {sys.version}")

    return is_cml


def check_dependencies():
    """Check if required Python packages are installed."""
    print_section("Dependency Check")

    packages = {
        'pyhive': 'PyHive (Hive connectivity)',
        'impala': 'impyla (Impala connectivity)',
        'sasl': 'SASL (authentication)',
        'thrift_sasl': 'thrift-sasl (SASL transport)',
        'requests': 'requests (HTTP client)',
        'thrift': 'thrift (RPC protocol)'
    }

    results = {}

    for pkg, desc in packages.items():
        try:
            if pkg == 'impala':
                import impala.dbapi
            else:
                __import__(pkg)
            print(f"  [OK] {desc}")
            results[pkg] = True
        except ImportError:
            print(f"  [MISSING] {desc}")
            results[pkg] = False

    return results


def test_direct_pyhive(host: str, port: int, database: str, auth: str):
    """Test direct PyHive connection (will fail in CML)."""
    print_section(f"Testing Direct PyHive Connection")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")
    print(f"  Auth: {auth}")

    try:
        success, message = attempt_direct_pyhive_connection(
            host=host,
            port=port,
            database=database,
            auth=auth
        )

        if success:
            print(f"\n  [SUCCESS] Direct PyHive connection works!")
            print(f"  Message: {message}")
        else:
            print(f"\n  [FAILED] Direct connection failed")
            print(f"  Error: {message}")

    except GlibcCompatibilityError as e:
        print(f"\n  [GLIBC ERROR] Expected error in CML environment!")
        print(f"  {e}")
        print("\n  >>> This is the error we are trying to replicate <<<")
        print("  >>> Solution: Use REST Proxy <<<")

    except SASlAuthenticationError as e:
        print(f"\n  [SASL ERROR] Authentication mechanism failure!")
        print(f"  {e}")
        print("\n  >>> This is the error we are trying to replicate <<<")
        print("  >>> Solution: Use REST Proxy <<<")

    except Exception as e:
        print(f"\n  [ERROR] Unexpected error: {type(e).__name__}")
        print(f"  {e}")


def test_direct_impyla(host: str, port: int, database: str, auth: str):
    """Test direct impyla connection (will fail in CML)."""
    print_section(f"Testing Direct impyla Connection")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")
    print(f"  Auth mechanism: {auth}")

    try:
        success, message = attempt_direct_impyla_connection(
            host=host,
            port=port,
            database=database,
            auth_mechanism=auth
        )

        if success:
            print(f"\n  [SUCCESS] Direct impyla connection works!")
        else:
            print(f"\n  [FAILED] Direct connection failed")
            print(f"  Error: {message}")

    except GlibcCompatibilityError as e:
        print(f"\n  [GLIBC ERROR] Expected error in CML environment!")
        print(f"  {e}")

    except SASlAuthenticationError as e:
        print(f"\n  [SASL ERROR] Authentication mechanism failure!")
        print(f"  {e}")

    except Exception as e:
        print(f"\n  [ERROR] Unexpected error: {type(e).__name__}")
        print(f"  {e}")


def test_rest_proxy(proxy_url: str, database: str):
    """Test REST Proxy connection (the solution)."""
    print_section(f"Testing REST Proxy Connection (SOLUTION)")
    print(f"  Proxy URL: {proxy_url}")
    print(f"  Database: {database}")

    try:
        config = CMLConfig(
            rest_proxy_url=proxy_url,
            hive_database=database
        )
        manager = HybridConnectionManager(config)

        # Test proxy health
        print("\n  Testing proxy health...")
        result = manager.test_proxy_connection()

        if result.get('success'):
            print(f"  [SUCCESS] REST Proxy is healthy!")
            print(f"  Version: {result.get('proxy_version')}")
            print(f"  Database: {result.get('database')}")

            # Test query execution
            print("\n  Testing query execution...")
            try:
                rows = manager.execute_query("SELECT 1 AS test_value")
                print(f"  [SUCCESS] Query executed successfully!")
                print(f"  Result: {rows}")

            except Exception as e:
                print(f"  [FAILED] Query failed: {e}")

            # Test schema fetch
            print("\n  Testing schema fetch...")
            try:
                schema = manager.get_schema("portfolio_hive")
                print(f"  [SUCCESS] Schema fetched!")
                columns = schema.get('columns', [])[:5]
                print(f"  First 5 columns: {[c['name'] for c in columns]}")

            except Exception as e:
                print(f"  [FAILED] Schema fetch failed: {e}")

        else:
            print(f"  [FAILED] Proxy health check failed")
            print(f"  Error: {result.get('error')}")

    except RestProxyError as e:
        print(f"\n  [ERROR] Cannot connect to REST Proxy!")
        print(f"  {e}")
        print("\n  Make sure app_v2.py is running on the edge node:")
        print("    gunicorn -b 0.0.0.0:5000 -w 1 --timeout 300 app_v2:app")

    except Exception as e:
        print(f"\n  [ERROR] Unexpected error: {type(e).__name__}")
        print(f"  {e}")


def test_crud_operations(proxy_url: str, database: str, table: str):
    """Test CRUD operations via REST Proxy."""
    print_section(f"Testing CRUD Operations via REST Proxy")
    print(f"  Table: {database}.{table}")

    try:
        config = CMLConfig(
            rest_proxy_url=proxy_url,
            hive_database=database
        )
        manager = HybridConnectionManager(config)

        # Generate unique test ID
        test_id = f"TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Test INSERT
        print(f"\n  1. Testing INSERT (name={test_id})...")
        try:
            result = manager.insert(table, {
                'name': test_id,
                'description': 'Test portfolio from glibc test',
                'status': 'DRAFT',
                'created_by': 'glibc_test',
                'created_at': 'now'
            })
            print(f"     [SUCCESS] INSERT completed in {result.get('elapsed_ms')}ms")
        except Exception as e:
            print(f"     [FAILED] INSERT failed: {e}")
            return

        # Test SELECT
        print(f"\n  2. Testing SELECT...")
        try:
            rows = manager.execute_query(
                f"SELECT * FROM {table} WHERE name = '{test_id}'"
            )
            print(f"     [SUCCESS] Found {len(rows)} row(s)")
            if rows:
                print(f"     Data: {rows[0]}")
        except Exception as e:
            print(f"     [FAILED] SELECT failed: {e}")

        # Test UPDATE
        print(f"\n  3. Testing UPDATE...")
        try:
            result = manager.update(
                table,
                where={'name': test_id},
                data={
                    'description': 'Updated by glibc test',
                    'status': 'ACTIVE',
                    'updated_by': 'glibc_test',
                    'updated_at': 'now'
                }
            )
            print(f"     [SUCCESS] UPDATE completed in {result.get('elapsed_ms')}ms")
        except Exception as e:
            print(f"     [FAILED] UPDATE failed: {e}")

        # Verify UPDATE
        print(f"\n  4. Verifying UPDATE...")
        try:
            rows = manager.execute_query(
                f"SELECT status, description FROM {table} WHERE name = '{test_id}'"
            )
            if rows:
                print(f"     Status: {rows[0].get('status')}")
                print(f"     Description: {rows[0].get('description')}")
        except Exception as e:
            print(f"     [FAILED] Verify failed: {e}")

        # Test SOFT DELETE
        print(f"\n  5. Testing SOFT DELETE...")
        try:
            result = manager.delete(
                table,
                where={'name': test_id},
                soft_delete=True
            )
            print(f"     [SUCCESS] SOFT DELETE completed in {result.get('elapsed_ms')}ms")
        except Exception as e:
            print(f"     [FAILED] DELETE failed: {e}")

        print(f"\n  [COMPLETE] All CRUD operations tested!")

    except Exception as e:
        print(f"\n  [ERROR] Test failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Test glibc/SASL error replication and REST Proxy solution',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test direct connection (will fail in CML)
  python test_glibc_error.py --direct --host lxmrwtsgv0m1.sg.uobnet.com

  # Test REST Proxy solution
  python test_glibc_error.py --proxy http://edge-node:5000

  # Full test with CRUD operations
  python test_glibc_error.py --proxy http://edge-node:5000 --crud

  # Test everything
  python test_glibc_error.py --all --host lxmrwtsgv0m1.sg.uobnet.com --proxy http://edge-node:5000
        """
    )

    parser.add_argument('--host', default='lxmrwtsgv0m1.sg.uobnet.com',
                        help='HiveServer2 host for direct connection test')
    parser.add_argument('--port', type=int, default=10000,
                        help='HiveServer2 port (default: 10000)')
    parser.add_argument('--impala-port', type=int, default=21050,
                        help='Impala port (default: 21050)')
    parser.add_argument('--database', default='mrw_ima',
                        help='Database name (default: mrw_ima)')
    parser.add_argument('--auth', default='KERBEROS',
                        choices=['KERBEROS', 'GSSAPI', 'LDAP', 'NOSASL'],
                        help='Authentication method')

    parser.add_argument('--direct', action='store_true',
                        help='Test direct PyHive/impyla connection (will fail in CML)')
    parser.add_argument('--proxy', type=str,
                        help='REST Proxy URL to test (e.g., http://edge-node:5000)')
    parser.add_argument('--crud', action='store_true',
                        help='Test CRUD operations via REST Proxy')
    parser.add_argument('--table', default='portfolio_hive',
                        help='Table for CRUD test (default: portfolio_hive)')

    parser.add_argument('--all', action='store_true',
                        help='Run all tests')

    args = parser.parse_args()

    # Print banner
    print_banner("GLIBC/SASL Error Replication Test for CML")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Check environment
    is_cml = check_environment()

    # Check dependencies
    deps = check_dependencies()

    # Run selected tests
    if args.all or args.direct:
        if deps.get('pyhive'):
            test_direct_pyhive(args.host, args.port, args.database, args.auth)
        else:
            print("\n[SKIP] PyHive not installed, skipping direct PyHive test")

        if deps.get('impala'):
            test_direct_impyla(args.host, args.impala_port, args.database,
                              'GSSAPI' if args.auth == 'KERBEROS' else args.auth)
        else:
            print("\n[SKIP] impyla not installed, skipping direct impyla test")

    if args.all or args.proxy:
        proxy_url = args.proxy or os.environ.get('HIVE_REST_PROXY_URL', 'http://localhost:5000')
        test_rest_proxy(proxy_url, args.database)

        if args.crud:
            test_crud_operations(proxy_url, args.database, args.table)

    if not (args.all or args.direct or args.proxy):
        print("\n[INFO] No tests specified. Use --help for options.")
        print("\nQuick start:")
        print("  # Replicate glibc error (in CML)")
        print("  python test_glibc_error.py --direct")
        print("")
        print("  # Test REST Proxy solution")
        print("  python test_glibc_error.py --proxy http://edge-node:5000")

    print_banner("Test Complete")


if __name__ == '__main__':
    main()
