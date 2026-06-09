"""
Django Management Command: Process Approved Cash Flows

EOD job that applies APPROVED user-created cash flows (src_system='CIS')
to cis_trade_position. Runs after process_corporate_actions and before
position reval (refresh_positions).

Logic per cash_flow_type (ALL types accumulate — SA confirmed 2026-06-09):
  UNCALL_COMMITMENT   → accumulate uncall_fc / uncall_lc
  PROVISION           → accumulate provision_fc / provision_lc
  PIPELINE            → accumulate pipeline_fc / pipeline_lc
  YTD_REALISE         → accumulate realized_pnl_fc / realized_pnl_lc
  DIVIDEND            → accumulate dividend_fc / dividend_lc
  CASH_DIVIDEND       → accumulate dividend_fc / dividend_lc
  INCOME_DISTRIBUTION → accumulate realized_pnl_fc / realized_pnl_lc
  CAPITAL_DISTRIBUTION→ AVP reduction: avp_new = avp_old - (amount_fc / qty)
  RETURN_OF_CAPITAL   → AVP reduction: avp_new = avp_old - (amount_fc / qty)
  OTHER               → skip (log warning)

send_receive sign convention (SA spec):
  SEND    → increase (positive)
  RECEIVE → decrease (negative)
  NULL    → treated as SEND (positive, logged)

Idempotency: once processed, position_updated=true is set on the cash flow
record so re-runs on the same date skip already-processed records.

Usage:
    python manage.py process_approved_cashflows
    python manage.py process_approved_cashflows --date 2026-06-09
    python manage.py process_approved_cashflows --date 2026-05-01  # backdated
    python manage.py process_approved_cashflows --dry-run
    python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING
"""

import logging
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError

from core.repositories.impala_connection import impala_manager
from trade.services.multicurrency_service import multicurrency_service

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
POSITION_TABLE = 'cis_trade_position'
CASH_FLOW_TABLE = 'cis_cash_flow'
PRECISION = Decimal('0.00000001')


def _escape(value: str) -> str:
    if value is None:
        return ''
    return str(value).replace("'", "''")


def _sign(send_receive: str, cf_number: str) -> Decimal:
    """SEND=+1, RECEIVE=-1, NULL=+1 (logged)."""
    sr = (send_receive or '').upper().strip()
    if sr == 'RECEIVE':
        return Decimal('-1')
    if not sr:
        logger.warning(f"[CF {cf_number}] send_receive is NULL — treating as SEND (positive)")
    return Decimal('1')


class Command(BaseCommand):
    help = 'Apply APPROVED user-created cash flows to positions (EOD job)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--date',
            type=str,
            default=None,
            help='Process cash flows up to and including this date (YYYY-MM-DD). Default: today'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without writing'
        )
        parser.add_argument(
            '--portfolio',
            type=str,
            default=None,
            help='Limit to a single portfolio short name'
        )
        parser.add_argument(
            '--reprocess',
            action='store_true',
            help='Re-process already-processed records (position_updated=true). Use for corrections.'
        )

    def handle(self, *args, **options):
        run_date = options['date'] or date.today().strftime('%Y-%m-%d')
        dry_run = options['dry_run']
        portfolio_filter = options['portfolio']
        reprocess = options['reprocess']

        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — Process Approved Cash Flows'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Run date  : {run_date}')
        self.stdout.write(f'Started   : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        if portfolio_filter:
            self.stdout.write(f'Portfolio : {portfolio_filter}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode      : DRY RUN — no writes'))
        if reprocess:
            self.stdout.write(self.style.WARNING('Mode      : REPROCESS — includes already-processed records'))
        self.stdout.write('')

        try:
            cash_flows = self._get_approved_cash_flows(run_date, portfolio_filter, reprocess)
        except Exception as e:
            raise CommandError(f'Failed to fetch cash flows: {e}')

        if not cash_flows:
            self.stdout.write(self.style.WARNING('No approved cash flows found to process'))
            return

        self.stdout.write(f'Found {len(cash_flows)} approved cash flow(s) to process\n')

        stats = {'processed': 0, 'skipped': 0, 'failed': 0, 'no_position': 0}

        for cf in cash_flows:
            cf_id = cf.get('cash_flow_id')
            cf_number = cf.get('cash_flow_number', str(cf_id))
            cf_type = (cf.get('cash_flow_type') or '').upper().strip()
            portfolio = cf.get('portfolio_short_name', '')
            security = cf.get('security_label', '')
            send_receive = cf.get('send_receive', '')
            amount_fc = Decimal(str(cf.get('foreign_ccy_amt') or cf.get('local_ccy_amt') or 0))
            amount_lc = Decimal(str(cf.get('local_ccy_amt') or 0))
            payment_date = cf.get('payment_date') or run_date

            self.stdout.write(
                f'  [{cf_number}] {cf_type} | {portfolio}/{security} | '
                f'{send_receive} | FC={amount_fc} LC={amount_lc}'
            )

            if cf_type == 'OTHER':
                self.stdout.write(self.style.WARNING(f'    → Skipping type OTHER'))
                stats['skipped'] += 1
                continue

            if not portfolio or not security:
                self.stdout.write(self.style.WARNING(f'    → Skipping: missing portfolio or security'))
                stats['skipped'] += 1
                continue

            try:
                success, message = self._apply_to_position(
                    cf=cf,
                    cf_type=cf_type,
                    portfolio=portfolio,
                    security=security,
                    amount_fc=amount_fc,
                    amount_lc=amount_lc,
                    send_receive=send_receive,
                    payment_date=payment_date,
                    dry_run=dry_run
                )
                if success:
                    self.stdout.write(self.style.SUCCESS(f'    ✓ {message}'))
                    if not dry_run:
                        self._mark_position_updated(cf_id)
                    stats['processed'] += 1
                else:
                    if 'No open position' in message:
                        self.stdout.write(self.style.WARNING(f'    ⚠ {message}'))
                        stats['no_position'] += 1
                    else:
                        self.stdout.write(self.style.ERROR(f'    ✗ {message}'))
                        stats['failed'] += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    ✗ Exception: {e}'))
                logger.exception(f'Error processing cash flow {cf_number}: {e}')
                stats['failed'] += 1

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  Summary'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.SUCCESS(f'  Processed    : {stats["processed"]}'))
        self.stdout.write(f'  No position  : {stats["no_position"]}')
        self.stdout.write(f'  Skipped      : {stats["skipped"]}')
        if stats['failed']:
            self.stdout.write(self.style.ERROR(f'  Failed       : {stats["failed"]}'))
        else:
            self.stdout.write(f'  Failed       : {stats["failed"]}')
        self.stdout.write(f'\nCompleted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    # =========================================================================
    # FETCH
    # =========================================================================

    def _get_approved_cash_flows(
        self,
        run_date: str,
        portfolio_filter: Optional[str],
        reprocess: bool
    ) -> List[Dict[str, Any]]:
        """
        Fetch APPROVED CIS cash flows where payment_date <= run_date.
        Excludes already-processed records unless --reprocess is set.
        """
        clauses = [
            "status = 'APPROVED'",
            "src_system = 'CIS'",
            "(is_deleted = false OR is_deleted IS NULL)",
            f"payment_date <= '{_escape(run_date)}'",
        ]
        if not reprocess:
            clauses.append("(position_updated = false OR position_updated IS NULL)")
        if portfolio_filter:
            clauses.append(f"portfolio_short_name = '{_escape(portfolio_filter)}'")

        query = f"""
        SELECT
            cash_flow_id, cash_flow_number,
            portfolio_short_name, security_label,
            cash_flow_type, send_receive,
            foreign_ccy, local_ccy,
            foreign_ccy_amt, local_ccy_amt,
            fx_rate,
            payment_date, value_date, ex_date
        FROM {DATABASE}.{CASH_FLOW_TABLE}
        WHERE {' AND '.join(clauses)}
        ORDER BY payment_date ASC, created_at ASC
        """
        results = impala_manager.execute_query(query, database=DATABASE)
        return results if results else []

    # =========================================================================
    # APPLY TO POSITION
    # =========================================================================

    def _apply_to_position(
        self,
        cf: Dict[str, Any],
        cf_type: str,
        portfolio: str,
        security: str,
        amount_fc: Decimal,
        amount_lc: Decimal,
        send_receive: str,
        payment_date: str,
        dry_run: bool
    ) -> Tuple[bool, str]:
        """Route to the correct position update logic based on cash flow type."""

        # Get current SETTLE_DATE position
        position = self._get_current_position(portfolio, security)
        if not position:
            return False, f'No open SETTLE_DATE position for {portfolio}/{security}'

        sign = _sign(send_receive, cf.get('cash_flow_number', ''))
        signed_fc = (amount_fc * sign).quantize(PRECISION, rounding=ROUND_HALF_UP)
        signed_lc = (amount_lc * sign).quantize(PRECISION, rounding=ROUND_HALF_UP)

        # --- ALL TYPES ACCUMULATE (SA confirmed 2026-06-09) ---
        if cf_type in ('UNCALL_COMMITMENT',):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='uncall_fc', lc_field='uncall_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        if cf_type in ('PROVISION',):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='provision_fc', lc_field='provision_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        if cf_type in ('PIPELINE',):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='pipeline_fc', lc_field='pipeline_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        if cf_type in ('YTD_REALISE',):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        # --- ACCUMULATE TYPES ---
        if cf_type in ('DIVIDEND', 'CASH_DIVIDEND'):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='dividend_fc', lc_field='dividend_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        if cf_type in ('INCOME_DISTRIBUTION',):
            return self._accumulate_field(
                position, portfolio, security, payment_date,
                fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                delta_fc=signed_fc, delta_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        # --- AVP REDUCTION TYPES ---
        if cf_type in ('RETURN_OF_CAPITAL', 'CAPITAL_DISTRIBUTION'):
            return self._reduce_avp(
                position, portfolio, security, payment_date,
                amount_fc=signed_fc, amount_lc=signed_lc,
                cf_type=cf_type, dry_run=dry_run
            )

        return False, f'Unrecognised cash flow type: {cf_type}'

    # =========================================================================
    # POSITION UPDATE HELPERS
    # =========================================================================

    def _accumulate_field(
        self,
        position: Dict[str, Any],
        portfolio: str,
        security: str,
        position_date: str,
        fc_field: str,
        lc_field: str,
        delta_fc: Decimal,
        delta_lc: Decimal,
        cf_type: str,
        dry_run: bool
    ) -> Tuple[bool, str]:
        """Add delta to existing FC/LC field (running total)."""
        old_fc = Decimal(str(position.get(fc_field, 0) or 0))
        old_lc = Decimal(str(position.get(lc_field, 0) or 0))
        new_fc = (old_fc + delta_fc).quantize(PRECISION, rounding=ROUND_HALF_UP)
        new_lc = (old_lc + delta_lc).quantize(PRECISION, rounding=ROUND_HALF_UP)

        if dry_run:
            return True, (
                f'[DRY RUN] {cf_type}: {fc_field} {old_fc} + {delta_fc} = {new_fc}'
            )

        overrides = {fc_field: float(new_fc), lc_field: float(new_lc)}
        success = self._write_new_position_version(
            position, portfolio, security, position_date, cf_type, overrides
        )
        if success:
            return True, f'{cf_type}: {fc_field} {old_fc} + {delta_fc} = {new_fc}'
        return False, f'{cf_type}: failed to write position version'

    def _reduce_avp(
        self,
        position: Dict[str, Any],
        portfolio: str,
        security: str,
        position_date: str,
        amount_fc: Decimal,
        amount_lc: Decimal,
        cf_type: str,
        dry_run: bool
    ) -> Tuple[bool, str]:
        """
        AVP reduction: avp_new = avp_old - (amount_fc / qty)
        Total cost recalculated from new AVP.
        """
        qty = Decimal(str(position.get('quantity', 0) or 0))
        if qty <= 0:
            return False, f'{cf_type}: quantity is 0, cannot reduce AVP'

        old_avp_fc = Decimal(str(position.get('average_cost_fc', 0) or 0))
        old_avp_lc = Decimal(str(position.get('average_cost_lc', 0) or 0))

        per_share_fc = (amount_fc / qty).quantize(PRECISION, rounding=ROUND_HALF_UP)
        per_share_lc = (amount_lc / qty).quantize(PRECISION, rounding=ROUND_HALF_UP)

        new_avp_fc = max(Decimal('0'), (old_avp_fc - per_share_fc).quantize(PRECISION, rounding=ROUND_HALF_UP))
        new_avp_lc = max(Decimal('0'), (old_avp_lc - per_share_lc).quantize(PRECISION, rounding=ROUND_HALF_UP))
        new_total_cost_fc = (new_avp_fc * qty).quantize(PRECISION, rounding=ROUND_HALF_UP)
        new_total_cost_lc = (new_avp_lc * qty).quantize(PRECISION, rounding=ROUND_HALF_UP)

        if dry_run:
            return True, (
                f'[DRY RUN] {cf_type}: avp_fc {old_avp_fc} - {per_share_fc} = {new_avp_fc} | '
                f'total_cost_fc → {new_total_cost_fc}'
            )

        overrides = {
            'average_cost_fc': float(new_avp_fc),
            'average_cost_lc': float(new_avp_lc),
            'total_cost_fc': float(new_total_cost_fc),
            'total_cost_lc': float(new_total_cost_lc),
        }
        success = self._write_new_position_version(
            position, portfolio, security, position_date, cf_type, overrides
        )
        if success:
            return True, f'{cf_type}: avp_fc {old_avp_fc} → {new_avp_fc}'
        return False, f'{cf_type}: failed to write position version'

    # =========================================================================
    # POSITION WRITE
    # =========================================================================

    def _write_new_position_version(
        self,
        current: Dict[str, Any],
        portfolio: str,
        security: str,
        position_date: str,
        cf_type: str,
        overrides: Dict[str, Any]
    ) -> bool:
        """
        Mark current version is_latest=false, insert new version with overrides applied.
        All other fields carried forward from current position.
        """
        try:
            old_version_id = current.get('version_id')
            position_id = current.get('position_id')

            # Mark old as not latest
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            impala_manager.execute_write(
                f"""UPDATE {DATABASE}.{POSITION_TABLE}
                    SET is_latest = false, updated_at = '{ts}'
                    WHERE version_id = {old_version_id}""",
                database=DATABASE
            )

            new_version_id = int(datetime.now().timestamp() * 1000)

            # Build field values: start from current, apply overrides
            def _v(field, default=0):
                if field in overrides:
                    return overrides[field]
                return current.get(field, default)

            def _s(field, default=''):
                val = current.get(field, default) or default
                return f"'{_escape(str(val))}'"

            def _f(field, default=0):
                val = _v(field, default)
                if val is None:
                    return 0.0
                return float(val)

            def _b(field, default=True):
                val = current.get(field, default)
                return 'true' if val else 'false'

            sql = f"""
            UPSERT INTO {DATABASE}.{POSITION_TABLE} (
                version_id, position_id, position_date, position_basis,
                portfolio_short_name, security_label,
                quantity,
                average_cost_fc, total_cost_fc,
                average_cost_lc, total_cost_lc,
                market_price, market_value_fc, market_value_lc,
                realized_pnl_fc, unrealized_pnl_fc,
                realized_pnl_lc, unrealized_pnl_lc,
                dividend_fc, dividend_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                commit_fc, commit_lc,
                provision_fc, provision_lc,
                position_type, trade_type,
                security_currency, portfolio_currency, fx_rate,
                status, is_active, is_latest,
                last_ca_id, last_ca_number, last_ca_type, last_ca_date,
                last_cash_flow_id, last_cash_flow_number,
                last_cash_flow_amount_fc, last_cash_flow_amount_lc,
                created_by, created_at, updated_by, updated_at
            ) VALUES (
                {new_version_id},
                {position_id},
                '{_escape(position_date)}',
                'SETTLE_DATE',
                '{_escape(portfolio)}',
                '{_escape(security)}',
                {_f('quantity')},
                {_f('average_cost_fc')},  {_f('total_cost_fc')},
                {_f('average_cost_lc')},  {_f('total_cost_lc')},
                {_f('market_price')},     {_f('market_value_fc')}, {_f('market_value_lc')},
                {_f('realized_pnl_fc')},  {_f('unrealized_pnl_fc')},
                {_f('realized_pnl_lc')},  {_f('unrealized_pnl_lc')},
                {_f('dividend_fc')},      {_f('dividend_lc')},
                {_f('uncall_fc')},        {_f('uncall_lc')},
                {_f('pipeline_fc')},      {_f('pipeline_lc')},
                {_f('commit_fc')},        {_f('commit_lc')},
                {_f('provision_fc')},     {_f('provision_lc')},
                {_s('position_type', 'NORMAL')},
                'CF_{_escape(cf_type)}',
                {_s('security_currency', '')},
                {_s('portfolio_currency', '')},
                {_f('fx_rate', 1)},
                'OPEN', true, true,
                {current.get('last_ca_id') or 'NULL'},
                {_s('last_ca_number', '')},
                {_s('last_ca_type', '')},
                {_s('last_ca_date', '')},
                {current.get('last_cash_flow_id') or 'NULL'},
                {_s('last_cash_flow_number', '')},
                {_f('last_cash_flow_amount_fc')},
                {_f('last_cash_flow_amount_lc')},
                'SYSTEM_CF', '{ts}',
                'SYSTEM_CF', '{ts}'
            )
            """
            return impala_manager.execute_write(sql, database=DATABASE)

        except Exception as e:
            logger.error(f'Error writing position version for {portfolio}/{security}: {e}')
            return False

    # =========================================================================
    # MARK PROCESSED
    # =========================================================================

    def _mark_position_updated(self, cash_flow_id: int) -> None:
        """Set position_updated=true on the cash flow record."""
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            impala_manager.execute_write(
                f"""UPDATE {DATABASE}.{CASH_FLOW_TABLE}
                    SET position_updated = true, updated_at = '{ts}'
                    WHERE cash_flow_id = {cash_flow_id}""",
                database=DATABASE
            )
        except Exception as e:
            logger.warning(f'Could not mark cash_flow {cash_flow_id} as position_updated: {e}')

    # =========================================================================
    # POSITION FETCH
    # =========================================================================

    def _get_current_position(
        self,
        portfolio: str,
        security: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest open SETTLE_DATE position for portfolio/security."""
        try:
            query = f"""
            SELECT *
            FROM {DATABASE}.{POSITION_TABLE}
            WHERE portfolio_short_name = '{_escape(portfolio)}'
              AND security_label = '{_escape(security)}'
              AND position_basis = 'SETTLE_DATE'
              AND status = 'OPEN'
              AND is_active = true
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f'Error fetching position for {portfolio}/{security}: {e}')
            return None
