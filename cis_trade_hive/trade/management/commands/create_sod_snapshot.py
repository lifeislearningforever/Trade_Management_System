"""
Django Management Command: Create SOD Snapshot

Creates Start-of-Day (SOD) position rows in cis_position by:
  1. Copying the previous business day's EOD rows
  2. Applying any settlement queue entries with settle_date == today BEFORE writing SOD
     (so the SOD already reflects those settled trades, not a raw EOD copy followed
     by separate INT positions created later)
  3. Writing the merged result as position_type='SOD'

Queue entries processed here are marked COMPLETED so the async settlement
worker skips them.

Date logic (from gmp_cis_sta_dly_alldatesinfo):
  - src_system='gmp', sub_system='cis', data_frq='dly', record_type='D'
  - prev_day          → find EOD rows with this position_date  (e.g. 20260226)
  - contextual_today  → SOD rows get this as position_date     (e.g. 20260302)

Dates in the reference table are YYYYMMDD strings; converted to YYYY-MM-DD
for cis_position.

Usage:
    # Normal SOD — dates inferred from alldatesinfo
    python manage.py create_sod_snapshot
    python manage.py create_sod_snapshot --dry-run
    python manage.py create_sod_snapshot --portfolio UOB-SG-TRADING
    python manage.py create_sod_snapshot --source CIS

    # Override dates manually
    python manage.py create_sod_snapshot --eod-date 2026-03-02 --sod-date 2026-03-03
    python manage.py create_sod_snapshot --eod-date 2026-03-02 --sod-date 2026-03-03 --source GMP

    # Fill-gaps mode — keep existing SOD rows, only create missing ones from EOD
    # Use when SOD run was partially completed and you want to top-up without
    # replacing the SOD rows that were already written correctly.
    python manage.py create_sod_snapshot --eod-date 2026-03-02 --sod-date 2026-03-03 --fill-gaps
    python manage.py create_sod_snapshot --eod-date 2026-03-02 --sod-date 2026-03-03 --source CIS --fill-gaps
    python manage.py create_sod_snapshot --eod-date 2026-03-02 --sod-date 2026-03-03 --fill-gaps --dry-run
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
ALL_SOURCES = ['CIS', 'GMP', 'AMSICEQ', 'USER_UPLOAD']
AVP_PRECISION = Decimal('0.00000001')


class Command(BaseCommand):
    help = 'Create SOD snapshot: copy previous EOD rows (+ apply today\'s settlements) as SOD'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be written without making changes')
        parser.add_argument('--portfolio', type=str,
                            help='Limit to a single portfolio (optional)')
        parser.add_argument(
            '--source', type=str, choices=ALL_SOURCES,
            help='Limit to one source system: CIS, GMP, AMSICEQ, USER_UPLOAD (default: all)'
        )
        parser.add_argument(
            '--sod-date', type=str, default=None,
            help='Override SOD position_date (YYYY-MM-DD). Default: alldatesinfo.contextual_today'
        )
        parser.add_argument(
            '--eod-date', type=str, default=None,
            help='Override source EOD date to copy from (YYYY-MM-DD). Default: alldatesinfo.prev_day'
        )
        parser.add_argument(
            '--fill-gaps', action='store_true', default=False,
            dest='fill_gaps',
            help='Only create SOD rows for positions that have NO existing SOD row for sod_date. '
                 'Keeps existing SOD rows untouched; only fills missing ones from EOD.'
        )

    def handle(self, *args, **options):
        dry_run          = options.get('dry_run', False)
        portfolio_filter = options.get('portfolio')
        source_filter    = options.get('source')
        fill_gaps        = options.get('fill_gaps', False)

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('SOD Snapshot — cis_position'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written'))
        self.stdout.write('')

        # ── 1. Get business dates (alldatesinfo or manual override) ─────────
        today_yyyymmdd, prev_yyyymmdd = self._get_business_dates()

        if options.get('sod_date') or options.get('eod_date'):
            # Manual override — at least one date was supplied
            sod_date  = options['sod_date'] or self._to_iso(today_yyyymmdd)
            eod_date  = options['eod_date'] or self._to_iso(prev_yyyymmdd)
            proc_date = sod_date.replace('-', '')
            date_source = 'manual override'
        else:
            if not today_yyyymmdd or not prev_yyyymmdd:
                raise CommandError(
                    'Could not read business dates from gmp_cis_sta_dly_alldatesinfo. '
                    'Use --sod-date and --eod-date to override.'
                )
            sod_date  = self._to_iso(today_yyyymmdd)   # SOD position_date  e.g. 2026-03-02
            eod_date  = self._to_iso(prev_yyyymmdd)    # source EOD date    e.g. 2026-02-26
            proc_date = today_yyyymmdd
            date_source = 'alldatesinfo'

        self.stdout.write(
            f"Business date (contextual_today) : {today_yyyymmdd}  →  SOD position_date = {sod_date}  (from {date_source})"
        )
        self.stdout.write(
            f"Previous day  (prev_day)         : {prev_yyyymmdd}  →  source EOD date   = {eod_date}  (from {date_source})"
        )
        self.stdout.write('')

        if fill_gaps:
            self.stdout.write(self.style.WARNING(
                'Fill-gaps  : ON — only positions with no existing SOD row for '
                f'{sod_date} will be created'
            ))

        # ── 2. Fetch EOD rows for prev_day ───────────────────────────────────
        sources   = [source_filter] if source_filter else ALL_SOURCES
        eod_rows  = self._get_eod_rows(eod_date, sources, portfolio_filter,
                                        fill_gaps=fill_gaps, sod_date=sod_date)

        if not eod_rows:
            self.stdout.write(self.style.WARNING(
                f'No EOD rows found for position_date={eod_date} — nothing to snapshot'
            ))
            return

        self.stdout.write(f"Found {len(eod_rows)} EOD row(s) to copy as SOD")

        # ── 3. Apply today's pending settlements to EOD baseline ─────────────
        #
        # Fetch cis_settlement_queue entries where settle_date == sod_date and
        # status = PENDING.  These are T+1/T+2 trades whose SETTLED position
        # was deferred.  Apply each trade's effect to the matching EOD row so
        # the resulting SOD row already reflects the settled quantity and cost.
        #
        # Trades that have no existing EOD position (new security settling today)
        # are inserted as brand-new SOD rows with opening position.
        #
        # After applying, each queue entry is marked COMPLETED so the async
        # worker does not double-process it.

        pending_settlements = self._get_pending_settlements(sod_date)
        self.stdout.write(
            f"Found {len(pending_settlements)} pending settlement(s) "
            f"with settle_date = {sod_date}"
        )

        # Index EOD rows by (portfolio, security_label, position_basis) for O(1) lookup
        eod_index: dict = {}
        for row in eod_rows:
            key = (
                row.get('portfolio', ''),
                row.get('security_label', ''),
                row.get('position_basis', 'SETTLED'),
            )
            eod_index[key] = row

        settled_queue_ids = []
        failed_queue_ids  = []
        new_sod_rows      = []   # brand-new positions (no prior EOD)

        # Cache portfolio revaluation status to avoid repeated DB calls
        _reval_cache: dict = {}

        for item in pending_settlements:
            portfolio  = item.get('portfolio_id', '')
            security   = item.get('security_id', '')
            basis      = item.get('position_basis', 'SETTLED')
            trade_type = item.get('trade_type', '')
            qty        = Decimal(str(item.get('quantity', 0) or 0))
            price      = Decimal(str(item.get('price', 0) or 0))
            charges    = Decimal(str(item.get('charges', 0) or 0))
            queue_id   = item.get('queue_id')
            trade_id   = item.get('trade_id')
            raw_lc     = item.get('total_amount_lc')
            trade_lc   = Decimal(str(raw_lc)) if raw_lc else None

            if portfolio not in _reval_cache:
                _reval_cache[portfolio] = self._get_portfolio_revaluation_status(portfolio)
            reval_status = _reval_cache[portfolio]

            key = (portfolio, security, basis)
            existing = eod_index.get(key)

            try:
                updated = self._apply_settlement_to_position(
                    existing=existing,
                    trade_type=trade_type,
                    quantity=qty,
                    price=price,
                    charges=charges,
                    settle_date=sod_date,
                    trade_id=trade_id,
                    item=item,
                    reval_status=reval_status,
                    trade_lc=trade_lc,
                )
                if updated is None:
                    # e.g. SELL with no existing position — skip
                    failed_queue_ids.append(queue_id)
                    logger.error(
                        f"[SOD settlement] queue_id={queue_id} trade_id={trade_id} "
                        f"SELL {qty} {security} but no existing position — skipped"
                    )
                    continue

                if existing:
                    # Replace in eod_index so downstream insert uses the updated values
                    eod_index[key] = updated
                else:
                    # New position — collect separately
                    new_sod_rows.append(updated)
                    eod_index[key] = updated   # prevent double-insert if same security queued twice

                settled_queue_ids.append(queue_id)
                self.stdout.write(
                    f"  Applied {trade_type} {qty} {security} "
                    f"({portfolio}/{basis}) → SOD position updated"
                )

            except Exception as exc:
                failed_queue_ids.append(queue_id)
                logger.error(
                    f"[SOD settlement] Failed to apply queue_id={queue_id}: {exc}",
                    exc_info=True
                )

        # Merge new_sod_rows into the main list so they get inserted as SOD
        sod_rows = list(eod_index.values()) + [
            r for r in new_sod_rows if r not in eod_index.values()
        ]

        self.stdout.write(
            f"SOD rows to write: {len(sod_rows)} "
            f"({len(pending_settlements)} settlement(s) applied, "
            f"{len(failed_queue_ids)} failed)"
        )

        if dry_run:
            for r in sod_rows[:10]:
                self.stdout.write(
                    f"  [DRY RUN] SOD  {r.get('portfolio')}/{r.get('security_label')}  "
                    f"basis={r.get('position_basis')}  qty={r.get('quantity')}"
                )
            if len(sod_rows) > 10:
                self.stdout.write(f"  ... and {len(sod_rows) - 10} more")
            self.stdout.write(self.style.WARNING('\nDRY RUN — no changes written'))
            return

        # ── 4. EOD rows are NOT touched — is_latest stays as-is ─────────────
        #
        # EOD is the latest record for its own date (eod_date). SOD is a new
        # record for sod_date (a different position_date) with its own
        # position_id. The two rows coexist independently — EOD retains
        # is_latest=true for eod_date, SOD is inserted with is_latest=true
        # for sod_date. No need to touch the EOD rows at all.

        # ── 5. Delete any existing SOD rows for sod_date (idempotent re-run) ─
        # Skip when --fill-gaps: existing SOD rows must be preserved.
        if not fill_gaps:
            self._delete_existing_sod(sod_date, sources, portfolio_filter)

        # ── 6. Batch-insert SOD rows with is_latest=true ─────────────────────
        inserted = self._batch_insert_sod(sod_rows, sod_date, proc_date)

        # ── 7. Mark processed settlements as COMPLETED ───────────────────────
        if settled_queue_ids:
            self._mark_settlements_completed(settled_queue_ids)
            self.stdout.write(
                f"Marked {len(settled_queue_ids)} settlement queue item(s) as COMPLETED"
            )

        if failed_queue_ids:
            self._mark_settlements_failed(failed_queue_ids)
            self.stdout.write(self.style.WARNING(
                f"Marked {len(failed_queue_ids)} settlement queue item(s) as FAILED "
                f"(check logs for details)"
            ))

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.SUCCESS(
            f'SOD snapshot complete — {inserted} row(s) inserted '
            f'({len(settled_queue_ids)} settlement(s) applied)'
        ))

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
                  AND processing_date = (
                      SELECT MAX(processing_date)
                      FROM {DATABASE}.gmp_cis_sta_dly_alldatesinfo
                      WHERE src_system = 'gmp'
                        AND sub_system = 'cis'
                        AND data_frq   = 'dly'
                        AND record_type = 'D'
                  )
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

    def _get_eod_rows(self, eod_date, sources, portfolio_filter,
                      fill_gaps=False, sod_date=None):
        """
        Fetch EOD rows from cis_position for the given date (written by refresh_positions).

        fill_gaps=True: excludes natural keys that already have a SOD row for sod_date,
                        so only positions missing a SOD row are returned.
        """
        src_list    = ', '.join(f"'{self._escape(s)}'" for s in sources)
        port_clause = (
            f"AND portfolio = '{self._escape(portfolio_filter)}'"
            if portfolio_filter else ''
        )

        # --fill-gaps: LEFT JOIN existing SOD rows and exclude matches
        fill_gaps_join  = ""
        fill_gaps_where = ""
        if fill_gaps and sod_date:
            escaped_sod = self._escape(sod_date)
            fill_gaps_join = f"""
            LEFT JOIN (
                SELECT DISTINCT portfolio, security_label, position_basis
                FROM {DATABASE}.cis_position
                WHERE position_type = 'SOD'
                  AND is_latest     = true
                  AND position_date = '{escaped_sod}'
            ) existing_sod
              ON p.portfolio      = existing_sod.portfolio
             AND p.security_label = existing_sod.security_label
             AND p.position_basis = existing_sod.position_basis
            """
            fill_gaps_where = "AND existing_sod.portfolio IS NULL"

        try:
            return impala_manager.execute_query(
                f"""
                SELECT
                    p.position_id, p.version_id,
                    p.portfolio, p.security_label,
                    p.position_basis, p.position_date,
                    p.src_system, p.processing_date,
                    p.quantity,
                    p.average_cost_fc, p.cost_fc,
                    p.average_cost_lc, p.cost_lc,
                    p.market_value_fc, p.market_value_lc,
                    p.net_book_value_fc, p.net_book_value_lc,
                    p.unrealized_pnl_fc, p.unrealized_pnl_lc,
                    p.realized_pnl_fc, p.realized_pnl_lc,
                    p.provision_fc, p.provision_lc,
                    p.dividend_fc, p.dividend_lc,
                    p.uncall_fc, p.uncall_lc,
                    p.pipeline_fc, p.pipeline_lc,
                    p.position_type, p.isin, p.source_table, p.processing_timestamp
                FROM {DATABASE}.cis_position p
                {fill_gaps_join}
                WHERE p.position_type = 'EOD'
                  AND p.position_date  = '{eod_date}'
                  AND p.src_system IN ({src_list})
                  {port_clause}
                  {fill_gaps_where}
                """,
                database=DATABASE
            ) or []
        except Exception as e:
            logger.error(f'Error fetching EOD rows for {eod_date}: {e}')
            raise

    # ── Settlement queue fetch ────────────────────────────────────────────────

    def _get_pending_settlements(self, settle_date: str):
        """
        Fetch PENDING settlement queue entries with settle_date == today.

        Only entries settling today are folded into SOD.  Future entries
        (settle_date > today) remain in the queue for a later SOD run.

        Joins cis_trade to pick up total_amount_lc (the as-traded LC amount
        entered by the user at booking time) — needed for NON-REVAL portfolios.
        """
        try:
            return impala_manager.execute_query(
                f"""
                SELECT
                    q.queue_id, q.trade_id,
                    q.portfolio_id, q.security_id,
                    q.trade_type,
                    q.quantity, q.price, q.charges,
                    q.settle_date, q.position_basis,
                    q.security_currency, q.portfolio_currency,
                    q.isin, q.security_name,
                    q.custodian, q.sub_custodian,
                    t.total_amount_lc
                FROM {DATABASE}.cis_settlement_queue q
                LEFT JOIN {DATABASE}.cis_trade t ON t.trade_id = q.trade_id
                WHERE q.settle_date = '{settle_date}'
                  AND q.status      = 'PENDING'
                ORDER BY q.queued_at ASC
                """,
                database=DATABASE
            ) or []
        except Exception as e:
            logger.error(f'Error fetching pending settlements for {settle_date}: {e}')
            return []

    # ── Apply one settlement trade to an EOD baseline row ────────────────────

    def _apply_settlement_to_position(
        self,
        existing: dict,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        trade_id,
        item: dict,
        reval_status: str = 'REVALUED',
        trade_lc: Decimal = None,
    ) -> dict:
        """
        Apply a BUY or SELL trade to an EOD position dict and return
        an updated dict suitable for SOD insertion.

        Returns None if the trade cannot be applied (e.g. SELL with no position).

        AVP formulas (same as position_service):
          BUY:  new_total_cost = old_total_cost + (qty × price) + charges
                new_avg_cost   = new_total_cost / new_qty
          SELL: avg_cost unchanged; realized_pnl += (price − avg_cost) × qty
                (full close: avg_cost → 0, qty → 0)
        """
        def _f(v, default=0.0):
            try:
                return float(v) if v is not None else float(default)
            except (TypeError, ValueError):
                return float(default)

        def _d(v, default=0):
            try:
                return Decimal(str(v)) if v is not None else Decimal(str(default))
            except Exception:
                return Decimal(str(default))

        if trade_type == 'BUY':
            old_qty      = _d(existing.get('quantity') if existing else None)
            old_avg_fc   = _d(existing.get('average_cost_fc') if existing else None)
            old_cost_fc  = old_qty * old_avg_fc
            old_avg_lc   = _d(existing.get('average_cost_lc') if existing else None)
            old_cost_lc  = old_qty * old_avg_lc

            trade_cost_fc = (quantity * price) + charges
            new_qty       = old_qty + quantity
            new_cost_fc   = old_cost_fc + trade_cost_fc

            new_avg_fc = (new_cost_fc / new_qty).quantize(
                AVP_PRECISION, rounding=ROUND_HALF_UP
            ) if new_qty > 0 else Decimal('0')

            # LC cost for this trade:
            #   NON-REVAL: use as-traded total_amount_lc (preserves the rate at booking time).
            #              Fallback to fx_ratio proxy if trade_lc not available.
            #   REVAL:     use the existing position's lc/fc ratio (latest FX applied at EOD).
            if reval_status == 'NON-REVALUED' and trade_lc is not None:
                trade_cost_lc = trade_lc
            elif old_avg_fc > 0 and old_avg_lc > 0:
                fx_ratio      = old_avg_lc / old_avg_fc
                trade_cost_lc = trade_cost_fc * fx_ratio
            else:
                trade_cost_lc = trade_cost_fc   # same-currency fallback
            new_cost_lc   = old_cost_lc + trade_cost_lc
            new_avg_lc    = (new_cost_lc / new_qty).quantize(
                AVP_PRECISION, rounding=ROUND_HALF_UP
            ) if new_qty > 0 else Decimal('0')

            # Build result — market value/unrealized_pnl carried from EOD (not recalculated
            # here; EOD job will price them correctly at day-end)
            base = dict(existing) if existing else {}
            base.update({
                'portfolio':       item.get('portfolio_id', base.get('portfolio', '')),
                'security_label':  item.get('security_id', base.get('security_label', '')),
                'position_basis':  item.get('position_basis', 'SETTLED'),
                'src_system':      base.get('src_system', 'CIS'),
                'isin':            item.get('isin') or base.get('isin'),
                'source_table':    base.get('source_table', 'cis_settlement_queue'),
                'quantity':        float(new_qty),
                'average_cost_fc': float(new_avg_fc),
                'cost_fc':         float(new_cost_fc),
                'average_cost_lc': float(new_avg_lc),
                'cost_lc':         float(new_cost_lc),
                # market_value / unrealized_pnl: keep EOD values (will be re-priced at EOD tonight)
                'market_value_fc':    _f(base.get('market_value_fc')),
                'market_value_lc':    _f(base.get('market_value_lc')),
                'unrealized_pnl_fc':  _f(base.get('unrealized_pnl_fc')),
                'unrealized_pnl_lc':  _f(base.get('unrealized_pnl_lc')),
                'net_book_value_fc':  float(new_cost_fc) + _f(base.get('unrealized_pnl_fc')) - _f(base.get('provision_fc')),
                'net_book_value_lc':  float(new_cost_lc) + _f(base.get('unrealized_pnl_lc')) - _f(base.get('provision_lc')),
                # carry all CA/CF fields unchanged
                'realized_pnl_fc':  _f(base.get('realized_pnl_fc')),
                'realized_pnl_lc':  _f(base.get('realized_pnl_lc')),
                'dividend_fc':      _f(base.get('dividend_fc')),
                'dividend_lc':      _f(base.get('dividend_lc')),
                'provision_fc':     _f(base.get('provision_fc')),
                'provision_lc':     _f(base.get('provision_lc')),
                'uncall_fc':        _f(base.get('uncall_fc')),
                'uncall_lc':        _f(base.get('uncall_lc')),
                'pipeline_fc':      _f(base.get('pipeline_fc')),
                'pipeline_lc':      _f(base.get('pipeline_lc')),
            })
            return base

        elif trade_type == 'SELL':
            if not existing:
                return None   # cannot sell without a position

            old_qty     = _d(existing.get('quantity'))
            old_avg_fc  = _d(existing.get('average_cost_fc'))
            old_avg_lc  = _d(existing.get('average_cost_lc'))
            old_rpnl_fc = _d(existing.get('realized_pnl_fc'))
            old_rpnl_lc = _d(existing.get('realized_pnl_lc'))

            if quantity > old_qty:
                logger.error(
                    f"[SOD settlement] SELL {quantity} > position {old_qty} "
                    f"for {existing.get('security_label')} — capped to available qty"
                )
                quantity = old_qty   # treat as full close

            rpnl_this_fc = (price - old_avg_fc) * quantity
            new_qty      = old_qty - quantity

            # LC realized P&L (use historical avg_cost_lc as cost basis)
            rpnl_this_lc = (price * _d(1 if old_avg_fc == 0 else old_avg_lc / old_avg_fc) - old_avg_lc) * quantity

            base = dict(existing)
            if new_qty <= 0:
                # Full close
                base.update({
                    'quantity':        0.0,
                    'average_cost_fc': 0.0,
                    'cost_fc':         0.0,
                    'average_cost_lc': 0.0,
                    'cost_lc':         0.0,
                    'market_value_fc': 0.0,
                    'market_value_lc': 0.0,
                    'unrealized_pnl_fc': 0.0,
                    'unrealized_pnl_lc': 0.0,
                    'net_book_value_fc': 0.0,
                    'net_book_value_lc': 0.0,
                    'realized_pnl_fc': float(old_rpnl_fc + rpnl_this_fc),
                    'realized_pnl_lc': float(old_rpnl_lc + rpnl_this_lc),
                    # CA/CF fields carried (obligations survive full close)
                    'uncall_fc':   float(_d(base.get('uncall_fc'))),
                    'uncall_lc':   float(_d(base.get('uncall_lc'))),
                    'pipeline_fc': float(_d(base.get('pipeline_fc'))),
                    'pipeline_lc': float(_d(base.get('pipeline_lc'))),
                    'provision_fc': float(_d(base.get('provision_fc'))),
                    'provision_lc': float(_d(base.get('provision_lc'))),
                })
            else:
                # Partial sell — AVP unchanged
                new_cost_fc  = new_qty * old_avg_fc
                new_cost_lc  = new_qty * old_avg_lc
                prov_fc      = _d(base.get('provision_fc'))
                prov_lc      = _d(base.get('provision_lc'))
                upnl_fc      = _d(base.get('unrealized_pnl_fc')) * (new_qty / old_qty)
                upnl_lc      = _d(base.get('unrealized_pnl_lc')) * (new_qty / old_qty)
                base.update({
                    'quantity':        float(new_qty),
                    'cost_fc':         float(new_cost_fc),
                    'cost_lc':         float(new_cost_lc),
                    'market_value_fc': float(_d(base.get('market_value_fc')) * (new_qty / old_qty)),
                    'market_value_lc': float(_d(base.get('market_value_lc')) * (new_qty / old_qty)),
                    'unrealized_pnl_fc': float(upnl_fc),
                    'unrealized_pnl_lc': float(upnl_lc),
                    'net_book_value_fc': float(new_cost_fc) + float(upnl_fc) - float(prov_fc),
                    'net_book_value_lc': float(new_cost_lc) + float(upnl_lc) - float(prov_lc),
                    'realized_pnl_fc': float(old_rpnl_fc + rpnl_this_fc),
                    'realized_pnl_lc': float(old_rpnl_lc + rpnl_this_lc),
                })
            return base

        else:
            logger.warning(
                f"[SOD settlement] Unsupported trade_type '{trade_type}' "
                f"for queue_id — skipped"
            )
            return None

    # ── Delete existing SOD rows ─────────────────────────────────────────────

    def _delete_existing_sod(self, sod_date, sources, portfolio_filter):
        """Remove any SOD rows already written for sod_date (idempotent re-run)."""
        src_list   = ', '.join(f"'{self._escape(s)}'" for s in sources)
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

    def _batch_insert_sod(self, sod_rows, sod_date, proc_date):
        """
        UPSERT SOD rows into cis_position in batches of 500.

        SOD is a new position_date, so every row gets a NEW position_id:
          - CIS / GMP / AMSICEQ : random (timestamp-based sequential)
          - USER_UPLOAD          : deterministic fnv_hash of the natural key
                                   (portfolio|security_label|position_basis|
                                    sod_date|src_system)
                                   — ensures re-running SOD for the same date
                                     replaces rather than duplicates.

        version_id is always a new timestamp value (records when SOD ran).
        is_latest = true — this SOD row is now the authoritative current state.
        """
        BATCH  = 500
        now_ms = int(datetime.now().timestamp() * 1000)

        UPLOAD_SOURCES = {'USER_UPLOAD'}

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
            position_type, isin, source_table, is_latest, processing_timestamp
        )"""

        def _val(v, default=0):
            return float(v) if v is not None else float(default)

        def _fnv_hash_expr(portfolio, security, basis, date, src):
            """
            Impala fnv_hash expression for a USER_UPLOAD SOD position_id.
            Uses the same 5-component natural key as all other writers —
            INT, EOD, SOD for the same natural key share the same position_id
            and coexist via the composite PK (position_id, position_type).
            """
            p = portfolio.replace("'", "''")
            s = security.replace("'", "''")
            b = basis.replace("'", "''")
            d = date
            sy = src.replace("'", "''")
            return (
                f"ABS(CAST(fnv_hash(CONCAT_WS('|', "
                f"'{p}', '{s}', '{b}', '{d}', '{sy}'"
                f")) AS BIGINT))"
            )

        def _build_row(idx, row):
            # Raw values for fnv_hash (escape happens inside _fnv_hash_expr)
            raw_portfolio = str(row.get('portfolio', '') or '')
            raw_security  = str(row.get('security_label', '') or '')
            raw_basis     = str(row.get('position_basis', 'TRADED') or 'TRADED')
            raw_src       = str(row.get('src_system', 'CIS') or 'CIS')

            # Escaped values for SQL VALUES clause
            portfolio = self._escape(raw_portfolio)
            security  = self._escape(raw_security)
            pos_basis = self._escape(raw_basis)
            src_sys   = self._escape(raw_src)
            isin_val  = f"'{self._escape(row['isin'])}'" if row.get('isin') else 'NULL'
            src_tbl   = f"'{self._escape(row['source_table'])}'" if row.get('source_table') else 'NULL'

            version_id = now_ms + idx   # new: records when SOD ran

            # position_id: deterministic for uploads, random for CIS sources
            # Pass RAW values to _fnv_hash_expr — it does its own escaping internally
            if row.get('src_system', '') in UPLOAD_SOURCES:
                position_id_expr = _fnv_hash_expr(raw_portfolio, raw_security, raw_basis, sod_date, raw_src)
            else:
                position_id_expr = str(now_ms + idx + 1_000_000)  # offset avoids collision with version_id

            return (
                f"({position_id_expr}, {version_id}, "
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
                f"'SOD', {isin_val}, {src_tbl}, true, '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')"
            )

        total = 0
        for i in range(0, len(sod_rows), BATCH):
            chunk  = sod_rows[i: i + BATCH]
            values = ',\n'.join(_build_row(i + j, r) for j, r in enumerate(chunk))
            impala_manager.execute_write(
                f"UPSERT INTO {DATABASE}.cis_position {col_list} VALUES {values}",
                database=DATABASE
            )
            total += len(chunk)
            self.stdout.write(f'  Inserted rows {i + 1}–{i + len(chunk)}')

        return total

    # ── Mark settlement queue entries ────────────────────────────────────────

    def _mark_settlements_completed(self, queue_ids: list):
        """Mark processed settlement queue entries as COMPLETED."""
        if not queue_ids:
            return
        ids_csv   = ', '.join(str(qid) for qid in queue_ids)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            impala_manager.execute_write(
                f"""
                UPDATE {DATABASE}.cis_settlement_queue
                SET status       = 'COMPLETED',
                    processed_at = '{timestamp}',
                    updated_at   = '{timestamp}'
                WHERE queue_id IN ({ids_csv})
                """,
                database=DATABASE
            )
        except Exception as e:
            logger.error(f'Error marking settlements completed: {e}')

    def _mark_settlements_failed(self, queue_ids: list):
        """Mark failed settlement queue entries as FAILED."""
        if not queue_ids:
            return
        ids_csv   = ', '.join(str(qid) for qid in queue_ids)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            impala_manager.execute_write(
                f"""
                UPDATE {DATABASE}.cis_settlement_queue
                SET status     = 'FAILED',
                    updated_at = '{timestamp}',
                    error_message = 'Failed during SOD settlement application — see logs'
                WHERE queue_id IN ({ids_csv})
                """,
                database=DATABASE
            )
        except Exception as e:
            logger.error(f'Error marking settlements failed: {e}')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_portfolio_revaluation_status(self, portfolio_id: str) -> str:
        """Return 'REVALUED' or 'NON-REVALUED' for the given portfolio."""
        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT revaluation_status
                FROM {DATABASE}.cis_portfolio
                WHERE name = '{self._escape(portfolio_id)}'
                LIMIT 1
                """,
                database=DATABASE
            )
            if rows and rows[0].get('revaluation_status'):
                status = rows[0]['revaluation_status'].upper()
                if status in ('REVALUED', 'NON-REVALUED'):
                    return status
        except Exception as e:
            logger.error(f'Error fetching revaluation status for {portfolio_id}: {e}')
        return 'REVALUED'

    @staticmethod
    def _escape(value):
        if value is None:
            return ''
        return str(value).replace("'", "''")

    @staticmethod
    def _to_iso(yyyymmdd):
        """Convert YYYYMMDD string to YYYY-MM-DD."""
        s = str(yyyymmdd).strip()
        if len(s) == 8:
            return f'{s[:4]}-{s[4:6]}-{s[6:]}'
        return s
