"""
Django Management Command: Create SOD Snapshot

Creates Start-of-Day (SOD) position rows in cis_position by copying the
previous business day's EOD rows and stamping them with today's business date.

Date logic (from gmp_cis_sta_dly_alldatesinfo):
  - src_system='gmp', sub_system='cis', data_frq='dly', record_type='D'
  - prev_day          → find EOD rows with this position_date  (e.g. 20260226)
  - contextual_today  → SOD rows get this as position_date     (e.g. 20260302)

Dates in the reference table are YYYYMMDD strings; converted to YYYY-MM-DD
for cis_position.

Usage:
    python manage.py create_sod_snapshot
    python manage.py create_sod_snapshot --dry-run
    python manage.py create_sod_snapshot --portfolio UOB-SG-TRADING
    python manage.py create_sod_snapshot --source CIS
"""

import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
ALL_SOURCES = ['CIS', 'GMP', 'AMSICEQ', 'USER_UPLOAD']


class Command(BaseCommand):
    help = 'Create SOD snapshot: copy previous EOD rows as SOD rows for today'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be written without making changes')
        parser.add_argument('--portfolio', type=str,
                            help='Limit to a single portfolio (optional)')
        parser.add_argument(
            '--source', type=str, choices=ALL_SOURCES,
            help='Limit to one source system: CIS, GMP, AMSICEQ, USER_UPLOAD (default: all)'
        )

    def handle(self, *args, **options):
        dry_run        = options.get('dry_run', False)
        portfolio_filter = options.get('portfolio')
        source_filter  = options.get('source')

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('SOD Snapshot — cis_position'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written'))
        self.stdout.write('')

        # ── 1. Get business dates from reference table ──────────────────────
        today_yyyymmdd, prev_yyyymmdd = self._get_business_dates()
        if not today_yyyymmdd or not prev_yyyymmdd:
            raise CommandError(
                'Could not read business dates from gmp_cis_sta_dly_alldatesinfo'
            )

        sod_date = self._to_iso(today_yyyymmdd)   # SOD position_date  e.g. 2026-03-02
        eod_date = self._to_iso(prev_yyyymmdd)    # source EOD date    e.g. 2026-02-26
        proc_date = today_yyyymmdd                 # processing_date stays YYYYMMDD

        self.stdout.write(f"Business date (contextual_today) : {today_yyyymmdd}  →  SOD position_date = {sod_date}")
        self.stdout.write(f"Previous day  (prev_day)         : {prev_yyyymmdd}  →  source EOD date   = {eod_date}")
        self.stdout.write('')

        # ── 2. Fetch EOD rows for prev_day ───────────────────────────────────
        sources = [source_filter] if source_filter else ALL_SOURCES
        eod_rows = self._get_eod_rows(eod_date, sources, portfolio_filter)

        if not eod_rows:
            self.stdout.write(self.style.WARNING(
                f'No EOD rows found for position_date={eod_date} — nothing to snapshot'
            ))
            return

        self.stdout.write(f"Found {len(eod_rows)} EOD row(s) to copy as SOD")

        if dry_run:
            for r in eod_rows[:10]:
                self.stdout.write(
                    f"  [DRY RUN] SOD  {r.get('portfolio')}/{r.get('security_label')}  "
                    f"basis={r.get('position_basis')}  qty={r.get('quantity')}"
                )
            if len(eod_rows) > 10:
                self.stdout.write(f"  ... and {len(eod_rows) - 10} more")
            self.stdout.write(self.style.WARNING('\nDRY RUN — no changes written'))
            return

        # ── 3. Delete any existing SOD rows for sod_date ────────────────────
        self._delete_existing_sod(sod_date, sources, portfolio_filter)

        # ── 4. Batch-insert SOD rows ─────────────────────────────────────────
        inserted = self._batch_insert_sod(eod_rows, sod_date, proc_date)

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.SUCCESS(f'SOD snapshot complete — {inserted} row(s) inserted'))

    # ── Business date lookup ─────────────────────────────────────────────────

    def _get_business_dates(self):
        """
        Return (contextual_today, prev_day) as YYYYMMDD strings from the
        gmp_cis_sta_dly_alldatesinfo reference table.
        """
        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT contextual_today, prev_day
                FROM {DATABASE}.gmp_cis_sta_dly_alldatesinfo
                WHERE src_system   = 'gmp'
                  AND sub_system   = 'cis'
                  AND data_frq     = 'dly'
                  AND record_type  = 'D'
                LIMIT 1
                """,
                database=DATABASE
            )
            if rows:
                return rows[0].get('contextual_today'), rows[0].get('prev_day')
        except Exception as e:
            logger.error(f'Error reading business dates: {e}')
        return None, None

    # ── EOD row fetch ─────────────────────────────────────────────────────────

    def _get_eod_rows(self, eod_date, sources, portfolio_filter):
        """Fetch all EOD rows from cis_position for the given date."""
        src_list = ', '.join(f"'{self._escape(s)}'" for s in sources)
        port_clause = (
            f"AND portfolio = '{self._escape(portfolio_filter)}'"
            if portfolio_filter else ''
        )
        try:
            return impala_manager.execute_query(
                f"""
                SELECT
                    position_id, version_id,
                    portfolio, security_label,
                    position_basis, position_date,
                    src_system, processing_date,
                    quantity,
                    average_cost_fc, cost_fc,
                    average_cost_lc, cost_lc,
                    market_value_fc, market_value_lc,
                    net_book_value_fc, net_book_value_lc,
                    unrealized_pnl_fc, unrealized_pnl_lc,
                    realized_pnl_fc, realized_pnl_lc,
                    provision_fc, provision_lc,
                    dividend_fc, dividend_lc,
                    uncall_fc, uncall_lc,
                    pipeline_fc, pipeline_lc,
                    position_type, isin, source_table
                FROM {DATABASE}.cis_position
                WHERE position_type = 'EOD'
                  AND position_date  = '{eod_date}'
                  AND src_system IN ({src_list})
                  {port_clause}
                """,
                database=DATABASE
            ) or []
        except Exception as e:
            logger.error(f'Error fetching EOD rows for {eod_date}: {e}')
            raise

    # ── Delete existing SOD rows ─────────────────────────────────────────────

    def _delete_existing_sod(self, sod_date, sources, portfolio_filter):
        """Remove any SOD rows already written for sod_date (idempotent re-run)."""
        src_list = ', '.join(f"'{self._escape(s)}'" for s in sources)
        port_clause = (
            f"AND portfolio = '{self._escape(portfolio_filter)}'"
            if portfolio_filter else ''
        )
        try:
            impala_manager.execute_write(
                f"""
                DELETE FROM {DATABASE}.cis_position
                WHERE position_type = 'SOD'
                  AND position_date  = '{sod_date}'
                  AND src_system IN ({src_list})
                  {port_clause}
                """,
                database=DATABASE
            )
            self.stdout.write(f'Cleared existing SOD rows for {sod_date}')
        except Exception as e:
            logger.error(f'Error deleting existing SOD rows: {e}')
            raise

    # ── Batch INSERT ─────────────────────────────────────────────────────────

    def _batch_insert_sod(self, eod_rows, sod_date, proc_date):
        """Insert SOD rows in batches of 500. Returns total rows inserted."""
        BATCH = 500
        now_ms = int(datetime.now().timestamp() * 1000)

        col_list = """(
            position_id, version_id,
            portfolio, security_label, position_basis, position_date,
            src_system, processing_date,
            quantity,
            average_cost_fc, cost_fc,
            average_cost_lc, cost_lc,
            market_value_fc, market_value_lc,
            net_book_value_fc, net_book_value_lc,
            unrealized_pnl_fc, unrealized_pnl_lc,
            realized_pnl_fc, realized_pnl_lc,
            provision_fc, provision_lc,
            dividend_fc, dividend_lc,
            uncall_fc, uncall_lc,
            pipeline_fc, pipeline_lc,
            position_type, isin, source_table
        )"""

        def _val(v, default=0):
            return float(v) if v is not None else float(default)

        def _build_row(idx, row):
            new_id   = now_ms + idx
            portfolio = self._escape(row.get('portfolio', ''))
            security  = self._escape(row.get('security_label', ''))
            pos_basis = self._escape(row.get('position_basis', 'TRADE_DATE'))
            src_sys   = self._escape(row.get('src_system', 'CIS'))
            isin_val  = f"'{self._escape(row['isin'])}'" if row.get('isin') else 'NULL'
            src_tbl   = f"'{self._escape(row['source_table'])}'" if row.get('source_table') else 'NULL'

            return (
                f"({new_id}, {new_id}, "
                f"'{portfolio}', '{security}', '{pos_basis}', '{sod_date}', "
                f"'{src_sys}', '{proc_date}', "
                f"{_val(row.get('quantity'))}, "
                f"{_val(row.get('average_cost_fc'))}, {_val(row.get('cost_fc'))}, "
                f"{_val(row.get('average_cost_lc'))}, {_val(row.get('cost_lc'))}, "
                f"{_val(row.get('market_value_fc'))}, {_val(row.get('market_value_lc'))}, "
                f"{_val(row.get('net_book_value_fc'))}, {_val(row.get('net_book_value_lc'))}, "
                f"{_val(row.get('unrealized_pnl_fc'))}, {_val(row.get('unrealized_pnl_lc'))}, "
                f"{_val(row.get('realized_pnl_fc'))}, {_val(row.get('realized_pnl_lc'))}, "
                f"{_val(row.get('provision_fc'))}, {_val(row.get('provision_lc'))}, "
                f"{_val(row.get('dividend_fc'))}, {_val(row.get('dividend_lc'))}, "
                f"{_val(row.get('uncall_fc'))}, {_val(row.get('uncall_lc'))}, "
                f"{_val(row.get('pipeline_fc'))}, {_val(row.get('pipeline_lc'))}, "
                f"'SOD', {isin_val}, {src_tbl})"
            )

        total = 0
        for i in range(0, len(eod_rows), BATCH):
            chunk = eod_rows[i: i + BATCH]
            values = ',\n'.join(_build_row(i + j, r) for j, r in enumerate(chunk))
            impala_manager.execute_write(
                f"INSERT INTO {DATABASE}.cis_position {col_list} VALUES {values}",
                database=DATABASE
            )
            total += len(chunk)
            self.stdout.write(f'  Inserted rows {i + 1}–{i + len(chunk)}')

        return total

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _escape(value):
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")

    @staticmethod
    def _to_iso(yyyymmdd):
        """Convert YYYYMMDD string to YYYY-MM-DD."""
        s = str(yyyymmdd).strip()
        if len(s) == 8:
            return f'{s[:4]}-{s[4:6]}-{s[6:]}'
        return s
