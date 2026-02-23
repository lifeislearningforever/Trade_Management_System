#!/usr/bin/env python3
"""
Hive Connection Test using JDBC (JayDeBeApi)
=============================================

This script connects to Hive using JDBC via JayDeBeApi - a Python DB-API 2.0
compliant interface to databases using JDBC drivers.

Benefits over subprocess/beeline:
- Standard Python DB-API (cursor, fetchall, etc.)
- Connection pooling possible
- Better error handling
- No shell command overhead

Prerequisites:
    pip install JayDeBeApi JPype1

JDBC URL (from your working beeline):
    jdbc:hive2://lxmrwtsgv0m1.sg.uobnet.com:2181,...
    with ZooKeeper service discovery, SSL, Kerberos

Usage:
    python test_hive_jdbc.py
    python test_hive_jdbc.py --query "SELECT * FROM cis_trade LIMIT 10"
    python test_hive_jdbc.py --describe cis_trade
"""

import os
import sys
import subprocess
import time
import argparse
from typing import List, Tuple, Any, Optional


# =============================================================================
# Configuration - Match your beeline settings
# =============================================================================

# ZooKeeper hosts for HiveServer2 discovery
ZOOKEEPER_HOSTS = (
    "lxmrwtsgv0m1.sg.uobnet.com:2181,"
    "lxmrwtsgv0m2.sg.uobnet.com:2181,"
    "lxmrwtsgv0w1.sg.uobnet.com:2181"
)

# Hive settings
HIVE_DATABASE = "mrw_ima"
HIVE_PRINCIPAL = "hive/_HOST@TST.UOBNET.COM"

# SSL settings
SSL_TRUSTSTORE = "/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks"
SSL_TRUSTSTORE_TYPE = "jks"

# ZooKeeper namespace
ZK_NAMESPACE = "hiveserver2"

# Build JDBC URL (same as beeline)
JDBC_URL = (
    f"jdbc:hive2://{ZOOKEEPER_HOSTS}/default;"
    f"principal={HIVE_PRINCIPAL};"
    f"serviceDiscoveryMode=zooKeeper;"
    f"zookeeperNamespace={ZK_NAMESPACE};"
    f"ssl=true;"
    f"sslTrustStore={SSL_TRUSTSTORE};"
    f"trustStoreType={SSL_TRUSTSTORE_TYPE}"
)

# Hive JDBC Driver
JDBC_DRIVER_CLASS = "org.apache.hive.jdbc.HiveDriver"

# Possible locations for Hive JDBC JAR
JDBC_JAR_PATHS = [
    "/opt/cloudera/parcels/CDH/lib/hive/lib/hive-jdbc-standalone.jar",
    "/opt/cloudera/parcels/CDH/jars/hive-jdbc-standalone.jar",
    "/usr/lib/hive/lib/hive-jdbc-standalone.jar",
    "/opt/cloudera/parcels/CDH/lib/hive/lib/hive-jdbc.jar",
    # Add more paths as needed
]


def print_banner(text: str):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_section(text: str):
    print("\n" + "-" * 50)
    print(text)
    print("-" * 50)


def check_kerberos() -> bool:
    """Check if Kerberos ticket is valid."""
    print_section("Checking Kerberos Ticket")

    try:
        result = subprocess.run(["klist", "-s"], capture_output=True)
        if result.returncode == 0:
            # Show ticket details
            klist = subprocess.run(["klist"], capture_output=True, text=True)
            for line in klist.stdout.split('\n')[:5]:
                if line.strip():
                    print(f"  {line}")
            print("\n  [OK] Valid Kerberos ticket")
            return True
        else:
            print("  [ERROR] No valid Kerberos ticket")
            print("  Run: kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM")
            return False
    except FileNotFoundError:
        print("  [WARNING] klist not found")
        return True  # Assume it might work


def find_jdbc_jar() -> Optional[str]:
    """Find Hive JDBC JAR file."""
    print_section("Finding Hive JDBC JAR")

    for path in JDBC_JAR_PATHS:
        if os.path.exists(path):
            print(f"  [OK] Found: {path}")
            return path
        else:
            print(f"  [--] Not found: {path}")

    # Try glob for wildcards
    import glob
    for pattern in ["/opt/cloudera/parcels/CDH/lib/hive/lib/hive-jdbc*.jar",
                    "/opt/cloudera/parcels/CDH/jars/hive-jdbc*.jar"]:
        matches = glob.glob(pattern)
        if matches:
            print(f"  [OK] Found via glob: {matches[0]}")
            return matches[0]

    print("  [ERROR] No Hive JDBC JAR found!")
    print("  Specify path with: --jar /path/to/hive-jdbc.jar")
    return None


def check_dependencies() -> bool:
    """Check if required Python packages are installed."""
    print_section("Checking Python Dependencies")

    required = {
        'jaydebeapi': 'JayDeBeApi',
        'jpype': 'JPype1'
    }

    all_ok = True
    for module, package in required.items():
        try:
            __import__(module)
            print(f"  [OK] {package}")
        except ImportError:
            print(f"  [MISSING] {package}")
            all_ok = False

    if not all_ok:
        print("\n  Install: pip install JayDeBeApi JPype1")

    return all_ok


class HiveJDBCConnection:
    """
    Hive connection using JDBC via JayDeBeApi.

    Usage:
        with HiveJDBCConnection(jar_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            print(cursor.fetchall())
    """

    def __init__(self, jdbc_jar: str, jdbc_url: str = None):
        self.jdbc_jar = jdbc_jar
        self.jdbc_url = jdbc_url or JDBC_URL
        self.connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def connect(self):
        """Establish JDBC connection."""
        import jaydebeapi

        print(f"\n  Connecting via JDBC...")
        print(f"  Driver: {JDBC_DRIVER_CLASS}")
        print(f"  JAR: {self.jdbc_jar}")
        print(f"  URL: {self.jdbc_url[:60]}...")

        start = time.time()

        self.connection = jaydebeapi.connect(
            JDBC_DRIVER_CLASS,
            self.jdbc_url,
            ['', ''],  # Empty username/password for Kerberos
            self.jdbc_jar
        )

        elapsed = time.time() - start
        print(f"  [OK] Connected in {elapsed:.2f}s")

        return self.connection

    def cursor(self):
        """Get database cursor."""
        if not self.connection:
            self.connect()
        return self.connection.cursor()

    def execute(self, sql: str) -> Tuple[List[str], List[Tuple]]:
        """Execute SQL and return (columns, rows)."""
        cursor = self.cursor()

        start = time.time()
        cursor.execute(sql)
        elapsed = time.time() - start

        # Get column names
        columns = []
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]

        # Fetch results
        rows = cursor.fetchall()

        print(f"  Query completed in {elapsed*1000:.1f}ms, {len(rows)} rows")

        cursor.close()
        return columns, rows

    def close(self):
        """Close connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            print("  Connection closed")


def test_jdbc_connection(jdbc_jar: str):
    """Test JDBC connection with various queries."""
    print_banner("JDBC CONNECTION TEST")

    try:
        with HiveJDBCConnection(jdbc_jar) as conn:

            # Test 1: Simple query
            print_section("Test 1: SELECT 1")
            cols, rows = conn.execute("SELECT 1 AS test")
            print(f"  Columns: {cols}")
            print(f"  Result: {rows}")

            # Test 2: Show databases
            print_section("Test 2: SHOW DATABASES")
            cols, rows = conn.execute("SHOW DATABASES")
            databases = [row[0] for row in rows]
            print(f"  Databases: {databases[:10]}{'...' if len(databases) > 10 else ''}")

            # Test 3: Use database and show tables
            print_section(f"Test 3: SHOW TABLES IN {HIVE_DATABASE}")
            cols, rows = conn.execute(f"SHOW TABLES IN {HIVE_DATABASE}")
            tables = [row[0] for row in rows]
            print(f"  Tables: {tables[:15]}{'...' if len(tables) > 15 else ''}")

            # Test 4: Describe a table
            if tables:
                table = 'cis_trade' if 'cis_trade' in tables else tables[0]
                print_section(f"Test 4: DESCRIBE {HIVE_DATABASE}.{table}")
                cols, rows = conn.execute(f"DESCRIBE {HIVE_DATABASE}.{table}")
                print(f"  Columns in {table}:")
                for row in rows[:10]:
                    print(f"    {row[0]}: {row[1]}")
                if len(rows) > 10:
                    print(f"    ... and {len(rows)-10} more columns")

            print_banner("ALL TESTS PASSED!")
            return True

    except ImportError as e:
        print(f"\n  [ERROR] Import failed: {e}")
        print("  Install: pip install JayDeBeApi JPype1")
        return False
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_custom_query(jdbc_jar: str, query: str, database: str = None):
    """Run a custom query."""
    print_banner("CUSTOM QUERY")
    print(f"Query: {query}")

    try:
        with HiveJDBCConnection(jdbc_jar) as conn:
            # Use database if specified
            if database:
                conn.execute(f"USE {database}")

            cols, rows = conn.execute(query)

            # Print results
            print(f"\nColumns: {cols}")
            print(f"\nResults ({len(rows)} rows):")

            for i, row in enumerate(rows[:20]):
                print(f"  {i+1}. {row}")

            if len(rows) > 20:
                print(f"  ... and {len(rows)-20} more rows")

            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


def describe_table(jdbc_jar: str, table: str, database: str = None):
    """Describe a table and output columns in Python format."""
    db = database or HIVE_DATABASE

    print_banner(f"DESCRIBE {db}.{table}")

    try:
        with HiveJDBCConnection(jdbc_jar) as conn:
            cols, rows = conn.execute(f"DESCRIBE {db}.{table}")

            print(f"\nTable: {db}.{table}")
            print(f"Total columns: {len(rows)}")
            print("\n" + "-"*60)
            print(f"{'Column Name':<35} {'Data Type':<25}")
            print("-"*60)

            column_names = []
            for row in rows:
                col_name = row[0]
                col_type = row[1] if len(row) > 1 else 'unknown'

                # Skip partition info and comments
                if col_name.startswith('#') or not col_name.strip():
                    continue

                print(f"{col_name:<35} {col_type:<25}")
                column_names.append(col_name)

            # Output as Python list
            print("\n" + "-"*60)
            print("Python list format:")
            print("-"*60)
            print(f"columns = [")
            for name in column_names:
                print(f"    '{name}',")
            print("]")

            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Test Hive Connection using JDBC',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--jar', type=str, help='Path to Hive JDBC JAR')
    parser.add_argument('--query', '-q', type=str, help='Custom SQL query')
    parser.add_argument('--describe', '-d', type=str, help='Describe a table')
    parser.add_argument('--database', type=str, default=HIVE_DATABASE,
                        help=f'Database (default: {HIVE_DATABASE})')
    parser.add_argument('--skip-checks', action='store_true',
                        help='Skip Kerberos and dependency checks')

    args = parser.parse_args()

    print_banner("HIVE JDBC CONNECTION TEST")
    print(f"JDBC URL: {JDBC_URL[:70]}...")

    # Run checks
    if not args.skip_checks:
        if not check_kerberos():
            return 1

        if not check_dependencies():
            return 1

    # Find JDBC JAR
    jdbc_jar = args.jar or find_jdbc_jar()
    if not jdbc_jar:
        return 1

    # Run appropriate test
    if args.describe:
        success = describe_table(jdbc_jar, args.describe, args.database)
    elif args.query:
        success = run_custom_query(jdbc_jar, args.query, args.database)
    else:
        success = test_jdbc_connection(jdbc_jar)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
