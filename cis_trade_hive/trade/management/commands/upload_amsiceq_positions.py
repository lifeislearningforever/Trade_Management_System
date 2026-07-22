"""
Upload position data from CIS_position_amsiceq.xlsx file to Kudu tables.

This command:
1. Creates portfolios (UOIOIF, UOIOIFMF, UOISHF) with USD currency if they don't exist
2. Looks up securities by ISIN from cis_security table (or creates placeholder if not found)
3. Uploads position data to cis_trade_position and cis_trade_position_history tables
4. Populates all 16 new multi-currency columns from the Excel data

Usage:
    python manage.py upload_amsiceq_positions
    python manage.py upload_amsiceq_positions --dry-run
    python manage.py upload_amsiceq_positions --file /path/to/file.xlsx
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Any, Optional, List

import pandas as pd
from django.core.management.base import BaseCommand

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'


class Command(BaseCommand):
    help = 'Upload position data from CIS_position_amsiceq.xlsx to Kudu tables'

    # Default file path
    DEFAULT_FILE = 'sql/sample_data/CIS_position_amsiceq.xlsx'

    # Portfolio base currency (from screenshots - all positions use USD as base)
    PORTFOLIO_CURRENCY = 'USD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=self.DEFAULT_FILE,
            help='Path to the Excel file (default: sql/sample_data/CIS_position_amsiceq.xlsx)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be uploaded without writing to database'
        )
        parser.add_argument(
            '--skip-portfolios',
            action='store_true',
            help='Skip portfolio creation (assume they already exist)'
        )
        parser.add_argument(
            '--skip-securities',
            action='store_true',
            help='Skip security lookup/creation'
        )

    def handle(self, *args, **options):
        file_path = options.get('file', self.DEFAULT_FILE)
        dry_run = options.get('dry_run', False)
        skip_portfolios = options.get('skip_portfolios', False)
        skip_securities = options.get('skip_securities', False)

        # Display header
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('AMSICEQ Position Data Upload'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be written'))
            self.stdout.write('')

        # Load Excel file
        try:
            df = self._load_excel(file_path)
            if df is None or df.empty:
                self.stderr.write(self.style.ERROR('Failed to load Excel file or file is empty'))
                return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error loading Excel file: {str(e)}'))
            return

        total_rows = len(df)
        self.stdout.write(f'Loaded {total_rows} rows from Excel file')
        self.stdout.write('')

        # Step 1: Create portfolios if needed
        if not skip_portfolios:
            portfolio_codes = df['portfolio_code'].unique().tolist()
            self._ensure_portfolios_exist(portfolio_codes, dry_run)

        # Step 2: Cache security lookups by ISIN
        security_cache = {}
        if not skip_securities:
            isins = df['isin'].unique().tolist()
            security_cache = self._build_security_cache(isins, dry_run)

        # Step 3: Upload positions
        success_count = 0
        error_count = 0
        skipped_count = 0

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Uploading Positions'))
        self.stdout.write('-' * 40)

        for idx, row in df.iterrows():
            try:
                result = self._upload_position(row, security_cache, dry_run, idx + 1, total_rows)
                if result == 'success':
                    success_count += 1
                elif result == 'skipped':
                    skipped_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(f'Error uploading row {idx + 1}: {str(e)}')
                )
                logger.error(f'Error uploading row {idx + 1}: {str(e)}', exc_info=True)

        # Display summary
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('Summary'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(f'Total Rows: {total_rows}')
        self.stdout.write(self.style.SUCCESS(f'Successful: {success_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        else:
            self.stdout.write(f'Errors: {error_count}')

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were written to database'))
        else:
            self.stdout.write(self.style.SUCCESS('Position upload completed'))

    def _load_excel(self, file_path: str) -> Optional[pd.DataFrame]:
        """Load and validate the Excel file."""
        path = Path(file_path)
        if not path.is_absolute():
            # Make it relative to project root
            from django.conf import settings
            path = Path(settings.BASE_DIR) / file_path

        self.stdout.write(f'Loading file: {path}')

        if not path.exists():
            self.stderr.write(self.style.ERROR(f'File not found: {path}'))
            return None

        df = pd.read_excel(path)
        self.stdout.write(f'Columns found: {list(df.columns)}')

        # Rename columns to standardized names
        # Handle the complex column names in the Excel file
        column_mapping = {
            'country': 'country',
            'security_currency': 'security_currency',
            'asset_class': 'asset_class',
            'listing_status': 'listing_status',
            'quantity': 'quantity',
            'pct_ratio': 'pct_ratio',
            'cost_unit_price(avg_price)': 'cost_unit_price',
            'market_unit_price(into equity market closing price)': 'market_unit_price',
            'cost_value_local(foregin/security ccy)/total cost': 'cost_value_local',
            'market_value_local/market value/security ccy': 'market_value_local',
            'cost_value_base(local/portfolio ccy)/total cost': 'cost_value_base',
            'market_value_base/market value/portfolio ccy': 'market_value_base',
            'unrealized_p_l_local/security ccy': 'unrealized_pnl_local',
            'unrealized_p_l_base/portfolio ccy': 'unrealized_pnl_base',
            'isin': 'isin',
            'fx_rate': 'fx_rate',
            'portfolio_code_repeated': 'portfolio_code',  # Excel column name
            'valuation_date': 'valuation_date',
            'flag': 'flag',
        }

        # Try to map columns (handle case-insensitive matching)
        for excel_col in df.columns:
            excel_col_lower = excel_col.lower().strip()
            for key, value in column_mapping.items():
                if key.lower() == excel_col_lower:
                    df.rename(columns={excel_col: value}, inplace=True)
                    break

        # Check required columns
        required_cols = ['isin', 'portfolio_code', 'quantity']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            self.stderr.write(self.style.ERROR(f'Missing required columns: {missing}'))
            self.stdout.write(f'Available columns: {list(df.columns)}')
            return None

        return df

    def _ensure_portfolios_exist(self, portfolio_codes: List[str], dry_run: bool):
        """Create portfolios if they don't exist."""
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Ensuring Portfolios Exist'))
        self.stdout.write('-' * 40)

        for code in portfolio_codes:
            if not code or pd.isna(code):
                continue

            code = str(code).strip()

            # Check if portfolio exists
            exists = self._portfolio_exists(code)
            if exists:
                self.stdout.write(f'  Portfolio {code}: EXISTS')
                continue

            self.stdout.write(f'  Portfolio {code}: CREATING...')
            if not dry_run:
                success = self._create_portfolio(code)
                if success:
                    self.stdout.write(self.style.SUCCESS(f'    Created portfolio {code}'))
                else:
                    self.stderr.write(self.style.ERROR(f'    Failed to create portfolio {code}'))
            else:
                self.stdout.write(self.style.WARNING(f'    Would create portfolio {code}'))

    def _portfolio_exists(self, portfolio_code: str) -> bool:
        """Check if portfolio exists in cis_portfolio."""
        try:
            safe_code = self._escape_string(portfolio_code)
            query = f"""
                SELECT name FROM {DATABASE}.cis_portfolio
                WHERE name = '{safe_code}'
                LIMIT 1
            """
            results = impala_manager.execute_query(query, database=DATABASE)
            return bool(results)
        except Exception as e:
            logger.error(f'Error checking portfolio {portfolio_code}: {str(e)}')
            return False

    def _create_portfolio(self, portfolio_code: str) -> bool:
        """Create a new portfolio with USD base currency."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            safe_code = self._escape_string(portfolio_code)

            query = f"""
                INSERT INTO {DATABASE}.cis_portfolio
                (name, description, currency, manager, status, is_active,
                 src_system, created_by, created_at, updated_by, updated_at)
                VALUES (
                    '{safe_code}',
                    'Portfolio {safe_code} - Auto-created from AMSICEQ data',
                    '{self.PORTFOLIO_CURRENCY}',
                    'SYSTEM',
                    'SETTLED',
                    true,
                    'AMSICEQ',
                    'SYSTEM',
                    '{timestamp}',
                    'SYSTEM',
                    '{timestamp}'
                )
            """
            return impala_manager.execute_write(query, database=DATABASE)
        except Exception as e:
            logger.error(f'Error creating portfolio {portfolio_code}: {str(e)}')
            return False

    def _build_security_cache(self, isins: List[str], dry_run: bool) -> Dict[str, Dict[str, Any]]:
        """Build a cache of security data by ISIN."""
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Building Security Cache'))
        self.stdout.write('-' * 40)

        cache = {}
        found_count = 0
        created_count = 0

        for isin in isins:
            if not isin or pd.isna(isin):
                continue

            isin = str(isin).strip()

            # Try to find security by ISIN
            security = self._find_security_by_isin(isin)
            if security:
                cache[isin] = security
                found_count += 1
            else:
                # Create a placeholder security using ISIN as the label
                if not dry_run:
                    security = self._create_placeholder_security(isin)
                    if security:
                        cache[isin] = security
                        created_count += 1
                else:
                    # For dry run, create a mock entry
                    cache[isin] = {
                        'security_name': isin,
                        'isin': isin,
                        'currency_code': None
                    }
                    created_count += 1

        self.stdout.write(f'  Securities found: {found_count}')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'  Securities to create: {created_count}'))
        else:
            self.stdout.write(f'  Securities created: {created_count}')
        self.stdout.write(f'  Total cached: {len(cache)}')

        return cache

    def _find_security_by_isin(self, isin: str) -> Optional[Dict[str, Any]]:
        """Find a security by ISIN in cis_security_kudu."""
        try:
            safe_isin = self._escape_string(isin)
            query = f"""
                SELECT security_id, security_name, isin, currency_code, country_of_incorporation
                FROM {DATABASE}.cis_security_kudu
                WHERE isin = '{safe_isin}'
                LIMIT 1
            """
            results = impala_manager.execute_query(query, database=DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f'Error finding security by ISIN {isin}: {str(e)}')
            return None

    def _create_placeholder_security(self, isin: str) -> Optional[Dict[str, Any]]:
        """Create a placeholder security using ISIN as the security name."""
        try:
            timestamp = int(datetime.now().timestamp() * 1000)
            security_id = timestamp + (uuid.uuid4().int % 1000)
            safe_isin = self._escape_string(isin)
            created_at = timestamp

            query = f"""
                UPSERT INTO {DATABASE}.cis_security_kudu
                (security_id, security_name, isin, is_active, status,
                 created_by, created_at, updated_by, updated_at)
                VALUES (
                    {security_id},
                    '{safe_isin}',
                    '{safe_isin}',
                    true,
                    'ACTIVE',
                    'SYSTEM',
                    {created_at},
                    'SYSTEM',
                    {created_at}
                )
            """
            success = impala_manager.execute_write(query, database=DATABASE)
            if success:
                return {
                    'security_id': security_id,
                    'security_name': isin,
                    'isin': isin,
                    'currency_code': None
                }
            return None
        except Exception as e:
            logger.error(f'Error creating placeholder security for {isin}: {str(e)}')
            return None

    def _upload_position(self, row: pd.Series, security_cache: Dict[str, Dict[str, Any]],
                         dry_run: bool, row_num: int, total_rows: int) -> str:
        """Upload a single position row to cis_trade_position and cis_trade_position_history."""
        isin = str(row.get('isin', '')).strip() if pd.notna(row.get('isin')) else ''
        portfolio_code = str(row.get('portfolio_code', '')).strip() if pd.notna(row.get('portfolio_code')) else ''

        if not isin or not portfolio_code:
            self.stdout.write(self.style.WARNING(f'  Row {row_num}: Skipping - missing ISIN or portfolio_code'))
            return 'skipped'

        # Get security info from cache
        security = security_cache.get(isin, {})
        security_label = security.get('security_name', isin)

        # Progress indicator
        if row_num % 10 == 0 or row_num == total_rows:
            self.stdout.write(f'  Processing row {row_num}/{total_rows}: {portfolio_code}/{isin[:12]}...')

        # Generate IDs
        timestamp = int(datetime.now().timestamp() * 1000)
        position_id = timestamp + (uuid.uuid4().int % 1000)
        version_id = timestamp + (uuid.uuid4().int % 10000)

        # Extract values from row
        position_data = self._extract_position_data(row, security, portfolio_code, position_id, version_id)

        if dry_run:
            return 'success'

        # Insert into cis_trade_position
        success = self._insert_position(position_data)
        if not success:
            self.stderr.write(self.style.ERROR(f'  Row {row_num}: Failed to insert position'))
            return 'error'

        # Insert into cis_trade_position_history
        success = self._insert_position_history(position_data)
        if not success:
            self.stderr.write(self.style.WARNING(f'  Row {row_num}: Position created but history insert failed'))

        return 'success'

    def _extract_position_data(self, row: pd.Series, security: Dict[str, Any],
                               portfolio_code: str, position_id: int, version_id: int) -> Dict[str, Any]:
        """Extract and normalize position data from Excel row."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        position_date = datetime.now().strftime('%Y-%m-%d')

        # Parse valuation date
        valuation_date = None
        if pd.notna(row.get('valuation_date')):
            val_date = row.get('valuation_date')
            if isinstance(val_date, datetime):
                valuation_date = val_date.strftime('%Y-%m-%d')
            else:
                valuation_date = str(val_date)

        isin = str(row.get('isin', '')).strip() if pd.notna(row.get('isin')) else ''
        security_label = security.get('security_name', isin)

        return {
            'version_id': version_id,
            'position_id': position_id,
            'position_date': valuation_date or position_date,
            'portfolio_short_name': portfolio_code,
            'security_label': security_label,
            'quantity': self._to_decimal(row.get('quantity'), 0),
            'average_cost': self._to_decimal(row.get('cost_unit_price'), 0),
            'total_cost': self._to_decimal(row.get('cost_value_local'), 0),
            'realized_pnl': Decimal('0'),
            'current_price': self._to_decimal(row.get('market_unit_price'), 0),
            'market_value': self._to_decimal(row.get('market_value_local'), 0),
            'unrealized_pnl': self._to_decimal(row.get('unrealized_pnl_local'), 0),
            'trade_id': 0,
            'trade_type': 'INITIAL_LOAD',
            'status': 'OPEN',
            'is_active': True,
            'created_by': 'AMSICEQ_UPLOAD',
            'created_at': timestamp,
            # New columns
            'src_system': 'AMSICEQ',
            'security_currency': str(row.get('security_currency', '')).strip() if pd.notna(row.get('security_currency')) else None,
            'portfolio_currency': self.PORTFOLIO_CURRENCY,
            'pct_ratio': self._to_decimal(row.get('pct_ratio'), None),
            'isin': isin,
            'country': str(row.get('country', '')).strip() if pd.notna(row.get('country')) else None,
            'asset_class': str(row.get('asset_class', '')).strip() if pd.notna(row.get('asset_class')) else None,
            'listing_status': str(row.get('listing_status', '')).strip() if pd.notna(row.get('listing_status')) else None,
            'cost_value_local': self._to_decimal(row.get('cost_value_local'), None),
            'cost_value_base': self._to_decimal(row.get('cost_value_base'), None),
            'market_value_local': self._to_decimal(row.get('market_value_local'), None),
            'market_value_base': self._to_decimal(row.get('market_value_base'), None),
            'unrealized_pnl_local': self._to_decimal(row.get('unrealized_pnl_local'), None),
            'unrealized_pnl_base': self._to_decimal(row.get('unrealized_pnl_base'), None),
            'valuation_date': valuation_date,
            'market_unit_price': self._to_decimal(row.get('market_unit_price'), None),
        }

    def _to_decimal(self, value, default) -> Optional[Decimal]:
        """Convert value to Decimal, returning default on failure."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return default

    def _insert_position(self, data: Dict[str, Any]) -> bool:
        """
        Insert position record into cis_trade_position.

        position_id/version_id here are timestamp+random (not a deterministic
        natural-key hash), so re-uploading the same portfolio/security/date
        always creates a brand-new PK row. Without explicitly retiring the
        prior is_latest=true row for this natural key first, a reupload would
        leave two simultaneous is_latest=true rows for the same position.
        """
        try:
            self._retire_prior_latest(
                data['portfolio_short_name'], data['security_label'], data['position_date']
            )
            query = f"""
                UPSERT INTO {DATABASE}.cis_trade_position
                (version_id, position_id, position_date, portfolio_short_name, security_label,
                 quantity, average_cost, total_cost, realized_pnl, current_price, market_value, unrealized_pnl,
                 trade_id, trade_type, status, is_active, is_latest, created_by, created_at,
                 src_system, security_currency, portfolio_currency, pct_ratio, isin,
                 country, asset_class, listing_status,
                 cost_value_local, cost_value_base, market_value_local, market_value_base,
                 unrealized_pnl_local, unrealized_pnl_base, valuation_date, market_unit_price)
                VALUES (
                    {data['version_id']}, {data['position_id']},
                    '{self._escape_string(data['position_date'])}',
                    '{self._escape_string(data['portfolio_short_name'])}',
                    '{self._escape_string(data['security_label'])}',
                    {data['quantity']}, {data['average_cost']}, {data['total_cost']},
                    {data['realized_pnl']}, {data['current_price']}, {data['market_value']}, {data['unrealized_pnl']},
                    {data['trade_id']}, '{data['trade_type']}',
                    '{data['status']}', {str(data['is_active']).lower()}, true,
                    '{data['created_by']}', '{data['created_at']}',
                    {self._format_nullable_string(data.get('src_system'))},
                    {self._format_nullable_string(data.get('security_currency'))},
                    {self._format_nullable_string(data.get('portfolio_currency'))},
                    {self._format_nullable_decimal(data.get('pct_ratio'))},
                    {self._format_nullable_string(data.get('isin'))},
                    {self._format_nullable_string(data.get('country'))},
                    {self._format_nullable_string(data.get('asset_class'))},
                    {self._format_nullable_string(data.get('listing_status'))},
                    {self._format_nullable_decimal(data.get('cost_value_local'))},
                    {self._format_nullable_decimal(data.get('cost_value_base'))},
                    {self._format_nullable_decimal(data.get('market_value_local'))},
                    {self._format_nullable_decimal(data.get('market_value_base'))},
                    {self._format_nullable_decimal(data.get('unrealized_pnl_local'))},
                    {self._format_nullable_decimal(data.get('unrealized_pnl_base'))},
                    {self._format_nullable_string(data.get('valuation_date'))},
                    {self._format_nullable_decimal(data.get('market_unit_price'))}
                )
            """
            return impala_manager.execute_write(query, database=DATABASE)
        except Exception as e:
            logger.error(f'Error inserting position: {str(e)}')
            return False

    def _retire_prior_latest(self, portfolio_short_name: str, security_label: str, position_date: str) -> None:
        """Mark any existing is_latest=true row for this natural key+date as false before inserting."""
        try:
            impala_manager.execute_write(
                f"""
                UPDATE {DATABASE}.cis_trade_position
                SET is_latest = false
                WHERE portfolio_short_name = '{self._escape_string(portfolio_short_name)}'
                  AND security_label       = '{self._escape_string(security_label)}'
                  AND position_date        = '{self._escape_string(position_date)}'
                  AND is_latest = true
                """,
                database=DATABASE
            )
        except Exception as e:
            logger.warning(f'Could not retire prior is_latest row (non-fatal): {str(e)}')

    def _insert_position_history(self, data: Dict[str, Any]) -> bool:
        """Insert position history record into cis_trade_position_history."""
        try:
            history_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

            query = f"""
                UPSERT INTO {DATABASE}.cis_trade_position_history
                (history_id, version_id, position_id, position_date, portfolio_short_name, security_label,
                 quantity, average_cost, total_cost, realized_pnl, current_price, market_value, unrealized_pnl,
                 trade_id, trade_type, status, is_active, created_by, created_at,
                 change_type, change_timestamp,
                 src_system, security_currency, portfolio_currency, pct_ratio, isin,
                 country, asset_class, listing_status,
                 cost_value_local, cost_value_base, market_value_local, market_value_base,
                 unrealized_pnl_local, unrealized_pnl_base, valuation_date, market_unit_price)
                VALUES (
                    {history_id}, {data['version_id']}, {data['position_id']},
                    '{self._escape_string(data['position_date'])}',
                    '{self._escape_string(data['portfolio_short_name'])}',
                    '{self._escape_string(data['security_label'])}',
                    {data['quantity']}, {data['average_cost']}, {data['total_cost']},
                    {data['realized_pnl']}, {data['current_price']}, {data['market_value']}, {data['unrealized_pnl']},
                    {data['trade_id']}, '{data['trade_type']}',
                    '{data['status']}', {str(data['is_active']).lower()},
                    '{data['created_by']}', '{data['created_at']}',
                    'INITIAL_LOAD', '{data['created_at']}',
                    {self._format_nullable_string(data.get('src_system'))},
                    {self._format_nullable_string(data.get('security_currency'))},
                    {self._format_nullable_string(data.get('portfolio_currency'))},
                    {self._format_nullable_decimal(data.get('pct_ratio'))},
                    {self._format_nullable_string(data.get('isin'))},
                    {self._format_nullable_string(data.get('country'))},
                    {self._format_nullable_string(data.get('asset_class'))},
                    {self._format_nullable_string(data.get('listing_status'))},
                    {self._format_nullable_decimal(data.get('cost_value_local'))},
                    {self._format_nullable_decimal(data.get('cost_value_base'))},
                    {self._format_nullable_decimal(data.get('market_value_local'))},
                    {self._format_nullable_decimal(data.get('market_value_base'))},
                    {self._format_nullable_decimal(data.get('unrealized_pnl_local'))},
                    {self._format_nullable_decimal(data.get('unrealized_pnl_base'))},
                    {self._format_nullable_string(data.get('valuation_date'))},
                    {self._format_nullable_decimal(data.get('market_unit_price'))}
                )
            """
            return impala_manager.execute_write(query, database=DATABASE)
        except Exception as e:
            logger.error(f'Error inserting position history: {str(e)}')
            return False

    def _escape_string(self, value) -> str:
        """Escape single quotes for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def _format_nullable_string(self, value) -> str:
        """Format a nullable string value for SQL."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 'NULL'
        return f"'{self._escape_string(value)}'"

    def _format_nullable_decimal(self, value) -> str:
        """Format a nullable decimal value for SQL."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 'NULL'
        return str(value)
