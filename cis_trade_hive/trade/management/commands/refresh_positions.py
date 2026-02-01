"""
Refresh market values for all open positions using latest equity prices.

Usage:
    python manage.py refresh_positions
    python manage.py refresh_positions --portfolio UOB-SG-TRADING
    python manage.py refresh_positions --dry-run
"""

import logging
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'


class Command(BaseCommand):
    help = 'Refresh market values for all open positions using latest equity prices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--portfolio',
            type=str,
            help='Filter by portfolio short name (optional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without writing to database'
        )

    def handle(self, *args, **options):
        portfolio_filter = options.get('portfolio')
        dry_run = options.get('dry_run', False)

        # Display header
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write(self.style.MIGRATE_HEADING('Position Market Value Refresh'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be written'))
            self.stdout.write('')

        if portfolio_filter:
            self.stdout.write(f"Portfolio Filter: {portfolio_filter}")
            self.stdout.write('')

        # Counters
        positions_processed = 0
        positions_updated = 0
        positions_skipped = 0
        errors = 0

        try:
            # Query all OPEN positions
            positions = self._get_open_positions(portfolio_filter)

            if not positions:
                self.stdout.write(self.style.WARNING('No open positions found'))
                return

            total_positions = len(positions)
            self.stdout.write(f"Found {total_positions} open position(s) to process")
            self.stdout.write('')

            # Process each position
            for idx, position in enumerate(positions, 1):
                positions_processed += 1

                # Progress indicator
                if idx % 10 == 0 or idx == total_positions:
                    self.stdout.write(f"Processing position {idx}/{total_positions}...")

                try:
                    result = self._process_position(position, dry_run)

                    if result == 'updated':
                        positions_updated += 1
                    elif result == 'skipped':
                        positions_skipped += 1

                except Exception as e:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"Error processing position {position.get('position_id')}: {str(e)}"
                        )
                    )
                    logger.error(
                        f"Error processing position {position.get('position_id')}: {str(e)}",
                        exc_info=True
                    )

            # Display summary
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(self.style.MIGRATE_HEADING('Summary'))
            self.stdout.write(self.style.MIGRATE_HEADING('=' * 80))
            self.stdout.write(f"Total Positions Processed: {positions_processed}")
            self.stdout.write(self.style.SUCCESS(f"Positions Updated: {positions_updated}"))
            self.stdout.write(self.style.WARNING(f"Positions Skipped (no price): {positions_skipped}"))

            if errors > 0:
                self.stdout.write(self.style.ERROR(f"Errors: {errors}"))
            else:
                self.stdout.write(f"Errors: {errors}")

            self.stdout.write('')

            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN - No changes were written to database'))
            else:
                self.stdout.write(self.style.SUCCESS('Position refresh completed successfully'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Fatal error: {str(e)}"))
            logger.error(f"Fatal error in refresh_positions: {str(e)}", exc_info=True)
            raise

    def _get_open_positions(self, portfolio_filter):
        """
        Fetch all OPEN positions (latest version per position_id) from cis_trade_position.

        Args:
            portfolio_filter: Optional portfolio short name filter

        Returns:
            List of position dictionaries
        """
        try:
            # Build optional portfolio filter
            portfolio_clause = ""
            if portfolio_filter:
                safe_portfolio = self._escape_string(portfolio_filter)
                portfolio_clause = f"AND p.portfolio_short_name = '{safe_portfolio}'"

            query = f"""
                SELECT
                    p.position_id,
                    p.version_id,
                    p.portfolio_short_name,
                    p.security_label,
                    p.quantity,
                    p.average_cost,
                    p.total_cost,
                    p.realized_pnl,
                    p.current_price,
                    p.market_value,
                    p.unrealized_pnl,
                    p.trade_id
                FROM {DATABASE}.cis_trade_position p
                INNER JOIN (
                    SELECT position_id, MAX(version_id) as max_version
                    FROM {DATABASE}.cis_trade_position
                    GROUP BY position_id
                ) latest ON p.position_id = latest.position_id AND p.version_id = latest.max_version
                WHERE p.status = 'OPEN' AND p.is_active = true
                {portfolio_clause}
            """

            positions = impala_manager.execute_query(query, database=DATABASE)
            return positions

        except Exception as e:
            logger.error(f"Error fetching open positions: {str(e)}")
            raise

    def _process_position(self, position, dry_run):
        """
        Process a single position - fetch latest price and insert new version with updated market values.

        Args:
            position: Position dictionary
            dry_run: If True, don't write to database

        Returns:
            'updated', 'skipped', or 'error'
        """
        position_id = position.get('position_id')
        portfolio = position.get('portfolio_short_name')
        security = position.get('security_label')
        quantity = position.get('quantity')
        total_cost = position.get('total_cost')

        # Validate required fields
        if not quantity or not total_cost:
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipping position {position_id}: Missing quantity or total_cost"
                )
            )
            return 'skipped'

        # Fetch latest price
        latest_price = self._get_latest_price(security)

        if latest_price is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipping position {position_id} ({portfolio}/{security}): No price found"
                )
            )
            return 'skipped'

        # Calculate new values
        quantity_decimal = Decimal(str(quantity))
        total_cost_decimal = Decimal(str(total_cost))
        price_decimal = Decimal(str(latest_price))

        market_value = quantity_decimal * price_decimal
        unrealized_pnl = market_value - total_cost_decimal

        # Display update info
        self.stdout.write(
            f"  Updating {portfolio}/{security}: "
            f"Price={latest_price:.2f}, MktValue={market_value:.2f}, PnL={unrealized_pnl:.2f}"
        )

        # Insert new version (if not dry-run)
        if not dry_run:
            success = self._insert_position_version(
                position,
                latest_price,
                market_value,
                unrealized_pnl
            )

            if not success:
                self.stderr.write(
                    self.style.ERROR(
                        f"  Failed to update position {position_id}"
                    )
                )
                return 'error'

        return 'updated'

    def _get_latest_price(self, security):
        """
        Fetch the latest equity price for a security.

        Args:
            security: Security label

        Returns:
            Latest price as Decimal, or None if not found
        """
        try:
            # Escape security label to prevent SQL injection
            safe_security = self._escape_string(security)

            # Try to get price from cis_equity_price_kudu
            query = f"""
                SELECT main_closing_price, price_date
                FROM {DATABASE}.cis_equity_price_kudu
                WHERE security_label = '{safe_security}' AND is_active = true
                ORDER BY price_date DESC, price_timestamp DESC
                LIMIT 1
            """

            results = impala_manager.execute_query(query, database=DATABASE)

            if results and results[0].get('main_closing_price') is not None:
                return Decimal(str(results[0]['main_closing_price']))

            # Fallback: try cis_security_kudu
            fallback_query = f"""
                SELECT price
                FROM {DATABASE}.cis_security_kudu
                WHERE security_name = '{safe_security}'
                LIMIT 1
            """

            fallback_results = impala_manager.execute_query(fallback_query, database=DATABASE)

            if fallback_results and fallback_results[0].get('price') is not None:
                return Decimal(str(fallback_results[0]['price']))

            return None

        except Exception as e:
            logger.error(f"Error fetching price for {security}: {str(e)}")
            return None

    def _insert_position_version(self, position, current_price, market_value, unrealized_pnl):
        """
        Insert a new position version with updated market values (versioned snapshot pattern).

        Args:
            position: Current position dictionary
            current_price: Current price
            market_value: Calculated market value
            unrealized_pnl: Calculated unrealized P&L

        Returns:
            True if successful, False otherwise
        """
        try:
            import uuid
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            version_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

            upsert_query = f"""
                UPSERT INTO {DATABASE}.cis_trade_position
                (version_id, position_id, position_date, portfolio_short_name, security_label,
                 quantity, average_cost, total_cost,
                 realized_pnl, current_price, market_value, unrealized_pnl,
                 trade_id, trade_type,
                 status, is_active,
                 created_by, created_at)
                VALUES (
                    {version_id}, {position.get('position_id')},
                    '{datetime.now().strftime('%Y-%m-%d')}',
                    '{self._escape_string(position.get('portfolio_short_name', ''))}',
                    '{self._escape_string(position.get('security_label', ''))}',
                    {position.get('quantity', 0)},
                    {position.get('average_cost', 0)},
                    {position.get('total_cost', 0)},
                    {position.get('realized_pnl', 0)},
                    {current_price}, {market_value}, {unrealized_pnl},
                    {position.get('trade_id', 0)}, 'MARKET_REFRESH',
                    'OPEN', true,
                    'SYSTEM', '{timestamp}'
                )
            """

            success = impala_manager.execute_write(upsert_query, database=DATABASE)

            if success:
                logger.debug(f"Inserted new version for position {position.get('position_id')}")
            else:
                logger.error(f"Failed to insert version for position {position.get('position_id')}")

            return success

        except Exception as e:
            logger.error(f"Error inserting position version {position.get('position_id')}: {str(e)}")
            return False

    def _escape_string(self, value):
        """
        Escape single quotes to prevent SQL injection.

        Args:
            value: String to escape

        Returns:
            Escaped string
        """
        if value is None:
            return ''

        # Replace single quotes with two single quotes (SQL standard escaping)
        return str(value).replace("'", "''")
