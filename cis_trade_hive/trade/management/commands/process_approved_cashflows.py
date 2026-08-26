"""
Django Management Command: Process Approved Cash Flows

EOD / CORR job that applies APPROVED user-created cash flows (src_system='CIS')
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
  CAPITAL_DISTRIBUTION→ AVP adjustment: total_cost_fc_new = total_cost_fc_old +
                        signed_amount_fc (INCREASE adds, DECREASE subtracts —
                        same send_receive sign as every other type below);
                        avp_fc_new is then derived as total_cost_fc_new / qty.
                        total_cost_lc_new: NON-REVALUED uses the cash flow's own
                        signed amount_lc the same way; REVALUED instead re-derives
                        total_cost_lc_new = total_cost_fc_new x current FX rate
                        (avp_lc_new = avp_fc_new x current FX rate).
                        unrealized_pnl_fc/lc (and therefore net_book_value)
                        are recalculated against the new cost basis.
                        CA-generated cash flows of this type default
                        send_receive to DECREASE (a return of capital reduces
                        cost basis — see ca_cash_flow_service.py's
                        AVP_REDUCTION_CA_TYPES); user-created ones may specify
                        either INCREASE or DECREASE and are applied as given.
  RETURN_OF_CAPITAL   → same as CAPITAL_DISTRIBUTION (see above)
  OTHER               → skip (log warning)

send_receive sign convention (SA-confirmed, uniform across every cash_flow_type
above, no per-type exceptions):
  SEND / INCREASE    → increase the respective field (positive)
  RECEIVE / DECREASE → decrease the respective field (negative)
  NULL               → treated as SEND/INCREASE (positive, logged)
  (CA-sourced cash flows use INCREASE/DECREASE; user-created CIS ones use
  SEND/RECEIVE — see ca_cash_flow_service.py vs load_migration_data.py)

Idempotency: once processed, cf_processed=true is set on the cash flow
record so re-runs on the same date skip already-processed records.

Position lookup: always the current is_latest=true row (cis_trade_position
for CIS sources, cis_position for non-CIS) — this is the base every run
increases/decreases the cost from, regardless of what position_type that
latest row happens to be. If no current row exists, UNCALL_COMMITMENT and
PIPELINE seed a zero-quantity SETTLED CIS position for the run date and then
apply the cash flow to that first version.

average_cost precision: average_cost_fc/lc are a per-unit price, not a
currency amount, and are always written at AVP_PRECISION (8dp) — never
truncated to the currency's display decimal places (fc_dp/lc_dp).

Run types
---------
  EOD  (default): Normal end-of-day run.
        - CF cutoff (payment_date <=) inferred from alldatesinfo reporting_date (prev_day).
        - Looks up the latest open SETTLED position (is_latest=true) for each portfolio/security.
        - Restricts position lookup to positions on reporting_date.
        - Writes/updates position_type = 'INT' into cis_trade_position / cis_position,
          marking the new row is_latest=true.
        - Override cutoff with --position-date if needed.

  CORR: Month-end correction run (scheduled D+1 … D+5 after month-end).
        - CF cutoff inferred as last calendar day of month before reporting_date.
        - Looks up the latest open SETTLED position (is_latest=true) for each portfolio/security.
        - Restricts position lookup to positions on that last_month_end date.
        - Writes position_type = 'CORR' into cis_trade_position / cis_position,
          marking the new row is_latest=true.
        - Override cutoff with --position-date if needed.

Usage:
    # Normal EOD — date inferred from alldatesinfo
    python manage.py process_approved_cashflows
    python manage.py process_approved_cashflows --dry-run
    python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING

    # Month-end CORR run — date inferred automatically as last_month_end
    python manage.py process_approved_cashflows --run-type CORR
    python manage.py process_approved_cashflows --run-type CORR --dry-run
    python manage.py process_approved_cashflows --run-type CORR --reprocess

    # Override date explicitly (both run types)
    python manage.py process_approved_cashflows --position-date 2026-06-27
    python manage.py process_approved_cashflows --run-type CORR --position-date 2026-05-31
"""
from django.conf import settings

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError

from core.repositories.impala_connection import impala_manager
from trade.services.multicurrency_service import multicurrency_service
from trade.services.position_id_service import position_id as _calc_position_id

logger = logging.getLogger(__name__)

DATABASE = settings.IMPALA_CONFIG['DATABASE']
POSITION_TABLE = 'cis_trade_position'   # versioned CIS ledger
GOLDEN_TABLE   = 'cis_position'         # golden copy (all sources)
CASH_FLOW_TABLE = 'cis_cash_flow'
PRECISION = Decimal('0.00000001')
DEFAULT_DP = 2
AVP_PRECISION = 8  # average cost is price-per-unit, not an amount
SEED_POSITION_CF_TYPES = {'UNCALL_COMMITMENT', 'PIPELINE'}


def _escape(value: str) -> str:
    # Impala uses C-style \' escaping, not doubled quotes.
    if value is None:
        return ''
    return str(value).replace('\\', '\\\\').replace("'", "\\'")


def _sign(send_receive: str, cf_number: str) -> Decimal:
    """Global convention: SEND/INCREASE=+1, RECEIVE/DECREASE=-1, NULL=+1 (logged).

    Two vocabularies exist in this codebase's send_receive values: user-created
    CIS cash flows use SEND/RECEIVE (see load_migration_data.py), while
    CA-sourced ones use INCREASE/DECREASE (see ca_cash_flow_service.py, which
    always sets 'INCREASE' today). INCREASE is grouped with SEND (+1) to match
    the +1 the old bare default already gave it — DECREASE is new/never
    emitted yet, but is grouped with RECEIVE (-1) so it doesn't silently fall
    through to +1 the day it starts being used.
    """
    sr = (send_receive or '').upper().strip()
    if sr in ('SEND', 'INCREASE'):
        return Decimal('1')
    if sr in ('RECEIVE', 'DECREASE'):
        return Decimal('-1')
    logger.warning(f"[CF {cf_number}] send_receive '{sr}' unrecognised — treating as SEND (positive)")
    return Decimal('1')


class Command(BaseCommand):
    help = 'Apply APPROVED user-created cash flows to positions (EOD job)'

    def add_arguments(self, parser):
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
            help='Re-process already-processed records (cf_processed=true). Use for corrections.'
        )
        parser.add_argument(
            '--run-type', type=str, choices=['EOD', 'CORR'], default='EOD',
            help='EOD (default): normal end-of-day run. CORR: month-end correction run.'
        )
        parser.add_argument(
            '--position-date', type=str, default=None,
            dest='position_date',
            help='Override the inferred position_date / CF cutoff (YYYY-MM-DD). '
                 'EOD default: reporting_date from alldatesinfo. '
                 'CORR default: last calendar day of previous month.'
        )

    def handle(self, *args, **options):
        run_type         = options['run_type']
        position_date    = options['position_date']
        dry_run          = options['dry_run']
        portfolio_filter = options['portfolio']
        reprocess        = options['reprocess']
        today            = date.today().strftime('%Y-%m-%d')

        # Infer position_date / CF cutoff from alldatesinfo when not explicitly supplied
        if not position_date:
            reporting_date, last_month_end = self._get_dates_from_alldatesinfo()
            position_date = last_month_end if run_type == 'CORR' else reporting_date

        # CF cutoff = position_date for both run types
        run_date = position_date

        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('  CIS Trade Hive — Process Approved Cash Flows'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(f'Run type  : {run_type}')
        self.stdout.write(f'Run date  : {today}  (actual execution date)')
        self.stdout.write(f'Pos date  : {position_date}  (CF cutoff + position lookup date)')
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
            payment_date = cf.get('payment_date') or cf.get('value_date') or run_date

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
                    dry_run=dry_run,
                    run_type=run_type,
                    position_date=position_date,
                )
                if success:
                    self.stdout.write(self.style.SUCCESS(f'    ✓ {message}'))
                    if not dry_run:
                        self._mark_cf_processed(cf_id)
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
    # DATE INFERENCE
    # =========================================================================

    def _get_dates_from_alldatesinfo(self):
        """
        Query alldatesinfo for the two dates used by EOD and CORR runs.

        Returns (reporting_date, last_month_end) as 'YYYY-MM-DD' strings.

        reporting_date = reporting_date column (T-1) — used for EOD runs.

        CORR last_month_end logic (SA rule):
          - If contextual_today and reporting_date are in DIFFERENT months
            → last_month_end = reporting_date  (reporting_date IS the month-end)
          - Else (same month)
            → last_month_end = last calendar day of month before reporting_date

        Falls back to (yesterday, last calendar day of previous month) if the
        table is unavailable.
        """
        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT contextual_today, reporting_date
                FROM {DATABASE}.gmp_cis_sta_dly_alldatesinfo
                WHERE src_system  = 'gmp'
                  AND sub_system  = 'cis'
                  AND data_frq    = 'dly'
                  AND record_type = 'D'
                  AND processing_date = (
                      SELECT MAX(processing_date)
                      FROM {DATABASE}.gmp_cis_sta_dly_alldatesinfo
                      WHERE src_system  = 'gmp'
                        AND sub_system  = 'cis'
                        AND data_frq    = 'dly'
                        AND record_type = 'D'
                  )
                LIMIT 1
                """,
                database=DATABASE
            )
            if rows:
                raw_ct = str(rows[0].get('contextual_today', '') or '')[:8]
                raw_rd = str(rows[0].get('reporting_date', '') or '')[:8]
                if raw_ct and raw_rd:
                    contextual_today = datetime.strptime(raw_ct, '%Y%m%d').date()
                    reporting_date   = datetime.strptime(raw_rd, '%Y%m%d').date()
                    reporting_date_iso = reporting_date.strftime('%Y-%m-%d')

                    # SA rule: if contextual_today and reporting_date are in different
                    # months, reporting_date itself is the month-end for CORR.
                    if contextual_today.month != reporting_date.month or \
                       contextual_today.year  != reporting_date.year:
                        last_month_end = reporting_date_iso
                    else:
                        first_of_ref_month = reporting_date.replace(day=1)
                        last_month_end = (first_of_ref_month - timedelta(days=1)).strftime('%Y-%m-%d')

                    logger.info(
                        f'[CF] alldatesinfo: contextual_today={raw_ct} reporting_date={raw_rd} '
                        f'→ reporting_date_iso={reporting_date_iso} last_month_end={last_month_end}'
                    )
                    return reporting_date_iso, last_month_end
        except Exception as e:
            logger.warning(f'Could not read alldatesinfo for date inference: {e}')

        # Fallback: use calendar dates
        today = date.today()
        yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        first_of_month = today.replace(day=1)
        last_month_end = (first_of_month - timedelta(days=1)).strftime('%Y-%m-%d')
        logger.warning(
            f'alldatesinfo unavailable — falling back to reporting_date={yesterday}, '
            f'last_month_end={last_month_end}'
        )
        return yesterday, last_month_end

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
            f"COALESCE(payment_date, value_date) <= '{_escape(run_date)}'",
        ]
        if not reprocess:
            clauses.append("(cf_processed = false OR cf_processed IS NULL)")
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
        dry_run: bool,
        run_type: str = 'EOD',
        position_date: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Route to the correct position update logic based on cash flow type.
        Applies CF to the SETTLED position in cis_trade_position (CIS) or cis_position (non-CIS).
        position_date restricts lookup to a specific date (used for both EOD and CORR)."""

        # Fetch positions for both bases; apply to each independently
        positions = self._get_current_positions(portfolio, security, position_date=position_date)
        if not positions and cf_type in SEED_POSITION_CF_TYPES:
            positions = [(
                self._build_seed_position(
                    portfolio=portfolio,
                    security=security,
                    position_date=position_date or payment_date,
                ),
                'CIS',
            )]

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
            basis = position.get('position_basis') or position.get('pos_basis') or 'SETTLED'

            # Pass the FOUND position's own position_date, not the cash flow's
            # payment_date, into the accumulate/reduce helpers below. Both
            # feed into the golden-copy position_id hash (position_id_service),
            # which includes position_date -- using payment_date there instead
            # of the row's actual position_date produces a genuinely different
            # position_id than the one the trade flow already created for this
            # natural key, silently spawning a second live INT row for the
            # same portfolio/security/basis with the accumulated field (e.g.
            # dividend_fc) sitting on the wrong one -- observed for
            # UOBS_CIU_FVE_REIT/CLAS SP: two SETTLED INT position_ids, one
            # with dividend_fc=0, one with the real accumulated value.
            common = dict(
                cf_type=cf_type, cf_id=cf_id, cf_number=cf_number,
                amount_fc=amount_fc, amount_lc=amount_lc,
                fc_dp=fc_dp, lc_dp=lc_dp,
                dry_run=dry_run, pos_src=pos_src, run_type=run_type,
            )

            if cf_type in ('UNCALL_COMMITMENT',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='uncall_fc', lc_field='uncall_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('PROVISION',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='provision_fc', lc_field='provision_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('PIPELINE',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='pipeline_fc', lc_field='pipeline_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('YTD_REALISE',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('INCOME_DISTRIBUTION',):
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='realized_pnl_fc', lc_field='realized_pnl_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('DIVIDEND', 'CASH_DIVIDEND'):
                # Same shared _sign() convention as every other type: INCREASE
                # increases dividend_fc/lc, DECREASE decreases it.
                ok, msg = self._accumulate_field(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    fc_field='dividend_fc', lc_field='dividend_lc',
                    delta_fc=signed_fc, delta_lc=signed_lc, **common
                )

            elif cf_type in ('RETURN_OF_CAPITAL', 'CAPITAL_DISTRIBUTION'):
                # common already carries amount_fc/amount_lc (the raw, unsigned
                # amounts) -- _reduce_avp wants the SIGNED amounts under those
                # same names, with the raw ones passed separately as
                # raw_amount_fc/raw_amount_lc. Spreading **common unfiltered
                # collided with the explicit amount_fc=/amount_lc= below
                # ("got multiple values for keyword argument 'amount_fc'").
                common_no_amount = {k: v for k, v in common.items() if k not in ('amount_fc', 'amount_lc')}
                ok, msg = self._reduce_avp(
                    position, portfolio, security, position.get('position_date') or payment_date,
                    amount_fc=signed_fc, amount_lc=signed_lc,
                    raw_amount_fc=amount_fc, raw_amount_lc=amount_lc,
                    **common_no_amount
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

    def _build_seed_position(
        self,
        portfolio: str,
        security: str,
        position_date: str,
    ) -> Dict[str, Any]:
        """Build a zero-quantity SETTLED CIS position used to seed CF-only rows."""
        sec_ccy = self._get_security_currency(security)
        port_ccy = self._get_portfolio_currency(portfolio)
        fx_rate = Decimal('1')
        try:
            fx_rate, _ = multicurrency_service.get_fx_rate(sec_ccy, port_ccy, position_date)
        except Exception as e:
            logger.warning(
                f'Could not derive FX rate for seeded CF position {portfolio}/{security}: {e}'
            )

        return {
            'position_id': _calc_position_id(
                portfolio=portfolio,
                security_label=security,
                position_basis='SETTLED',
                position_date=position_date,
                src_system='CIS',
            ),
            'position_basis': 'SETTLED',
            'position_date': position_date,
            'portfolio_short_name': portfolio,
            'security_label': security,
            'quantity': 0,
            'average_cost_fc': 0,
            'total_cost_fc': 0,
            'average_cost_lc': 0,
            'total_cost_lc': 0,
            'market_price': 0,
            'market_value_fc': 0,
            'market_value_lc': 0,
            'realized_pnl_fc': 0,
            'unrealized_pnl_fc': 0,
            'realized_pnl_lc': 0,
            'unrealized_pnl_lc': 0,
            'dividend_fc': 0,
            'dividend_lc': 0,
            'uncall_fc': 0,
            'uncall_lc': 0,
            'pipeline_fc': 0,
            'pipeline_lc': 0,
            'commit_fc': 0,
            'commit_lc': 0,
            'provision_fc': 0,
            'provision_lc': 0,
            'trade_type': 'BUY',
            'security_currency': sec_ccy,
            'portfolio_currency': port_ccy,
            'fx_rate': float(fx_rate),
            'status': 'OPEN',
            'is_active': True,
            'is_latest': True,
        }

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
        run_type: str = 'EOD',
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
            fc_dp=fc_dp, lc_dp=lc_dp, pos_src=pos_src, run_type=run_type,
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
        run_type: str = 'EOD',
    ) -> Tuple[bool, str]:
        """
        AVP adjustment: total_cost_fc_new = total_cost_fc_old + amount_fc, where
        amount_fc is already signed by send_receive (INCREASE=+1, DECREASE=-1
        via _sign() in _apply_to_position) -- an INCREASE cash flow increases
        cost, a DECREASE one decreases it. average_cost_fc is then DERIVED as
        total_cost_fc_new / qty (the proper definition of average cost), rather
        than adjusting average_cost_fc first and recomputing total cost from it.

        send_receive convention for RETURN_OF_CAPITAL/CAPITAL_DISTRIBUTION:
        CA-generated ROC cash flows default to DECREASE (a return of capital —
        cash received — reduces cost basis; see ca_cash_flow_service.py's
        AVP_REDUCTION_CA_TYPES). User-created ones may set either INCREASE or
        DECREASE explicitly and are applied exactly as given.

        This ordering (adjust total first, derive average second) matters
        regardless of direction: this position's stored total_cost_fc can
        already be slightly out of sync with average_cost_fc x quantity (a
        pre-existing data quirk, unrelated to any cash flow). Adjusting average
        cost first and then recomputing total_cost_fc = new_avp_fc x qty would
        silently snap total cost to that inconsistent baseline, producing a
        swing far larger than the cash flow's actual amount. Adjusting the
        stored total_cost_fc directly keeps the change exactly equal to
        amount_fc, regardless of any pre-existing average/total mismatch.

        total_cost_lc / avp_lc:
          NON-REVALUED: total_cost_lc_old + amount_lc -- same exact-adjustment
            approach, trusting the cash flow's own signed LC amount; avp_lc
            derived as total_cost_lc_new / qty.
          REVALUED: total_cost_fc_new x current FX rate -- re-derived fresh
            rather than adjusted by the cash flow's raw LC amount, matching the
            AVP engine's general REVAL rule (cost_lc always mirrors cost_fc x
            current FX rate; see position_service._save_position). avp_lc is
            avp_fc_new x current FX rate, per the same rule.

        unrealized_pnl_fc/lc are recalculated against the new total cost --
        previously left stale from the prior position version, which
        misstated the unrealized gain a capital return actually produces.
        net_book_value_fc/lc then follows automatically in
        _write_new_position_version's own nbv formula, since it reads
        unrealized_pnl_fc/lc through the same overrides dict.
        """
        from trade.services.position_service import position_service

        qty = Decimal(str(position.get('quantity', 0) or 0))
        if qty <= 0:
            return False, f'{cf_type}: quantity is 0, cannot adjust AVP'

        old_total_cost_fc = Decimal(str(position.get('total_cost_fc', 0) or 0))
        old_total_cost_lc = Decimal(str(position.get('total_cost_lc', 0) or 0))

        new_total_cost_fc = max(Decimal('0'), round(old_total_cost_fc + amount_fc, fc_dp))
        new_avp_fc = round(new_total_cost_fc / qty, AVP_PRECISION)

        reval_status = position_service._get_portfolio_revaluation_status(portfolio)
        if reval_status == 'NON-REVALUED':
            new_total_cost_lc = max(Decimal('0'), round(old_total_cost_lc + amount_lc, lc_dp))
            new_avp_lc = round(new_total_cost_lc / qty, AVP_PRECISION)
            fx_rate = None
        else:
            sec_ccy = self._get_security_currency(security)
            port_ccy = self._get_portfolio_currency(portfolio)
            fx_rate = position_service._get_fx_rate(sec_ccy, port_ccy, rate_date=position_date)
            new_avp_lc = round(new_avp_fc * fx_rate, AVP_PRECISION)
            new_total_cost_lc = round(new_total_cost_fc * fx_rate, lc_dp)

        is_equity_method = position_service._is_equity_method_security(security)
        market_value_fc = Decimal(str(position.get('market_value_fc', 0) or 0))
        market_value_lc = Decimal(str(position.get('market_value_lc', 0) or 0))
        new_unrealized_pnl_fc = Decimal('0') if is_equity_method else round(market_value_fc - new_total_cost_fc, fc_dp)
        new_unrealized_pnl_lc = Decimal('0') if is_equity_method else round(market_value_lc - new_total_cost_lc, lc_dp)

        if dry_run:
            return True, (
                f'[DRY RUN] {cf_type} ({reval_status}{f", fx={fx_rate}" if fx_rate else ""}): '
                f'total_cost_fc {old_total_cost_fc} + ({amount_fc}) = {new_total_cost_fc} (avp_fc → {new_avp_fc}) | '
                f'total_cost_lc {old_total_cost_lc} → {new_total_cost_lc} (avp_lc → {new_avp_lc}) | '
                f'unrealized_pnl_fc → {new_unrealized_pnl_fc} | unrealized_pnl_lc → {new_unrealized_pnl_lc}'
            )

        overrides = {
            'average_cost_fc': float(new_avp_fc),
            'average_cost_lc': float(new_avp_lc),
            'total_cost_fc': float(new_total_cost_fc),
            'total_cost_lc': float(new_total_cost_lc),
            'unrealized_pnl_fc': float(new_unrealized_pnl_fc),
            'unrealized_pnl_lc': float(new_unrealized_pnl_lc),
        }
        success = self._write_new_position_version(
            position, portfolio, security, position_date, cf_type, overrides,
            cf_id=cf_id, cf_number=cf_number,
            cf_amount_fc=float(round(raw_amount_fc, fc_dp)), cf_amount_lc=float(round(raw_amount_lc, lc_dp)),
            fc_dp=fc_dp, lc_dp=lc_dp, pos_src=pos_src, run_type=run_type,
        )
        if success:
            return True, (
                f'{cf_type} ({reval_status}): total_cost_fc {old_total_cost_fc} → {new_total_cost_fc} '
                f'(avp_fc → {new_avp_fc}), total_cost_lc {old_total_cost_lc} → {new_total_cost_lc} '
                f'(avp_lc → {new_avp_lc})'
            )
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
        run_type: str = 'EOD',
    ) -> bool:
        """
        For CIS positions: mark current version is_latest=false, insert new version,
        then sync to golden copy.
        For non-CIS positions (GMP, AMSICEQ, USER_UPLOAD): skip cis_trade_position
        entirely and write directly to cis_position (golden copy).
        Writes position_type='CORR' when run_type='CORR', else 'INT' — either way
        the new row is marked is_latest=true (it becomes the base for the next run).
        """
        position_type = 'CORR' if run_type == 'CORR' else 'INT'
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
                    run_type=run_type,
                )
                return True

            old_version_id = current.get('version_id')
            position_id = current.get('position_id')
            if not position_id:
                if old_version_id:
                    raise ValueError(
                        f'Missing position_id on existing position for {portfolio}/{security}'
                    )
                position_id = _calc_position_id(
                    portfolio=portfolio,
                    security_label=security,
                    position_basis=current.get('position_basis') or 'SETTLED',
                    position_date=position_date,
                    src_system='CIS',
                )

            # Look up currencies from reference tables (not position row — may be empty)
            sec_ccy  = self._get_security_currency(security)
            port_ccy = self._get_portfolio_currency(portfolio)

            # Mark old as not latest
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processing_date = datetime.now().strftime('%Y%m%d')  # YYYYMMDD to match INT records
            if old_version_id:
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

            def _favp(field, default=0):
                # average_cost is a per-unit price, not a currency amount — it
                # must keep AVP_PRECISION (8dp), not be truncated to the
                # currency's display decimal places (fc_dp/lc_dp, often 2).
                return float(round(Decimal(str(_f(field, default))), AVP_PRECISION))

            def _b(field, default=True):
                val = current.get(field, default)
                return 'true' if val else 'false'

            # net_book_value = cost + unrealized_pnl - provision
            nbv_fc = float(round(Decimal(str(_f('total_cost_fc'))) + Decimal(str(_f('unrealized_pnl_fc'))) - Decimal(str(_f('provision_fc'))), fc_dp))
            nbv_lc = float(round(Decimal(str(_f('total_cost_lc'))) + Decimal(str(_f('unrealized_pnl_lc'))) - Decimal(str(_f('provision_lc'))), lc_dp))

            sql = f"""
            INSERT INTO {DATABASE}.{POSITION_TABLE} (
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
                '{_escape(current.get("position_basis") or "SETTLED")}',
                '{_escape(portfolio)}',
                '{_escape(security)}',
                {_f('quantity')},
                {_favp('average_cost_fc')}, {_ffc('total_cost_fc')},
                {_favp('average_cost_lc')}, {_flc('total_cost_lc')},
                {_f('market_price')},      {_ffc('market_value_fc')}, {_flc('market_value_lc')},
                {_ffc('realized_pnl_fc')}, {_ffc('unrealized_pnl_fc')},
                {_flc('realized_pnl_lc')}, {_flc('unrealized_pnl_lc')},
                {_ffc('dividend_fc')},     {_flc('dividend_lc')},
                {_ffc('uncall_fc')},       {_flc('uncall_lc')},
                {_ffc('pipeline_fc')},     {_flc('pipeline_lc')},
                {_ffc('commit_fc')},       {_flc('commit_lc')},
                {_ffc('provision_fc')},    {_flc('provision_lc')},
                '{position_type}',
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
                    run_type=run_type,
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
        run_type: str = 'EOD',
    ) -> None:
        """
        Mirror the cash-flow position update into cis_position (golden copy).
        Looks up existing row for this portfolio+security across any src_system.
        If no row exists, creates a new one with a fresh position_id.
        Non-fatal: logs errors but does not fail the parent write.
        Writes position_type='CORR' when run_type='CORR', else 'INT'.
        """
        position_type = 'CORR' if run_type == 'CORR' else 'INT'
        try:
            # Look up the existing golden row for this exact date to determine
            # src_system — needed to compute the correct natural key hash.
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
            WHERE portfolio      = '{_escape(portfolio)}'
              AND security_label = '{_escape(security)}'
              AND position_basis = 'SETTLED'
              AND position_date  = '{_escape(position_date)}'
            ORDER BY position_id DESC
            LIMIT 1
            """
            rows = impala_manager.execute_query(find_q, database=DATABASE)
            processing_date = datetime.now().strftime('%Y%m%d')  # YYYYMMDD to match INT records
            processing_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # position_id: deterministic natural key hash — consistent with upload_service
            # and trade creation: fnv_hash(portfolio|security_label|position_basis|position_date|src_system)
            # Use effective_src after we know it; compute after rows check below.
            # (We compute new_position_id after the rows block where pos_basis/effective_src are set.)

            if rows:
                row           = rows[0]
                isin          = row.get('isin')
                source_table  = row.get('source_table')
                effective_src = row.get('src_system') or src_system
                pos_basis     = row.get('position_basis') or 'SETTLED'
            else:
                row           = {}
                isin          = current.get('isin')
                source_table  = POSITION_TABLE

                effective_src = src_system
                pos_basis     = current.get('position_basis') or 'SETTLED'

            # Natural key hash — uses same MD5-based formula as position_id_service
            # (position_service, upload_service, refresh_positions all use this)
            new_position_id = _calc_position_id(
                portfolio=portfolio,
                security_label=security,
                position_basis=pos_basis,
                position_date=position_date,
                src_system=effective_src,
            )
            logger.info(
                f'[GOLDEN] position_id={new_position_id} for '
                f'{portfolio}/{security}/{pos_basis}/{position_date}/{effective_src}'
            )

            def _gv(field, default=0.0):
                """Prefer override → cis_trade_position current → golden row.

                `field` may be a single name or a list of aliases tried in
                order: the CIS ledger (cis_trade_position) and the golden
                schema (cis_position) use different column names for the same
                value (total_cost_fc/lc vs cost_fc/lc). Checking only the
                golden name here meant an override keyed 'total_cost_fc' was
                never found, so cost_fc/cost_lc (and therefore net_book_value)
                silently kept the stale pre-cashflow value on every RETURN_OF_
                CAPITAL/CAPITAL_DISTRIBUTION sync, even though average_cost_fc
                updated correctly.
                """
                names = field if isinstance(field, (list, tuple)) else [field]
                for name in names:
                    if name in overrides:
                        return float(overrides[name])
                for name in names:
                    if current.get(name) is not None:
                        return float(current[name])
                for name in names:
                    v = row.get(name)
                    if v is not None:
                        return float(v)
                return float(default)

            def _gfc(field, default=0.0):
                return float(round(Decimal(str(_gv(field, default))), fc_dp))

            def _glc(field, default=0.0):
                return float(round(Decimal(str(_gv(field, default))), lc_dp))

            def _gavp(field, default=0.0):
                # average_cost is a per-unit price, not a currency amount — keep
                # AVP_PRECISION (8dp) rather than truncating to fc_dp/lc_dp.
                return float(round(Decimal(str(_gv(field, default))), AVP_PRECISION))

            # net_book_value = cost + unrealized_pnl - provision
            cost_fc_val      = _gfc(['total_cost_fc', 'cost_fc'])
            cost_lc_val      = _glc(['total_cost_lc', 'cost_lc'])
            upnl_fc_val      = _gfc('unrealized_pnl_fc')
            upnl_lc_val      = _glc('unrealized_pnl_lc')
            provision_fc_val = _gfc('provision_fc')
            provision_lc_val = _glc('provision_lc')
            nbv_fc = float(round(Decimal(str(cost_fc_val)) + Decimal(str(upnl_fc_val)) - Decimal(str(provision_fc_val)), fc_dp))
            nbv_lc = float(round(Decimal(str(cost_lc_val)) + Decimal(str(upnl_lc_val)) - Decimal(str(provision_lc_val)), lc_dp))

            insert_sql = f"""
            UPSERT INTO {DATABASE}.{GOLDEN_TABLE} (
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
                position_type, is_latest,
                processing_timestamp,
                isin, source_table
            ) VALUES (
                {new_position_id}, {new_position_id},
                '{_escape(portfolio)}', '{_escape(security)}',
                '{_escape(pos_basis)}', '{_escape(position_date)}',
                '{_escape(effective_src)}', '{processing_date}',
                {_gv('quantity')},
                {_gavp('average_cost_fc')}, {cost_fc_val},
                {_gavp('average_cost_lc')}, {cost_lc_val},
                {_gfc('market_value_fc')}, {_glc('market_value_lc')},
                {nbv_fc}, {nbv_lc},
                {upnl_fc_val}, {upnl_lc_val},
                {_gfc('realized_pnl_fc')}, {_glc('realized_pnl_lc')},
                {_gfc('dividend_fc')}, {_glc('dividend_lc')},
                {provision_fc_val}, {provision_lc_val},
                {_gfc('uncall_fc')}, {_glc('uncall_lc')},
                {_gfc('pipeline_fc')}, {_glc('pipeline_lc')},
                '{position_type}', true,
                '{processing_timestamp}',
                {f"'{_escape(isin)}'" if isin else 'NULL'},
                {f"'{_escape(source_table)}'" if source_table else 'NULL'}
            )
            """
            ok = impala_manager.execute_write(insert_sql, database=DATABASE)
            if ok:
                logger.info(
                    f'[GOLDEN] cis_position inserted: new_position_id={new_position_id} '
                    f'{portfolio}/{security} src={effective_src} cf_type={cf_type} '
                    f'last_cf={cf_number} amount_fc={cf_amount_fc}'
                )
            else:
                logger.error(
                    f'[GOLDEN] Failed to insert cis_position for {portfolio}/{security} '
                    f'cf_type={cf_type}'
                )
        except Exception as e:
            logger.error(f'[GOLDEN] Error syncing to cis_position for {portfolio}/{security}: {e}')

    # =========================================================================
    # MARK PROCESSED
    # =========================================================================

    def _mark_cf_processed(self, cash_flow_id: int) -> None:
        """Set cf_processed=true on the cash flow record after positions are updated."""
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            impala_manager.execute_write(
                f"""UPDATE {DATABASE}.{CASH_FLOW_TABLE}
                    SET cf_processed = true, updated_at = '{ts}'
                    WHERE cash_flow_id = {cash_flow_id}""",
                database=DATABASE
            )
        except Exception as e:
            logger.warning(f'Could not mark cash_flow {cash_flow_id} as cf_processed: {e}')

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
        security: str,
        position_date: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], str]]:
        """
        Get latest open SETTLED position for portfolio/security.
        Returns list of (position_dict, src_system) with one entry if found.
        First tries cis_trade_position (CIS versioned ledger).
        Falls back to cis_position (golden copy) for non-CIS sources.

        position_date (CORR only): when supplied, restricts the lookup to rows
        whose position_date equals this value (the month-end date being corrected).
        For EOD (None): picks the most recent position across all dates.
        """
        date_clause_tp = (
            f"AND position_date = '{_escape(position_date)}'" if position_date else ""
        )
        date_clause_gp = (
            f"AND position_date = '{_escape(position_date)}'" if position_date else ""
        )

        try:
            query = f"""
            SELECT *
            FROM {DATABASE}.{POSITION_TABLE}
            WHERE portfolio_short_name = '{_escape(portfolio)}'
              AND security_label = '{_escape(security)}'
              AND position_basis = 'SETTLED'
              AND status = 'OPEN'
              AND is_active = true
              AND is_latest = true
              {date_clause_tp}
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            cis_rows = impala_manager.execute_query(query, database=DATABASE)
            if cis_rows:
                return [(cis_rows[0], 'CIS')]
        except Exception as e:
            logger.error(f'Error fetching CIS SETTLED position for {portfolio}/{security}: {e}')

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
              AND position_basis = 'SETTLED'
              AND quantity > 0
              AND (is_latest = true OR is_latest IS NULL)
              {date_clause_gp}
            ORDER BY position_date DESC
            LIMIT 1
            """
            golden_rows = impala_manager.execute_query(golden_query, database=DATABASE)
            if golden_rows:
                row = golden_rows[0]
                src = row.get('src_system') or 'GMP'
                logger.info(
                    f'[CF] No CIS SETTLED position for {portfolio}/{security} — '
                    f'using golden copy (src_system={src})'
                )
                return [(row, src)]
        except Exception as e:
            logger.error(f'Error fetching golden SETTLED position for {portfolio}/{security}: {e}')

        return []
