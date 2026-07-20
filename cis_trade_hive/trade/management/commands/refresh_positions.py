"""
EOD / CORR Position Revaluation

Refreshes market values for all open positions in cis_position (the golden copy),
covering all source systems: CIS, GMP, AMS/AMSICEQ, USER_UPLOAD.

For each position:
  1. Fetch latest price from cis_equity_price (always used; REVALUED and NON-REVALUED)
  2. If no price found, keep existing market_value_fc; recalculate LC via latest FX rate
  3. unrealized_pnl = 0 if security_investment IN (ASSOC, SUBSI), else market_value_fc - cost_fc
  4. NON-REVALUED: LC columns recalculated from FC × latest FX rate (no MTM override)
  5. net_book_value = cost + unrealized_pnl - provision
  6. Marks source row is_latest=false, inserts new EOD/CORR row with is_latest=true.

Run types
---------
  EOD  (default): Normal end-of-day run.
        - position_date inferred from alldatesinfo: reporting_date (prev_day, T-1).
        - Restricts to positions whose position_date = reporting_date.
        - Writes position_type = 'EOD'.
        - Override with --position-date if needed.

  CORR: Month-end correction run (scheduled D+1 … D+5 after month-end).
        - position_date inferred as last calendar day of month before reporting_date.
        - Restricts to positions whose position_date = last_month_end.
        - Writes position_type = 'CORR'.
        - Override with --position-date if needed.

  In both cases processing_date = today (the actual run date).

Source priority
---------------
  For each natural key (portfolio, security_label, position_basis):
    INT exists  → use INT (authoritative running position, updated by every trade/CA)
    INT missing → fall back to SOD (no new trades today; SOD carries yesterday's closing
                  position and must still be revalued and published to cis_position_rep)

Usage:
    # Normal EOD — position_date inferred from alldatesinfo reporting_date
    python manage.py refresh_positions
    python manage.py refresh_positions --portfolio UOB-SG-TRADING
    python manage.py refresh_positions --security 'UQ-UOB-102 CH'
    python manage.py refresh_positions --portfolio UOB-SG-TRADING --security 'UQ-UOB-102 CH'
    python manage.py refresh_positions --source CIS
    python manage.py refresh_positions --dry-run

    # Month-end CORR — position_date inferred as last_month_end automatically
    python manage.py refresh_positions --run-type CORR
    python manage.py refresh_positions --run-type CORR --portfolio UOB-SG-TRADING
    python manage.py refresh_positions --run-type CORR --dry-run

    # Override inferred date explicitly (both run types)
    python manage.py refresh_positions --position-date 2026-06-27
    python manage.py refresh_positions --run-type CORR --position-date 2026-05-31

    # Fill-gaps mode — keep existing EOD rows, only create missing ones from SOD/INT
    # Use when EOD run was partially completed and you want to top-up without
    # replacing the EOD rows that were already written correctly.
    python manage.py refresh_positions --position-date 2026-03-02 --fill-gaps
    python manage.py refresh_positions --position-date 2026-03-02 --source GMP --fill-gaps
    python manage.py refresh_positions --position-date 2026-03-02 --fill-gaps --dry-run
"""

import logging
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.repositories.impala_connection import impala_manager
from trade.services.multicurrency_service import multicurrency_service
from trade.services import position_id_service

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'

ALL_SOURCES = ['CIS', 'GMP', 'AMSICEQ', 'USER_UPLOAD']

AVP_PRECISION = 8  # average cost is price-per-unit, not an amount — always 8 dp


class Command(BaseCommand):
    help = 'EOD revaluation: refresh market values for all positions in cis_position (golden copy)'

    def add_arguments(self, parser):
        parser.add_argument('--portfolio', type=str, help='Filter by portfolio short name (optional)')
        parser.add_argument('--security', type=str, help='Filter by security label (optional)')
        parser.add_argument(
            '--source', type=str, choices=ALL_SOURCES,
            help='Filter by source system: CIS, GMP, AMSICEQ, USER_UPLOAD (default: all)'
        )
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be updated without writing to database')
        parser.add_argument(
            '--run-type', type=str, choices=['EOD', 'CORR'], default='EOD',
            help='EOD (default): normal end-of-day run. CORR: month-end correction run.'
        )
        parser.add_argument(
            '--position-date', type=str, default=None,
            dest='position_date',
            help='Override the inferred position_date (YYYY-MM-DD). '
                 'EOD default: reporting_date from alldatesinfo. '
                 'CORR default: last calendar day of previous month.'
        )
        parser.add_argument(
            '--fill-gaps', action='store_true', default=False,
            dest='fill_gaps',
            help='Only process positions that have NO existing EOD row for the date. '
                 'Keeps existing EOD rows untouched; only fills missing ones from SOD/INT.'
        )

    def handle(self, *args, **options):
        portfolio_filter = options.get('portfolio')
        security_filter  = options.get('security')
        source_filter    = options.get('source')
        dry_run          = options.get('dry_run', False)
        run_type         = options.get('run_type', 'EOD')
        position_date    = options.get('position_date')
        fill_gaps        = options.get('fill_gaps', False)
        today            = datetime.now().strftime('%Y-%m-%d')

        # Infer position_date from alldatesinfo when not explicitly supplied
        if not position_date:
            reporting_date, last_month_end = self._get_dates_from_alldatesinfo()
            if run_type == 'EOD':
                position_date = reporting_date
            else:
                position_date = last_month_end

        position_type = run_type  # 'EOD' or 'CORR'

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'{run_type} Position Revaluation — cis_position (golden copy)'
        ))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE — no changes will be written'))
            self.stdout.write('')

        sources = [source_filter] if source_filter else ALL_SOURCES
        self.stdout.write(f"Run type   : {run_type}")
        self.stdout.write(f"Run date   : {today}  (processing_date stamped on output)")
        self.stdout.write(f"Pos date   : {position_date}  (positions on this date revalued)")
        self.stdout.write(f"Sources    : {', '.join(sources)}")
        if fill_gaps:
            self.stdout.write(self.style.WARNING(
                'Fill-gaps  : ON — only positions with no existing EOD row will be processed'
            ))
        if portfolio_filter:
            self.stdout.write(f"Portfolio  : {portfolio_filter}")
        if security_filter:
            self.stdout.write(f"Security   : {security_filter}")
        self.stdout.write('')

        processed = updated = skipped = errors = 0

        try:
            positions = self._get_open_positions(
                portfolio_filter, sources, position_date, security_filter, fill_gaps=fill_gaps
            )

            if not positions:
                self.stdout.write(self.style.WARNING('No positions found'))
                return

            total = len(positions)
            self.stdout.write(f"Found {total} position(s) to process")

            # Batch-load all reference data in a handful of queries
            self.stdout.write('Loading reference data...')
            ref = self._load_reference_data(positions)
            self.stdout.write(f"  securities={len(ref['sec_ccy'])}  portfolios={len(ref['port_info'])}  "
                              f"prices={len(ref['prices'])}  fx_rates={len(ref['fx_rates'])}")
            self.stdout.write('')

            insert_rows = []  # accumulate VALUES tuples for batch INSERT

            for idx, position in enumerate(positions, 1):
                processed += 1

                if idx % 200 == 0 or idx == total:
                    self.stdout.write(f"Processing {idx}/{total}...")

                try:
                    result = self._process_position(position, dry_run, today, ref, insert_rows)
                    if result == 'updated':
                        updated += 1
                    elif result == 'skipped':
                        skipped += 1

                except Exception as e:
                    errors += 1
                    logger.error(
                        f"Error on position {position.get('position_id')}: {str(e)}",
                        exc_info=True
                    )
                    self.stderr.write(self.style.ERROR(
                        f"  Error on position {position.get('position_id')} "
                        f"({position.get('portfolio')}/{position.get('security_label')}): {str(e)}"
                    ))

            # Mark source rows is_latest=false, then insert EOD/CORR rows with is_latest=true
            if not dry_run and insert_rows:
                self.stdout.write(f'Writing {len(insert_rows)} {position_type} rows...')
                self._batch_mark_source_not_latest(insert_rows)
                self._batch_upsert_eod(insert_rows, today, position_type)

                # Publish EOD rows to cis_position_rep datamart (EOD only, not CORR)
                if position_type == 'EOD':
                    self.stdout.write(f'Publishing {position_date} to cis_position_rep...')
                    rep_count = self._publish_position_rep(position_date, sources)
                    self.stdout.write(self.style.SUCCESS(
                        f'  Published {rep_count} rows to cis_position_rep for {position_date}'
                    ))

            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(self.style.MIGRATE_HEADING('Summary'))
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(f"Total Processed : {processed}")
            self.stdout.write(self.style.SUCCESS(f"Updated         : {updated}"))
            self.stdout.write(self.style.WARNING(f"Skipped         : {skipped}"))
            if errors:
                self.stdout.write(self.style.ERROR(f"Errors          : {errors}"))
            else:
                self.stdout.write(f"Errors          : {errors}")
            self.stdout.write('')

            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN — no changes written'))
            else:
                self.stdout.write(self.style.SUCCESS(f'{run_type} revaluation completed'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Fatal error: {str(e)}"))
            logger.error(f"Fatal error in refresh_positions: {str(e)}", exc_info=True)
            raise

    # -------------------------------------------------------------------------
    # Date inference
    # -------------------------------------------------------------------------

    def _get_dates_from_alldatesinfo(self):
        """
        Query alldatesinfo for the two dates used by EOD and CORR runs.

        Returns (reporting_date, last_month_end) as 'YYYY-MM-DD' strings.

        reporting_date  = reporting_date column (T-1) — used by EOD.

        CORR last_month_end logic (SA rule):
          - If contextual_today and reporting_date are in DIFFERENT months
            → last_month_end = reporting_date  (reporting_date IS the month-end)
          - Else (same month)
            → last calendar day of month before reporting_date

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
                raw_rd = str(rows[0].get('reporting_date',   '') or '')[:8]
                if raw_ct and raw_rd:
                    contextual_today = datetime.strptime(raw_ct, '%Y%m%d').date()
                    reporting_date   = datetime.strptime(raw_rd, '%Y%m%d').date()
                    reporting_date_iso = reporting_date.strftime('%Y-%m-%d')

                    # SA rule: different months → reporting_date is the month-end
                    if contextual_today.month != reporting_date.month or \
                       contextual_today.year  != reporting_date.year:
                        last_month_end = reporting_date_iso
                    else:
                        first_of_ref_month = reporting_date.replace(day=1)
                        last_month_end = (first_of_ref_month - timedelta(days=1)).strftime('%Y-%m-%d')

                    logger.info(
                        f"alldatesinfo: contextual_today={raw_ct} reporting_date={raw_rd} "
                        f"→ reporting_date_iso={reporting_date_iso} last_month_end={last_month_end}"
                    )
                    return reporting_date_iso, last_month_end
        except Exception as e:
            logger.warning(f"Could not read alldatesinfo for date inference: {e}")

        # Fallback: use calendar dates
        today = date.today()
        yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        first_of_month = today.replace(day=1)
        last_month_end = (first_of_month - timedelta(days=1)).strftime('%Y-%m-%d')
        logger.warning(
            f"alldatesinfo unavailable — falling back to reporting_date={yesterday}, "
            f"last_month_end={last_month_end}"
        )
        return yesterday, last_month_end

    # -------------------------------------------------------------------------
    # Data fetching
    # -------------------------------------------------------------------------

    def _get_open_positions(self, portfolio_filter, sources, position_date=None,
                            security_filter=None, fill_gaps=False):
        """
        Fetch the single best source row per (portfolio, security_label, position_basis).

        Priority: INT > SOD.
        - INT exists  → use it (authoritative running position, updated by every trade/CA).
        - INT missing → fall back to SOD (no new trades today; SOD carries forward yesterday's
          closing position and must still be revalued and published to cis_position_rep).
        - EOD/CORR are never used as source (they are outputs, not inputs).

        fill_gaps=True: excludes natural keys that already have an EOD row for position_date.
                        Use this to top-up missing EOD rows without touching existing ones.

        CORR run: restricts to rows whose position_date equals the supplied month-end date.
        """
        try:
            src_list = "', '".join(self._escape(s) for s in sources)
            portfolio_clause = (
                f"AND portfolio = '{self._escape(portfolio_filter)}'"
                if portfolio_filter else ""
            )
            security_clause = (
                f"AND security_label = '{self._escape(security_filter)}'"
                if security_filter else ""
            )
            date_clause = (
                f"AND position_date = '{self._escape(position_date)}'"
                if position_date else ""
            )

            # --fill-gaps: exclude keys that already have an EOD row for this date
            fill_gaps_join  = ""
            fill_gaps_where = ""
            if fill_gaps and position_date:
                escaped_date = self._escape(position_date)
                fill_gaps_join = f"""
                LEFT JOIN (
                    SELECT DISTINCT portfolio, security_label, position_basis
                    FROM {DATABASE}.cis_position
                    WHERE position_type = 'EOD'
                      AND is_latest     = true
                      AND position_date = '{escaped_date}'
                ) existing_eod
                  ON p.portfolio      = existing_eod.portfolio
                 AND p.security_label = existing_eod.security_label
                 AND p.position_basis = existing_eod.position_basis
                """
                fill_gaps_where = "WHERE existing_eod.portfolio IS NULL"

            query = f"""
                SELECT
                    p.position_id, p.version_id,
                    p.portfolio, p.security_label,
                    p.position_basis, p.position_date,
                    p.src_system, p.processing_date,
                    p.quantity,
                    p.average_cost_fc, p.cost_fc,
                    p.average_cost_lc, p.cost_lc,
                    p.market_value_fc, p.market_value_lc,
                    p.unrealized_pnl_fc, p.unrealized_pnl_lc,
                    p.realized_pnl_fc, p.realized_pnl_lc,
                    p.provision_fc, p.provision_lc,
                    p.dividend_fc, p.dividend_lc,
                    p.uncall_fc, p.uncall_lc,
                    p.pipeline_fc, p.pipeline_lc,
                    p.position_type, p.isin, p.source_table
                FROM {DATABASE}.cis_position p
                INNER JOIN (
                    -- For each natural key pick INT if it exists, else fall back to SOD.
                    -- INT has priority=2, SOD has priority=1; COALESCE picks INT first.
                    SELECT
                        portfolio, security_label, position_basis,
                        COALESCE(
                            MAX(CASE WHEN position_type = 'INT' THEN position_id END),
                            MAX(CASE WHEN position_type = 'SOD' THEN position_id END)
                        ) AS best_position_id
                    FROM {DATABASE}.cis_position
                    WHERE src_system IN ('{src_list}')
                      AND position_type IN ('INT', 'SOD')
                      AND is_latest = true
                      AND quantity > 0
                      {portfolio_clause}
                      {security_clause}
                      {date_clause}
                    GROUP BY portfolio, security_label, position_basis
                ) latest
                  ON p.portfolio       = latest.portfolio
                 AND p.security_label  = latest.security_label
                 AND p.position_basis  = latest.position_basis
                 AND p.position_id     = latest.best_position_id
                {fill_gaps_join}
                {fill_gaps_where}
            """
            return impala_manager.execute_query(query, database=DATABASE) or []
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            raise

    # -------------------------------------------------------------------------
    # Per-position processing
    # -------------------------------------------------------------------------

    def _process_position(self, position, dry_run, run_date, ref, insert_rows):
        position_id = position.get('position_id')
        portfolio   = position.get('portfolio')
        security    = position.get('security_label')
        quantity    = position.get('quantity')

        if not quantity:
            return 'skipped'

        qty          = Decimal(str(quantity))
        cost_fc_dec  = Decimal(str(position.get('cost_fc') or 0))
        cost_lc_dec  = Decimal(str(position.get('cost_lc') or 0))
        provision_fc = Decimal(str(position.get('provision_fc') or 0))
        provision_lc = Decimal(str(position.get('provision_lc') or 0))

        # All lookups from pre-loaded cache — no per-row DB queries
        port_info    = ref['port_info'].get(portfolio, {})
        port_ccy     = port_info.get('currency')
        reval_status = (port_info.get('revaluation_status') or '').strip().upper()
        sec_ccy      = ref['sec_ccy'].get(security)
        is_equity    = ref['equity_method'].get(security, False)
        latest_price = ref['prices'].get(security)
        fx_pair      = f'{sec_ccy}-{port_ccy}' if sec_ccy and port_ccy and sec_ccy != port_ccy else None
        fx_rate      = ref['fx_rates'].get(fx_pair, Decimal('1')) if fx_pair else Decimal('1')
        fc_dp        = ref['currency_dp'].get(sec_ccy, 2)
        lc_dp        = ref['currency_dp'].get(port_ccy, 2)

        # cost_lc rules (SA):
        #   NON-REVAL: always carry forward the as-traded LC (never recompute)
        #   REVAL: use latest FX rate if it is >= position_date (the traded date);
        #          otherwise keep the as-traded LC stored on the position
        average_cost_fc = Decimal(str(position.get('average_cost_fc') or 0))
        if reval_status == 'NON-REVALUED':
            average_cost_lc = Decimal(str(position.get('average_cost_lc') or 0))
            cost_lc_write   = cost_lc_dec
        else:
            # Determine whether the latest FX rate is more recent than the traded rate
            raw_pos_date = position.get('position_date')
            pos_date_str = str(raw_pos_date)[:10] if raw_pos_date else ''
            fx_rate_date = ref['fx_rate_dates'].get(fx_pair, '') if fx_pair else ''
            # Normalise both to YYYY-MM-DD for string comparison
            if isinstance(fx_rate_date, str) and len(fx_rate_date) == 8 and '-' not in fx_rate_date:
                fx_rate_date = f'{fx_rate_date[:4]}-{fx_rate_date[4:6]}-{fx_rate_date[6:]}'

            if fx_rate_date and pos_date_str and fx_rate_date >= pos_date_str:
                # Latest FX rate is as-of or after the trade date — use it
                average_cost_lc = round(average_cost_fc * fx_rate, AVP_PRECISION)
                cost_lc_write   = round(cost_fc_dec * fx_rate, lc_dp)
            else:
                # Latest FX rate predates the trade — keep as-traded LC
                average_cost_lc = Decimal(str(position.get('average_cost_lc') or 0))
                cost_lc_write   = cost_lc_dec

        # Market value
        if latest_price is not None:
            price_dec       = Decimal(str(latest_price))
            market_value_fc = round(qty * price_dec, fc_dp)
        else:
            price_dec       = Decimal(str(position.get('market_value_fc') or 0)) / qty if qty else Decimal('0')
            market_value_fc = round(Decimal(str(position.get('market_value_fc') or 0)), fc_dp)

        market_value_lc = round(market_value_fc * fx_rate, lc_dp)

        # Unrealized P&L
        if is_equity:
            unrealized_pnl_fc = Decimal('0')
            unrealized_pnl_lc = Decimal('0')
        else:
            unrealized_pnl_fc = round(market_value_fc - cost_fc_dec, fc_dp)
            unrealized_pnl_lc = round(market_value_lc - cost_lc_write, lc_dp)

        # net_book_value = cost + unrealized_pnl - provision
        nbv_fc = round(cost_fc_dec + unrealized_pnl_fc - provision_fc, fc_dp)
        nbv_lc = round(cost_lc_write + unrealized_pnl_lc - provision_lc, lc_dp)

        if not dry_run:
            insert_rows.append({
                'position': position,
                'price_dec': price_dec,
                'market_value_fc': market_value_fc, 'market_value_lc': market_value_lc,
                'unrealized_pnl_fc': unrealized_pnl_fc, 'unrealized_pnl_lc': unrealized_pnl_lc,
                'nbv_fc': nbv_fc, 'nbv_lc': nbv_lc,
                'average_cost_lc': average_cost_lc, 'cost_lc_write': cost_lc_write,
                'fc_dp': fc_dp, 'lc_dp': lc_dp,
            })

        return 'updated'

    # -------------------------------------------------------------------------
    # Batch reference-data loading (avoids N+1 per-position queries)
    # -------------------------------------------------------------------------

    def _load_reference_data(self, positions):
        """
        Load all reference data needed for EOD revaluation in ~6 queries.
        Returns a dict with keys:
          sec_ccy        : {security_label: currency_code}
          equity_method  : {security_label: bool}  (True if ASSOC/SUBSI)
          port_info      : {portfolio: {currency, revaluation_status}}
          prices         : {security_label: Decimal}  (latest closing price)
          fx_rates       : {'SEC-PORT': Decimal}  (spot_rate_d)
          currency_dp    : {iso_code: int}  (decimal places)
        """
        securities  = list({p.get('security_label') for p in positions if p.get('security_label')})
        portfolios  = list({p.get('portfolio') for p in positions if p.get('portfolio')})

        ref = {
            'sec_ccy':       {},
            'equity_method': {},
            'port_info':     {},
            'prices':        {},
            'fx_rates':      {},
            'fx_rate_dates': {},  # {pair_key: date_str} — date of latest FX rate
            'currency_dp':   {},
        }

        if not securities and not portfolios:
            return ref

        def _placeholders(items):
            return ', '.join(['%s'] * len(items))

        # 1. Securities: currency_code + security_investment
        # Bound as query params (not string-interpolated) — security names can
        # contain apostrophes (e.g. "CD INT'L ENT"), and PyHive's SQL parser
        # rejects escaped '' quotes inside long IN (...) literal lists.
        if securities:
            rows = impala_manager.execute_query(
                f"SELECT security_name, currency_code, security_investment "
                f"FROM {DATABASE}.cis_security "
                f"WHERE security_name IN ({_placeholders(securities)})",
                securities,
                database=DATABASE
            ) or []
            for r in rows:
                lbl = r.get('security_name')
                ref['sec_ccy'][lbl] = r.get('currency_code')
                inv = (r.get('security_investment') or '').upper()
                ref['equity_method'][lbl] = inv in ('ASSOC', 'SUBSI')

        # 2. Portfolios: currency + revaluation_status
        if portfolios:
            rows = impala_manager.execute_query(
                f"SELECT name, currency, revaluation_status "
                f"FROM {DATABASE}.cis_portfolio "
                f"WHERE name IN ({_placeholders(portfolios)})",
                portfolios,
                database=DATABASE
            ) or []
            for r in rows:
                ref['port_info'][r.get('name')] = {
                    'currency': r.get('currency'),
                    'revaluation_status': r.get('revaluation_status'),
                }

        # 3. Latest closing prices for all securities
        if securities:
            rows = impala_manager.execute_query(
                f"""
                SELECT ep.security_label, ep.main_closing_price
                FROM {DATABASE}.cis_equity_price ep
                INNER JOIN (
                    SELECT security_label, MAX(price_date) AS max_date
                    FROM {DATABASE}.cis_equity_price
                    WHERE security_label IN ({_placeholders(securities)}) AND is_active = true
                    GROUP BY security_label
                ) latest
                  ON ep.security_label = latest.security_label
                 AND ep.price_date      = latest.max_date
                WHERE ep.is_active = true
                """,
                securities,
                database=DATABASE
            ) or []
            for r in rows:
                v = r.get('main_closing_price')
                if v is not None:
                    ref['prices'][r.get('security_label')] = Decimal(str(v))

        # 4. Collect all sec_ccy-port_ccy pairs that need FX rates.
        # Use multicurrency_service.get_fx_rates_batch which fetches both direct
        # and reverse pairs and inverts when only the reverse direction exists —
        # matching the same logic used during trade booking.
        pair_tuples = []
        for p in positions:
            sec   = p.get('security_label')
            port  = p.get('portfolio')
            s_ccy = ref['sec_ccy'].get(sec)
            p_ccy = ref['port_info'].get(port, {}).get('currency')
            if s_ccy and p_ccy and s_ccy != p_ccy:
                pair_tuples.append((s_ccy, p_ccy))

        if pair_tuples:
            batch_rates = multicurrency_service.get_fx_rates_batch(pair_tuples)
            for pair_key, (rate, date_used) in batch_rates.items():
                if rate and rate != Decimal('0'):
                    ref['fx_rates'][pair_key] = rate
                    # Store the FX rate date so _process_position can compare
                    # against position_date (traded rate date) for REVAL portfolios
                    ref['fx_rate_dates'][pair_key] = date_used

        # 5. Currency decimal places for all currencies involved
        all_ccys = set()
        for v in ref['sec_ccy'].values():
            if v:
                all_ccys.add(v)
        for info in ref['port_info'].values():
            c = info.get('currency')
            if c:
                all_ccys.add(c)

        if all_ccys:
            ccy_list = list(all_ccys)
            rows = impala_manager.execute_query(
                f"SELECT iso_code, precision FROM {DATABASE}.gmp_cis_sta_dly_currency "
                f"WHERE iso_code IN ({_placeholders(ccy_list)})",
                ccy_list,
                database=DATABASE
            ) or []
            for r in rows:
                prec_str = str(r.get('precision') or '')
                if '.' in prec_str:
                    dp = len(prec_str.split('.')[1].rstrip('0') or '0')
                else:
                    dp = 2
                ref['currency_dp'][r.get('iso_code')] = dp

        return ref

    # -------------------------------------------------------------------------
    # Batch write: mark source rows is_latest=false, then UPSERT EOD rows
    # -------------------------------------------------------------------------

    def _batch_mark_source_not_latest(self, insert_rows):
        """
        Mark the source row (the latest INT or SOD for this natural key) as
        is_latest=false before inserting the new EOD row.

        EOD gets a brand-new position_id and coexists with INT/SOD on the same
        position_date — they are separate rows distinguished by position_type.
        The source row is re-UPSERTed in-place (by its own position_id, the
        Kudu PK) with is_latest=false so it is no longer returned by
        is_latest=true queries.
        """
        BATCH = 500
        # Collect (position_id, full row dict) pairs — we need all fields to re-insert
        rows_by_pid = {r['position'].get('position_id'): r['position'] for r in insert_rows}
        pid_list = list(rows_by_pid.keys())

        for i in range(0, len(pid_list), BATCH):
            chunk_ids = pid_list[i: i + BATCH]
            ids_csv   = ', '.join(str(pid) for pid in chunk_ids if pid is not None)
            if not ids_csv:
                continue

            # Fetch existing rows so we can re-insert with is_latest=false
            existing = impala_manager.execute_query(
                f"""
                SELECT *
                FROM {DATABASE}.cis_position
                WHERE position_id IN ({ids_csv})
                  AND (is_latest = true OR is_latest IS NULL)
                """,
                database=DATABASE
            ) or []

            for row in existing:
                # Re-UPSERT same row with is_latest=false (position_id is PK → overwrites)
                # Values come directly from Kudu (already clean) — escape only for SQL embedding.
                pid      = row.get('position_id')
                vid      = row.get('version_id')
                port     = str(row.get('portfolio', '') or '').replace("'", "''")
                sec      = str(row.get('security_label', '') or '').replace("'", "''")
                basis    = str(row.get('position_basis', 'TRADED') or 'TRADED').replace("'", "''")
                pos_date = row.get('position_date', '')
                src_sys  = str(row.get('src_system', '') or '').replace("'", "''")
                proc_dt  = str(row.get('processing_date', '') or '').replace("'", "''")

                def _fv(v):
                    return float(v) if v is not None else 0.0

                isin_val = f"'{str(row[\"isin\"]).replace(chr(39), chr(39)*2)}'" if row.get('isin') else 'NULL'
                src_tbl  = f"'{str(row[\"source_table\"]).replace(chr(39), chr(39)*2)}'" if row.get('source_table') else 'NULL'
                ptype    = str(row.get('position_type', '') or '').replace("'", "''")

                impala_manager.execute_write(
                    f"""
                    UPSERT INTO {DATABASE}.cis_position (
                        position_id, version_id,
                        portfolio, security_label, position_basis, position_date,
                        src_system, processing_date, quantity,
                        average_cost_fc, cost_fc, average_cost_lc, cost_lc,
                        market_value_fc, market_value_lc,
                        net_book_value_fc, net_book_value_lc,
                        unrealized_pnl_fc, unrealized_pnl_lc,
                        realized_pnl_fc, realized_pnl_lc,
                        provision_fc, provision_lc,
                        dividend_fc, dividend_lc,
                        uncall_fc, uncall_lc,
                        pipeline_fc, pipeline_lc,
                        position_type, isin, source_table, is_latest,
                        processing_timestamp
                    ) VALUES (
                        {pid}, {vid},
                        '{port}', '{sec}', '{basis}', '{pos_date}',
                        '{src_sys}', '{proc_dt}', {_fv(row.get('quantity'))},
                        {_fv(row.get('average_cost_fc'))}, {_fv(row.get('cost_fc'))},
                        {_fv(row.get('average_cost_lc'))}, {_fv(row.get('cost_lc'))},
                        {_fv(row.get('market_value_fc'))}, {_fv(row.get('market_value_lc'))},
                        {_fv(row.get('net_book_value_fc'))}, {_fv(row.get('net_book_value_lc'))},
                        {_fv(row.get('unrealized_pnl_fc'))}, {_fv(row.get('unrealized_pnl_lc'))},
                        {_fv(row.get('realized_pnl_fc'))}, {_fv(row.get('realized_pnl_lc'))},
                        {_fv(row.get('provision_fc'))}, {_fv(row.get('provision_lc'))},
                        {_fv(row.get('dividend_fc'))}, {_fv(row.get('dividend_lc'))},
                        {_fv(row.get('uncall_fc'))}, {_fv(row.get('uncall_lc'))},
                        {_fv(row.get('pipeline_fc'))}, {_fv(row.get('pipeline_lc'))},
                        '{ptype}', {isin_val}, {src_tbl}, false,
                        {f"'{str(row[\"processing_timestamp\"]).replace(chr(39), chr(39)*2)}'" if row.get('processing_timestamp') else 'NULL'}
                    )
                    """,
                    database=DATABASE
                )

    def _batch_upsert_eod(self, insert_rows, run_date, position_type='EOD'):
        """
        UPSERT EOD or CORR rows into cis_position in batches of 500.

        position_id: deterministic hash of the natural key (portfolio,
                     security_label, position_basis, position_date, src_system)
                     via position_id_service.position_id() — same natural key
                     always produces the same position_id (see DDL 67). EOD/CORR
                     coexist with INT/SOD on the same position_date as separate
                     rows, distinguished by position_type in the composite PK
                     (position_id, position_type). Re-running this command for
                     the same inputs is idempotent via Kudu UPSERT — no DELETE
                     step, so no window where both an old and new row exist.
        version_id:  timestamp-based, records when this run executed.
        is_latest:   true — this row is now the authoritative state.
        position_type: 'EOD' for normal end-of-day; 'CORR' for month-end correction.
        """
        BATCH  = 500
        now_ms = int(datetime.now().timestamp() * 1000)

        def _build_value(idx, row):
            position      = row['position']
            fc_dp         = row['fc_dp']
            lc_dp         = row['lc_dp']
            avg_cost_lc   = row['average_cost_lc']
            cost_lc_write = row['cost_lc_write']
            mkt_fc        = row['market_value_fc']
            mkt_lc        = row['market_value_lc']
            upnl_fc       = row['unrealized_pnl_fc']
            upnl_lc       = row['unrealized_pnl_lc']
            nbv_fc        = row['nbv_fc']
            nbv_lc        = row['nbv_lc']

            raw_pos_date = position.get('position_date')
            pos_date  = str(raw_pos_date)[:10] if raw_pos_date else run_date
            proc_date = run_date.replace('-', '')  # YYYYMMDD — always the actual run date, not position_date

            # Deterministic position_id — same natural key always UPSERTs the same row
            src_position_id = position_id_service.position_id(
                position.get('portfolio', ''),
                position.get('security_label', ''),
                position.get('position_basis', 'TRADED'),
                pos_date,
                position.get('src_system', 'CIS'),
            )
            version_id = now_ms + idx  # records when this run executed

            def fc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, fc_dp))

            def lc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, lc_dp))

            def _sq(v):
                return str(v or '').replace("'", "''")

            portfolio = _sq(position.get('portfolio', ''))
            security  = _sq(position.get('security_label', ''))
            pos_basis = _sq(position.get('position_basis', 'TRADED'))
            src_sys   = _sq(position.get('src_system', 'CIS'))
            isin_val  = f"'{_sq(position['isin'])}'" if position.get('isin') else 'NULL'
            src_tbl   = f"'{_sq(position['source_table'])}'" if position.get('source_table') else 'NULL'

            return (
                f"({src_position_id}, {version_id}, "
                f"'{portfolio}', '{security}', '{pos_basis}', '{pos_date}', "
                f"'{src_sys}', '{proc_date}', "
                f"{float(position.get('quantity') or 0)}, "
                f"{float(round(Decimal(str(position.get('average_cost_fc') or 0)), AVP_PRECISION))}, {fc(position.get('cost_fc'))}, "
                f"{float(round(avg_cost_lc, AVP_PRECISION))}, {float(round(cost_lc_write, lc_dp))}, "
                f"{float(round(mkt_fc, fc_dp))}, {float(round(mkt_lc, lc_dp))}, "
                f"{float(round(nbv_fc, fc_dp))}, {float(round(nbv_lc, lc_dp))}, "
                f"{float(round(upnl_fc, fc_dp))}, {float(round(upnl_lc, lc_dp))}, "
                f"{fc(position.get('realized_pnl_fc'))}, {lc(position.get('realized_pnl_lc'))}, "
                f"{fc(position.get('provision_fc'))}, {lc(position.get('provision_lc'))}, "
                f"{fc(position.get('dividend_fc'))}, {lc(position.get('dividend_lc'))}, "
                f"{fc(position.get('uncall_fc'))}, {lc(position.get('uncall_lc'))}, "
                f"{fc(position.get('pipeline_fc'))}, {lc(position.get('pipeline_lc'))}, "
                f"'{position_type}', {isin_val}, {src_tbl}, true, "
                f"'{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')"
            )

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

        # UPSERT on the deterministic (position_id, position_type) composite PK —
        # re-running for the same natural key atomically replaces the existing
        # row in Kudu. No DELETE step, so no window where both an old and new
        # row can exist with is_latest=true simultaneously.
        for i in range(0, len(insert_rows), BATCH):
            chunk = insert_rows[i: i + BATCH]

            values = ',\n'.join(_build_value(i + j, r) for j, r in enumerate(chunk))
            impala_manager.execute_write(
                f"UPSERT INTO {DATABASE}.cis_position {col_list} VALUES {values}",
                database=DATABASE
            )
            self.stdout.write(f"  Upserted {position_type} rows {i + 1}–{i + len(chunk)}")

    # -------------------------------------------------------------------------
    # INSERT new EOD row into cis_position (legacy single-row path, kept for reference)
    # -------------------------------------------------------------------------

    def _insert_eod_position(self, position, price,
                              market_value_fc, market_value_lc,
                              unrealized_pnl_fc, unrealized_pnl_lc,
                              nbv_fc, nbv_lc,
                              average_cost_lc, cost_lc_write,
                              fc_dp: int = 2, lc_dp: int = 2,
                              run_date: str = None):
        """
        INSERT a new EOD row into cis_position for the given run_date.
        Deletes any existing EOD row for the same portfolio/security/position_basis/position_date
        first so there is exactly one EOD record per combination per date.
        """
        try:
            position_date   = run_date or datetime.now().strftime('%Y-%m-%d')
            processing_date = position_date.replace('-', '')  # YYYYMMDD — same date as position_date
            new_position_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 999999)
            version_id      = new_position_id

            portfolio     = self._escape(position.get('portfolio', ''))
            security      = self._escape(position.get('security_label', ''))
            pos_basis     = self._escape(position.get('position_basis', 'TRADED'))

            # Remove any existing EOD row for this portfolio/security/basis/date before inserting
            impala_manager.execute_write(
                f"""DELETE FROM {DATABASE}.cis_position
                    WHERE portfolio = '{portfolio}'
                      AND security_label = '{security}'
                      AND position_basis = '{pos_basis}'
                      AND position_date = '{position_date}'
                      AND position_type = 'EOD'""",
                database=DATABASE
            )

            def _fc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, fc_dp))

            def _lc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, lc_dp))

            query = f"""
                INSERT INTO {DATABASE}.cis_position (
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
                    position_type,
                    isin, source_table, processing_timestamp
                ) VALUES (
                    {new_position_id}, {version_id},
                    '{portfolio}',
                    '{security}',
                    '{pos_basis}',
                    '{position_date}',
                    '{self._escape(position.get('src_system', 'CIS'))}',
                    '{processing_date}',
                    {float(position.get('quantity') or 0)},
                    {float(round(Decimal(str(position.get('average_cost_fc') or 0)), AVP_PRECISION))}, {_fc(position.get('cost_fc'))},
                    {float(round(average_cost_lc, AVP_PRECISION))}, {float(round(cost_lc_write, lc_dp))},
                    {float(round(market_value_fc, fc_dp))}, {float(round(market_value_lc, lc_dp))},
                    {float(round(nbv_fc, fc_dp))}, {float(round(nbv_lc, lc_dp))},
                    {float(round(unrealized_pnl_fc, fc_dp))}, {float(round(unrealized_pnl_lc, lc_dp))},
                    {_fc(position.get('realized_pnl_fc'))}, {_lc(position.get('realized_pnl_lc'))},
                    {_fc(position.get('provision_fc'))}, {_lc(position.get('provision_lc'))},
                    {_fc(position.get('dividend_fc'))}, {_lc(position.get('dividend_lc'))},
                    {_fc(position.get('uncall_fc'))}, {_lc(position.get('uncall_lc'))},
                    {_fc(position.get('pipeline_fc'))}, {_lc(position.get('pipeline_lc'))},
                    'EOD',
                    {f"'{self._escape(position['isin'])}'" if position.get('isin') else 'NULL'},
                    {f"'{self._escape(position['source_table'])}'" if position.get('source_table') else 'NULL'},
                    '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'
                )
            """

            success = impala_manager.execute_write(query, database=DATABASE)
            if success:
                logger.debug(f"EOD insert OK: new_id={new_position_id} src_id={position.get('position_id')}")
            return success

        except Exception as e:
            logger.error(f"Error inserting EOD position {position.get('position_id')}: {str(e)}")
            return False

    # -------------------------------------------------------------------------
    # Publish EOD snapshot to cis_position_rep datamart
    # -------------------------------------------------------------------------

    def _publish_position_rep(self, position_date: str, sources: list) -> int:
        """
        Overwrite the cis_position_rep partition for position_date with the latest
        EOD rows from cis_position (is_latest=true, position_type='EOD').

        Hive external table — INSERT OVERWRITE replaces just the target partition,
        leaving all other dates' partitions untouched. Safe to call on every EOD run
        (idempotent: re-running the same date overwrites with the same or newer data).

        Returns the number of rows written.
        """
        src_list = "', '".join(self._escape(s) for s in sources)
        escaped_date = self._escape(position_date)

        # INSERT OVERWRITE replaces just the partition for this date — atomic and idempotent.
        # cis_position_rep is a Hive external Parquet table (not Kudu), so INSERT OVERWRITE
        # PARTITION is the correct idiom; DELETE is not supported on Hive external tables.
        impala_manager.execute_write(
            f"""
            INSERT OVERWRITE {DATABASE}.cis_position_rep
            PARTITION (position_date = '{escaped_date}')
            SELECT
                position_id, version_id,
                portfolio, security_label, position_basis,
                src_system, processing_date, processing_timestamp,
                isin, source_table,
                quantity,
                average_cost_fc, cost_fc,
                market_value_fc, net_book_value_fc,
                unrealized_pnl_fc, realized_pnl_fc,
                provision_fc, dividend_fc, uncall_fc, pipeline_fc,
                average_cost_lc, cost_lc,
                market_value_lc, net_book_value_lc,
                unrealized_pnl_lc, realized_pnl_lc,
                provision_lc, dividend_lc, uncall_lc, pipeline_lc
            FROM {DATABASE}.cis_position
            WHERE position_type = 'EOD'
              AND is_latest      = true
              AND position_date  = '{escaped_date}'
              AND src_system     IN ('{src_list}')
            """,
            database=DATABASE
        )

        # Step 3: Count what we just wrote
        count_rows = impala_manager.execute_query(
            f"""
            SELECT COUNT(*) AS cnt
            FROM {DATABASE}.cis_position_rep
            WHERE position_date = '{escaped_date}'
            """,
            database=DATABASE
        )
        return int((count_rows[0].get('cnt') or 0)) if count_rows else 0

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_latest_price(self, security_label):
        """Fetch latest closing price from cis_equity_price (is_active=true)."""
        safe = self._escape(security_label)
        try:
            results = impala_manager.execute_query(
                f"""
                SELECT main_closing_price
                FROM {DATABASE}.cis_equity_price
                WHERE security_label = '{safe}' AND is_active = true
                ORDER BY price_date DESC, price_timestamp DESC
                LIMIT 1
                """,
                database=DATABASE
            )
            if results and results[0].get('main_closing_price') is not None:
                return Decimal(str(results[0]['main_closing_price']))
        except Exception as e:
            logger.warning(f"cis_equity_price lookup failed for {security_label}: {str(e)}")
        return None

    def _get_security_currency(self, security_label):
        """Return currency_code for a security from cis_security."""
        try:
            safe = self._escape(security_label)
            results = impala_manager.execute_query(
                f"SELECT currency_code FROM {DATABASE}.cis_security "
                f"WHERE security_name = '{safe}' LIMIT 1",
                database=DATABASE
            )
            if results:
                return results[0].get('currency_code') or None
        except Exception as e:
            logger.debug(f"Could not get currency for {security_label}: {str(e)}")
        return None

    def _get_portfolio_info(self, portfolio):
        """Return currency and revaluation_status for a portfolio from cis_portfolio."""
        try:
            safe = self._escape(portfolio)
            results = impala_manager.execute_query(
                f"SELECT currency, revaluation_status FROM {DATABASE}.cis_portfolio "
                f"WHERE name = '{safe}' LIMIT 1",
                database=DATABASE
            )
            if results:
                return results[0]
        except Exception as e:
            logger.debug(f"Could not get portfolio info for {portfolio}: {str(e)}")
        return {}

    def _get_fx_rate(self, sec_ccy, port_ccy):
        """
        Return spot FX rate to convert FC (security currency) → LC (portfolio currency).
        ref_quot_ccy = '{sec_ccy}-{port_ccy}', spot_rate_d is the FC→LC multiplier.
        Returns Decimal('1') if same currency or rate not found.
        """
        if not sec_ccy or not port_ccy or sec_ccy == port_ccy:
            return Decimal('1')
        try:
            pair = self._escape(f'{sec_ccy}-{port_ccy}')
            results = impala_manager.execute_query(
                f"""
                SELECT spot_rate_d
                FROM {DATABASE}.gmp_cis_sta_dly_fx_rates
                WHERE ref_quot_ccy = '{pair}'
                ORDER BY `date` DESC
                LIMIT 1
                """,
                database=DATABASE
            )
            if results and results[0].get('spot_rate_d') is not None:
                return Decimal(str(results[0]['spot_rate_d']))
        except Exception as e:
            logger.debug(f"FX rate not found for {sec_ccy}-{port_ccy}: {str(e)}")
        return Decimal('1')

    def _get_currency_dp(self, currency_code) -> int:
        """
        Return decimal places for a currency from gmp_cis_sta_dly_currency.
        e.g. '0000000000.01' → 2.  Falls back to 2 if not found.
        """
        if not currency_code:
            return 2
        try:
            safe = self._escape(currency_code)
            results = impala_manager.execute_query(
                f"SELECT precision FROM {DATABASE}.gmp_cis_sta_dly_currency "
                f"WHERE iso_code = '{safe}' LIMIT 1",
                database=DATABASE
            )
            if results:
                prec_str = str(results[0].get('precision') or '')
                if '.' in prec_str:
                    return len(prec_str.split('.')[1].rstrip('0') or '0')
        except Exception as e:
            logger.debug(f"Could not get precision for {currency_code}: {str(e)}")
        return 2

    def _is_equity_method_security(self, security_label):
        """Return True if security_investment is ASSOC or SUBSI (equity method — no unrealized P&L)."""
        try:
            safe = self._escape(security_label)
            results = impala_manager.execute_query(
                f"SELECT security_investment FROM {DATABASE}.cis_security "
                f"WHERE security_name = '{safe}' LIMIT 1",
                database=DATABASE
            )
            if results:
                inv_type = (results[0].get('security_investment') or '').upper()
                return inv_type in ('ASSOC', 'SUBSI')
        except Exception as e:
            logger.error(f"Error checking security_investment for {security_label}: {str(e)}")
        return False

    def _escape(self, value):
        if value is None:
            return ''
        return str(value).replace("'", "''")
