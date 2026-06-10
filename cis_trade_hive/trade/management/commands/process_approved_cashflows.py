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

send_receive sign convention (global):
  SEND    → increase (positive)
  RECEIVE → decrease (negative)
  NULL    → treated as SEND (positive, logged)

Exception — DIVIDEND / CASH_DIVIDEND:
  RECEIVE → increase (fund received dividend)
  SEND    → decrease (fund distributed/paid out dividend)

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
POSITION_TABLE = 'cis_trade_position'   # versioned CIS ledger
GOLDEN_TABLE   = 'cis_position'         # golden copy (all sources)
CASH_FLOW_TABLE = 'cis_cash_flow'
PRECISION = Decimal('0.00000001')
DEFAULT_DP = 2


def _escape(value: str) -> str:
    if value is None:
        return ''
    return str(value).replace("'", "''")


def _sign(send_receive: str, cf_number: str) -> Decimal:
    """Global convention: SEND=+1, RECEIVE=-1, NULL=+1 (logged)."""
    sr = (send_receive or '').upper().strip()
    if sr == 'RECEIVE':
        return Decimal('-1')
    if not sr:
        logger.warning(f"[CF {cf_number}] send_receive is NULL — treating as SEND (positive)")
    return Decimal('1')


def _sign_dividend(send_receive: str, cf_number: str) -> Decimal:
    """Dividend convention: RECEIVE=+1 (fund got paid), SEND=-1 (fund paid out)."""
    sr = (send_receive or '').upper().strip()
    if sr == 'SEND':
        return Decimal('-1')
    if not sr:
        logger.warning(f"[CF {cf_number}] send_receive is NULL for DIVIDEND — treating as RECEIVE (positive)")
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
            # FIX: no fallback from local to foreign — zero is correct if foreign_ccy_amt is null
            amount_fc = Decimal(str(cf.get('foreign_ccy_amt') or 0))
            amount_lc = Decimal(str(cf.get('local_ccy_amt') or 0))
            payment_date = cf.get('payment_date') or run_date

            self.stdout.write(
                f'  [{cf_number}] {cf_type} | {portfolio}/{security} | '
                f'{send_receive} | FC={amount_fc} ({cf.get("foreign_ccy","")}) '
                f'LC={amount_lc} ({cf.get("local_ccy","")})'
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
        Fetch APPROVED or VALIDATED cash flows (src_system CIS or CA) where payment_date <= run_date.
        Excludes already-processed records unless --reprocess is set.
        """
        clauses = [
            "status IN ('APPROVED', 'VALIDATED')",
            "src_system IN ('CIS', 'CA')",
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
        """Route to the correct position update logic based on cash flow type.
        Applies CF to both TRADE_DATE and SETTLE_DATE position bases."""

        # Fetch positions for both bases; apply to each independently
        positions = self._get_current_positions(portfolio, security)
        if not positions:
            return False, f'No open position for {portfolio}/{security} in cis_trade_position or cis_position'

        cf_id = cf.get('cash_flow_id')
        cf_number = cf.get('cash_flow_number', str(cf_id))

        # Currency precision from reference tables (same approach as refresh_positions)
        sec_ccy  = self._get_security_currency(security)
        port_ccy = self._get_portfolio_currency(portfolio)
        fc_dp    = self._get_currency_dp(sec_ccy)
        lc_dp    = self._get_currency_dp(port_ccy)

        sign = _sign(send_receive, cf_number)
        signed_fc = round(amount_fc * sign, fc_dp)
        signed_lc = round(amount_lc * sign, lc_dp)

        any_success = False
        messages = []

        for position, pos_src in positions:
            basis = position.get('position_basis') or position.get('pos_basis') or 'SETTLE_DATE'

            if cf_type in ('UNCALL_COMMITMENT',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='uncall_fc', lc_field='uncall_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('PROVISION',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='provision_fc', lc_field='provision_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('PIPELINE',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='pipeline_fc', lc_field='pipeline_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('YTD_REALISE',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('INCOME_DISTRIBUTION',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('DIVIDEND', 'CASH_DIVIDEND'):
                # DIVIDEND: RECEIVE=increase, SEND=decrease (opposite of global convention)
                div_sign = _sign_dividend(send_receive, cf_number)
                div_fc = round(amount_fc * div_sign, fc_dp)
                div_lc = round(amount_lc * div_sign, lc_dp)
                ok, msg = self._accumulate_field(
                    position, portfolio, security, payment_date,
                    fc_field='dividend_fc', lc_field='dividend_lc',
                    delta_fc=div_fc, delta_lc=div_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    amount_fc=amount_fc, amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            elif cf_type in ('RETURN_OF_CAPITAL', 'CAPITAL_DISTRIBUTION'):
                ok, msg = self._reduce_avp(
                    position, portfolio, security, payment_date,
                    amount_fc=signed_fc, amount_lc=signed_lc,
                    cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                    raw_amount_fc=amount_fc, raw_amount_lc=amount_lc,
                    fc_dp=fc_dp, lc_dp=lc_dp,
                    dry_run=dry_run, pos_src=pos_src
                )

            else:
                ok, msg = False, f'Unrecognised cash flow type: {cf_type}'

            messages.append(f'[{basis}] {msg}')
            if ok:
                any_success = True
            else:
                logger.warning(f'CF {cf_number} basis={basis}: {msg}')

        combined = ' | '.join(messages)
        if any_success:
            return True, combined
        return False, combined

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
        cf_id: int,
        cf_number: str,
        amount_fc: Decimal,
        amount_lc: Decimal,
        fc_dp: int = DEFAULT_DP,
        lc_dp: int = DEFAULT_DP,
        dry_run: bool = False,
        pos_src: str = 'CIS',
    ) -> Tuple[bool, str]:
        """Add delta to existing FC/LC field (running total)."""
        old_fc = Decimal(str(position.get(fc_field, 0) or 0))
        old_lc = Decimal(str(position.get(lc_field, 0) or 0))
        new_fc = round(old_fc + delta_fc, fc_dp)
        new_lc = round(old_lc + delta_lc, lc_dp)

        if dry_run:
            return True, (
                f'[DRY RUN] {cf_type}: {fc_field} {old_fc} + {delta_fc} = {new_fc}'
            )

        overrides = {fc_field: float(new_fc), lc_field: float(new_lc)}
        success = self._write_new_position_version(
            position, portfolio, security, position_date, cf_type, overrides,
            cf_id=cf_id, cf_number=cf_number,
            cf_amount_fc=float(round(amount_fc, fc_dp)), cf_amount_lc=float(round(amount_lc, lc_dp)),
            fc_dp=fc_dp, lc_dp=lc_dp, pos_src=pos_src
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
        cf_id: int,
        cf_number: str,
        raw_amount_fc: Decimal,
        raw_amount_lc: Decimal,
        fc_dp: int = DEFAULT_DP,
        lc_dp: int = DEFAULT_DP,
        dry_run: bool = False,
        pos_src: str = 'CIS',
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

        per_share_fc = round(amount_fc / qty, fc_dp)
        per_share_lc = round(amount_lc / qty, lc_dp)

        new_avp_fc = max(Decimal('0'), round(old_avp_fc - per_share_fc, fc_dp))
        new_avp_lc = max(Decimal('0'), round(old_avp_lc - per_share_lc, lc_dp))
        new_total_cost_fc = round(new_avp_fc * qty, fc_dp)
        new_total_cost_lc = round(new_avp_lc * qty, lc_dp)

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
            position, portfolio, security, position_date, cf_type, overrides,
            cf_id=cf_id, cf_number=cf_number,
            cf_amount_fc=float(round(raw_amount_fc, fc_dp)), cf_amount_lc=float(round(raw_amount_lc, lc_dp)),
            fc_dp=fc_dp, lc_dp=lc_dp, pos_src=pos_src
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
        overrides: Dict[str, Any],
        cf_id: int,
        cf_number: str,
        cf_amount_fc: float,
        cf_amount_lc: float,
        fc_dp: int = DEFAULT_DP,
        lc_dp: int = DEFAULT_DP,
        pos_src: str = 'CIS',
    ) -> bool:
        """
        For CIS positions: mark current version is_latest=false, insert new version,
        then sync to golden copy.
        For non-CIS positions (GMP, AMSICEQ, USER_UPLOAD): skip cis_trade_position
        entirely and write directly to cis_position (golden copy).
        """
        try:
            # Non-CIS: golden copy only — no cis_trade_position ledger for these sources
            if pos_src != 'CIS':
                self._sync_to_golden_position(
                    portfolio=portfolio,
                    security=security,
                    position_date=position_date,
                    cf_type=cf_type,
                    current=current,
                    overrides=overrides,
                    cf_id=cf_id,
                    cf_number=cf_number,
                    cf_amount_fc=cf_amount_fc,
                    cf_amount_lc=cf_amount_lc,
                    fc_dp=fc_dp,
                    lc_dp=lc_dp,
                    src_system=pos_src,
                )
                return True

            old_version_id = current.get('version_id')
            position_id = current.get('position_id')

            # Look up currencies from reference tables (not position row — may be empty)
            sec_ccy  = self._get_security_currency(security)
            port_ccy = self._get_portfolio_currency(portfolio)

            # Mark old as not latest
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processing_date = datetime.now().strftime('%Y%m%d')  # YYYYMMDD to match INT records
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

            def _ffc(field, default=0):
                return float(round(Decimal(str(_f(field, default))), fc_dp))

            def _flc(field, default=0):
                return float(round(Decimal(str(_f(field, default))), lc_dp))

            def _b(field, default=True):
                val = current.get(field, default)
                return 'true' if val else 'false'

            # net_book_value = cost + unrealized_pnl - provision
            nbv_fc = float(round(Decimal(str(_f('total_cost_fc'))) + Decimal(str(_f('unrealized_pnl_fc'))) - Decimal(str(_f('provision_fc'))), fc_dp))
            nbv_lc = float(round(Decimal(str(_f('total_cost_lc'))) + Decimal(str(_f('unrealized_pnl_lc'))) - Decimal(str(_f('provision_lc'))), lc_dp))

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
                '{_escape(current.get("position_basis") or "SETTLE_DATE")}',
                '{_escape(portfolio)}',
                '{_escape(security)}',
                {_f('quantity')},
                {_ffc('average_cost_fc')}, {_ffc('total_cost_fc')},
                {_flc('average_cost_lc')}, {_flc('total_cost_lc')},
                {_f('market_price')},      {_ffc('market_value_fc')}, {_flc('market_value_lc')},
                {_ffc('realized_pnl_fc')}, {_ffc('unrealized_pnl_fc')},
                {_flc('realized_pnl_lc')}, {_flc('unrealized_pnl_lc')},
                {_ffc('dividend_fc')},     {_flc('dividend_lc')},
                {_ffc('uncall_fc')},       {_flc('uncall_lc')},
                {_ffc('pipeline_fc')},     {_flc('pipeline_lc')},
                {_ffc('commit_fc')},       {_flc('commit_lc')},
                {_ffc('provision_fc')},    {_flc('provision_lc')},
                'INT',
                {_s('trade_type', 'BUY')},
                '{_escape(sec_ccy)}',
                '{_escape(port_ccy)}',
                {_f('fx_rate', 1)},
                'OPEN', true, true,
                {current.get('last_ca_id') or 'NULL'},
                {_s('last_ca_number', '')},
                {_s('last_ca_type', '')},
                {_s('last_ca_date', '')},
                {cf_id if cf_id else 'NULL'},
                '{_escape(str(cf_number))}',
                {cf_amount_fc},
                {cf_amount_lc},
                'SYSTEM_CF', '{ts}',
                'SYSTEM_CF', '{ts}'
            )
            """
            success = impala_manager.execute_write(sql, database=DATABASE)
            if success:
                self._sync_to_golden_position(
                    portfolio=portfolio,
                    security=security,
                    position_date=position_date,
                    cf_type=cf_type,
                    current=current,
                    overrides=overrides,
                    cf_id=cf_id,
                    cf_number=cf_number,
                    cf_amount_fc=cf_amount_fc,
                    cf_amount_lc=cf_amount_lc,
                    fc_dp=fc_dp,
                    lc_dp=lc_dp,
                )
            return success

        except Exception as e:
            logger.error(f'Error writing position version for {portfolio}/{security}: {e}')
            return False

    def _sync_to_golden_position(
        self,
        portfolio: str,
        security: str,
        position_date: str,
        cf_type: str,
        current: Dict[str, Any],
        overrides: Dict[str, Any],
        cf_id: int,
        cf_number: str,
        cf_amount_fc: float,
        cf_amount_lc: float,
        fc_dp: int = DEFAULT_DP,
        lc_dp: int = DEFAULT_DP,
        src_system: str = 'CIS',
    ) -> None:
        """
        Mirror the cash-flow position update into cis_position (golden copy).
        Looks up existing row for this portfolio+security across any src_system.
        If no row exists, creates a new one with a fresh position_id.
        Non-fatal: logs errors but does not fail the parent write.
        """
        try:
            find_q = f"""
            SELECT position_id, version_id, realized_pnl_fc, realized_pnl_lc,
                   isin, source_table, src_system, position_basis,
                   quantity, average_cost_fc, cost_fc, average_cost_lc, cost_lc,
                   market_value_fc, market_value_lc,
                   unrealized_pnl_fc, unrealized_pnl_lc,
                   dividend_fc, dividend_lc,
                   provision_fc, provision_lc,
                   uncall_fc, uncall_lc,
                   pipeline_fc, pipeline_lc
            FROM {DATABASE}.{GOLDEN_TABLE}
            WHERE portfolio = '{_escape(portfolio)}'
              AND security_label = '{_escape(security)}'
            ORDER BY position_date DESC
            LIMIT 1
            """
            rows = impala_manager.execute_query(find_q, database=DATABASE)
            today = datetime.now().strftime('%Y-%m-%d')
            processing_date = datetime.now().strftime('%Y%m%d')  # YYYYMMDD to match INT records
            new_ver = int(datetime.now().timestamp() * 1000) + 3

            # Always look up currencies from reference tables — position rows may be empty
            sec_ccy  = self._get_security_currency(security)
            port_ccy = self._get_portfolio_currency(portfolio)

            if rows:
                row = rows[0]
                position_id   = row['position_id']
                isin          = row.get('isin')
                source_table  = row.get('source_table')
                effective_src = row.get('src_system') or src_system
                pos_basis     = row.get('position_basis') or 'SETTLE_DATE'
            else:
                import uuid as _uuid
                position_id   = int(datetime.now().timestamp() * 1000) + (_uuid.uuid4().int % 9999)
                row           = {}
                isin          = current.get('isin')
                source_table  = POSITION_TABLE
                effective_src = src_system
                pos_basis     = current.get('position_basis') or 'SETTLE_DATE'
                logger.info(
                    f'[GOLDEN] No existing cis_position row for {portfolio}/{security} '
                    f'— creating new position_id={position_id}'
                )

            def _gv(field, default=0.0):
                """Prefer override → cis_trade_position current → golden row."""
                if field in overrides:
                    return float(overrides[field])
                if current.get(field) is not None:
                    return float(current[field])
                v = row.get(field)
                return float(v) if v is not None else float(default)

            def _gfc(field, default=0.0):
                return float(round(Decimal(str(_gv(field, default))), fc_dp))

            def _glc(field, default=0.0):
                return float(round(Decimal(str(_gv(field, default))), lc_dp))

            # net_book_value = cost + unrealized_pnl - provision
            cost_fc_val      = _gfc('cost_fc', _gv('total_cost_fc'))
            cost_lc_val      = _glc('cost_lc', _gv('total_cost_lc'))
            upnl_fc_val      = _gfc('unrealized_pnl_fc')
            upnl_lc_val      = _glc('unrealized_pnl_lc')
            provision_fc_val = _gfc('provision_fc')
            provision_lc_val = _glc('provision_lc')
            nbv_fc = float(round(Decimal(str(cost_fc_val)) + Decimal(str(upnl_fc_val)) - Decimal(str(provision_fc_val)), fc_dp))
            nbv_lc = float(round(Decimal(str(cost_lc_val)) + Decimal(str(upnl_lc_val)) - Decimal(str(provision_lc_val)), lc_dp))

            upsert = f"""
            INSERT INTO {DATABASE}.{GOLDEN_TABLE} (
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
                dividend_fc, dividend_lc,
                provision_fc, provision_lc,
                uncall_fc, uncall_lc,
                pipeline_fc, pipeline_lc,
                position_type,
                isin, source_table
            ) VALUES (
                {position_id}, {new_ver},
                '{_escape(portfolio)}', '{_escape(security)}',
                '{_escape(pos_basis)}', '{_escape(position_date)}',
                '{_escape(effective_src)}', '{processing_date}',
                {_gv('quantity')},
                {_gfc('average_cost_fc')}, {cost_fc_val},
                {_glc('average_cost_lc')}, {cost_lc_val},
                {_gfc('market_value_fc')}, {_glc('market_value_lc')},
                {nbv_fc}, {nbv_lc},
                {upnl_fc_val}, {upnl_lc_val},
                {_gfc('realized_pnl_fc')}, {_glc('realized_pnl_lc')},
                {_gfc('dividend_fc')}, {_glc('dividend_lc')},
                {provision_fc_val}, {provision_lc_val},
                {_gfc('uncall_fc')}, {_glc('uncall_lc')},
                {_gfc('pipeline_fc')}, {_glc('pipeline_lc')},
                'INT',
                {f"'{_escape(isin)}'" if isin else 'NULL'},
                {f"'{_escape(source_table)}'" if source_table else 'NULL'}
            )
            """
            ok = impala_manager.execute_write(upsert, database=DATABASE)
            if ok:
                logger.info(
                    f'[GOLDEN] cis_position upserted: position_id={position_id} '
                    f'{portfolio}/{security} src={effective_src} cf_type={cf_type} '
                    f'last_cf={cf_number} amount_fc={cf_amount_fc}'
                )
            else:
                logger.error(
                    f'[GOLDEN] Failed to upsert cis_position for {portfolio}/{security} '
                    f'cf_type={cf_type}'
                )
        except Exception as e:
            logger.error(f'[GOLDEN] Error syncing to cis_position for {portfolio}/{security}: {e}')

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

    def _get_security_currency(self, security: str) -> str:
        """Return currency_code from cis_security for the given security_name."""
        try:
            results = impala_manager.execute_query(
                f"SELECT currency_code FROM {DATABASE}.cis_security "
                f"WHERE security_name = '{_escape(security)}' LIMIT 1",
                database=DATABASE
            )
            if results:
                return results[0].get('currency_code') or ''
        except Exception as e:
            logger.debug(f'Could not get security currency for {security}: {e}')
        return ''

    def _get_portfolio_currency(self, portfolio: str) -> str:
        """Return currency from cis_portfolio for the given portfolio name."""
        try:
            results = impala_manager.execute_query(
                f"SELECT currency FROM {DATABASE}.cis_portfolio "
                f"WHERE name = '{_escape(portfolio)}' LIMIT 1",
                database=DATABASE
            )
            if results:
                return results[0].get('currency') or ''
        except Exception as e:
            logger.debug(f'Could not get portfolio currency for {portfolio}: {e}')
        return ''

    def _get_currency_dp(self, currency_code: str) -> int:
        """Return decimal places for a currency from gmp_cis_sta_dly_currency.
        e.g. '0000000000.01' → 2.  Falls back to 2 if not found."""
        if not currency_code:
            return DEFAULT_DP
        try:
            results = impala_manager.execute_query(
                f"SELECT precision FROM {DATABASE}.gmp_cis_sta_dly_currency "
                f"WHERE iso_code = '{_escape(currency_code)}' LIMIT 1",
                database=DATABASE
            )
            if results:
                prec_str = str(results[0].get('precision') or '')
                if '.' in prec_str:
                    return len(prec_str.split('.')[1].rstrip('0') or '0')
        except Exception as e:
            logger.debug(f'Could not get precision for {currency_code}: {e}')
        return DEFAULT_DP

    def _get_current_positions(
        self,
        portfolio: str,
        security: str
    ) -> List[Tuple[Dict[str, Any], str]]:
        """
        Get latest open positions for portfolio/security for BOTH position bases.
        Returns list of (position_dict, src_system) tuples — one per basis found.
        First tries cis_trade_position (CIS versioned ledger) for each basis.
        Falls back to cis_position (golden copy) per basis for non-CIS sources.
        """
        results_out = []

        for basis in ('TRADE_DATE', 'SETTLE_DATE'):
            try:
                query = f"""
                SELECT *
                FROM {DATABASE}.{POSITION_TABLE}
                WHERE portfolio_short_name = '{_escape(portfolio)}'
                  AND security_label = '{_escape(security)}'
                  AND position_basis = '{basis}'
                  AND status = 'OPEN'
                  AND is_active = true
                  AND (is_latest = true OR is_latest IS NULL)
                ORDER BY position_date DESC, version_id DESC
                LIMIT 1
                """
                cis_rows = impala_manager.execute_query(query, database=DATABASE)
                if cis_rows:
                    results_out.append((cis_rows[0], 'CIS'))
                    continue
            except Exception as e:
                logger.error(f'Error fetching CIS {basis} position for {portfolio}/{security}: {e}')

            # Fallback: golden copy for non-CIS sources
            try:
                golden_query = f"""
                SELECT
                    position_id,
                    position_id        AS version_id,
                    portfolio          AS portfolio_short_name,
                    security_label,
                    position_basis,
                    position_date,
                    src_system,
                    quantity,
                    average_cost_fc,
                    cost_fc            AS total_cost_fc,
                    average_cost_lc,
                    cost_lc            AS total_cost_lc,
                    market_value_fc,
                    market_value_lc,
                    unrealized_pnl_fc,
                    unrealized_pnl_lc,
                    realized_pnl_fc,
                    realized_pnl_lc,
                    dividend_fc,
                    dividend_lc,
                    provision_fc,
                    provision_lc,
                    uncall_fc,
                    uncall_lc,
                    pipeline_fc,
                    pipeline_lc,
                    isin,
                    source_table
                FROM {DATABASE}.{GOLDEN_TABLE}
                WHERE portfolio = '{_escape(portfolio)}'
                  AND security_label = '{_escape(security)}'
                  AND position_basis = '{basis}'
                  AND quantity > 0
                ORDER BY position_date DESC
                LIMIT 1
                """
                golden_rows = impala_manager.execute_query(golden_query, database=DATABASE)
                if golden_rows:
                    row = golden_rows[0]
                    src = row.get('src_system') or 'GMP'
                    logger.info(
                        f'[CF] No CIS {basis} position for {portfolio}/{security} — '
                        f'using golden copy (src_system={src})'
                    )
                    results_out.append((row, src))
            except Exception as e:
                logger.error(f'Error fetching golden {basis} position for {portfolio}/{security}: {e}')

        return results_out
