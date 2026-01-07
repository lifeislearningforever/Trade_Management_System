"""
Load Counterparty Data to Kudu Table
=====================================
Purpose: Load counterparty_with_mlabel.csv into cis_counterparty_kudu table
Author: Claude Code
Date: 2025-01-07

Features:
- Converts Y/N strings to BOOLEAN
- Handles NULL/empty values
- Generates UPSERT statements for Kudu
- Batch processing for performance
"""

import csv
import os
from datetime import datetime
from typing import Dict, Any, List

# File paths
CSV_FILE = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/sample_data/counterparty_with_mlabel.csv'
OUTPUT_SQL = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/data_load/insert_counterparty_data.sql'

def convert_yn_to_bool(value: str) -> str:
    """Convert Y/N string to boolean SQL value"""
    if not value or value.strip().upper() == 'N':
        return 'FALSE'
    elif value.strip().upper() == 'Y':
        return 'TRUE'
    else:
        return 'FALSE'  # Default to FALSE

def escape_string(value: str) -> str:
    """Escape single quotes for SQL"""
    if not value:
        return ''
    return value.replace("'", "''")

def format_value(value: str, is_boolean: bool = False) -> str:
    """Format value for SQL INSERT"""
    if is_boolean:
        return convert_yn_to_bool(value)

    if not value or value.strip() == '':
        return 'NULL'

    # Escape and quote string values
    escaped = escape_string(value.strip())
    return f"'{escaped}'"

def generate_insert_statement(row: Dict[str, str]) -> str:
    """Generate INSERT statement for a single row"""

    # Extract and format values
    counterparty_short_name = format_value(row.get('counterparty_short_name', ''))
    m_label = format_value(row.get('m_label', ''))
    counterparty_full_name = format_value(row.get('counterparty_full_name', ''))
    record_type = format_value(row.get('record_type', ''))

    # Address fields
    address_line_0 = format_value(row.get('address_line_0', ''))
    address_line_1 = format_value(row.get('address_line_1', ''))
    address_line_2 = format_value(row.get('address_line_2', ''))
    address_line_3 = format_value(row.get('address_line_3', ''))
    city = format_value(row.get('city', ''))
    country = format_value(row.get('country', ''))
    postal_code = format_value(row.get('postal_code', ''))

    # Contact fields
    fax_number = format_value(row.get('fax_number', ''))
    telex_number = format_value(row.get('telex_number', ''))
    primary_contact = format_value(row.get('primary_contact', ''))
    primary_number = format_value(row.get('primary_number', ''))
    other_contact = format_value(row.get('other_contact', ''))
    other_number = format_value(row.get('other_number', ''))

    # Classification
    industry = format_value(row.get('industry', ''))
    industry_group = format_value(row.get('industry_group', ''))

    # Boolean flags
    is_broker = format_value(row.get('is_broker', ''), is_boolean=True)
    is_custodian = format_value(row.get('is_custodian', ''), is_boolean=True)
    is_issuer = format_value(row.get('is_issuer', ''), is_boolean=True)
    is_bank = format_value(row.get('is_bank', ''), is_boolean=True)
    is_subsidiary = format_value(row.get('is_subsidiary', ''), is_boolean=True)
    is_corporate = format_value(row.get('is_corporate', ''), is_boolean=True)

    # Hierarchy
    subsidiary_level = format_value(row.get('subsidiary_level', ''))
    counterparty_grandparent = format_value(row.get('counterparty_grandparent', ''))
    counterparty_parent = format_value(row.get('counterparty_parent', ''))

    # Regulatory
    resident_y_n = format_value(row.get('resident_y_n', ''))
    mas_industry_code = format_value(row.get('mas_industry_code', ''))
    country_of_incorporation = format_value(row.get('country_of_incorporation', ''))
    cels_code = format_value(row.get('cels_code', ''))

    # Source metadata
    src_system = format_value(row.get('src_system', ''))
    sub_system = format_value(row.get('sub_system', ''))
    data_cat = format_value(row.get('data_cat', ''))
    data_frq = format_value(row.get('data_frq', ''))
    src_id = format_value(row.get('src_id', ''))
    processing_date = format_value(row.get('processing_date', ''))

    # Audit fields
    created_by = "'ETL_SYSTEM'"
    updated_by = "'ETL_SYSTEM'"

    # Generate UPSERT statement (INSERT or UPDATE if exists)
    sql = f"""
UPSERT INTO gmp_cis.cis_counterparty_kudu (
    counterparty_short_name, m_label, counterparty_full_name, record_type,
    address_line_0, address_line_1, address_line_2, address_line_3,
    city, country, postal_code,
    fax_number, telex_number, primary_contact, primary_number, other_contact, other_number,
    industry, industry_group,
    is_broker, is_custodian, is_issuer, is_bank, is_subsidiary, is_corporate,
    subsidiary_level, counterparty_grandparent, counterparty_parent,
    resident_y_n, mas_industry_code, country_of_incorporation, cels_code,
    src_system, sub_system, data_cat, data_frq, src_id, processing_date,
    is_active, is_deleted, created_by, updated_by
) VALUES (
    {counterparty_short_name}, {m_label}, {counterparty_full_name}, {record_type},
    {address_line_0}, {address_line_1}, {address_line_2}, {address_line_3},
    {city}, {country}, {postal_code},
    {fax_number}, {telex_number}, {primary_contact}, {primary_number}, {other_contact}, {other_number},
    {industry}, {industry_group},
    {is_broker}, {is_custodian}, {is_issuer}, {is_bank}, {is_subsidiary}, {is_corporate},
    {subsidiary_level}, {counterparty_grandparent}, {counterparty_parent},
    {resident_y_n}, {mas_industry_code}, {country_of_incorporation}, {cels_code},
    {src_system}, {sub_system}, {data_cat}, {data_frq}, {src_id}, {processing_date},
    TRUE, FALSE, {created_by}, {updated_by}
);
"""
    return sql.strip()

def main():
    """Main execution function"""
    print("=" * 80)
    print("Counterparty Data Loader for Kudu")
    print("=" * 80)
    print(f"Input CSV: {CSV_FILE}")
    print(f"Output SQL: {OUTPUT_SQL}")
    print()

    if not os.path.exists(CSV_FILE):
        print(f"ERROR: CSV file not found: {CSV_FILE}")
        return

    # Read CSV and generate SQL
    insert_statements = []
    skipped_count = 0

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=1):
            counterparty_name = row.get('counterparty_short_name', '').strip()

            if not counterparty_name:
                print(f"WARNING: Skipping row {i} - missing counterparty_short_name")
                skipped_count += 1
                continue

            try:
                sql = generate_insert_statement(row)
                insert_statements.append(sql)

                if i % 500 == 0:
                    print(f"Processed {i} rows...")

            except Exception as e:
                print(f"ERROR: Failed to process row {i} ({counterparty_name}): {str(e)}")
                skipped_count += 1

    print()
    print(f"Total rows processed: {len(insert_statements)}")
    print(f"Rows skipped: {skipped_count}")

    # Write SQL file
    with open(OUTPUT_SQL, 'w', encoding='utf-8') as f:
        f.write("-- ============================================================================\n")
        f.write("-- Counterparty Data Load - Auto-generated\n")
        f.write(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"-- Total Records: {len(insert_statements)}\n")
        f.write("-- ============================================================================\n\n")
        f.write("USE gmp_cis;\n\n")

        # Write in batches for readability
        for i, stmt in enumerate(insert_statements, start=1):
            f.write(stmt)
            f.write("\n\n")

            if i % 100 == 0:
                f.write(f"-- Batch checkpoint: {i} records processed\n\n")

    print()
    print("=" * 80)
    print(f"✅ SQL file generated successfully: {OUTPUT_SQL}")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Review the generated SQL file")
    print("2. Execute DDL: impala-shell -f sql/ddl/cis_counterparty_kudu.sql")
    print("3. Load data: impala-shell -f sql/data_load/insert_counterparty_data.sql")
    print()

if __name__ == '__main__':
    main()
