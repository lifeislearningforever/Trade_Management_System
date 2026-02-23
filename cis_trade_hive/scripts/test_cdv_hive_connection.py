#!/usr/bin/env python3
"""
Test Hive Connection - Matching Cloudera Data Visualization (CDV) Settings
===========================================================================

This script tests Hive connectivity using the same settings as CDV 7.2.9:
- Host: lxmrwtsgv0m2.sg.uobnet.com
- Port: 10000
- Connection mode: Binary
- Socket type: SSL
- Authentication: Kerberos
- Kerberos service name: hive

Prerequisites:
--------------
1. Valid Kerberos ticket:
   kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM

2. Install dependencies:
   pip install pyhive thrift thrift-sasl sasl

Usage:
------
    python test_cdv_hive_connection.py
    python test_cdv_hive_connection.py --database mrw_ima
    python test_cdv_hive_connection.py --query "SHOW TABLES"
"""

import os
import sys
import argparse
import subprocess
import ssl
import time
from datetime import datetime


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


def check_kerberos_ticket():
    """Check if valid Kerberos ticket exists."""
    print_section("Checking Kerberos Ticket")

    try:
        result = subprocess.run(['klist', '-s'], capture_output=True)
        if result.returncode == 0:
            print("  [OK] Valid Kerberos ticket found")

            # Show ticket details
            klist = subprocess.run(['klist'], capture_output=True, text=True)
            for line in klist.stdout.split('\n')[:8]:
                if line.strip():
                    print(f"       {line}")
            return True
        else:
            print("  [ERROR] No valid Kerberos ticket")
            print("  Run: kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM")
            return False
    except FileNotFoundError:
        print("  [WARNING] klist command not found")
        return None


def check_dependencies():
    """Check if required Python packages are installed."""
    print_section("Checking Python Dependencies")

    packages = {
        'pyhive': 'PyHive',
        'thrift': 'Thrift',
        'thrift_sasl': 'Thrift-SASL',
        'sasl': 'SASL',
        'ssl': 'SSL (built-in)'
    }

    all_ok = True
    for pkg, name in packages.items():
        try:
            __import__(pkg)
            print(f"  [OK] {name}")
        except ImportError:
            print(f"  [MISSING] {name}")
            all_ok = False

    if not all_ok:
        print("\n  Install missing packages:")
        print("  pip install pyhive thrift thrift-sasl sasl")

    return all_ok


def test_pyhive_connection(
    host: str,
    port: int,
    database: str,
    auth: str = 'KERBEROS',
    kerberos_service_name: str = 'hive',
    use_ssl: bool = True
):
    """
    Test PyHive connection with CDV-matching settings.

    CDV Settings:
    - Connection mode: Binary
    - Socket type: SSL
    - Authentication: Kerberos
    """
    print_section(f"Testing PyHive Connection")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Database: {database}")
    print(f"  Auth: {auth}")
    print(f"  SSL: {use_ssl}")
    print(f"  Kerberos Service: {kerberos_service_name}")

    try:
        from pyhive import hive

        # Connection parameters matching CDV
        conn_params = {
            'host': host,
            'port': port,
            'database': database,
            'auth': auth,
            'kerberos_service_name': kerberos_service_name,
        }

        # Add SSL configuration
        if use_ssl:
            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE  # For testing; use CERT_REQUIRED in production

            # Note: PyHive SSL support varies by version
            # Some versions use 'ssl' parameter, others use 'thrift_transport_protocol'
            conn_params['configuration'] = {
                'hive.server2.use.SSL': 'true'
            }

        print("\n  Connecting...")
        start = time.time()

        conn = hive.Connection(**conn_params)
        elapsed = time.time() - start

        print(f"  [OK] Connected in {elapsed:.2f}s")

        # Test query
        print("\n  Running test query: SELECT 1")
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS test")
        result = cursor.fetchone()
        print(f"  [OK] Result: {result}")

        # Show databases
        print("\n  Running: SHOW DATABASES")
        cursor.execute("SHOW DATABASES")
        databases = [row[0] for row in cursor.fetchall()]
        print(f"  [OK] Found {len(databases)} databases")
        print(f"       {', '.join(databases[:10])}{'...' if len(databases) > 10 else ''}")

        cursor.close()
        conn.close()

        print("\n  [SUCCESS] PyHive connection works!")
        return True

    except Exception as e:
        print(f"\n  [ERROR] Connection failed: {e}")

        # Suggest fixes based on error
        error_str = str(e)
        if 'SASL' in error_str:
            print("\n  Troubleshooting SASL errors:")
            print("  1. Check Kerberos ticket: klist")
            print("  2. Renew ticket: kinit -kt /path/to/keytab principal@REALM")
            print("  3. Install SASL: pip install sasl thrift-sasl")
        elif 'SSL' in error_str or 'certificate' in error_str.lower():
            print("\n  Troubleshooting SSL errors:")
            print("  1. Verify SSL certificate path")
            print("  2. Try with SSL verification disabled for testing")
        elif 'GLIBC' in error_str:
            print("\n  GLIBC Error - Use REST Proxy instead:")
            print("  This error occurs in CML Docker containers")
            print("  Solution: Deploy app_v2.py on edge node")

        return False


def test_thrift_connection(
    host: str,
    port: int,
    use_ssl: bool = True
):
    """
    Test low-level Thrift connection with SSL.
    This is what CDV uses internally.
    """
    print_section("Testing Thrift Connection")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  SSL: {use_ssl}")

    try:
        from thrift.transport import TSocket, TTransport
        from thrift.protocol import TBinaryProtocol

        # Create socket
        socket = TSocket.TSocket(host, port)
        socket.setTimeout(60000)  # 60 seconds timeout

        if use_ssl:
            # Wrap with SSL
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Note: TSSLSocket handling varies
            try:
                from thrift.transport import TSSLSocket
                socket = TSSLSocket.TSSLSocket(host, port, ssl_context=ssl_context)
                socket.setTimeout(60000)
            except ImportError:
                print("  [WARNING] TSSLSocket not available, using plain socket")

        # Create transport
        transport = TTransport.TBufferedTransport(socket)

        # Create protocol
        protocol = TBinaryProtocol.TBinaryProtocol(transport)

        print("  Opening connection...")
        transport.open()

        print("  [OK] Thrift transport connected")

        transport.close()
        return True

    except Exception as e:
        print(f"  [ERROR] Thrift connection failed: {e}")
        return False


def test_beeline_connection(
    host: str,
    port: int,
    database: str
):
    """
    Test connection using beeline CLI.
    This is the most reliable method as it matches what CDV does.
    """
    print_section("Testing Beeline Connection")

    # Build JDBC URL matching CDV settings
    jdbc_url = f"jdbc:hive2://{host}:{port}/{database};ssl=true;principal=hive/_HOST@TST.UOBNET.COM"

    print(f"  JDBC URL: {jdbc_url}")

    cmd = f'beeline -u "{jdbc_url}" -e "SELECT 1 AS test" --silent=true'

    print(f"  Running beeline...")

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
            print(f"  [OK] Beeline connected in {elapsed:.2f}s")
            print(f"  Output: {result.stdout[:200]}")
            return True
        else:
            print(f"  [ERROR] Beeline failed")
            print(f"  STDERR: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        print("  [ERROR] Beeline timed out after 120s")
        return False
    except FileNotFoundError:
        print("  [ERROR] beeline command not found")
        return False


def run_custom_query(
    host: str,
    port: int,
    database: str,
    query: str
):
    """Run a custom query via PyHive."""
    print_section(f"Running Custom Query")
    print(f"  Query: {query}")

    try:
        from pyhive import hive

        conn = hive.Connection(
            host=host,
            port=port,
            database=database,
            auth='KERBEROS',
            kerberos_service_name='hive'
        )

        cursor = conn.cursor()

        start = time.time()
        cursor.execute(query)
        elapsed = time.time() - start

        # Fetch results
        if query.strip().upper().startswith('SELECT') or \
           query.strip().upper().startswith('SHOW') or \
           query.strip().upper().startswith('DESCRIBE'):
            results = cursor.fetchall()

            print(f"\n  [OK] Query completed in {elapsed:.2f}s")
            print(f"  Rows: {len(results)}")

            if results:
                # Print header
                if cursor.description:
                    headers = [desc[0] for desc in cursor.description]
                    print(f"\n  Columns: {headers}")

                # Print first 10 rows
                print("\n  Results (first 10 rows):")
                for i, row in enumerate(results[:10]):
                    print(f"    {i+1}. {row}")

                if len(results) > 10:
                    print(f"    ... and {len(results) - 10} more rows")
        else:
            print(f"\n  [OK] Query executed in {elapsed:.2f}s")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"\n  [ERROR] Query failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Test Hive Connection (CDV Settings)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # CDV connection settings
    parser.add_argument('--host', default='lxmrwtsgv0m2.sg.uobnet.com',
                        help='HiveServer2 host (default: lxmrwtsgv0m2.sg.uobnet.com)')
    parser.add_argument('--port', type=int, default=10000,
                        help='HiveServer2 port (default: 10000)')
    parser.add_argument('--database', default='mrw_ima',
                        help='Database name (default: mrw_ima)')
    parser.add_argument('--auth', default='KERBEROS',
                        choices=['KERBEROS', 'NOSASL', 'LDAP'],
                        help='Authentication mode (default: KERBEROS)')
    parser.add_argument('--ssl', action='store_true', default=True,
                        help='Use SSL (default: True)')
    parser.add_argument('--no-ssl', action='store_true',
                        help='Disable SSL')

    # Test options
    parser.add_argument('--query', '-q', type=str,
                        help='Custom SQL query to run')
    parser.add_argument('--beeline', action='store_true',
                        help='Also test beeline connection')
    parser.add_argument('--thrift', action='store_true',
                        help='Also test low-level Thrift connection')
    parser.add_argument('--all', action='store_true',
                        help='Run all connection tests')

    args = parser.parse_args()

    use_ssl = args.ssl and not args.no_ssl

    # Print banner
    print_banner("HIVE CONNECTION TEST (CDV 7.2.9 Settings)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"\nCDV Settings:")
    print(f"  Connection mode: Binary")
    print(f"  Socket type: {'SSL' if use_ssl else 'Plain'}")
    print(f"  Authentication: {args.auth}")

    # Check Kerberos ticket
    if args.auth == 'KERBEROS':
        check_kerberos_ticket()

    # Check dependencies
    deps_ok = check_dependencies()

    if not deps_ok:
        print("\n[WARNING] Some dependencies missing, tests may fail")

    # Run tests
    results = {}

    # PyHive test
    results['pyhive'] = test_pyhive_connection(
        host=args.host,
        port=args.port,
        database=args.database,
        auth=args.auth,
        use_ssl=use_ssl
    )

    # Thrift test
    if args.thrift or args.all:
        results['thrift'] = test_thrift_connection(
            host=args.host,
            port=args.port,
            use_ssl=use_ssl
        )

    # Beeline test
    if args.beeline or args.all:
        results['beeline'] = test_beeline_connection(
            host=args.host,
            port=args.port,
            database=args.database
        )

    # Custom query
    if args.query:
        results['custom_query'] = run_custom_query(
            host=args.host,
            port=args.port,
            database=args.database,
            query=args.query
        )

    # Summary
    print_banner("TEST SUMMARY")
    for test, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test}")

    all_passed = all(results.values())
    print(f"\nOverall: {'SUCCESS' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
