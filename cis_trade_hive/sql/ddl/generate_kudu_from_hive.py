#!/usr/bin/env python3
"""
Generate Kudu table DDL from existing Hive tables in cis database.
Automatically converts all Hive tables to Kudu format with proper primary keys.
"""

import subprocess
import re
from datetime import datetime

# Hive to Kudu type mapping
TYPE_MAPPING = {
    'string': 'STRING',
    'int': 'INT32',
    'bigint': 'INT64',
    'double': 'DOUBLE',
    'float': 'FLOAT',
    'boolean': 'BOOL',
    'timestamp': 'UNIXTIME_MICROS',
    'date': 'STRING',  # Kudu doesn't have DATE, use STRING
}

# Primary key definitions for each table (based on actual Hive column names)
PRIMARY_KEYS = {
    'cis_audit_log': ['audit_id'],
    'cis_group_permissions': ['cis_group_permissions_id'],
    'cis_permission': ['cis_permission_id'],
    'cis_portfolio': ['name'],
    'cis_udf_definition': ['entity_type', 'field_name'],
    'cis_udf_option': ['udf_id', 'option_value'],
    'cis_udf_value': ['entity_id', 'entity_type', 'field_name'],
    'cis_udf_value_multi': ['entity_id', 'entity_type', 'field_name', 'option_value'],
    'cis_user': ['cis_user_id'],
    'cis_user_group': ['cis_user_group_id'],
    'gmp_cis_sta_dly_calendar': ['calendar_label', 'holiday_date'],
    'gmp_cis_sta_dly_counterparty': ['counterparty_name'],
    'gmp_cis_sta_dly_country': ['label'],
    'gmp_cis_sta_dly_currency': ['iso_code'],
    'test_insert_simple': ['id'],
}


def run_beeline_query(query):
    """Execute beeline query and return output."""
    result = subprocess.run(
        [
            '/usr/local/bin/beeline',
            '-u', 'jdbc:hive2://localhost:10000/cis',
            '-e', query,
            '--silent=true'
        ],
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        return None

    # Filter out log messages
    lines = []
    for line in result.stdout.split('\n'):
        if any(skip in line for skip in ['SLF4J', '2025-', 'WARN', 'INFO', 'Connecting',
                                          'Connected', 'Driver', 'Transaction', 'Beeline',
                                          'Closing', 'Please remove', 'See http', 'rows selected']):
            continue
        if line.strip():
            lines.append(line)

    return '\n'.join(lines)


def get_all_tables():
    """Get all table names from cis database."""
    output = run_beeline_query('SHOW TABLES;')
    if not output:
        return []

    tables = []
    for line in output.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2 and parts[1] and parts[1] != 'tab_name':
                tables.append(parts[1])

    return tables


def get_table_schema(table_name):
    """Get schema for a specific table."""
    output = run_beeline_query(f'DESCRIBE {table_name};')
    if not output:
        return []

    columns = []
    for line in output.split('\n'):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3 and parts[1] and parts[1] != 'col_name':
                col_name = parts[1]
                data_type = parts[2]
                if col_name and data_type:
                    columns.append({'name': col_name, 'type': data_type})

    return columns


def map_hive_to_kudu_type(hive_type):
    """Convert Hive type to Kudu type."""
    hive_type_lower = hive_type.lower()
    return TYPE_MAPPING.get(hive_type_lower, 'STRING')


def generate_kudu_ddl(table_name, columns, primary_keys):
    """Generate Kudu CREATE TABLE DDL."""

    # Build column definitions
    col_defs = []
    for col in columns:
        kudu_type = map_hive_to_kudu_type(col['type'])
        # Primary key columns must be NOT NULL
        if col['name'] in primary_keys:
            col_defs.append(f"  {col['name']} {kudu_type} NOT NULL")
        else:
            col_defs.append(f"  {col['name']} {kudu_type}")

    # Build PRIMARY KEY clause
    pk_clause = f"  PRIMARY KEY ({', '.join(primary_keys)})"

    # Join column definitions with newline
    columns_str = ',\n'.join(col_defs)

    ddl = f"""-- Kudu table for {table_name}
CREATE TABLE IF NOT EXISTS {table_name}_kudu (
{columns_str},
{pk_clause}
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'localhost:7051',
  'kudu.table_name' = '{table_name}_kudu'
);
"""
    return ddl


def main():
    """Main function to generate all Kudu DDL."""

    print("Fetching tables from Hive cis database...")
    tables = get_all_tables()

    if not tables:
        print("ERROR: No tables found!")
        return

    print(f"Found {len(tables)} tables: {', '.join(tables)}")

    # Generate DDL file
    output_file = 'cis_hive_to_kudu_tables.sql'

    with open(output_file, 'w') as f:
        # Write header
        f.write(f"""-- Kudu Table Definitions for CIS Database
-- Generated from Hive tables on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
--
-- This file contains Kudu table equivalents for all Hive tables in the cis database.
-- Kudu tables are optimized for fast random access and updates.
--
-- Usage:
--   Run this script using Impala (not Hive):
--   impala-shell -f {output_file}
--
-- Or run via beeline with Impala JDBC:
--   beeline -u "jdbc:impala://localhost:21050/cis" -f {output_file}
--

-- Switch to cis database
USE cis;

""")

        # Process each table
        for table_name in sorted(tables):
            print(f"Processing {table_name}...")

            # Get schema
            columns = get_table_schema(table_name)
            if not columns:
                print(f"  WARNING: Could not get schema for {table_name}")
                continue

            print(f"  Found {len(columns)} columns")

            # Get primary keys (use defaults if not defined)
            primary_keys = PRIMARY_KEYS.get(table_name)
            if not primary_keys:
                # Default: use first column as primary key
                primary_keys = [columns[0]['name']]
                print(f"  WARNING: No primary key defined, using first column: {primary_keys[0]}")

            # Generate DDL
            ddl = generate_kudu_ddl(table_name, columns, primary_keys)
            f.write(ddl)
            f.write('\n\n')

    print(f"\n✅ Successfully generated Kudu DDL for {len(tables)} tables!")
    print(f"📄 Output file: {output_file}")
    print(f"\nTo create the tables, run:")
    print(f"  impala-shell -f {output_file}")


if __name__ == '__main__':
    main()
