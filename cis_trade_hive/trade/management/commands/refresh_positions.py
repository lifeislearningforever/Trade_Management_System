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

    def handle(self, *args, **options):
        portfolio_filter = options.get('portfolio')
        source_filter = options.get('source')
        dry_run = options.get('dry_run', False)

        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('EOD Position Revaluation — cis_position (golden copy)'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE — no changes will be written'))
            self.stdout.write('')

        sources = [source_filter] if source_filter else ALL_SOURCES
        self.stdout.write(f"Sources    : {', '.join(sources)}")
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
            self.stdout.write('')

            for idx, position in enumerate(positions, 1):
                processed += 1

                if idx % 50 == 0 or idx == total:
                    self.stdout.write(f"Processing {idx}/{total}...")

                try:
                    result = self._process_position(position, dry_run)
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
        """Fetch all positions from cis_position (golden copy) for the given sources."""
        try:
            conditions = []
            src_list = "', '".join(self._escape(s) for s in sources)
            conditions.append(f"src_system IN ('{src_list}')")
            if portfolio_filter:
                conditions.append(f"portfolio = '{self._escape(portfolio_filter)}'")
            where = "WHERE " + " AND ".join(conditions)

            query = f"""
                SELECT
                    position_id, version_id,
                    portfolio, security_label,
                    position_basis, position_date,
                    src_system, processing_date,
                    quantity,
                    average_cost_fc, cost_fc,
                    average_cost_lc, cost_lc,
                    market_value_fc, market_value_lc,
                    unrealized_pnl_fc, unrealized_pnl_lc,
                    realized_pnl_fc, realized_pnl_lc,
                    provision_fc, provision_lc,
                    dividend_fc, dividend_lc,
                    uncall_fc, uncall_lc,
                    pipeline_fc, pipeline_lc,
                    position_type, isin, source_table
                FROM {DATABASE}.cis_position
                {where}
            """
            return impala_manager.execute_query(query, database=DATABASE) or []
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            raise

    # -------------------------------------------------------------------------
    # Per-position processing
    # -------------------------------------------------------------------------

    def _process_position(self, position, dry_run):
        position_id = position.get('position_id')
        portfolio   = position.get('portfolio')
        security    = position.get('security_label')
        quantity    = position.get('quantity')

        if not quantity:
            self.stdout.write(self.style.WARNING(
                f"  Skipping {position_id} ({portfolio}/{security}): missing quantity"
            ))
            return 'skipped'

        qty          = Decimal(str(quantity))
        cost_fc_dec  = Decimal(str(position.get('cost_fc') or 0))
        cost_lc_dec  = Decimal(str(position.get('cost_lc') or 0))
        provision_fc = Decimal(str(position.get('provision_fc') or 0))
        provision_lc = Decimal(str(position.get('provision_lc') or 0))
        is_equity    = self._is_equity_method_security(security)

        # Portfolio info: base currency and revaluation status
        port_info    = self._get_portfolio_info(portfolio)
        port_ccy     = port_info.get('currency')
        reval_status = (port_info.get('revaluation_status') or '').strip().upper()

        # Security currency and FX rate
        sec_ccy  = self._get_security_currency(security)
        fx_rate  = (
            self._get_fx_rate(sec_ccy, port_ccy)
            if sec_ccy and port_ccy and sec_ccy != port_ccy
            else Decimal('1')
        )

        # Currency decimal places for rounding
        fc_dp = self._get_currency_dp(sec_ccy)
        lc_dp = self._get_currency_dp(port_ccy)

        # cost_lc: recalculate from cost_fc × fx_rate for REVALUED; carry forward for NON-REVALUED
        average_cost_fc = Decimal(str(position.get('average_cost_fc') or 0))
        if reval_status == 'NON-REVALUED':
            average_cost_lc = Decimal(str(position.get('average_cost_lc') or 0))
            cost_lc_write   = cost_lc_dec  # carry forward unchanged
        else:
            average_cost_lc = round(average_cost_fc * fx_rate, lc_dp)
            cost_lc_write   = round(cost_fc_dec * fx_rate, lc_dp)

        # --- Market value: always use latest equity price ---
        latest_price = self._get_latest_price(security)

        if latest_price is not None:
            price_dec       = Decimal(str(latest_price))
            market_value_fc = round(qty * price_dec, fc_dp)
            price_source    = f"px={latest_price}"
        else:
            # No price available — keep existing FC market value unchanged
            price_dec       = Decimal(str(position.get('market_value_fc') or 0)) / qty if qty else Decimal('0')
            market_value_fc = round(Decimal(str(position.get('market_value_fc') or 0)), fc_dp)
            price_source    = "[NO PRICE — FC unchanged]"

        # Market value LC always recalculated from FC × latest FX rate
        market_value_lc = round(market_value_fc * fx_rate, lc_dp)

        # Unrealized P&L: 0 for SUBSI/ASSOC; otherwise market_value - cost
        # Use cost_lc_write (recalculated for REVALUED, carried for NON-REVALUED)
        if is_equity:
            unrealized_pnl_fc = Decimal('0')
            unrealized_pnl_lc = Decimal('0')
        else:
            unrealized_pnl_fc = round(market_value_fc - cost_fc_dec, fc_dp)
            unrealized_pnl_lc = round(market_value_lc - cost_lc_write, lc_dp)

        # net_book_value = cost + unrealized_pnl - provision
        nbv_fc = round(cost_fc_dec + unrealized_pnl_fc - provision_fc, fc_dp)
        nbv_lc = round(cost_lc_write + unrealized_pnl_lc - provision_lc, lc_dp)

        # NON-REVALUED: LC columns use FX-translated FC values but no MTM adjustment to cost basis
        # (market_value_fc still uses price; unrealized_pnl still calculated; LC just follows FC × FX)
        reval_tag = f"[{reval_status}]" if reval_status == 'NON-REVALUED' else ""

        self.stdout.write(
            f"  {portfolio}/{security} [{position.get('src_system')}]{reval_tag}: "
            f"{price_source}  mkt_fc={market_value_fc}  mkt_lc={market_value_lc}  "
            f"upnl_fc={unrealized_pnl_fc}  fx={fx_rate:.6f}"
            + ("  [EQUITY METHOD — pnl=0]" if is_equity else "")
        )

        if not dry_run:
            success = self._insert_eod_position(
                position, price_dec,
                market_value_fc, market_value_lc,
                unrealized_pnl_fc, unrealized_pnl_lc,
                nbv_fc, nbv_lc,
                average_cost_lc, cost_lc_write,
                fc_dp, lc_dp
            )
            if not success:
                self.stderr.write(self.style.ERROR(f"  Failed to insert EOD position {position_id}"))
                return 'error'

        return 'updated'

    # -------------------------------------------------------------------------
    # INSERT new EOD row into cis_position
    # -------------------------------------------------------------------------

    def _insert_eod_position(self, position, price,
                              market_value_fc, market_value_lc,
                              unrealized_pnl_fc, unrealized_pnl_lc,
                              nbv_fc, nbv_lc,
                              average_cost_lc, cost_lc_write,
                              fc_dp: int = 2, lc_dp: int = 2):
        """
        INSERT a new cis_position row per EOD run.
        Fresh position_id every time so EOD rows are distinct from INT/CA/CF rows.
        processing_date uses YYYYMMDD format to match INT records.
        """
        try:
            today           = datetime.now().strftime('%Y-%m-%d')
            processing_date = datetime.now().strftime('%Y%m%d')  # YYYYMMDD — matches INT records
            new_position_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 999999)
            version_id      = new_position_id

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
                    '{self._escape(position.get('portfolio', ''))}',
                    '{self._escape(position.get('security_label', ''))}',
                    '{self._escape(position.get('position_basis', 'TRADE_DATE'))}',
                    '{today}',
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
        return str(value).replace("'", "''")
