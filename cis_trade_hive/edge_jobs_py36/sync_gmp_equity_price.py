"""
Django-free Management Command: Sync GMP Equity Prices

Reads daily equity price data from the GMP source table
(gmp_cis_sta_dly_equity_prices), joined against gmp_cis_sta_dly_security for
currency_code/isin, and upserts into cis_equity_price.

GMP table columns (gmp_cis_sta_dly_equity_prices):
    security          - Security label (joins to gmp_cis_sta_dly_security.security_label)
    `date`            - Price date (YYYYMMDD string)
    main_closing_price - Closing price
    processing_date   - GMP processing date (YYYYMMDD)

Usage:
    python sync_gmp_equity_price.py --env SIT --processing-date 20260302
    python sync_gmp_equity_price.py --dry-run --verbose
    python sync_gmp_equity_price.py --full-sync   # no-op here (UPSERT is always idempotent)

Run schedule: Daily after GMP EOD price ETL job completes.

Pipeline:
    GMP ETL -> gmp_cis_sta_dly_equity_prices (+ gmp_cis_sta_dly_security for currency/isin)
                   |  (this command)
           cis_equity_price (src_system='GMP')
"""

import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _apply_early_env_override(argv):
    """--env must be applied before importing lib.config/lib.impala_connection
    below -- see sync_gmp_corporate_actions.py for the full rationale."""
    for i, arg in enumerate(argv):
        if arg == '--env' and i + 1 < len(argv):
            os.environ['CIS_ENV'] = argv[i + 1].upper()
            return
        if arg.startswith('--env='):
            os.environ['CIS_ENV'] = arg.split('=', 1)[1].upper()
            return


_apply_early_env_override(sys.argv)

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from lib.management_base import BaseCommand, CommandError, run_command

from lib.impala_connection import impala_manager
from lib.equity_price_repository import equity_price_repository, EquityPriceRepository
from lib.config import settings

logger = logging.getLogger(__name__)

GMP_DATABASE = settings.IMPALA_CONFIG['DATABASE']
GMP_SOURCE_TABLE = 'gmp_cis_sta_dly_equity_prices'
GMP_SECURITY_TABLE = 'gmp_cis_sta_dly_security'


def parse_gmp_price(price_val: Any) -> Optional[Decimal]:
    """Parse GMP price field into Decimal. Returns None if invalid."""
    if price_val is None or str(price_val).strip() in ('', 'None', 'null', 'NULL'):
        return None
    try:
        return Decimal(str(price_val).strip())
    except InvalidOperation:
        return None


def parse_gmp_price_date(date_val: Any) -> Optional[str]:
    """Parse GMP `date` field (YYYYMMDD) into YYYY-MM-DD."""
    if not date_val:
        return None
    s = str(date_val).strip()
    if len(s) == 8 and s.isdigit():
        return f'{s[0:4]}-{s[4:6]}-{s[6:8]}'
    # Already YYYY-MM-DD or another recognisable form — pass through as-is,
    # _process_row() will reject anything that doesn't look like a date.
    return s if len(s) == 10 and s[4] == '-' and s[7] == '-' else None


class Command(BaseCommand):
    help = 'Sync equity prices from GMP source table into cis_equity_price'

    def add_arguments(self, parser):
        parser.add_argument(
            '--env',
            type=str,
            default=None,
            choices=['LOCAL', 'SIT', 'UAT', 'PROD', 'DR'],
            help=(
                'Override CIS_ENV (Impala host/port/auth) for this run. '
                'NOTE: read directly from sys.argv before argparse runs '
                '(see _apply_early_env_override) -- declared here only so '
                'it shows up in --help and gets validated.'
            )
        )
        parser.add_argument(
            '--database',
            type=str,
            default=None,
            help='Override target Kudu database name (default: from CIS_ENV config, e.g. gmp_cis)'
        )
        parser.add_argument(
            '-d', '--date', '--processing-date',
            dest='date',
            type=str,
            default=None,
            help='Filter GMP records by processing_date (YYYY-MM-DD or YYYYMMDD). Default: latest available'
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Preview what would be synced without writing anything'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print each record processed'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='GMP_ETL',
            help='User name to record as creator. Default: GMP_ETL'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=2000,
            help='Records per batch fetch from GMP table. Default: 2000'
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        global GMP_DATABASE

        env_override = options.get('env')
        database_override = options.get('database')
        processing_date = options['date']
        dry_run = options['dry_run']
        verbose = options['verbose']
        run_by = options['user']
        batch_size = options['batch_size']

        if database_override:
            GMP_DATABASE = database_override
            EquityPriceRepository.DATABASE = database_override

        self._print_header(processing_date, dry_run, run_by, env_override, database_override)

        gmp_records = self._fetch_gmp_records(processing_date, batch_size)
        self.stdout.write(f'GMP records fetched  : {len(gmp_records)}')

        if not gmp_records:
            self.stdout.write(self.style.WARNING('No GMP equity price records found. Exiting.'))
            return

        stats = {'upserted': 0, 'skipped_invalid': 0, 'errors': 0}
        errors = []

        for row in gmp_records:
            result = self._process_row(row, run_by, dry_run, verbose)
            stats[result['outcome']] += 1
            if result.get('error'):
                errors.append(result['error'])

        self._print_summary(stats, errors, dry_run)

    # ------------------------------------------------------------------
    # Fetch from GMP source table (LEFT JOIN security for currency/isin)
    # ------------------------------------------------------------------
    def _fetch_gmp_records(self, processing_date: Optional[str], batch_size: int) -> List[Dict[str, Any]]:
        try:
            query = f"""
            SELECT
                eq.security             AS security_label,
                eq.`date`                AS price_date_raw,
                eq.main_closing_price   AS main_closing_price,
                eq.processing_date      AS processing_date,
                seu.currency_code       AS currency_code,
                seu.isin                AS isin
            FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE} eq
            LEFT JOIN {GMP_DATABASE}.{GMP_SECURITY_TABLE} seu
                ON eq.security = seu.security_label
            WHERE eq.security NOT LIKE '%LOG DEL%'
            """

            if processing_date:
                pd = processing_date.replace('-', '')
                query += f" AND CAST(eq.processing_date AS STRING) = '{pd}'"

            query += f" ORDER BY eq.processing_date ASC LIMIT {batch_size}"

            result = impala_manager.execute_query(query, database=GMP_DATABASE)
            return result if result else []

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error fetching GMP records: {e}'))
            logger.error(f'Error fetching GMP records: {e}')
            return []

    # ------------------------------------------------------------------
    # Process a single GMP row
    # ------------------------------------------------------------------
    def _process_row(self, row: Dict[str, Any], run_by: str, dry_run: bool, verbose: bool) -> Dict[str, Any]:
        security_label = row.get('security_label', '')
        currency_code = row.get('currency_code', '')
        price_date = parse_gmp_price_date(row.get('price_date_raw'))
        price = parse_gmp_price(row.get('main_closing_price'))

        if not security_label:
            msg = 'Skipping row: missing security label'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if not price_date:
            msg = f'Skipping {security_label}: unparseable date={row.get("price_date_raw")!r}'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if price is None:
            msg = f'Skipping {security_label}: invalid price={row.get("main_closing_price")!r}'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if not currency_code:
            # LEFT JOIN miss — security not found in gmp_cis_sta_dly_security.
            # Don't silently write a NULL-currency row (breaks the composite
            # key semantics downstream); skip and surface it instead.
            msg = f'Skipping {security_label}: no currency_code match in {GMP_SECURITY_TABLE}'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if verbose:
            self.stdout.write(f'  [SYNC] {security_label} | {currency_code} | {price_date} | {price}')

        if dry_run:
            return {'outcome': 'upserted'}

        equity_price_data = {
            'currency_code':  currency_code,
            'security_label': security_label,
            'isin':            row.get('isin'),
            'price_date':      price_date,
            'main_closing_price': price,
            'price_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'src_system':       'GMP',
            'created_by':       run_by,
            'updated_by':       run_by,
            'updated_at':       datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        try:
            success = equity_price_repository.upsert(equity_price_data)
        except Exception as e:
            msg = f'DB error upserting {security_label}: {e}'
            logger.error(msg)
            return {'outcome': 'errors', 'error': msg}

        if not success:
            msg = f'Upsert failed for {security_label}'
            return {'outcome': 'errors', 'error': msg}

        return {'outcome': 'upserted'}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _print_header(self, processing_date, dry_run, run_by, env_override=None, database_override=None):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — GMP Equity Price Sync'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Started      : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run by       : {run_by}')
        self.stdout.write(f'CIS_ENV      : {os.environ.get("CIS_ENV", "LOCAL")}' + (' (overridden)' if env_override else ''))
        self.stdout.write(f'Source table : {GMP_DATABASE}.{GMP_SOURCE_TABLE}')
        self.stdout.write(f'Target table : {GMP_DATABASE}.cis_equity_price' + (' (overridden)' if database_override else ''))
        if processing_date:
            self.stdout.write(f'Date filter  : {processing_date}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode         : DRY RUN (no writes)'))
        self.stdout.write('')

    def _print_summary(self, stats, errors, dry_run):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        self.stdout.write(self.style.HTTP_INFO('  Summary'))
        self.stdout.write(self.style.HTTP_INFO('─' * 70))
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Upserted into cis_equity_price : {stats["upserted"]}')
        self.stdout.write(f'Skipped (invalid)               : {stats["skipped_invalid"]}')
        self.stdout.write(f'Errors                          : {stats["errors"]}')

        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors:'))
            for e in errors[:20]:
                self.stdout.write(self.style.ERROR(f'  • {e}'))
            if len(errors) > 20:
                self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 20} more'))

        self.stdout.write('')
        self.stdout.write(f'Finished     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))


if __name__ == '__main__':
    run_command(Command)
