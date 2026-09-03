#!/usr/bin/env python3
"""
Standalone script to create Hive database 'cis'
This script doesn't require Django to be installed.

Usage:
    python create_db.py

Requirements:
    pip install pyhive sasl thrift thrift-sasl
"""

import sys

print("=" * 60)
print("Creating Hive Database: cis")
print("=" * 60)
print()

# Check if PyHive is installed
try:
    from pyhive import hive
    print("✓ PyHive is installed")
except ImportError:
    print("✗ PyHive is not installed")
    print("\nPlease install required packages:")
    print("  pip install pyhive sasl thrift thrift-sasl")
    sys.exit(1)

# Configuration
HIVE_HOST = 'localhost'
HIVE_PORT = 10000
HIVE_AUTH = 'NOSASL'
DATABASE_NAME = 'cis'

print(f"\nConfiguration:")
print(f"  Host: {HIVE_HOST}")
print(f"  Port: {HIVE_PORT}")
print(f"  Auth: {HIVE_AUTH}")
print(f"  Database: {DATABASE_NAME}")
print()

try:
    # Connect to Hive (using 'default' database)
    print("Connecting to Hive...")
    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        auth=HIVE_AUTH,
        database='default'
    )
    print("✓ Connected to Hive successfully!")
    print()

    cursor = conn.cursor()

    # Create database
    print(f"Creating database '{DATABASE_NAME}'...")
    create_db_query = f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}"
    print(f"Executing: {create_db_query}")
    cursor.execute(create_db_query)
    print(f"✓ Database '{DATABASE_NAME}' created successfully!")
    print()

    # Show all databases
    print("Fetching list of databases...")
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()

    print(f"\nAvailable databases ({len(databases)}):")
    for db in databases:
        db_name = db[0]
        marker = '→' if db_name == DATABASE_NAME else ' '
        print(f"  {marker} {db_name}")

    # Verify our database exists
    db_names = [db[0] for db in databases]
    if DATABASE_NAME in db_names:
        print()
        print("=" * 60)
        print(f"✓ SUCCESS: Database '{DATABASE_NAME}' is ready to use!")
        print("=" * 60)
    else:
        print()
        print(f"⚠ WARNING: Database '{DATABASE_NAME}' was created but not found in database list")

    # Close connection
    cursor.close()
    conn.close()
    print("\n✓ Connection closed")

except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")
    print("\nTroubleshooting:")
    print("1. Make sure HiveServer2 is running:")
    print("   jps | grep HiveServer2")
    print()
    print("2. Start HiveServer2 if not running:")
    print("   hive --service hiveserver2 &")
    print()
    print("3. Check if port 10000 is open:")
    print("   netstat -an | grep 10000")
    print()
    print("4. Try using beeline instead:")
    print(f"   beeline -u jdbc:hive2://{HIVE_HOST}:{HIVE_PORT}")
    print(f"   CREATE DATABASE IF NOT EXISTS {DATABASE_NAME};")
    sys.exit(1)

print()
print("Next steps:")
print("1. Test connection: python manage.py test_hive")
print("2. Create tables using DDL scripts in sql/ddl/")
print()
