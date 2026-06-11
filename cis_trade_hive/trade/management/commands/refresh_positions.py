"""
EOD Position Revaluation

Refreshes market values for all open positions in cis_position (the golden copy),
covering all source systems: CIS, GMP, AMS/AMSICEQ, USER_UPLOAD.

For each position:
  1. Fetch latest price from cis_equity_price (always used; REVALUED and NON-REVALUED)
  2. If no price found, keep existing market_value_fc; recalculate LC via latest FX rate
  3. unrealized_pnl = 0 if security_investment IN (ASSOC, SUBSI), else market_value_fc - cost_fc
  4. NON-REVALUED: LC columns recalculated from FC × latest FX rate (no MTM override)
  5. net_book_value = cost + unrealized_pnl - provision
  6. INSERT new cis_position row per run (position_type='EOD', position_basis both TRADE_DATE+SETTLE_DATE) — never overwrite

Usage:
    python manage.py refresh_positions
    python manage.py refresh_positions --portfolio UOB-SG-TRADING
    python manage.py refresh_positions --source CIS
    python manage.py refresh_positions --source AMS
    python manage.py refresh_positions --source USER_UPLOAD
    python manage.py refresh_positions --source GMP
    python manage.py refresh_positions --dry-run
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'

ALL_SOURCES = ['CIS', 'GMP', 'AMSICEQ', 'USER_UPLOAD']


class Command(BaseCommand):
    help = 'EOD revaluation: refresh market values for all positions in cis_position (golden copy)'

    def add_arguments(self, parser):
        parser.add_argument('--portfolio', type=str, help='Filter by portfolio short name (optional)')
        parser.add_argument(
            '--source', type=str, choices=ALL_SOURCES,
            help='Filter by source system: CIS, GMP, AMSICEQ, USER_UPLOAD (default: all)'
        )
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be updated without writing to database')
        parser.add_argument(
            '--date', type=str, default=None,
            help='Position date for EOD records (YYYY-MM-DD). Default: today'
        )

    def handle(self, *args, **options):
        portfolio_filter = options.get('portfolio')
        source_filter = options.get('source')
        dry_run = options.get('dry_run', False)
        run_date = options.get('date') or datetime.now().strftime('%Y-%m-%d')

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('EOD Position Revaluation — cis_position (golden copy)'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE — no changes will be written'))
            self.stdout.write('')

        sources = [source_filter] if source_filter else ALL_SOURCES
        self.stdout.write(f"Sources    : {', '.join(sources)}")
        self.stdout.write(f"Position date: {run_date}")
        if portfolio_filter:
            self.stdout.write(f"Portfolio  : {portfolio_filter}")
        self.stdout.write('')

        processed = updated = skipped = errors = 0

        try:
            positions = self._get_open_positions(portfolio_filter, sources)

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
                    result = self._process_position(position, dry_run, run_date, ref, insert_rows)
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

            # Batch DELETE existing EOD rows then batch INSERT new ones
            if not dry_run and insert_rows:
                self.stdout.write(f'Writing {len(insert_rows)} EOD rows...')
                self._batch_delete_eod(insert_rows, run_date)
                self._batch_insert_eod(insert_rows, run_date)

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
                self.stdout.write(self.style.SUCCESS('EOD revaluation completed'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Fatal error: {str(e)}"))
            logger.error(f"Fatal error in refresh_positions: {str(e)}", exc_info=True)
            raise

    # -------------------------------------------------------------------------
    # Data fetching
    # -------------------------------------------------------------------------

    def _get_open_positions(self, portfolio_filter, sources):
        """
        Fetch the single latest row per portfolio/security/position_basis from cis_position.
        Latest = highest position_id (most recently inserted row of any type).
        This ensures the EOD revaluation carries forward all accumulated CF/CA amounts
        and only creates one EOD record per combination per run date.
        """
        try:
            src_list = "', '".join(self._escape(s) for s in sources)
            portfolio_clause = (
                f"AND portfolio = '{self._escape(portfolio_filter)}'"
                if portfolio_filter else ""
            )

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
                    SELECT portfolio, security_label, position_basis,
                           MAX(position_id) AS max_position_id
                    FROM {DATABASE}.cis_position
                    WHERE src_system IN ('{src_list}')
                      AND quantity > 0
                      {portfolio_clause}
                    GROUP BY portfolio, security_label, position_basis
                ) latest
                  ON p.portfolio       = latest.portfolio
                 AND p.security_label  = latest.security_label
                 AND p.position_basis  = latest.position_basis
                 AND p.position_id     = latest.max_position_id
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

        # cost_lc: recalculate for REVALUED; carry forward for NON-REVALUED
        average_cost_fc = Decimal(str(position.get('average_cost_fc') or 0))
        if reval_status == 'NON-REVALUED':
            average_cost_lc = Decimal(str(position.get('average_cost_lc') or 0))
            cost_lc_write   = cost_lc_dec
        else:
            average_cost_lc = round(average_cost_fc * fx_rate, lc_dp)
            cost_lc_write   = round(cost_fc_dec * fx_rate, lc_dp)

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
            'currency_dp':   {},
        }

        if not securities and not portfolios:
            return ref

        def _in_list(items):
            escaped = [f"'{self._escape(i)}'" for i in items]
            return ', '.join(escaped)

        # 1. Securities: currency_code + security_investment
        if securities:
            rows = impala_manager.execute_query(
                f"SELECT security_name, currency_code, security_investment "
                f"FROM {DATABASE}.cis_security "
                f"WHERE security_name IN ({_in_list(securities)})",
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
                f"WHERE name IN ({_in_list(portfolios)})",
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
                    WHERE security_label IN ({_in_list(securities)}) AND is_active = true
                    GROUP BY security_label
                ) latest
                  ON ep.security_label = latest.security_label
                 AND ep.price_date      = latest.max_date
                WHERE ep.is_active = true
                """,
                database=DATABASE
            ) or []
            for r in rows:
                v = r.get('main_closing_price')
                if v is not None:
                    ref['prices'][r.get('security_label')] = Decimal(str(v))

        # 4. Collect all sec_ccy-port_ccy pairs that need FX rates
        pairs = set()
        for p in positions:
            sec   = p.get('security_label')
            port  = p.get('portfolio')
            s_ccy = ref['sec_ccy'].get(sec)
            p_ccy = ref['port_info'].get(port, {}).get('currency')
            if s_ccy and p_ccy and s_ccy != p_ccy:
                pairs.add(f'{s_ccy}-{p_ccy}')

        if pairs:
            rows = impala_manager.execute_query(
                f"""
                SELECT fr.ref_quot_ccy, fr.spot_rate_d
                FROM {DATABASE}.gmp_cis_sta_dly_fx_rates fr
                INNER JOIN (
                    SELECT ref_quot_ccy, MAX(`date`) AS max_date
                    FROM {DATABASE}.gmp_cis_sta_dly_fx_rates
                    WHERE ref_quot_ccy IN ({_in_list(list(pairs))})
                    GROUP BY ref_quot_ccy
                ) latest
                  ON fr.ref_quot_ccy = latest.ref_quot_ccy
                 AND fr.`date`        = latest.max_date
                """,
                database=DATABASE
            ) or []
            for r in rows:
                v = r.get('spot_rate_d')
                if v is not None:
                    ref['fx_rates'][r.get('ref_quot_ccy')] = Decimal(str(v))

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
            rows = impala_manager.execute_query(
                f"SELECT iso_code, precision FROM {DATABASE}.gmp_cis_sta_dly_currency "
                f"WHERE iso_code IN ({_in_list(list(all_ccys))})",
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
    # Batch write: DELETE existing EOD rows then INSERT new ones
    # -------------------------------------------------------------------------

    def _batch_delete_eod(self, insert_rows, run_date):
        """
        Delete all existing EOD rows for the (portfolio, security_label, position_basis, position_date)
        combinations we are about to insert.  Uses a single DELETE per batch of 500 tuples.
        """
        BATCH = 500
        tuples = [
            (
                self._escape(r['position'].get('portfolio', '')),
                self._escape(r['position'].get('security_label', '')),
                self._escape(r['position'].get('position_basis', 'TRADE_DATE')),
            )
            for r in insert_rows
        ]
        position_date = run_date

        for i in range(0, len(tuples), BATCH):
            chunk = tuples[i: i + BATCH]
            in_clause = ', '.join(
                f"('{p}', '{s}', '{b}')" for p, s, b in chunk
            )
            impala_manager.execute_write(
                f"""DELETE FROM {DATABASE}.cis_position
                    WHERE position_type = 'EOD'
                      AND position_date  = '{position_date}'
                      AND (portfolio, security_label, position_basis)
                          IN ({in_clause})""",
                database=DATABASE
            )

    def _batch_insert_eod(self, insert_rows, run_date):
        """
        INSERT all accumulated EOD rows in batches of 500.
        Each row dict comes from _process_position().
        run_date is the --date arg (YYYY-MM-DD), used as position_date for all EOD rows.
        """
        BATCH = 500
        now_ms = int(datetime.now().timestamp() * 1000)

        def _build_value(idx, row):
            position  = row['position']
            fc_dp     = row['fc_dp']
            lc_dp     = row['lc_dp']
            avg_cost_lc   = row['average_cost_lc']
            cost_lc_write = row['cost_lc_write']
            mkt_fc    = row['market_value_fc']
            mkt_lc    = row['market_value_lc']
            upnl_fc   = row['unrealized_pnl_fc']
            upnl_lc   = row['unrealized_pnl_lc']
            nbv_fc    = row['nbv_fc']
            nbv_lc    = row['nbv_lc']

            new_id    = now_ms + idx  # unique within this batch run
            pos_date  = run_date      # EOD position_date = the --date run arg
            proc_date = pos_date.replace('-', '')  # YYYYMMDD

            def fc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, fc_dp))

            def lc(v, default=0):
                val = Decimal(str(v)) if v is not None else Decimal(str(default))
                return float(round(val, lc_dp))

            portfolio = self._escape(position.get('portfolio', ''))
            security  = self._escape(position.get('security_label', ''))
            pos_basis = self._escape(position.get('position_basis', 'TRADE_DATE'))
            src_sys   = self._escape(position.get('src_system', 'CIS'))
            isin_val  = f"'{self._escape(position['isin'])}'" if position.get('isin') else 'NULL'
            src_tbl   = f"'{self._escape(position['source_table'])}'" if position.get('source_table') else 'NULL'

            return (
                f"({new_id}, {new_id}, "
                f"'{portfolio}', '{security}', '{pos_basis}', '{pos_date}', "
                f"'{src_sys}', '{proc_date}', "
                f"{float(position.get('quantity') or 0)}, "
                f"{fc(position.get('average_cost_fc'))}, {fc(position.get('cost_fc'))}, "
                f"{float(round(avg_cost_lc, lc_dp))}, {float(round(cost_lc_write, lc_dp))}, "
                f"{float(round(mkt_fc, fc_dp))}, {float(round(mkt_lc, lc_dp))}, "
                f"{float(round(nbv_fc, fc_dp))}, {float(round(nbv_lc, lc_dp))}, "
                f"{float(round(upnl_fc, fc_dp))}, {float(round(upnl_lc, lc_dp))}, "
                f"{fc(position.get('realized_pnl_fc'))}, {lc(position.get('realized_pnl_lc'))}, "
                f"{fc(position.get('provision_fc'))}, {lc(position.get('provision_lc'))}, "
                f"{fc(position.get('dividend_fc'))}, {lc(position.get('dividend_lc'))}, "
                f"{fc(position.get('uncall_fc'))}, {lc(position.get('uncall_lc'))}, "
                f"{fc(position.get('pipeline_fc'))}, {lc(position.get('pipeline_lc'))}, "
                f"'EOD', {isin_val}, {src_tbl})"
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
            position_type, isin, source_table
        )"""

        for i in range(0, len(insert_rows), BATCH):
            chunk = insert_rows[i: i + BATCH]
            values = ',\n'.join(_build_value(i + j, r) for j, r in enumerate(chunk))
            impala_manager.execute_write(
                f"INSERT INTO {DATABASE}.cis_position {col_list} VALUES {values}",
                database=DATABASE
            )
            self.stdout.write(f"  Inserted rows {i + 1}–{i + len(chunk)}")

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
            pos_basis     = self._escape(position.get('position_basis', 'TRADE_DATE'))

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
                    isin, source_table
                ) VALUES (
                    {new_position_id}, {version_id},
                    '{portfolio}',
                    '{security}',
                    '{pos_basis}',
                    '{position_date}',
                    '{self._escape(position.get('src_system', 'CIS'))}',
                    '{processing_date}',
                    {float(position.get('quantity') or 0)},
                    {_fc(position.get('average_cost_fc'))}, {_fc(position.get('cost_fc'))},
                    {float(round(average_cost_lc, lc_dp))}, {float(round(cost_lc_write, lc_dp))},
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
                    {f"'{self._escape(position['source_table'])}'" if position.get('source_table') else 'NULL'}
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
        return str(value).replace("\\", "\\\\").replace("'", "\\'")
