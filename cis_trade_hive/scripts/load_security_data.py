#!/usr/bin/env python
"""
Security Data Loader Script
Loads security master data from CSV into Kudu cis_security table
"""

import csv
import sys
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from core.repositories.impala_connection import impala_manager


class SecurityDataLoader:
    """Loads security data from CSV to Kudu"""

    CSV_FILE = 'sql/sample_data/Security.csv'
    DATABASE = 'gmp_cis'
    TABLE = 'cis_security'

    # CSV column to database column mapping
    COLUMN_MAPPING = {
        'Security Name': 'security_name',
        'ISIN': 'isin',
        'Security Description': 'security_description',
        'Issuer': 'issuer',
        'Ticker': 'ticker',
        'Industry': 'industry',
        'Security Type': 'security_type',
        'Investment Type': 'investment_type',
        'Issuer Type': 'issuer_type',
        'Quoted / Unquoted': 'quoted_unquoted',
        'Country of Incorporation': 'country_of_incorporation',
        'Country of Exchange': 'country_of_exchange',
        'Country of Issue': 'country_of_issue',
        'Country of Primary Exchange': 'country_of_primary_exchange',
        'Exchange Code': 'exchange_code',
        'Currency Code': 'currency_code',
        'Price': 'price',
        'Price Date': 'price_date',
        'Price Source': 'price_source',
        'Shares Outstanding': 'shares_outstanding',
        'Beta': 'beta',
        'PAR Value': 'par_value',
        '% Shareholding Entity 1': 'shareholding_entity_1',
        '% Shareholding Entity 2': 'shareholding_entity_2',
        '% Shareholding Entity 3': 'shareholding_entity_3',
        '% Shareholding Aggregated': 'shareholding_aggregated',
        'Substantial >10%': 'substantial_10_pct',
        'BWCIIF': 'bwciif',
        'BWCIIF Others': 'bwciif_others',
        'CELS': 'cels',
        'Approved S32': 'approved_s32',
        'BASEL IV - FUND': 'basel_iv_fund',
        'MAS 643 Entity Type': 'mas_643_entity_type',
        'MAS 6D Code': 'mas_6d_code',
        'Fin/Non-fin IND': 'fin_nonfin_ind',
        'Business Unit Head': 'business_unit_head',
        'Person In Charge': 'person_in_charge',
        'Core/Non-core': 'core_noncore',
        'Fund / Index Fund': 'fund_index_fund',
        'Management Limit Classification': 'management_limit_classification',
        'Relative Index': 'relative_index',
    }

    def __init__(self):
        self.loaded_count = 0
        self.error_count = 0
        self.errors = []

    def safe_decimal(self, value: str, default=None) -> str:
        """Convert string to decimal, handling errors"""
        if not value or value.strip() == '':
            return 'NULL' if default is None else str(default)
        try:
            dec_val = Decimal(value)
            return str(dec_val)
        except (InvalidOperation, ValueError):
            return 'NULL' if default is None else str(default)

    def safe_bigint(self, value: str, default=None) -> str:
        """Convert string to bigint, handling errors"""
        if not value or value.strip() == '':
            return 'NULL' if default is None else str(default)
        try:
            int_val = int(float(value))  # Handle decimals in integer fields
            return str(int_val)
        except (ValueError, TypeError):
            return 'NULL' if default is None else str(default)

    def escape_string(self, value: str) -> str:
        """Escape string for SQL"""
        if value is None or value == '':
            return 'NULL'
        # Escape backslashes and single quotes
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    def load_csv_data(self):
        """Load data from CSV file"""
        print("=" * 80)
        print("SECURITY DATA LOADER")
        print("=" * 80)
        print(f"CSV File: {self.CSV_FILE}")
        print(f"Target Table: {self.DATABASE}.{self.TABLE}")
        print("=" * 80)

        csv_path = os.path.join(project_root, self.CSV_FILE)

        if not os.path.exists(csv_path):
            print(f"✗ ERROR: CSV file not found: {csv_path}")
            return False

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                    try:
                        self.insert_security(row, row_num)
                        self.loaded_count += 1

                        if self.loaded_count % 10 == 0:
                            print(f"  Loaded {self.loaded_count} records...")

                    except Exception as e:
                        self.error_count += 1
                        error_msg = f"Row {row_num} ({row.get('Security Name', 'Unknown')}): {str(e)}"
                        self.errors.append(error_msg)
                        print(f"  ✗ ERROR: {error_msg}")

            return True

        except Exception as e:
            print(f"✗ FATAL ERROR reading CSV: {str(e)}")
            return False

    def insert_security(self, row: dict, row_num: int):
        """Insert a single security record"""
        # Generate security_id (timestamp-based with row offset)
        timestamp_ms = int(datetime.now().timestamp() * 1000)
        security_id = timestamp_ms + row_num

        # Audit fields
        audit_timestamp = timestamp_ms
        created_by = 'SYSTEM_IMPORT'

        # Map CSV columns to database columns
        columns = ['security_id']
        values = [str(security_id)]

        # Process each CSV column
        for csv_col, db_col in self.COLUMN_MAPPING.items():
            csv_value = row.get(csv_col, '').strip()

            columns.append(db_col)

            # Handle different data types
            if db_col in ['price', 'beta', 'par_value', 'shareholding_entity_1',
                          'shareholding_entity_2', 'shareholding_entity_3', 'shareholding_aggregated']:
                values.append(self.safe_decimal(csv_value))

            elif db_col in ['shares_outstanding', 'bwciif', 'bwciif_others']:
                values.append(self.safe_bigint(csv_value))

            else:  # String fields
                values.append(self.escape_string(csv_value))

        # Add audit columns
        columns.extend(['is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'])
        values.extend([
            'true',
            self.escape_string(created_by),
            str(audit_timestamp),
            self.escape_string(created_by),
            str(audit_timestamp)
        ])

        # Build UPSERT statement
        upsert_sql = f"""
        UPSERT INTO {self.DATABASE}.{self.TABLE}
        ({', '.join(columns)})
        VALUES ({', '.join(values)})
        """

        # Execute
        success = impala_manager.execute_write(upsert_sql, database=self.DATABASE)

        if not success:
            raise Exception("Failed to execute UPSERT")

    def print_summary(self):
        """Print loading summary"""
        print("\n" + "=" * 80)
        print("LOADING SUMMARY")
        print("=" * 80)
        print(f"✓ Successfully loaded: {self.loaded_count} records")
        print(f"✗ Errors: {self.error_count} records")

        if self.errors:
            print("\nError Details:")
            print("-" * 80)
            for error in self.errors[:10]:  # Show first 10 errors
                print(f"  {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more errors")

        print("=" * 80)


def main():
    """Main execution"""
    loader = SecurityDataLoader()

    success = loader.load_csv_data()

    if success:
        loader.print_summary()

        # Verify final count
        print("\nVerifying data in Kudu...")
        count_query = f"SELECT COUNT(*) as count FROM {loader.DATABASE}.{loader.TABLE}"
        results = impala_manager.execute_query(count_query, database=loader.DATABASE)

        if results:
            final_count = results[0].get('count', 0)
            print(f"✓ Final record count in Kudu: {final_count}")

            # Show sample records
            sample_query = f"""
            SELECT
                security_id,
                security_name,
                isin,
                security_type,
                currency_code,
                price,
                created_by
            FROM {loader.DATABASE}.{loader.TABLE}
            LIMIT 5
            """
            sample_results = impala_manager.execute_query(sample_query, database=loader.DATABASE)

            if sample_results:
                print("\nSample Records:")
                print("-" * 80)
                for rec in sample_results:
                    print(f"  {rec.get('security_id')} | {rec.get('security_name')} | "
                          f"{rec.get('isin')} | {rec.get('security_type')} | "
                          f"{rec.get('currency_code')} | {rec.get('price')}")

        return 0 if loader.error_count == 0 else 1
    else:
        print("\n✗ Data loading failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
