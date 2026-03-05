"""
Settlement Service - Settlement Date Logic for AVP Position Calculation

Phase 2: Settlement date handling with:
- Current date settlement (immediate processing)
- Future settlement (T+1, T+2, etc.) - queued for settle_date
- Backdated settlement (allowed up to previous month-end)
- Position recalculation chain for backdated trades

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date, timedelta
from calendar import monthrange
import uuid

from core.repositories.impala_connection import impala_manager
from trade.services.position_service import position_service, PositionService

logger = logging.getLogger(__name__)


class SettlementService:
    """
    Service for handling settlement date logic.

    Settlement Rules:
    - Current Date: Process immediately
    - Future Date (T+1, T+2): Queue for settlement on settle_date
    - Backdated: Allowed up to previous month-end, triggers recalculation
    """

    DATABASE = 'gmp_cis'
    SETTLEMENT_QUEUE_TABLE = 'cis_settlement_queue'
    TRADE_TABLE = 'cis_trade'

    # Settlement queue status
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_CANCELLED = 'CANCELLED'

    def __init__(self, position_svc: PositionService = None):
        """Initialize settlement service."""
        self.position_service = position_svc or position_service

    # =========================================================================
    # MAIN SETTLEMENT PROCESSING
    # =========================================================================

    def process_trade_settlement(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        trade_date: str,
        settle_date: str,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process trade settlement based on settlement date.

        Args:
            trade_id: Trade ID
            portfolio_id: Portfolio short name
            security_id: Security label
            trade_type: BUY or SELL
            quantity: Trade quantity
            price: Trade price
            charges: Total charges
            trade_date: Trade date (YYYY-MM-DD)
            settle_date: Settlement date (YYYY-MM-DD)
            updated_by: User performing the update

        Returns:
            Tuple of (success, message, result_data)
        """
        try:
            today = datetime.now().date()
            settle_dt = self._parse_date(settle_date)
            trade_dt = self._parse_date(trade_date)

            if settle_dt is None:
                return False, f"Invalid settlement date: {settle_date}", None

            logger.info(
                f"Processing settlement for trade {trade_id}: "
                f"settle_date={settle_date}, today={today}"
            )

            # Determine settlement scenario
            if settle_dt == today:
                # Current date settlement - process immediately
                return self._process_immediate_settlement(
                    trade_id=trade_id,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    trade_type=trade_type,
                    quantity=quantity,
                    price=price,
                    charges=charges,
                    position_date=settle_date,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name
                )

            elif settle_dt > today:
                # Future settlement - queue for later
                return self._queue_for_settlement(
                    trade_id=trade_id,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    trade_type=trade_type,
                    quantity=quantity,
                    price=price,
                    charges=charges,
                    settle_date=settle_date,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name
                )

            else:
                # Backdated settlement
                return self._process_backdated_settlement(
                    trade_id=trade_id,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    trade_type=trade_type,
                    quantity=quantity,
                    price=price,
                    charges=charges,
                    settle_date=settle_date,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name
                )

        except Exception as e:
            logger.error(f"Error processing trade settlement: {str(e)}")
            return False, f"Settlement processing error: {str(e)}", None

    # =========================================================================
    # IMMEDIATE SETTLEMENT (settle_date = today)
    # =========================================================================

    def _process_immediate_settlement(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        position_date: str,
        updated_by: str,
        **kwargs
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Process immediate settlement - position calculated now."""
        logger.info(f"Processing immediate settlement for trade {trade_id}")

        success, message, position = self.position_service.calculate_position(
            portfolio_id=portfolio_id,
            security_id=security_id,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            charges=charges,
            position_date=position_date,
            trade_id=trade_id,
            updated_by=updated_by,
            security_currency=kwargs.get('security_currency'),
            portfolio_currency=kwargs.get('portfolio_currency'),
            isin=kwargs.get('isin'),
            security_name=kwargs.get('security_name')
        )

        if success:
            return True, f"Immediate settlement completed. {message}", position
        else:
            return False, f"Immediate settlement failed: {message}", None

    # =========================================================================
    # FUTURE SETTLEMENT (settle_date > today)
    # =========================================================================

    def _queue_for_settlement(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        updated_by: str,
        **kwargs
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Queue trade for future settlement."""
        try:
            queue_id = self._generate_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processing_date = datetime.now().strftime('%Y%m%d')

            # Insert into settlement queue
            query = f"""
            INSERT INTO {self.DATABASE}.{self.SETTLEMENT_QUEUE_TABLE}
            (queue_id, trade_id, portfolio_id, security_id, trade_type,
             quantity, price, charges, settle_date,
             status, retry_count, queued_at, queued_by,
             security_currency, portfolio_currency, isin, security_name,
             processing_date)
            VALUES (
                {queue_id}, {trade_id},
                '{self._escape(portfolio_id)}', '{self._escape(security_id)}',
                '{trade_type}',
                {float(quantity)}, {float(price)}, {float(charges)},
                '{settle_date}',
                '{self.STATUS_PENDING}', 0,
                '{timestamp}', '{self._escape(updated_by)}',
                {self._null_or_str(kwargs.get('security_currency'))},
                {self._null_or_str(kwargs.get('portfolio_currency'))},
                {self._null_or_str(kwargs.get('isin'))},
                {self._null_or_str(kwargs.get('security_name'))},
                '{processing_date}'
            )
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(
                    f"Trade {trade_id} queued for settlement on {settle_date} (queue_id={queue_id})"
                )
                return True, f"Trade queued for settlement on {settle_date}", {
                    'queue_id': queue_id,
                    'settle_date': settle_date,
                    'status': self.STATUS_PENDING
                }
            else:
                return False, "Failed to queue trade for settlement", None

        except Exception as e:
            logger.error(f"Error queuing trade for settlement: {str(e)}")
            return False, f"Queue error: {str(e)}", None

    def get_pending_settlements(self, settle_date: str = None) -> List[Dict[str, Any]]:
        """
        Get trades pending settlement.

        Args:
            settle_date: Optional specific date (YYYY-MM-DD). If None, uses today.

        Returns:
            List of pending settlement records
        """
        try:
            if settle_date is None:
                settle_date = datetime.now().strftime('%Y-%m-%d')

            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.SETTLEMENT_QUEUE_TABLE}
            WHERE settle_date <= '{settle_date}'
              AND status = '{self.STATUS_PENDING}'
            ORDER BY queued_at ASC
            LIMIT 1000
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting pending settlements: {str(e)}")
            return []

    def process_pending_settlements(self, settle_date: str = None) -> Dict[str, int]:
        """
        Process all pending settlements for a given date.
        This is the daily settlement job.

        Args:
            settle_date: Date to process (YYYY-MM-DD). If None, uses today.

        Returns:
            Dict with counts: processed, failed, skipped
        """
        counters = {'processed': 0, 'failed': 0, 'skipped': 0}

        try:
            if settle_date is None:
                settle_date = datetime.now().strftime('%Y-%m-%d')

            pending = self.get_pending_settlements(settle_date)
            logger.info(f"Processing {len(pending)} pending settlements for {settle_date}")

            for item in pending:
                try:
                    # Mark as processing
                    self._update_queue_status(
                        item['queue_id'], self.STATUS_PROCESSING
                    )

                    # Calculate position
                    success, message, position = self.position_service.calculate_position(
                        portfolio_id=item['portfolio_id'],
                        security_id=item['security_id'],
                        trade_type=item['trade_type'],
                        quantity=Decimal(str(item['quantity'])),
                        price=Decimal(str(item['price'])),
                        charges=Decimal(str(item.get('charges', 0) or 0)),
                        position_date=item['settle_date'],
                        trade_id=item['trade_id'],
                        updated_by='SYSTEM',
                        security_currency=item.get('security_currency'),
                        portfolio_currency=item.get('portfolio_currency'),
                        isin=item.get('isin'),
                        security_name=item.get('security_name')
                    )

                    if success:
                        self._update_queue_status(
                            item['queue_id'], self.STATUS_COMPLETED
                        )
                        counters['processed'] += 1
                        logger.info(f"Processed settlement for trade {item['trade_id']}")
                    else:
                        self._update_queue_status(
                            item['queue_id'], self.STATUS_FAILED, message
                        )
                        counters['failed'] += 1
                        logger.error(f"Failed settlement for trade {item['trade_id']}: {message}")

                except Exception as e:
                    self._update_queue_status(
                        item['queue_id'], self.STATUS_FAILED, str(e)
                    )
                    counters['failed'] += 1
                    logger.error(f"Error processing settlement {item['queue_id']}: {str(e)}")

            return counters

        except Exception as e:
            logger.error(f"Error in process_pending_settlements: {str(e)}")
            return counters

    def _update_queue_status(
        self,
        queue_id: int,
        status: str,
        error_message: str = None
    ) -> bool:
        """Update settlement queue status."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            error_clause = ""
            if error_message:
                error_clause = f", error_message = '{self._escape(error_message)}'"

            processed_clause = ""
            if status in [self.STATUS_COMPLETED, self.STATUS_FAILED]:
                processed_clause = f", processed_at = '{timestamp}'"

            retry_clause = ""
            if status == self.STATUS_FAILED:
                retry_clause = ", retry_count = retry_count + 1"

            query = f"""
            UPDATE {self.DATABASE}.{self.SETTLEMENT_QUEUE_TABLE}
            SET status = '{status}',
                updated_at = '{timestamp}'
                {error_clause}
                {processed_clause}
                {retry_clause}
            WHERE queue_id = {queue_id}
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error updating queue status: {str(e)}")
            return False

    # =========================================================================
    # BACKDATED SETTLEMENT (settle_date < today)
    # =========================================================================

    def _process_backdated_settlement(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        updated_by: str,
        **kwargs
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process backdated settlement.

        Rules:
        - Allowed up to previous month-end
        - Triggers recalculation of positions from settle_date to today
        """
        settle_dt = self._parse_date(settle_date)
        prev_month_end = self._get_previous_month_end()

        # Validate: not beyond previous month-end
        if settle_dt < prev_month_end:
            return False, (
                f"Backdated settlement not allowed before {prev_month_end.strftime('%Y-%m-%d')}. "
                f"Settlement date {settle_date} is too far in the past."
            ), None

        logger.info(
            f"Processing backdated settlement for trade {trade_id}: "
            f"settle_date={settle_date}, prev_month_end={prev_month_end}"
        )

        # Step 1: Calculate position for the backdated date
        success, message, position = self.position_service.calculate_position(
            portfolio_id=portfolio_id,
            security_id=security_id,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            charges=charges,
            position_date=settle_date,
            trade_id=trade_id,
            updated_by=updated_by,
            security_currency=kwargs.get('security_currency'),
            portfolio_currency=kwargs.get('portfolio_currency'),
            isin=kwargs.get('isin'),
            security_name=kwargs.get('security_name')
        )

        if not success:
            return False, f"Backdated settlement failed: {message}", None

        # Step 2: Recalculate position chain from settle_date to today
        recalc_result = self._recalculate_position_chain(
            portfolio_id=portfolio_id,
            security_id=security_id,
            from_date=settle_date,
            updated_by=updated_by
        )

        return True, (
            f"Backdated settlement completed for {settle_date}. "
            f"Recalculated {recalc_result['recalculated']} positions."
        ), {
            'position': position,
            'recalculation': recalc_result
        }

    def _recalculate_position_chain(
        self,
        portfolio_id: str,
        security_id: str,
        from_date: str,
        updated_by: str
    ) -> Dict[str, int]:
        """
        Recalculate all positions from a given date to today.

        This handles the case where a backdated trade affects subsequent positions.
        """
        counters = {'recalculated': 0, 'errors': 0}

        try:
            from_dt = self._parse_date(from_date)
            today = datetime.now().date()

            # Get all trades for this portfolio+security from the date onwards
            query = f"""
            SELECT trade_id, trade_type, quantity, price,
                   COALESCE(commission, 0) + COALESCE(sec_fee, 0) + COALESCE(other_charges, 0) as charges,
                   settle_date
            FROM {self.DATABASE}.{self.TRADE_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND settle_date > '{from_date}'
              AND settle_date <= '{today.strftime("%Y-%m-%d")}'
              AND status IN ('VALIDATED', 'SETTLED')
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY settle_date ASC, created_at ASC
            """

            trades = impala_manager.execute_query(query, database=self.DATABASE)

            if trades:
                logger.info(
                    f"Recalculating {len(trades)} trades from {from_date} to {today}"
                )

                for trade in trades:
                    try:
                        # Recalculate each position
                        success, _, _ = self.position_service.calculate_position(
                            portfolio_id=portfolio_id,
                            security_id=security_id,
                            trade_type=trade['trade_type'],
                            quantity=Decimal(str(trade['quantity'])),
                            price=Decimal(str(trade['price'])),
                            charges=Decimal(str(trade.get('charges', 0) or 0)),
                            position_date=trade['settle_date'],
                            trade_id=trade['trade_id'],
                            updated_by=updated_by
                        )

                        if success:
                            counters['recalculated'] += 1
                        else:
                            counters['errors'] += 1

                    except Exception as e:
                        logger.error(f"Error recalculating trade {trade['trade_id']}: {str(e)}")
                        counters['errors'] += 1

            return counters

        except Exception as e:
            logger.error(f"Error in recalculate_position_chain: {str(e)}")
            return counters

    def validate_backdated_settlement(self, settle_date: str) -> Tuple[bool, str]:
        """
        Validate if a backdated settlement is allowed.

        Args:
            settle_date: Settlement date (YYYY-MM-DD)

        Returns:
            Tuple of (is_valid, message)
        """
        settle_dt = self._parse_date(settle_date)
        if settle_dt is None:
            return False, f"Invalid date format: {settle_date}"

        today = datetime.now().date()

        if settle_dt > today:
            return True, "Future settlement - will be queued"

        if settle_dt == today:
            return True, "Same-day settlement - will process immediately"

        prev_month_end = self._get_previous_month_end()

        if settle_dt < prev_month_end:
            return False, (
                f"Backdated settlement not allowed before {prev_month_end.strftime('%Y-%m-%d')}. "
                f"Maximum backdating is to previous month-end."
            )

        return True, f"Backdated settlement allowed (within previous month-end limit)"

    # =========================================================================
    # DATE UTILITIES
    # =========================================================================

    def _get_previous_month_end(self) -> date:
        """Get the last day of the previous month."""
        today = datetime.now().date()
        first_of_month = today.replace(day=1)
        last_of_prev_month = first_of_month - timedelta(days=1)
        return last_of_prev_month

    def _get_current_month_start(self) -> date:
        """Get the first day of the current month."""
        today = datetime.now().date()
        return today.replace(day=1)

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None

        try:
            # Handle various formats
            if isinstance(date_str, date):
                return date_str

            for fmt in ['%Y-%m-%d', '%Y%m%d', '%d-%m-%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue

            return None

        except Exception:
            return None

    def _get_dates_in_range(self, start_date: str, end_date: str) -> List[str]:
        """Get all dates in a range (inclusive)."""
        dates = []
        start_dt = self._parse_date(start_date)
        end_dt = self._parse_date(end_date)

        if start_dt and end_dt:
            current = start_dt
            while current <= end_dt:
                dates.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)

        return dates

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self) -> int:
        """Generate unique ID."""
        return int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def _escape(self, value: str) -> str:
        """Escape string value for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def _null_or_str(self, value: str) -> str:
        """Return NULL or quoted string."""
        if value is None or value == '':
            return 'NULL'
        return f"'{self._escape(value)}'"

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_settlement_statistics(self) -> Dict[str, Any]:
        """Get settlement queue statistics."""
        try:
            query = f"""
            SELECT
                status,
                COUNT(*) as count,
                MIN(settle_date) as earliest_date,
                MAX(settle_date) as latest_date
            FROM {self.DATABASE}.{self.SETTLEMENT_QUEUE_TABLE}
            GROUP BY status
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            stats = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0,
                'total': 0
            }

            if results:
                for row in results:
                    status = row.get('status', '').lower()
                    count = row.get('count', 0)
                    stats[status] = count
                    stats['total'] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting settlement statistics: {str(e)}")
            return {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'total': 0}


# Singleton instance
settlement_service = SettlementService()
