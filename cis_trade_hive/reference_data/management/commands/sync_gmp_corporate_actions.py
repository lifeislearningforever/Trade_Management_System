"""
Django Management Command: Sync GMP Corporate Actions

Reads corporate action data from the GMP source table
(gmp_cis_sfa_dly_corporate_action) and syncs new/updated records
into cis_corporate_actions, then queues them for cash flow processing.

GMP table columns:
    src_system        - 'gmp'
    sub_system        - 'cis'
    data_cat          - 'sta'
    data_frq          - 'dly'
    record_type       - 'D' (detail)
    ca_id             - GMP's CA identifier (used as ca_number: GMP-<ca_id>)
    security          - Security name/label
    ca_type           - GMP type code (e.g. 'Cash dividend', 'CLAS SP')
    announcement_date - Announcement date
    ex_date           - Ex-dividend date
    record_date       - Record date
    payment_date      - Payment date
    price             - Price/rate per unit
    status            - GMP processing status (e.g. 'VALIDATED')
    src_id            - Source table name (= 'gmp_cis_sfa_dly_corporate_action')
    processing_date   - GMP processing date (YYYYMMDD)

Usage:
    python manage.py sync_gmp_corporate_actions                        # Sync all unprocessed
    python manage.py sync_gmp_corporate_actions --date 2026-01-30      # Filter by processing_date
    python manage.py sync_gmp_corporate_actions --dry-run              # Preview without writing
    python manage.py sync_gmp_corporate_actions --full-sync            # Re-process all (ignore already synced)
    python manage.py sync_gmp_corporate_actions --verbose              # Verbose output

Run schedule: Daily after GMP ETL job completes (before EOD CA processing).

Pipeline:
    GMP ETL → gmp_cis_sfa_dly_corporate_action
                   ↓  (this command)
           cis_corporate_actions (src_system='GMP', status='VALIDATED')
                   ↓
           cis_ca_cash_flow_queue (PENDING)
                   ↓  (process_corporate_actions command)
           cis_cash_flow (one per portfolio holding the security)
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from django.core.management.base import BaseCommand

from core.repositories.impala_connection import impala_manager
from reference_data.repositories.corporate_action_repository import corporate_action_repository
from reference_data.services.ca_cash_flow_service import ca_cash_flow_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GMP CA type → CIS CA type mapping
# ---------------------------------------------------------------------------
GMP_CA_TYPE_MAP = {
    # Dividend variants
    'cash dividend':          'DIVIDEND',
    'dividend':               'DIVIDEND',
    'div':                    'DIVIDEND',
    'special dividend':       'SPECIAL_DIVIDEND',
    'special div':            'SPECIAL_DIVIDEND',

    # Interest / Coupon
    'interest':               'INTEREST',
    'coupon':                 'COUPON',
    'coupon payment':         'COUPON',

    # Return of Capital
    'roc':                    'ROC',
    'return of capital':      'ROC',
    'capital distribution':   'CAPITAL_DISTRIBUTION',

    # Bonus / Split
    'bonus issue':            'BONUS_ISSUE',
    'bonus':                  'BONUS_ISSUE',
    'stock split':            'STOCK_SPLIT',
    'split':                  'SPLIT',
    'reverse split':          'REVERSE_SPLIT',
    'consolidation':          'CONSOLIDATION',

    # Rights / Warrants
    'rights issue':           'RIGHTS_ISSUE',
    'rights entitlement':     'RIGHTS_ENTITLEMENT',
    'rights':                 'RIGHTS_ENTITLEMENT',
    'warrant':                'WARRANT_ENTITLEMENT',
    'warrant entitlement':    'WARRANT_ENTITLEMENT',

    # GMP specific codes
    'clas sp':                'SPECIAL_DIVIDEND',   # Classification Special
    'd':                      'DIVIDEND',
    'i':                      'INTEREST',
    'c':                      'COUPON',
    'b':                      'BONUS_ISSUE',
    's':                      'SPLIT',
}

# GMP date formats to try
GMP_DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y', '%m/%d/%Y']

GMP_DATABASE = 'gmp_cis'
GMP_SOURCE_TABLE = 'gmp_cis_sfa_dly_corporate_action'


def map_gmp_ca_type(gmp_type: str) -> Optional[str]:
    """Map a GMP CA type string to a CIS CA type constant."""
    if not gmp_type:
        return None
    return GMP_CA_TYPE_MAP.get(gmp_type.strip().lower())


def parse_gmp_date(date_str: Any) -> Optional[str]:
    """
    Parse a GMP date value into YYYY-MM-DD string.
    GMP dates can be strings in various formats or YYYYMMDD integers.
    Returns None if unparseable.
    """
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s or s in ('None', 'null', 'NULL', '0', ''):
        return None
    for fmt in GMP_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str!r}")
    return None


def parse_gmp_price(price_val: Any) -> Optional[Decimal]:
    """Parse GMP price/rate field into Decimal. Returns None if invalid."""
    if price_val is None or str(price_val).strip() in ('', 'None', 'null', 'NULL'):
        return None
    try:
        return Decimal(str(price_val).strip())
    except InvalidOperation:
        return None


class Command(BaseCommand):
    help = 'Sync corporate actions from GMP source table into cis_corporate_actions and queue for cash flow processing'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--date',
            type=str,
            default=None,
            help='Filter GMP records by processing_date (YYYY-MM-DD or YYYYMMDD). Default: all unprocessed'
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help='Preview what would be synced without writing anything'
        )
        parser.add_argument(
            '--full-sync',
            action='store_true',
            help='Re-process all GMP records, ignoring already-synced check'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print each record processed'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='SYSTEM',
            help='User name to record as creator. Default: SYSTEM'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Records per batch fetch from GMP table. Default: 500'
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        processing_date = options['date']
        dry_run = options['dry_run']
        full_sync = options['full_sync']
        verbose = options['verbose']
        run_by = options['user']
        batch_size = options['batch_size']

        self._print_header(processing_date, dry_run, run_by)

        # 1. Fetch GMP records
        gmp_records = self._fetch_gmp_records(processing_date, batch_size)
        self.stdout.write(f'GMP records fetched  : {len(gmp_records)}')

        if not gmp_records:
            self.stdout.write(self.style.WARNING('No GMP corporate action records found. Exiting.'))
            return

        # 2. Load already-synced GMP ca_numbers to avoid duplicates
        synced_numbers = set() if full_sync else self._get_synced_gmp_ca_numbers()
        self.stdout.write(f'Already synced       : {len(synced_numbers)} records (skipped)')

        # 3. Process each record
        stats = {'inserted': 0, 'skipped_duplicate': 0, 'skipped_invalid': 0,
                 'queued': 0, 'errors': 0}
        errors = []

        for row in gmp_records:
            result = self._process_row(row, synced_numbers, run_by, dry_run, verbose)
            stats[result['outcome']] += 1
            if result.get('queued'):
                stats['queued'] += 1
            if result.get('error'):
                errors.append(result['error'])

        self._print_summary(stats, errors, dry_run)

    # ------------------------------------------------------------------
    # Fetch from GMP source table
    # ------------------------------------------------------------------
    def _fetch_gmp_records(self, processing_date: Optional[str], batch_size: int) -> List[Dict[str, Any]]:
        """Read rows from gmp_cis_sfa_dly_corporate_action."""
        try:
            query = f"""
            SELECT
                src_system,
                sub_system,
                data_cat,
                data_frq,
                record_type,
                ca_id,
                security,
                ca_type,
                announcement_date,
                ex_date,
                record_date,
                payment_date,
                price,
                status,
                src_id,
                processing_date
            FROM {GMP_DATABASE}.{GMP_SOURCE_TABLE}
            WHERE 1=1
            """

            # Filter by processing_date if provided
            if processing_date:
                # Normalise: accept YYYY-MM-DD or YYYYMMDD
                pd = processing_date.replace('-', '')
                query += f" AND CAST(processing_date AS STRING) = '{pd}'"

            query += f" ORDER BY processing_date ASC LIMIT {batch_size}"

            result = impala_manager.execute_query(query, database=GMP_DATABASE)
            return result if result else []

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error fetching GMP records: {e}'))
            logger.error(f'Error fetching GMP records: {e}')
            return []

    # ------------------------------------------------------------------
    # Get already-synced GMP ca_numbers from cis_corporate_actions
    # ------------------------------------------------------------------
    def _get_synced_gmp_ca_numbers(self) -> set:
        """
        Return set of ca_number values already in cis_corporate_actions
        that were sourced from GMP (src_system='GMP').
        """
        try:
            query = """
            SELECT ca_number
            FROM gmp_cis.cis_corporate_actions
            WHERE src_system = 'GMP'
              AND (is_deleted = false OR is_deleted IS NULL)
            """
            result = impala_manager.execute_query(query, database=GMP_DATABASE)
            if result:
                return {row.get('ca_number') for row in result if row.get('ca_number')}
            return set()
        except Exception as e:
            logger.warning(f'Could not load synced GMP ca_numbers: {e}')
            return set()

    # ------------------------------------------------------------------
    # Process a single GMP row
    # ------------------------------------------------------------------
    def _process_row(
        self,
        row: Dict[str, Any],
        synced_numbers: set,
        run_by: str,
        dry_run: bool,
        verbose: bool
    ) -> Dict[str, Any]:
        """
        Map one GMP row → cis_corporate_actions + queue.

        Returns dict with keys: outcome, queued, error
        """
        gmp_ca_id = row.get('ca_id', '')
        gmp_security = row.get('security', '')
        gmp_ca_type_raw = row.get('ca_type', '')

        # Build the CIS ca_number: GMP-<ca_id>
        ca_number = f'GMP-{gmp_ca_id}' if gmp_ca_id else None

        # --- Validate mandatory fields ---
        if not ca_number:
            msg = f'Skipping row: missing ca_id — security={gmp_security}'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        if not gmp_security:
            msg = f'Skipping {ca_number}: missing security'
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        # Map CA type
        cis_ca_type = map_gmp_ca_type(gmp_ca_type_raw)
        if not cis_ca_type:
            msg = (f'Skipping {ca_number}: unknown ca_type={gmp_ca_type_raw!r}. '
                   f'Add it to GMP_CA_TYPE_MAP in sync_gmp_corporate_actions.py')
            if verbose:
                self.stdout.write(self.style.WARNING(f'  [INVALID] {msg}'))
            return {'outcome': 'skipped_invalid', 'error': msg}

        # --- Duplicate check ---
        if ca_number in synced_numbers:
            if verbose:
                self.stdout.write(f'  [SKIP] {ca_number} already synced')
            return {'outcome': 'skipped_duplicate'}

        # Parse dates
        ex_date = parse_gmp_date(row.get('ex_date'))
        record_date = parse_gmp_date(row.get('record_date'))
        payment_date = parse_gmp_date(row.get('payment_date'))
        announcement_date = parse_gmp_date(row.get('announcement_date'))

        # Parse price
        price = parse_gmp_price(row.get('price'))

        if verbose:
            self.stdout.write(
                f'  [SYNC] {ca_number} | {gmp_security} | {cis_ca_type} | '
                f'ex={ex_date} pay={payment_date} price={price}'
            )

        if dry_run:
            return {'outcome': 'inserted', 'queued': True}

        # --- Insert into cis_corporate_actions ---
        ca_data = {
            'ca_number':          ca_number,
            'ca_type':            cis_ca_type,
            'security_name':      gmp_security,
            'announcement_date':  announcement_date,
            'ex_date':            ex_date,
            'record_date':        record_date,
            'payment_date':       payment_date,
            'price':              str(price) if price is not None else None,
            'currency':           None,    # GMP table has no currency column; enrich if needed
            'src_system':         'GMP',
            'status':             'VALIDATED',  # GMP records are pre-validated; skip four-eyes
        }

        try:
            success, ca_id = corporate_action_repository.insert(ca_data, created_by=run_by)
        except Exception as e:
            msg = f'DB error inserting {ca_number}: {e}'
            logger.error(msg)
            return {'outcome': 'errors', 'error': msg}

        if not success:
            msg = f'Insert failed for {ca_number}'
            return {'outcome': 'errors', 'error': msg}

        # Mark as synced so subsequent rows in same batch don't re-insert
        synced_numbers.add(ca_number)

        # --- Queue for cash flow processing ---
        queued = False
        try:
            q_success, queue_id = ca_cash_flow_service.queue_ca_for_processing(
                ca_id=ca_id,
                ca_data=ca_data,
                username=run_by
            )
            queued = q_success
            if q_success and verbose:
                self.stdout.write(
                    self.style.SUCCESS(f'    → Queued (queue_id={queue_id})')
                )
            elif not q_success:
                logger.warning(f'CA {ca_number} inserted but not queued (may not require cash flow)')
        except Exception as e:
            logger.warning(f'Queue error for {ca_number}: {e}')

        return {'outcome': 'inserted', 'queued': queued}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _print_header(self, processing_date, dry_run, run_by):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — GMP Corporate Action Sync'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Started      : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Run by       : {run_by}')
        self.stdout.write(f'Source table : {GMP_DATABASE}.{GMP_SOURCE_TABLE}')
        self.stdout.write(f'Target table : gmp_cis.cis_corporate_actions')
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
        self.stdout.write(f'{prefix}Inserted into cis_corporate_actions : {stats["inserted"]}')
        self.stdout.write(f'{prefix}Queued for cash flow processing     : {stats["queued"]}')
        self.stdout.write(f'Skipped (already synced)             : {stats["skipped_duplicate"]}')
        self.stdout.write(f'Skipped (invalid/unmapped)           : {stats["skipped_invalid"]}')
        self.stdout.write(f'Errors                               : {stats["errors"]}')

        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors:'))
            for e in errors[:20]:
                self.stdout.write(self.style.ERROR(f'  • {e}'))
            if len(errors) > 20:
                self.stdout.write(self.style.ERROR(f'  ... and {len(errors) - 20} more'))

        self.stdout.write('')
        if stats['inserted'] > 0 and not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'✓ Sync complete. Run process_corporate_actions to generate cash flows.'
            ))
            self.stdout.write(self.style.SUCCESS(
                '  python manage.py process_corporate_actions'
            ))
        self.stdout.write(f'Finished     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
