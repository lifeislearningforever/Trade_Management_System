#!/usr/bin/env python3
"""
Script to load ACL data from Excel into Hive tables

Usage:
    python load_acl_data.py
"""

import pandas as pd
from pyhive import hive
from datetime import datetime
import sys

# Configuration
HIVE_HOST = 'localhost'
HIVE_PORT = 10000
HIVE_DB = 'cis'
EXCEL_FILE = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/kudu_ddl/ACL_TABLES.xlsx'

print("=" * 70)
print("Loading ACL Data from Excel to Hive")
print("=" * 70)
print()

try:
    # Read Excel file
    print(f"Reading Excel file: {EXCEL_FILE}")
    xl = pd.ExcelFile(EXCEL_FILE)
    print(f"✓ Found {len(xl.sheet_names)} sheets")
    print()

    # Connect to Hive
    print(f"Connecting to Hive at {HIVE_HOST}:{HIVE_PORT}, database: {HIVE_DB}")
    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=HIVE_DB,
        auth='NOSASL'
    )
    cursor = conn.cursor()
    print("✓ Connected to Hive")
    print()

    # Load data for each sheet
    total_rows = 0

    # 1. Load cis_user_group (must load first due to foreign keys)
    print("-" * 70)
    print("Loading: cis_user_group")
    print("-" * 70)
    df = pd.read_excel(xl, sheet_name='cis_user_group')
    for _, row in df.iterrows():
        # Handle NaN values
        description = 'NULL' if pd.isna(row['description']) else f"'{row['description']}'"

        sql = f"""
        INSERT INTO cis_user_group VALUES (
            {row['cis_user_group_id']},
            '{row['name']}',
            '{row['entity']}',
            {description},
            {str(row['is_deleted']).lower()},
            CAST('{row['updated_on']}' AS TIMESTAMP),
            '{row['updated_by']}'
        )
        """
        cursor.execute(sql)
        total_rows += 1
    print(f"✓ Loaded {len(df)} rows into cis_user_group")
    print()

    # 2. Load cis_user
    print("-" * 70)
    print("Loading: cis_user")
    print("-" * 70)
    df = pd.read_excel(xl, sheet_name='cis_user')
    for _, row in df.iterrows():
        sql = f"""
        INSERT INTO cis_user VALUES (
            {row['cis_user_id']},
            '{row['login']}',
            '{row['name']}',
            '{row['entity']}',
            '{row['email']}',
            '{row['domain']}',
            {row['cis_user_group_id']},
            {str(row['is_deleted']).lower()},
            {str(row['enabled']).lower()},
            CAST('{row['last_login']}' AS TIMESTAMP),
            CAST('{row['created_on']}' AS TIMESTAMP),
            '{row['created_by']}',
            CAST('{row['updated_on']}' AS TIMESTAMP),
            '{row['updated_by']}'
        )
        """
        cursor.execute(sql)
        total_rows += 1
    print(f"✓ Loaded {len(df)} rows into cis_user")
    print()

    # 3. Load cis_permission
    print("-" * 70)
    print("Loading: cis_permission")
    print("-" * 70)
    df = pd.read_excel(xl, sheet_name='cis_permission')
    for _, row in df.iterrows():
        description = 'NULL' if pd.isna(row['description']) else f"'{row['description']}'"

        sql = f"""
        INSERT INTO cis_permission VALUES (
            {row['cis_permission_id']},
            '{row['permission']}',
            {description},
            {str(row['is_deleted']).lower()},
            CAST('{row['updated_on']}' AS TIMESTAMP),
            '{row['updated_by']}'
        )
        """
        cursor.execute(sql)
        total_rows += 1
    print(f"✓ Loaded {len(df)} rows into cis_permission")
    print()

    # 4. Load cis_group_permissions
    print("-" * 70)
    print("Loading: cis_group_permissions")
    print("-" * 70)
    df = pd.read_excel(xl, sheet_name='cis_group_permissions')
    for _, row in df.iterrows():
        sql = f"""
        INSERT INTO cis_group_permissions VALUES (
            {row['cis_group_permissions_id']},
            {row['cis_user_group_id']},
            '{row['permission']}',
            '{row['read_write']}',
            {str(row['is_deleted']).lower()},
            CAST('{row['updated_on']}' AS TIMESTAMP),
            '{row['updated_by']}'
        )
        """
        cursor.execute(sql)
        total_rows += 1
    print(f"✓ Loaded {len(df)} rows into cis_group_permissions")
    print()

    # Close connection
    cursor.close()
    conn.close()

    print("=" * 70)
    print(f"✓ SUCCESS! Loaded {total_rows} total rows into Hive")
    print("=" * 70)
    print()
    print("Tables loaded:")
    print("  - cis_user_group: 1 row")
    print("  - cis_user: 3 rows")
    print("  - cis_permission: 7 rows")
    print("  - cis_group_permissions: 30 rows")
    print()

except ImportError as e:
    print(f"✗ ERROR: Missing required Python packages")
    print(f"  {e}")
    print()
    print("Install required packages:")
    print("  pip install pandas openpyxl pyhive")
    sys.exit(1)

except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
