"""
EOD Position Revaluation

Refreshes market values for all open positions in cis_position (the golden copy),
covering all source systems: CIS, GMP, AMS/AMSICEQ, USER_UPLOAD.

For each position:
  1. Fetch latest price from cis_equity_price (fallback: cis_security_kudu.price)
  2. Apply equity-method rule: if security_investment IN (ASSOC, SUBSI) → unrealized_pnl = 0
  3. UPSERT back into cis_position with updated market values and position_type = 'EOD'

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

# All src_system values considered OPEN/active positions in cis_position
ALL_SOURCES = ['CIS', 'GMP', 'AMSICEQ', 'USER_UPLOAD']


class Command(BaseCommand):
    help = 'EOD revaluation: refresh market values for all positions in cis_position (golden copy)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--portfolio',
            type=str,
            help='Filter by portfolio short name (optional)'
        )
        parser.add_argument(
            '--source',
            type=str,
            choices=ALL_SOURCES,
            help='Filter by source system: CIS, GMP, AMSICEQ, USER_UPLOAD (default: all)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without writing to database'
        )

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
                    self.stderr.write(
                        self.style.ERROR(
                            f"  Error on position {position.get('position_id')} "
                            f"({position.get('portfolio')}/{position.get('security_label')}): {str(e)}"
                        )
                    )

            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(self.style.MIGRATE_HEADING('Summary'))
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(f"Total Processed : {processed}")
            self.stdout.write(self.style.SUCCESS(f"Updated         : {updated}"))
            self.stdout.write(self.style.WARNING(f"Skipped (no px) : {skipped}"))
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
        Fetch latest version of every position from cis_position (golden copy).
        cis_position PK is position_id — one row per position, so no version JOIN needed.
        """
        try:
            conditions = []

            src_list = "', '".join(self._escape(s) for s in sources)
            conditions.append(f"src_system IN ('{src_list}')")

            if portfolio_filter:
                conditions.append(f"portfolio = '{self._escape(portfolio_filter)}'")

            where = "WHERE " + " AND ".join(conditions)

            query = f"""
                SELECT
                    position_id,
                    version_id,
                    portfolio,
                    security_label,
                    position_basis,
                    position_date,
                    src_system,
                    processing_date,
                    quantity,
                    average_cost_fc,
                    cost_fc,
                    average_cost_lc,
                    cost_lc,
                    market_value_fc,
                    market_value_lc,
                    unrealized_pnl_fc,
                    unrealized_pnl_lc,
                    realized_pnl_fc,
                    realized_pnl_lc,
                    provision_fc,
                    provision_lc,
                    dividend_fc,
                    dividend_lc,
                    uncall_fc,
                    uncall_lc,
                    pipeline_fc,
                    pipeline_lc,
                    position_type,
                    isin,
                    source_table
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
        portfolio = position.get('portfolio')
        security = position.get('security_label')
        quantity = position.get('quantity')
        cost_fc = position.get('cost_fc')

        if not quantity or not cost_fc:
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipping {position_id} ({portfolio}/{security}): missing quantity or cost_fc"
                )
            )
            return 'skipped'

        latest_price = self._get_latest_price(security)

        if latest_price is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipping {position_id} ({portfolio}/{security}): no price found"
                )
            )
            return 'skipped'

        qty = Decimal(str(quantity))
        cost_fc_dec = Decimal(str(cost_fc))
        price_dec = Decimal(str(latest_price))

        market_value_fc = qty * price_dec

        # Equity method: associates/subsidiaries carried at cost — no MTM
        if self._is_equity_method_security(security):
            unrealized_pnl_fc = Decimal('0')
        else:
            unrealized_pnl_fc = market_value_fc - cost_fc_dec

        # LC: reapply FX if we have a stored LC cost, else mirror FC
        cost_lc_dec = Decimal(str(position.get('cost_lc') or cost_fc))
        if cost_lc_dec != cost_fc_dec and cost_fc_dec != 0:
            # Derive implied FX rate from stored values and reapply
            implied_fx = cost_lc_dec / cost_fc_dec
            market_value_lc = market_value_fc * implied_fx
            unrealized_pnl_lc = Decimal('0') if self._is_equity_method_security(security) else market_value_lc - cost_lc_dec
        else:
            market_value_lc = market_value_fc
            unrealized_pnl_lc = unrealized_pnl_fc

        self.stdout.write(
            f"  {portfolio}/{security} [{position.get('src_system')}]: "
            f"px={latest_price:.4f}  mkt_fc={market_value_fc:.2f}  "
            f"upnl_fc={unrealized_pnl_fc:.2f}"
            + ("  [EQUITY METHOD — pnl=0]" if self._is_equity_method_security(security) else "")
        )

        if not dry_run:
            success = self._upsert_eod_position(
                position, price_dec, market_value_fc, market_value_lc,
                unrealized_pnl_fc, unrealized_pnl_lc
            )
            if not success:
                self.stderr.write(self.style.ERROR(f"  Failed to upsert position {position_id}"))
                return 'error'

        return 'updated'

    # -------------------------------------------------------------------------
    # UPSERT back to cis_position
    # -------------------------------------------------------------------------

    def _upsert_eod_position(self, position, price, market_value_fc, market_value_lc,
                              unrealized_pnl_fc, unrealized_pnl_lc):
        """
        UPSERT the same position_id back into cis_position with:
          - updated market_value_fc/lc, unrealized_pnl_fc/lc, market_price (via net_book_value proxy)
          - position_type = 'EOD'
          - new version_id (timestamp-based)
          - processing_date = today
        All other columns (cost, realized_pnl, dividends, etc.) carried forward unchanged.
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            version_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

            def _f(v, default=0):
                return float(v) if v is not None else float(default)

            query = f"""
                UPSERT INTO {DATABASE}.cis_position (
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
                    {position['position_id']}, {version_id},
                    '{self._escape(position.get('portfolio', ''))}',
                    '{self._escape(position.get('security_label', ''))}',
                    '{self._escape(position.get('position_basis', 'TRADE_DATE'))}',
                    '{self._escape(position.get('position_date', today))}',
                    '{self._escape(position.get('src_system', 'CIS'))}',
                    '{today}',
                    {_f(position.get('quantity'))},
                    {_f(position.get('average_cost_fc'))}, {_f(position.get('cost_fc'))},
                    {_f(position.get('average_cost_lc'))}, {_f(position.get('cost_lc'))},
                    {float(market_value_fc)}, {float(market_value_lc)},
                    {float(market_value_fc)}, {float(market_value_lc)},
                    {float(unrealized_pnl_fc)}, {float(unrealized_pnl_lc)},
                    {_f(position.get('realized_pnl_fc'))}, {_f(position.get('realized_pnl_lc'))},
                    {_f(position.get('provision_fc'))}, {_f(position.get('provision_lc'))},
                    {_f(position.get('dividend_fc'))}, {_f(position.get('dividend_lc'))},
                    {_f(position.get('uncall_fc'))}, {_f(position.get('uncall_lc'))},
                    {_f(position.get('pipeline_fc'))}, {_f(position.get('pipeline_lc'))},
                    'EOD',
                    {f"'{self._escape(position['isin'])}'" if position.get('isin') else 'NULL'},
                    {f"'{self._escape(position['source_table'])}'" if position.get('source_table') else 'NULL'}
                )
            """

            success = impala_manager.execute_write(query, database=DATABASE)
            if success:
                logger.debug(f"EOD upsert OK: position_id={position['position_id']}")
            return success

        except Exception as e:
            logger.error(f"Error upserting position {position.get('position_id')}: {str(e)}")
            return False

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_latest_price(self, security_label):
        """Fetch latest closing price from cis_equity_price; fallback to cis_security_kudu."""
        try:
            safe = self._escape(security_label)
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

            # Fallback: last known price on security master
            fallback = impala_manager.execute_query(
                f"SELECT price FROM {DATABASE}.cis_security_kudu "
                f"WHERE security_label = '{safe}' LIMIT 1",
                database=DATABASE
            )
            if fallback and fallback[0].get('price') is not None:
                return Decimal(str(fallback[0]['price']))

            return None

        except Exception as e:
            logger.error(f"Error fetching price for {security_label}: {str(e)}")
            return None

    def _is_equity_method_security(self, security_label):
        """Return True if security_investment is ASSOC or SUBSI (equity method — no MTM)."""
        try:
            safe = self._escape(security_label)
            results = impala_manager.execute_query(
                f"SELECT security_investment FROM {DATABASE}.cis_security_kudu "
                f"WHERE security_label = '{safe}' LIMIT 1",
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
