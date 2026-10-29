#!/usr/bin/env python
"""
Portfolio Data Loader Script (One-Time Migration)
Loads portfolio master data from CSV into Kudu cis_portfolio table

Features:
- Dynamic column mapping from CSV headers to database columns
- Auto-detects CSV column names and maps to database schema
- Handles data type conversions (string, decimal, boolean)
- Validates required fields
- Provides detailed import summary

Usage:
    python scripts/load_portfolio_data.py <csv_file_path>

Example:
    python scripts/load_portfolio_data.py /path/to/portfolios.csv
    python scripts/load_portfolio_data.py sql/sample_data/portfolio_migration.csv
"""

import csv
import sys
import os
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any, Optional, Tuple

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from core.repositories.impala_connection import impala_manager


class PortfolioDataLoader:
    """
    Loads portfolio data from CSV to Kudu cis_portfolio table.

    Supports dynamic column mapping - user provides CSV with any column names,
    and the script maps them to database columns based on configuration.
    """

    DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')
    TABLE = 'cis_portfolio'

    # Database schema - columns in cis_portfolio table
    DB_COLUMNS = {
        # Primary key
        'code': {'type': 'string', 'required': True},
        # Basic info
        'name': {'type': 'string', 'required': True},
        'description': {'type': 'string', 'required': False},
        'currency': {'type': 'string', 'required': True},
        # Management
        'manager': {'type': 'string', 'required': False},
        'portfolio_client': {'type': 'string', 'required': False},
        # Financial
        'cash_balance': {'type': 'decimal', 'required': False},
        'cash_balance_list': {'type': 'string', 'required': False},
        # Classification
        'cost_centre_code': {'type': 'string', 'required': False},
        'corp_code': {'type': 'string', 'required': False},
        'account_group': {'type': 'string', 'required': False},
        'portfolio_group': {'type': 'string', 'required': False},
        'report_group': {'type': 'string', 'required': False},
        'entity_group': {'type': 'string', 'required': False},
        # Status
        'revaluation_status': {'type': 'string', 'required': False},
        'status': {'type': 'string', 'required': False, 'default': 'ACTIVE'},
        'is_active': {'type': 'boolean', 'required': False, 'default': True},
    }

    # CSV to DB column mapping - common variations
    # Key: possible CSV column name (lowercase), Value: database column name
    COLUMN_ALIASES = {
        # Code/Name
        'code': 'code',
        'portfolio_code': 'code',
        'portfolio code': 'code',
        'portfoliocode': 'code',
        'short_name': 'code',
        'short name': 'code',
        'shortname': 'code',

        'name': 'name',
        'portfolio_name': 'name',
        'portfolio name': 'name',
        'portfolioname': 'name',
        'full_name': 'name',
        'full name': 'name',

        # Description
        'description': 'description',
        'desc': 'description',
        'portfolio_description': 'description',

        # Currency
        'currency': 'currency',
        'currency_code': 'currency',
        'currency code': 'currency',
        'currencycode': 'currency',
        'ccy': 'currency',
        'base_currency': 'currency',
        'base currency': 'currency',

        # Management
        'manager': 'manager',
        'portfolio_manager': 'manager',
        'portfolio manager': 'manager',
        'fund_manager': 'manager',
        'fund manager': 'manager',

        'portfolio_client': 'portfolio_client',
        'portfolio client': 'portfolio_client',
        'client': 'portfolio_client',
        'client_name': 'portfolio_client',

        # Financial
        'cash_balance': 'cash_balance',
        'cash balance': 'cash_balance',
        'cashbalance': 'cash_balance',
        'balance': 'cash_balance',

        'cash_balance_list': 'cash_balance_list',
        'cash balance list': 'cash_balance_list',

        # Classification
        'cost_centre_code': 'cost_centre_code',
        'cost centre code': 'cost_centre_code',
        'costcentrecode': 'cost_centre_code',
        'cost_center': 'cost_centre_code',
        'cost center': 'cost_centre_code',

        'corp_code': 'corp_code',
        'corp code': 'corp_code',
        'corpcode': 'corp_code',
        'corporate_code': 'corp_code',

        'account_group': 'account_group',
        'account group': 'account_group',
        'accountgroup': 'account_group',

        'portfolio_group': 'portfolio_group',
        'portfolio group': 'portfolio_group',
        'portfoliogroup': 'portfolio_group',

        'report_group': 'report_group',
        'report group': 'report_group',
        'reportgroup': 'report_group',
        'reporting_group': 'report_group',

        'entity_group': 'entity_group',
        'entity group': 'entity_group',
        'entitygroup': 'entity_group',

        # Status
        'revaluation_status': 'revaluation_status',
        'revaluation status': 'revaluation_status',
        'reval_status': 'revaluation_status',

        'status': 'status',
        'portfolio_status': 'status',

        'is_active': 'is_active',
        'is active': 'is_active',
        'isactive': 'is_active',
        'active': 'is_active',
    }

    def __init__(self, csv_file: str, dry_run: bool = False, src_system: str = 'MIGRATION'):
        self.csv_file = csv_file
        self.dry_run = dry_run
        self.src_system = src_system
        self.loaded_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.errors = []
        self.warnings = []
        self.column_mapping = {}  # Will be populated from CSV headers

    def safe_decimal(self, value: str, default=None) -> str:
        """Convert string to decimal, handling errors"""
        if not value or str(value).strip() == '':
            return 'NULL' if default is None else str(default)
        try:
            # Remove commas and other formatting
            clean_value = str(value).replace(',', '').replace(' ', '').strip()
            dec_val = Decimal(clean_value)
            return str(dec_val)
        except (InvalidOperation, ValueError):
            return 'NULL' if default is None else str(default)

    def safe_boolean(self, value: str, default: bool = True) -> str:
        """Convert string to boolean"""
        if not value or str(value).strip() == '':
            return str(default).lower()

        val_lower = str(value).lower().strip()
        if val_lower in ('true', 'yes', 'y', '1', 'active', 'on'):
            return 'true'
        elif val_lower in ('false', 'no', 'n', '0', 'inactive', 'off'):
            return 'false'
        return str(default).lower()

    def escape_string(self, value: str) -> str:
        """Escape string for SQL"""
        if value is None or str(value).strip() == '':
            return 'NULL'
        # Escape backslashes and single quotes
        escaped = str(value).strip().replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    def detect_column_mapping(self, csv_headers: List[str]) -> Dict[str, str]:
        """
        Auto-detect column mapping from CSV headers to database columns.

        Returns:
            Dict mapping CSV column name -> database column name
        """
        mapping = {}
        unmapped = []

        for header in csv_headers:
            header_lower = header.lower().strip()

            # Check if this header maps to a known column
            if header_lower in self.COLUMN_ALIASES:
                db_col = self.COLUMN_ALIASES[header_lower]
                mapping[header] = db_col
            else:
                # Try exact match with database column names
                if header_lower.replace(' ', '_') in self.DB_COLUMNS:
                    mapping[header] = header_lower.replace(' ', '_')
                else:
                    unmapped.append(header)

        if unmapped:
            self.warnings.append(f"Unmapped CSV columns (will be ignored): {', '.join(unmapped)}")

        return mapping

    def validate_required_columns(self) -> Tuple[bool, List[str]]:
        """Validate that all required columns are mapped"""
        missing = []
        mapped_db_cols = set(self.column_mapping.values())

        for db_col, config in self.DB_COLUMNS.items():
            if config.get('required', False) and db_col not in mapped_db_cols:
                missing.append(db_col)

        return len(missing) == 0, missing

    def build_insert_sql(self, row: dict, row_num: int) -> Optional[str]:
        """Build UPSERT SQL for a single row"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        columns = []
        values = []

        # Process mapped columns
        for csv_col, db_col in self.column_mapping.items():
            csv_value = row.get(csv_col, '').strip()
            col_config = self.DB_COLUMNS.get(db_col, {'type': 'string'})

            columns.append(db_col)

            if col_config['type'] == 'decimal':
                values.append(self.safe_decimal(csv_value))
            elif col_config['type'] == 'boolean':
                default = col_config.get('default', True)
                values.append(self.safe_boolean(csv_value, default))
            else:  # string
                if not csv_value and col_config.get('default'):
                    csv_value = col_config['default']
                values.append(self.escape_string(csv_value))

        # Add default values for required columns not in CSV
        mapped_db_cols = set(self.column_mapping.values())

        if 'status' not in mapped_db_cols:
            columns.append('status')
            values.append("'ACTIVE'")

        if 'is_active' not in mapped_db_cols:
            columns.append('is_active')
            values.append('true')

        # Add audit columns
        columns.extend(['src_system', 'created_by', 'created_at', 'updated_by', 'updated_at'])
        values.extend([
            self.escape_string(self.src_system),
            self.escape_string('SYSTEM_MIGRATION'),
            self.escape_string(timestamp),
            self.escape_string('SYSTEM_MIGRATION'),
            self.escape_string(timestamp)
        ])

        # Validate required fields have values
        code_idx = columns.index('code') if 'code' in columns else None
        if code_idx is not None and values[code_idx] == 'NULL':
            raise ValueError(f"Row {row_num}: Missing required field 'code'")

        name_idx = columns.index('name') if 'name' in columns else None
        if name_idx is not None and values[name_idx] == 'NULL':
            raise ValueError(f"Row {row_num}: Missing required field 'name'")

        currency_idx = columns.index('currency') if 'currency' in columns else None
        if currency_idx is not None and values[currency_idx] == 'NULL':
            raise ValueError(f"Row {row_num}: Missing required field 'currency'")

        # Build UPSERT statement
        sql = f"""
        UPSERT INTO {self.DATABASE}.{self.TABLE}
        ({', '.join(columns)})
        VALUES ({', '.join(values)})
        """

        return sql

    def load_csv_data(self) -> bool:
        """Load data from CSV file"""
        print("=" * 80)
        print("PORTFOLIO DATA LOADER (One-Time Migration)")
        print("=" * 80)
        print(f"CSV File: {self.csv_file}")
        print(f"Target Table: {self.DATABASE}.{self.TABLE}")
        print(f"Dry Run: {self.dry_run}")
        print(f"Source System: {self.src_system}")
        print("=" * 80)

        if not os.path.exists(self.csv_file):
            print(f"ERROR: CSV file not found: {self.csv_file}")
            return False

        try:
            with open(self.csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                # Get headers and detect column mapping
                headers = reader.fieldnames
                if not headers:
                    print("ERROR: CSV file has no headers")
                    return False

                print(f"\nCSV Columns Found: {len(headers)}")
                for h in headers:
                    print(f"  - {h}")

                self.column_mapping = self.detect_column_mapping(headers)

                print(f"\nColumn Mapping ({len(self.column_mapping)} mapped):")
                for csv_col, db_col in self.column_mapping.items():
                    print(f"  {csv_col} -> {db_col}")

                # Validate required columns
                is_valid, missing = self.validate_required_columns()
                if not is_valid:
                    print(f"\nERROR: Missing required columns: {', '.join(missing)}")
                    print("Please ensure your CSV has columns that map to: code, name, currency")
                    return False

                if self.warnings:
                    print("\nWarnings:")
                    for w in self.warnings:
                        print(f"  {w}")

                print("\n" + "-" * 80)
                print("Processing rows...")
                print("-" * 80)

                for row_num, row in enumerate(reader, start=2):
                    try:
                        sql = self.build_insert_sql(row, row_num)

                        if self.dry_run:
                            print(f"  [DRY RUN] Row {row_num}: {row.get(list(self.column_mapping.keys())[0], 'Unknown')}")
                            self.loaded_count += 1
                        else:
                            success = impala_manager.execute_write(sql, database=self.DATABASE)
                            if success:
                                self.loaded_count += 1
                                if self.loaded_count % 10 == 0:
                                    print(f"  Loaded {self.loaded_count} records...")
                            else:
                                raise Exception("UPSERT failed")

                    except ValueError as ve:
                        self.skipped_count += 1
                        self.warnings.append(str(ve))
                        print(f"  SKIPPED: {str(ve)}")

                    except Exception as e:
                        self.error_count += 1
                        code_col = next((c for c in self.column_mapping if self.column_mapping[c] == 'code'), None)
                        code_val = row.get(code_col, 'Unknown') if code_col else 'Unknown'
                        error_msg = f"Row {row_num} ({code_val}): {str(e)}"
                        self.errors.append(error_msg)
                        print(f"  ERROR: {error_msg}")

            return True

        except Exception as e:
            print(f"FATAL ERROR reading CSV: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def print_summary(self):
        """Print loading summary"""
        print("\n" + "=" * 80)
        print("LOADING SUMMARY")
        print("=" * 80)
        print(f"Successfully loaded: {self.loaded_count} records")
        print(f"Skipped (validation): {self.skipped_count} records")
        print(f"Errors: {self.error_count} records")

        if self.warnings:
            print("\nWarnings:")
            print("-" * 80)
            for w in self.warnings[:20]:
                print(f"  {w}")
            if len(self.warnings) > 20:
                print(f"  ... and {len(self.warnings) - 20} more warnings")

        if self.errors:
            print("\nError Details:")
            print("-" * 80)
            for error in self.errors[:10]:
                print(f"  {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more errors")

        print("=" * 80)

    def verify_data(self):
        """Verify data was loaded correctly"""
        if self.dry_run:
            print("\n[DRY RUN] Skipping verification")
            return

        print("\nVerifying data in Kudu...")

        # Count records
        count_query = f"""
        SELECT COUNT(*) as count
        FROM {self.DATABASE}.{self.TABLE}
        WHERE src_system = '{self.src_system}'
        """
        results = impala_manager.execute_query(count_query, database=self.DATABASE)

        if results:
            count = results[0].get('count', 0)
            print(f"Records with src_system='{self.src_system}': {count}")

        # Show sample records
        sample_query = f"""
        SELECT code, name, currency, status, is_active, created_at
        FROM {self.DATABASE}.{self.TABLE}
        WHERE src_system = '{self.src_system}'
        ORDER BY created_at DESC
        LIMIT 5
        """
        sample_results = impala_manager.execute_query(sample_query, database=self.DATABASE)

        if sample_results:
            print("\nSample Records:")
            print("-" * 80)
            print(f"{'Code':<20} {'Name':<30} {'Currency':<10} {'Status':<10}")
            print("-" * 80)
            for rec in sample_results:
                print(f"{str(rec.get('code', ''))[:20]:<20} "
                      f"{str(rec.get('name', ''))[:30]:<30} "
                      f"{str(rec.get('currency', '')):<10} "
                      f"{str(rec.get('status', '')):<10}")


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(
        description='Load portfolio data from CSV into Kudu (One-Time Migration)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/load_portfolio_data.py portfolios.csv
    python scripts/load_portfolio_data.py /path/to/data.csv --dry-run
    python scripts/load_portfolio_data.py data.csv --src-system GMP_MIGRATION
        """
    )
    parser.add_argument('csv_file', help='Path to CSV file containing portfolio data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and validate CSV without inserting data')
    parser.add_argument('--src-system', default='MIGRATION',
                        help='Source system identifier (default: MIGRATION)')

    args = parser.parse_args()

    loader = PortfolioDataLoader(
        csv_file=args.csv_file,
        dry_run=args.dry_run,
        src_system=args.src_system
    )

    success = loader.load_csv_data()

    if success:
        loader.print_summary()
        loader.verify_data()
        return 0 if loader.error_count == 0 else 1
    else:
        print("\nData loading failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
