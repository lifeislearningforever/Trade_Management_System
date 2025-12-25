#!/usr/bin/env python3
"""
Generate SQL INSERT statements from ACL Excel data

Usage:
    python generate_acl_inserts.py > acl_data_inserts.sql
"""

import pandas as pd
import sys

EXCEL_FILE = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/kudu_ddl/ACL_TABLES.xlsx'

print("-- ================================================================")
print("-- ACL Data INSERT Statements")
print("-- Generated from ACL_TABLES.xlsx")
print("-- Database: cis")
print("-- ================================================================")
print()
print("USE cis;")
print()

try:
    xl = pd.ExcelFile(EXCEL_FILE)

    # 1. Load cis_user_group (must load first due to foreign keys)
    print("-- ================================================================")
    print("-- Table: cis_user_group (1 row)")
    print("-- ================================================================")
    df = pd.read_excel(xl, sheet_name='cis_user_group')
    for _, row in df.iterrows():
        description = 'NULL' if pd.isna(row['description']) else f"'{row['description']}'"

        print(f"""INSERT INTO cis_user_group VALUES (
    {row['cis_user_group_id']},
    '{row['name']}',
    '{row['entity']}',
    {description},
    {str(row['is_deleted']).lower()},
    CAST('{row['updated_on']}' AS TIMESTAMP),
    '{row['updated_by']}'
);""")
    print()

    # 2. Load cis_user
    print("-- ================================================================")
    print("-- Table: cis_user (3 rows)")
    print("-- ================================================================")
    df = pd.read_excel(xl, sheet_name='cis_user')
    for _, row in df.iterrows():
        print(f"""INSERT INTO cis_user VALUES (
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
);""")
    print()

    # 3. Load cis_permission
    print("-- ================================================================")
    print("-- Table: cis_permission (7 rows)")
    print("-- ================================================================")
    df = pd.read_excel(xl, sheet_name='cis_permission')
    for _, row in df.iterrows():
        description = 'NULL' if pd.isna(row['description']) else f"'{row['description']}'"

        print(f"""INSERT INTO cis_permission VALUES (
    {row['cis_permission_id']},
    '{row['permission']}',
    {description},
    {str(row['is_deleted']).lower()},
    CAST('{row['updated_on']}' AS TIMESTAMP),
    '{row['updated_by']}'
);""")
    print()

    # 4. Load cis_group_permissions
    print("-- ================================================================")
    print("-- Table: cis_group_permissions (30 rows)")
    print("-- ================================================================")
    df = pd.read_excel(xl, sheet_name='cis_group_permissions')
    for _, row in df.iterrows():
        print(f"""INSERT INTO cis_group_permissions VALUES (
    {row['cis_group_permissions_id']},
    {row['cis_user_group_id']},
    '{row['permission']}',
    '{row['read_write']}',
    {str(row['is_deleted']).lower()},
    CAST('{row['updated_on']}' AS TIMESTAMP),
    '{row['updated_by']}'
);""")
    print()

    print("-- ================================================================")
    print("-- End of INSERT statements")
    print("-- Total: 41 rows (1 + 3 + 7 + 30)")
    print("-- ================================================================")

    sys.stderr.write("\n✓ Successfully generated INSERT statements for all ACL tables\n")
    sys.stderr.write("  Output written to stdout\n\n")

except Exception as e:
    sys.stderr.write(f"✗ ERROR: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)
