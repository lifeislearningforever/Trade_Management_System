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
        self._position_queue_service = None

    @property
    def position_queue_service(self):
        """Lazy load position queue service to avoid circular imports."""
        if self._position_queue_service is None:
            from trade.services.position_queue_service import position_queue_service
            self._position_queue_service = position_queue_service
        return self._position_queue_service

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
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        async_mode: bool = True,
        position_basis: str = None  # None = dual (both bases). 'TRADE_DATE' or 'SETTLE_DATE' = single.
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process trade settlement based on settlement date.

        ALL settlements are queued for async processing to keep trade save fast.
        The background worker processes the queue within SLA (< 5 minutes).

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
            async_mode: If True (default), queue for async processing.
                       If False, process synchronously (for EOD job).

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
                f"settle_date={settle_date}, today={today}, async={async_mode}"
            )

            # Determine settlement type for logging/tracking
            if settle_dt == today:
                settlement_type = 'T+0'
            elif settle_dt > today:
                settlement_type = 'FUTURE'
            else:
                settlement_type = 'BACKDATED'

            trade_dt = self._parse_date(trade_date)

            # DUAL POSITION LOGIC
            # position_basis=None (default) means create BOTH bases.
            # position_basis='TRADE_DATE' or 'SETTLE_DATE' means a targeted single-basis call
            # (used by POSITION_MODIFY reversal and POSITION_CANCEL which must mirror what
            #  was originally created).
            #
            # Corner cases:
            # 1. T+0 (trade_date == settle_date): Both bases land on same date — we still
            #    create two rows so queries by position_basis remain consistent.
            # 2. FUTURE settle_date (> today): TRADE_DATE position is queued immediately
            #    (async), SETTLE_DATE position is queued to cis_settlement_queue for EOD.
            # 3. BACKDATED: Chain recalculation runs for BOTH bases (handled in worker).
            # 4. Single-basis calls (modify/cancel reversals): pass position_basis explicitly.

            bases_to_process = (
                ['TRADE_DATE', 'SETTLE_DATE'] if position_basis is None
                else [position_basis]
            )

            results = {}
            overall_success = True

            for basis in bases_to_process:
                # For TRADE_DATE basis: position_date = trade_date
                # For SETTLE_DATE basis: position_date = settle_date
                pos_date = trade_date if basis == 'TRADE_DATE' else settle_date

                kwargs = dict(
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
                    security_name=security_name,
                    custodian=custodian,
                    sub_custodian=sub_custodian,
                    position_basis=basis,
                    position_date=pos_date,
                    settlement_type=settlement_type
                )

                if async_mode:
                    if basis == 'SETTLE_DATE' and settle_dt > today:
                        # SETTLE_DATE future: queue to settlement queue (processed on settle_date)
                        success, msg, result = self._queue_for_settlement(**kwargs)
                    else:
                        # TRADE_DATE (any timing) + SETTLE_DATE T+0/backdated: async position queue
                        success, msg, result = self._queue_for_async_processing(**kwargs)
                else:
                    # SYNC MODE (worker / EOD job)
                    if settle_dt == today or basis == 'TRADE_DATE':
                        success, msg, result = self._process_immediate_settlement(
                            position_date=pos_date, **{
                                k: v for k, v in kwargs.items()
                                if k not in ('settle_date', 'settlement_type', 'position_date')
                            }
                        )
                    elif settle_dt > today:
                        success, msg, result = self._queue_for_settlement(**kwargs)
                    else:
                        success, msg, result = self._process_backdated_settlement(**kwargs)

                results[basis] = (success, msg, result)
                if not success:
                    overall_success = False
                logger.info(f"Trade {trade_id} basis={basis} date={pos_date}: {msg}")

            # Return combined result
            if len(bases_to_process) == 1:
                basis = bases_to_process[0]
                return results[basis]

            # Dual basis: return success only if both succeeded
            td_success, td_msg, td_result = results.get('TRADE_DATE', (False, 'not run', None))
            sd_success, sd_msg, sd_result = results.get('SETTLE_DATE', (False, 'not run', None))
            combined_msg = f"TRADE_DATE: {td_msg} | SETTLE_DATE: {sd_msg}"
            return overall_success, combined_msg, {
                'trade_date_result': td_result,
                'settle_date_result': sd_result,
                'settlement_type': settlement_type
            }

        except Exception as e:
            logger.error(f"Error processing trade settlement: {str(e)}")
            return False, f"Settlement processing error: {str(e)}", None

    # =========================================================================
    # ASYNC QUEUE FOR ALL SETTLEMENTS (Fast Trade Save)
    # =========================================================================

    def _queue_for_async_processing(
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
        settlement_type: str,
        position_basis: str = 'TRADE_DATE',
        position_date: str = None,
        **kwargs
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Queue settlement for async background processing.
        This is NON-BLOCKING - returns immediately after queuing.

        position_basis determines which chain this queue item belongs to.
        position_date is the effective date for this basis (trade_date or settle_date).
        """
        try:
            # For backdated, generate CHAIN_RECALC metadata upfront
            chain_recalc_metadata = None
            if settlement_type == 'BACKDATED':
                chain_recalc_metadata = (
                    f"CHAIN_RECALC:{portfolio_id}:{security_id}:{settle_date}"
                )
                logger.info(
                    f"Backdated trade detected basis={position_basis}, "
                    f"chain_recalc_metadata: {chain_recalc_metadata}"
                )

            # Enqueue to position_queue (processed by background worker)
            success, message, queue_id = self.position_queue_service.enqueue_position_calculation(
                trade_id=trade_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=trade_type,
                quantity=quantity,
                price=price,
                charges=charges,
                settle_date=settle_date,
                queued_by=updated_by,
                security_currency=kwargs.get('security_currency'),
                portfolio_currency=kwargs.get('portfolio_currency'),
                isin=kwargs.get('isin'),
                security_name=kwargs.get('security_name'),
                use_db_queue=True,
                chain_recalc_metadata=chain_recalc_metadata,
                position_basis=position_basis,
                position_date=position_date or settle_date
            )

            if success:

                logger.info(
                    f"Trade {trade_id} queued for async {settlement_type} processing "
                    f"(queue_id={queue_id})"
                )
                return True, f"Position calculation queued ({settlement_type})", {
                    'queue_id': queue_id,
                    'settlement_type': settlement_type,
                    'status': 'QUEUED'
                }
            else:
                return False, f"Failed to queue settlement: {message}", None

        except Exception as e:
            logger.error(f"Error queuing async settlement: {str(e)}")
            return False, f"Queue error: {str(e)}", None

    def _flag_for_chain_recalculation(
        self,
        queue_id: int,
        portfolio_id: str,
        security_id: str,
        from_date: str
    ) -> bool:
        """
        Flag a queue item for position chain recalculation.
        This adds metadata so the worker knows to recalculate subsequent positions.
        """
        try:
            # Store chain recalc info in error_message field (repurposed as metadata)
            # The worker will check this and trigger _recalculate_position_chain
            metadata = f"CHAIN_RECALC:{portfolio_id}:{security_id}:{from_date}"

            query = f"""
            UPDATE {self.DATABASE}.cis_position_queue
            SET error_message = '{self._escape(metadata)}'
            WHERE queue_id = {queue_id}
            """

            impala_manager.execute_write(query, database=self.DATABASE)
            logger.info(f"Flagged queue_id={queue_id} for chain recalculation from {from_date}")
            return True

        except Exception as e:
            logger.error(f"Error flagging for chain recalculation: {str(e)}")
            return False

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
            security_name=kwargs.get('security_name'),
            custodian=kwargs.get('custodian'),
            sub_custodian=kwargs.get('sub_custodian'),
            position_basis=kwargs.get('position_basis', 'TRADE_DATE')
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
        position_basis: str = 'SETTLE_DATE',
        position_date: str = None,
        **kwargs
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Queue trade for future settlement (EOD job processes on settle_date).
        Only SETTLE_DATE basis goes here — TRADE_DATE is always queued immediately."""
        try:
            queue_id = self._generate_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processing_date = datetime.now().strftime('%Y%m%d')
            effective_position_date = position_date or settle_date

            # Cast decimal values to avoid precision errors
            qty_cast = f"CAST({float(quantity)} AS DECIMAL(20,8))"
            price_cast = f"CAST({float(price)} AS DECIMAL(20,8))"
            charges_cast = f"CAST({float(charges)} AS DECIMAL(20,8))"

            # Insert into settlement queue (position_basis + position_date stored for worker)
            query = f"""
            INSERT INTO {self.DATABASE}.{self.SETTLEMENT_QUEUE_TABLE}
            (queue_id, trade_id, portfolio_id, security_id, trade_type,
             quantity, price, charges, settle_date, position_basis,
             status, retry_count, queued_at, queued_by,
             security_currency, portfolio_currency, isin, security_name,
             custodian, sub_custodian,
             processing_date)
            VALUES (
                {queue_id}, {trade_id},
                '{self._escape(portfolio_id)}', '{self._escape(security_id)}',
                '{trade_type}',
                {qty_cast}, {price_cast}, {charges_cast},
                '{settle_date}',
                '{position_basis}',
                '{self.STATUS_PENDING}', CAST(0 AS INT),
                '{timestamp}', '{self._escape(updated_by)}',
                {self._null_or_str(kwargs.get('security_currency'))},
                {self._null_or_str(kwargs.get('portfolio_currency'))},
                {self._null_or_str(kwargs.get('isin'))},
                {self._null_or_str(kwargs.get('security_name'))},
                {self._null_or_str(kwargs.get('custodian'))},
                {self._null_or_str(kwargs.get('sub_custodian'))},
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

                    # Calculate position — use basis stored in queue row
                    # EOD job processes SETTLE_DATE basis (the main use case for this queue)
                    basis = item.get('position_basis', 'SETTLE_DATE')
                    pos_date = item.get('position_date') or item['settle_date']

                    success, message, position = self.position_service.calculate_position(
                        portfolio_id=item['portfolio_id'],
                        security_id=item['security_id'],
                        trade_type=item['trade_type'],
                        quantity=Decimal(str(item['quantity'])),
                        price=Decimal(str(item['price'])),
                        charges=Decimal(str(item.get('charges', 0) or 0)),
                        position_date=pos_date,
                        trade_id=item['trade_id'],
                        updated_by='SYSTEM',
                        security_currency=item.get('security_currency'),
                        portfolio_currency=item.get('portfolio_currency'),
                        isin=item.get('isin'),
                        security_name=item.get('security_name'),
                        custodian=item.get('custodian'),
                        sub_custodian=item.get('sub_custodian'),
                        position_basis=basis
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
                retry_clause = ", retry_count = CAST(retry_count + 1 AS INT)"

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
        - Allowed for any past date (no restriction on how far back)
        - Triggers recalculation of positions from settle_date to today
        - Warning logged for dates before previous month-end
        """
        settle_dt = self._parse_date(settle_date)
        prev_month_end = self._get_previous_month_end()

        # Log warning for very old backdated trades (before previous month-end)
        if settle_dt < prev_month_end:
            logger.warning(
                f"Backdated settlement before previous month-end: "
                f"settle_date={settle_date}, prev_month_end={prev_month_end.strftime('%Y-%m-%d')}. "
                f"This may affect closed period positions."
            )

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
            security_name=kwargs.get('security_name'),
            custodian=kwargs.get('custodian'),
            sub_custodian=kwargs.get('sub_custodian'),
            position_basis=kwargs.get('position_basis', 'TRADE_DATE')
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
              AND (trade_status IN ('INITIAL', 'VALIDATED', 'SETTLED') OR status IN ('INITIAL', 'VALIDATED', 'SETTLED'))
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
                        # Recalculate each position using chain_recalc mode
                        # This ensures we get position BEFORE this date, not the old same-date position
                        success, _, _ = self.position_service.calculate_position(
                            portfolio_id=portfolio_id,
                            security_id=security_id,
                            trade_type=trade['trade_type'],
                            quantity=Decimal(str(trade['quantity'])),
                            price=Decimal(str(trade['price'])),
                            charges=Decimal(str(trade.get('charges', 0) or 0)),
                            position_date=trade['settle_date'],
                            trade_id=trade['trade_id'],
                            updated_by=updated_by,
                            is_chain_recalc=True  # Use position BEFORE this date
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
            # Allow but warn - may affect closed period
            return True, (
                f"Backdated settlement before previous month-end ({prev_month_end.strftime('%Y-%m-%d')}). "
                f"Warning: This may affect closed period positions."
            )

        return True, f"Backdated settlement allowed"

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
