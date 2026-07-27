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
from core.services.system_date_service import system_date_service
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
        position_basis: str = None,  # None = dual (both bases). 'TRADED' or 'SETTLED' = single.
        trade_lc: Decimal = None,
        gross_amount_lc: Decimal = None,
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
        print(f"==> ENTERED process_trade_settlement trade_id={trade_id} settle_date={settle_date!r} trade_date={trade_date!r}", flush=True)
        try:
            today = system_date_service.get_system_date()
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
            # position_basis='TRADED' or 'SETTLED' means a targeted single-basis call
            # (used by POSITION_MODIFY reversal and POSITION_CANCEL which must mirror what
            #  was originally created).
            #
            # Corner cases:
            # 1. T+0 (trade_date == settle_date): Both bases land on same date — we still
            #    create two rows so queries by position_basis remain consistent.
            # 2. FUTURE settle_date (> today): TRADED position is queued immediately
            #    (async), SETTLED position is queued to cis_settlement_queue for EOD.
            # 3. BACKDATED: Chain recalculation runs for BOTH bases (handled in worker).
            # 4. Single-basis calls (modify/cancel reversals): pass position_basis explicitly.

            bases_to_process = (
                ['TRADED', 'SETTLED'] if position_basis is None
                else [position_basis]
            )

            results = {}
            overall_success = True

            for basis in bases_to_process:
                # For TRADED basis: position_date = trade_date
                # For SETTLED basis: position_date = settle_date
                pos_date = trade_date if basis == 'TRADED' else settle_date
                pos_dt = trade_dt if basis == 'TRADED' else settle_dt

                # Settlement type must be evaluated per-basis using THIS basis's own
                # effective date, not the settle_date-based `settlement_type` computed
                # above. Otherwise a trade with a backdated trade_date but settle_date
                # == today (a very common shape: backdated trade settling today) gets
                # its TRADED basis misclassified as T+0 too, since T+0/FUTURE/BACKDATED
                # was decided once from settle_dt alone. A T+0-classified item only
                # gets chain-recalc treatment if a PRIOR backdated position already
                # exists (see the T+0 branch below) — for a brand-new position there
                # is nothing to find, so it silently runs as a single-day calculation
                # and never backfills the intermediate business days between the
                # backdated trade_date and today.
                if pos_dt is None:
                    basis_settlement_type = settlement_type
                elif pos_dt == today:
                    basis_settlement_type = 'T+0'
                elif pos_dt > today:
                    basis_settlement_type = 'FUTURE'
                else:
                    basis_settlement_type = 'BACKDATED'

                kwargs = dict(
                    trade_id=trade_id,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    trade_type=trade_type,
                    quantity=quantity,
                    price=price,
                    charges=charges,
                    trade_date=trade_date,
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
                    settlement_type=basis_settlement_type,
                    trade_lc=trade_lc,
                    gross_amount_lc=gross_amount_lc,
                )

                if async_mode:
                    if basis == 'SETTLED' and settle_dt > today:
                        # SETTLED future: queue to settlement queue (processed on settle_date)
                        success, msg, result = self._queue_for_settlement(**kwargs)
                    else:
                        # TRADED (any timing) + SETTLED T+0/backdated: async position queue
                        success, msg, result = self._queue_for_async_processing(**kwargs)
                else:
                    # SYNC MODE (worker / EOD job)
                    # Clear any stale cis_trade_position row for this trade_id+basis so the
                    # idempotency guard in calculate_position does not skip recalculation.
                    # This is safe: sync mode is only called on explicit re-settle.
                    try:
                        from core.repositories.impala_connection import impala_manager as _imp
                        _imp.execute_write(
                            f"DELETE FROM gmp_cis.cis_trade_position "
                            f"WHERE trade_id = {trade_id} AND position_basis = '{basis}'",
                            database='gmp_cis'
                        )
                        logger.info(f"Cleared stale cis_trade_position for trade_id={trade_id} basis={basis}")
                    except Exception as _de:
                        logger.warning(f"Could not clear stale position for trade {trade_id}: {_de}")
                    # Use basis_settlement_type (per-basis effective date), not the raw
                    # settle_dt/`basis == 'TRADED'` shortcut — the latter sent every
                    # TRADED basis through immediate settlement even when trade_date
                    # was backdated, skipping chain recalculation for sync-mode callers
                    # (EOD job / explicit re-settle) just like the async path did.
                    if basis_settlement_type == 'T+0':
                        success, msg, result = self._process_immediate_settlement(
                            position_date=pos_date, **{
                                k: v for k, v in kwargs.items()
                                if k not in ('settle_date', 'settlement_type', 'position_date')
                            }
                        )
                    elif basis_settlement_type == 'FUTURE':
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
            td_success, td_msg, td_result = results.get('TRADED', (False, 'not run', None))
            sd_success, sd_msg, sd_result = results.get('SETTLED', (False, 'not run', None))
            combined_msg = f"TRADED: {td_msg} | SETTLED: {sd_msg}"
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
        position_basis: str = 'TRADED',
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
            # Generate CHAIN_RECALC metadata for backdated trades, and also for T+0 trades
            # when a prior backdated position already exists for this portfolio/security.
            # Without this, a T+0 trade entered alongside a backdated trade runs as a direct
            # queue item and overwrites the chain-recalc result with a stale single-trade value.
            chain_recalc_metadata = None
            trade_date = kwargs.get('trade_date') or settle_date
            if settlement_type == 'BACKDATED':
                from_date = trade_date
                chain_recalc_metadata = (
                    f"CHAIN_RECALC:{portfolio_id}:{security_id}:{from_date}"
                )
                logger.info(
                    f"Backdated trade detected basis={position_basis}, "
                    f"from_date={from_date}, chain_recalc_metadata: {chain_recalc_metadata}"
                )
            elif settlement_type == 'T+0':
                # Check if any backdated position exists for this security (position_date < today).
                # If so, this T+0 trade must also use chain recalc to accumulate correctly.
                try:
                    today_str = system_date_service.get_system_date().isoformat()
                    prior_check = impala_manager.execute_query(
                        f"""
                        SELECT 1 FROM {self.DATABASE}.cis_trade_position
                        WHERE portfolio_short_name = '{portfolio_id}'
                          AND security_label = '{security_id}'
                          AND position_date < '{today_str}'
                          AND (is_latest = true OR is_latest IS NULL)
                        LIMIT 1
                        """,
                        database=self.DATABASE
                    )
                    if prior_check:
                        from_date = trade_date
                        chain_recalc_metadata = (
                            f"CHAIN_RECALC:{portfolio_id}:{security_id}:{from_date}"
                        )
                        logger.info(
                            f"T+0 trade has prior backdated positions — upgrading to "
                            f"CHAIN_RECALC from {from_date} basis={position_basis}"
                        )
                except Exception as e:
                    logger.warning(f"Could not check for prior backdated positions: {e}")

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
                position_date=position_date or settle_date,
                gross_amount_lc=kwargs.get('gross_amount_lc'),
                total_amount_lc=kwargs.get('trade_lc'),
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

        # Derive implied FX rate from trade LC/FC amounts (captures any user edits to LC)
        _gross_fc = kwargs.get('gross_amount_fc') or (float(quantity) * float(price))
        _gross_lc = kwargs.get('gross_amount_lc')
        _gross_amount_lc = Decimal(str(_gross_lc)) if _gross_lc else None

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
            position_basis=kwargs.get('position_basis', 'TRADED'),
            trade_lc=kwargs.get('trade_lc'),
            gross_amount_lc=_gross_amount_lc,
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
        position_basis: str = 'SETTLED',
        position_date: str = None,
        **kwargs
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Queue trade for future settlement (EOD job processes on settle_date).
        Only SETTLED basis goes here — TRADED is always queued immediately."""
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
                    # EOD job processes SETTLED basis (the main use case for this queue)
                    basis = item.get('position_basis', 'SETTLED')
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

        position_basis = kwargs.get('position_basis', 'TRADED')
        trade_date = kwargs.get('trade_date') or settle_date
        position_date = kwargs.get('position_date') or (
            trade_date if position_basis == 'TRADED' else settle_date
        )

        # Step 1: Calculate position for the backdated date
        _gross_lc_bd = kwargs.get('gross_amount_lc')
        _gross_amount_lc_bd = Decimal(str(_gross_lc_bd)) if _gross_lc_bd else None

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
            position_basis=position_basis,
            trade_lc=kwargs.get('trade_lc'),
            gross_amount_lc=_gross_amount_lc_bd,
        )

        if not success:
            return False, f"Backdated settlement failed: {message}", None

        # Step 2: Recalculate full position chain from earliest affected date.
        # Use trade_date (not settle_date) as from_date so TRADED basis positions
        # that land on trade_date are included in the chain.
        from_date = trade_date
        recalc_result = self._recalculate_position_chain(
            portfolio_id=portfolio_id,
            security_id=security_id,
            from_date=from_date,
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
        Recalculate all positions (both TRADED and SETTLED bases) from from_date to today.
        Uses in-memory accumulation to avoid Kudu stale-read races between iterations.
        """
        counters = {'recalculated': 0, 'errors': 0}

        try:
            today = system_date_service.get_system_date()
            today_str = today.strftime("%Y-%m-%d")

            # Drain any pending queue items for this portfolio/security before recalculating.
            # Old CHAIN_RECALC queue items from the initial settle may still be sitting in
            # PENDING state. If the worker picks them up after this synchronous recalc
            # completes, it will overwrite the correct result with a stale one.
            try:
                impala_manager.execute_write(
                    f"""
                    UPDATE {self.DATABASE}.cis_position_queue
                    SET status = 'COMPLETED',
                        error_message = 'Superseded by synchronous chain recalc',
                        updated_at = '{today_str}'
                    WHERE portfolio_id = '{self._escape(portfolio_id)}'
                      AND security_id = '{self._escape(security_id)}'
                      AND status IN ('PENDING', 'PROCESSING')
                    """,
                    database=self.DATABASE
                )
                logger.info(
                    f"Drained pending queue items for {portfolio_id}/{security_id} "
                    f"before chain recalc"
                )
            except Exception as _drain_err:
                logger.warning(f"Could not drain queue items (non-fatal): {_drain_err}")

            # Include the from_date itself (>=) so the reversed/modified trade is
            # replayed, and fetch trade_date so TRADED basis uses the right position_date.
            # Also fetch currency + LC amount fields for NON-REVAL portfolios.
            #
            # Upper bound is trade_date <= today, NOT settle_date <= today. A trade
            # with a future settle_date (queued to cis_settlement_queue) must still be
            # replayed here for its TRADED basis, which is keyed by trade_date and is
            # visible immediately regardless of settlement timing. Filtering on
            # settle_date <= today excluded such trades entirely — confirmed live:
            # amending a same-day BUY with a future settle_date, alongside another
            # trade with a future settle_date, caused chain recalc to drop both
            # trades' TRADED-basis contribution and collapse the position back to
            # only the trades that had already settled. The per-basis loop below
            # already skips SETTLED for any pos_date > today (future), so relaxing
            # this bound doesn't risk creating a future-dated SETTLED row.
            query = f"""
            SELECT t.trade_id, t.trade_type, t.quantity, t.price,
                   COALESCE(t.commission, 0) + COALESCE(t.sec_fee, 0) + COALESCE(t.other_charges, 0) as charges,
                   t.trade_date, t.settle_date,
                   t.currency_code AS security_currency,
                   pf.currency     AS portfolio_currency,
                   t.total_amount_lc, t.gross_amount_lc
            FROM {self.DATABASE}.{self.TRADE_TABLE} t
            JOIN {self.DATABASE}.cis_portfolio pf
                ON t.portfolio_short_name = pf.name
            WHERE t.portfolio_short_name = '{self._escape(portfolio_id)}'
              AND t.security_label = '{self._escape(security_id)}'
              AND (t.trade_date >= '{from_date}' OR t.settle_date >= '{from_date}')
              AND t.trade_date <= '{today_str}'
              AND (t.trade_status IN ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED') OR t.status IN ('INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED'))
              AND (t.is_deleted = false OR t.is_deleted IS NULL)
            ORDER BY t.trade_date ASC, t.settle_date ASC, t.trade_id ASC
            """

            trades = impala_manager.execute_query(query, database=self.DATABASE)

            if not trades:
                # No active trades remain from from_date onward (e.g. the only trade was
                # just cancelled). Zero-out all is_latest position rows from from_date so
                # the position table reflects an empty/closed position.
                logger.info(
                    f"No active trades from {from_date} — zeroing positions for "
                    f"{portfolio_id}/{security_id}"
                )
                _z = 'CAST(0 AS DECIMAL(20,8))'
                try:
                    impala_manager.execute_write(
                        f"""
                        UPDATE {self.DATABASE}.cis_trade_position
                        SET quantity           = {_z},
                            average_cost_fc    = {_z},
                            average_cost_lc    = {_z},
                            total_cost_fc      = {_z},
                            total_cost_lc      = {_z},
                            market_price       = {_z},
                            market_value_fc    = {_z},
                            market_value_lc    = {_z},
                            unrealized_pnl_fc  = {_z},
                            unrealized_pnl_lc  = {_z},
                            realized_pnl_fc    = {_z},
                            realized_pnl_lc    = {_z},
                            dividend_fc        = {_z},
                            dividend_lc        = {_z},
                            pipeline_fc        = {_z},
                            pipeline_lc        = {_z},
                            provision_fc       = {_z},
                            provision_lc       = {_z},
                            uncall_fc          = {_z},
                            uncall_lc          = {_z},
                            is_latest          = false,
                            status             = 'CLOSED',
                            is_active          = false,
                            updated_by         = '{self._escape(updated_by)}',
                            updated_at         = '{today_str}'
                        WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                          AND security_label = '{self._escape(security_id)}'
                          AND position_date >= '{from_date}'
                          AND is_latest = true
                        """,
                        database=self.DATABASE
                    )
                    logger.info(
                        f"Zeroed all value columns for {portfolio_id}/{security_id} "
                        f"from {from_date} (no remaining trades)"
                    )
                    # Also zero cis_position (gold/summary table) — uses 'portfolio' not 'portfolio_short_name'
                    try:
                        impala_manager.execute_write(
                            f"""
                            UPDATE {self.DATABASE}.cis_position
                            SET quantity           = {_z},
                                average_cost_fc    = {_z},
                                average_cost_lc    = {_z},
                                cost_fc            = {_z},
                                cost_lc            = {_z},
                                market_value_fc    = {_z},
                                market_value_lc    = {_z},
                                unrealized_pnl_fc  = {_z},
                                unrealized_pnl_lc  = {_z},
                                realized_pnl_fc    = {_z},
                                realized_pnl_lc    = {_z},
                                net_book_value_fc  = {_z},
                                net_book_value_lc  = {_z},
                                dividend_fc        = {_z},
                                dividend_lc        = {_z},
                                pipeline_fc        = {_z},
                                pipeline_lc        = {_z},
                                provision_fc       = {_z},
                                provision_lc       = {_z},
                                uncall_fc          = {_z},
                                uncall_lc          = {_z},
                                is_latest          = false
                            WHERE portfolio = '{self._escape(portfolio_id)}'
                              AND security_label = '{self._escape(security_id)}'
                              AND position_date >= '{from_date}'
                              AND is_latest = true
                            """,
                            database=self.DATABASE
                        )
                        logger.info(f"Zeroed cis_position for {portfolio_id}/{security_id} from {from_date}")
                    except Exception as _cpos_err:
                        logger.warning(f"cis_position zero update skipped (non-fatal): {_cpos_err}")
                except Exception as _zero_err:
                    logger.error(f"Failed to zero positions after full cancellation: {_zero_err}")
                return counters

            logger.info(f"Recalculating {len(trades)} trades (both bases) from {from_date} to {today_str}")

            # Before replaying, retire all is_latest=true position rows from from_date
            # onward. This prevents stale rows (e.g. a cancelled trade's settle_date
            # position) from remaining visible when no active trade covers that date.
            # The replay loop below will re-create rows only for dates with active trades;
            # carry-forward will then fill gaps from the last active position.
            _z = 'CAST(0 AS DECIMAL(20,8))'
            for _tbl, _port_col in [
                ('cis_trade_position', 'portfolio_short_name'),
                ('cis_position',       'portfolio'),
            ]:
                try:
                    impala_manager.execute_write(
                        f"""
                        UPDATE {self.DATABASE}.{_tbl}
                        SET is_latest = false
                        WHERE {_port_col} = '{self._escape(portfolio_id)}'
                          AND security_label = '{self._escape(security_id)}'
                          AND position_date >= '{from_date}'
                          AND is_latest = true
                        """,
                        database=self.DATABASE
                    )
                    logger.info(
                        f"Retired is_latest rows in {_tbl} for "
                        f"{portfolio_id}/{security_id} from {from_date}"
                    )
                except Exception as _ret_err:
                    logger.warning(f"Retire is_latest in {_tbl} skipped (non-fatal): {_ret_err}")

            # Seed the in-memory accumulator with the last known position BEFORE from_date
            # for each basis. Without this, when chain recalc starts mid-chain (e.g. from
            # Mar-02 after an amendment), it starts from zero and misses earlier positions
            # (e.g. Feb-26 + Feb-27) that form the base.
            last_position_by_basis: Dict[str, Any] = {'TRADED': {}, 'SETTLED': {}}
            for basis in ('TRADED', 'SETTLED'):
                seed_rows = impala_manager.execute_query(
                    f"""
                    SELECT position_id, quantity, average_cost_fc, average_cost_lc,
                           total_cost_fc, total_cost_lc, realized_pnl_fc, realized_pnl_lc,
                           dividend_fc, dividend_lc, pipeline_fc, pipeline_lc,
                           provision_fc, provision_lc
                    FROM {self.DATABASE}.cis_trade_position
                    WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                      AND security_label = '{self._escape(security_id)}'
                      AND position_basis = '{basis}'
                      AND position_date < '{from_date}'
                      AND is_latest = true
                    ORDER BY position_date DESC
                    LIMIT 1
                    """,
                    database=self.DATABASE
                )
                if seed_rows:
                    last_position_by_basis[basis] = seed_rows[0]
                    logger.info(
                        f"Chain recalc seed for {basis}: qty={seed_rows[0].get('quantity')} "
                        f"avg={seed_rows[0].get('average_cost_fc')} before {from_date}"
                    )

            # isin/security_name aren't stored on cis_trade — they're only ever
            # resolved from cis_security at trade-entry time and threaded through
            # as a kwarg. This replay loop reconstructs positions long after entry
            # time, so it must re-resolve them itself instead of passing None
            # (which is what silently drops isin from every chain-recalc'd row).
            sec_isin, sec_name = self._get_security_isin_and_name(security_id)

            for trade in trades:
                settle_date = trade.get('settle_date') or ''
                trade_date = trade.get('trade_date') or settle_date

                for basis, pos_date in [('TRADED', trade_date), ('SETTLED', settle_date)]:
                    if not pos_date:
                        logger.warning(
                            f"Skipping {basis} for trade {trade.get('trade_id')}: "
                            f"pos_date empty (trade_date={trade_date!r}, settle_date={settle_date!r})"
                        )
                        continue
                    if pos_date < from_date:
                        # This trade qualified for the candidate list via the OTHER
                        # basis's date (the query above is an OR across trade_date/
                        # settle_date so it can serve both bases), but for THIS basis
                        # its own effective date is before from_date — meaning it's
                        # already reflected in this basis's seed position (seeded
                        # above from the last position_date < from_date row). Replaying
                        # it here would double-count it on top of that seed. This was
                        # the root cause of amend/cancel operations inflating an
                        # earlier date's quantity that the operation never touched.
                        logger.debug(
                            f"Skipping {basis} for trade {trade.get('trade_id')}: "
                            f"pos_date={pos_date} < from_date={from_date} (already in seed)"
                        )
                        continue
                    if pos_date > today_str:
                        # settle_date in the future (relaxing the query's upper bound to
                        # trade_date <= today, above, now lets such trades through so their
                        # TRADED basis gets replayed) — SETTLED must NOT be computed yet;
                        # it's already queued in cis_settlement_queue for its own settle_date.
                        # calculate_position would reject this anyway via
                        # _derive_position_type's future-date check, but as a hard error
                        # rather than the expected no-op this is.
                        logger.debug(
                            f"Skipping {basis} for trade {trade.get('trade_id')}: "
                            f"pos_date={pos_date} > today={today_str} (future settlement, queued separately)"
                        )
                        continue
                    try:
                        base = last_position_by_basis.get(basis)  # {} = fresh start, dict = prior
                        raw_lc = trade.get('total_amount_lc')
                        trade_lc = Decimal(str(raw_lc)) if raw_lc else None
                        raw_gross_lc = trade.get('gross_amount_lc')
                        gross_amount_lc = Decimal(str(raw_gross_lc)) if raw_gross_lc else None
                        success, msg, result = self.position_service.calculate_position(
                            portfolio_id=portfolio_id,
                            security_id=security_id,
                            trade_type=trade['trade_type'],
                            quantity=Decimal(str(trade['quantity'])),
                            price=Decimal(str(trade['price'])),
                            charges=Decimal(str(trade.get('charges', 0) or 0)),
                            position_date=pos_date,
                            trade_id=trade['trade_id'],
                            updated_by=updated_by,
                            is_chain_recalc=True,
                            position_basis=basis,
                            base_position_override=base,
                            trade_lc=trade_lc,
                            gross_amount_lc=gross_amount_lc,
                            security_currency=trade.get('security_currency'),
                            portfolio_currency=trade.get('portfolio_currency'),
                            isin=sec_isin,
                            security_name=sec_name,
                        )
                        if success:
                            counters['recalculated'] += 1
                            if result:
                                last_position_by_basis[basis] = result
                        else:
                            counters['errors'] += 1
                            logger.error(
                                f"Chain recalc failed for trade {trade['trade_id']} basis={basis}: {msg}"
                            )
                    except Exception as e:
                        logger.error(f"Error recalculating trade {trade['trade_id']} basis={basis}: {e}")
                        counters['errors'] += 1

            # --- Carry-forward pass ---
            # Fill any business-day gaps with no position row by carrying the
            # preceding position's values forward. This covers:
            #   (a) days between two trades (e.g. Feb-27 between Feb-26 and Mar-02)
            #   (b) days after the last trade up to today
            # Weekends / non-business days are skipped via the alldatesinfo table.
            self._fill_carry_forward_positions(
                portfolio_id=portfolio_id,
                security_id=security_id,
                from_date=from_date,
                to_date=today_str,
                updated_by=updated_by,
                counters=counters,
            )

            return counters

        except Exception as e:
            logger.error(f"Error in recalculate_position_chain: {str(e)}")
            return counters

    def _fill_carry_forward_positions(
        self,
        portfolio_id: str,
        security_id: str,
        from_date: str,
        to_date: str,
        updated_by: str,
        counters: Dict[str, int],
    ) -> None:
        """
        After chain recalc, fill business-day gaps with no position row by
        carrying the nearest preceding position forward.

        Only valid business days (rows in gmp_cis_sta_dly_alldatesinfo) are
        considered — weekends and public holidays are skipped.
        Days that already have an is_latest=true position row are also skipped.
        """
        try:
            # 1. Fetch all valid business dates in [from_date, to_date] from alldatesinfo.
            # Falls back to calendar days (excluding weekends) if the table has no rows
            # for this range — without this fallback, a from_date/to_date span not yet
            # populated in alldatesinfo (e.g. a backdated trade whose trade_date is far
            # enough in the past, or a range this reference table simply doesn't cover)
            # silently produces ZERO carry-forward rows: the direct trade-replay writes
            # (the backdated date itself, and the settle date) still happen, but every
            # gap date in between is never backfilled. This was found by comparing
            # against position_queue_service._get_business_dates_between, which already
            # has this exact fallback for the same query shape.
            # contextual_today is stored as YYYYMMDD (no dashes) — see
            # system_date_repository.py's docstring ("business date T, YYYYMMDD").
            # Comparing it against dashed YYYY-MM-DD literals never matches any
            # real row here, which is the actual reason gap days were being missed
            # — not sparse table coverage. Convert both bounds to YYYYMMDD for the
            # query, then normalize results back to YYYY-MM-DD to match position_date.
            from_date_key = from_date.replace('-', '')
            to_date_key = to_date.replace('-', '')
            biz_dates_from_table = []
            try:
                biz_day_rows = impala_manager.execute_query(
                    f"""
                    SELECT contextual_today AS biz_date
                    FROM {self.DATABASE}.gmp_cis_sta_dly_alldatesinfo
                    WHERE src_system = 'gmp'
                      AND sub_system  = 'cis'
                      AND data_frq    = 'dly'
                      AND record_type = 'D'
                      AND contextual_today >= '{from_date_key}'
                      AND contextual_today <= '{to_date_key}'
                    ORDER BY contextual_today ASC
                    """,
                    database=self.DATABASE,
                )
                if biz_day_rows:
                    for r in biz_day_rows:
                        raw = str(r.get('biz_date') or '')
                        if len(raw) == 8 and raw.isdigit():
                            biz_dates_from_table.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
                        elif raw:
                            biz_dates_from_table.append(raw[:10])
            except Exception as e:
                logger.warning(f"Could not fetch business dates from alldatesinfo: {e}. Falling back to calendar days.")

            # Always compute the calendar-weekday range too, and union it with whatever
            # alldatesinfo returned. alldatesinfo has been observed to be only PARTIALLY
            # populated for some ranges — e.g. it may have rows for the trade date and
            # settle date but be silently missing a weekday in between. Falling back to
            # calendar days only when the table returns ZERO rows (the original fix)
            # misses exactly that gap: biz_dates isn't empty, it's just missing one day,
            # so no carry-forward row ever gets written for it. Union guarantees every
            # weekday in [from_date, to_date] is considered, regardless of how sparse
            # alldatesinfo's coverage of that range is.
            cur = date.fromisoformat(from_date)
            end = date.fromisoformat(to_date)
            calendar_weekdays = []
            while cur <= end:
                if cur.weekday() < 5:  # Mon-Fri
                    calendar_weekdays.append(cur.isoformat())
                cur += timedelta(days=1)

            biz_dates = sorted(set(biz_dates_from_table) | set(calendar_weekdays))

            # cis_trade_position doesn't carry isin, so the carried-forward `source`
            # row never has it to copy — must be resolved fresh, same as chain recalc.
            cf_isin, _cf_sec_name = self._get_security_isin_and_name(security_id)

            missing_from_table = set(calendar_weekdays) - set(biz_dates_from_table)
            if not biz_dates_from_table:
                logger.info(
                    "carry-forward: no business days found in alldatesinfo for "
                    f"{from_date}..{to_date} — using calendar days (excl. weekends)"
                )
            elif missing_from_table:
                logger.info(
                    f"carry-forward: alldatesinfo missing {len(missing_from_table)} "
                    f"weekday(s) in {from_date}..{to_date} ({sorted(missing_from_table)}) — "
                    "filled via calendar fallback"
                )

            # 2. Fetch all position_dates that already have is_latest=true in this range.
            existing_rows = impala_manager.execute_query(
                f"""
                SELECT DISTINCT position_basis, position_date
                FROM {self.DATABASE}.cis_trade_position
                WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                  AND security_label       = '{self._escape(security_id)}'
                  AND position_date >= '{from_date}'
                  AND position_date <= '{to_date}'
                  AND is_latest = true
                """,
                database=self.DATABASE,
            )
            existing_by_basis: Dict[str, set] = {'TRADED': set(), 'SETTLED': set()}
            for row in (existing_rows or []):
                b = row.get('position_basis', '')
                d = str(row.get('position_date', '') or '')[:10]
                if b in existing_by_basis and d:
                    existing_by_basis[b].add(d)

            # 3. For each basis, walk business dates and carry forward on gaps.
            for basis in ('TRADED', 'SETTLED'):
                last_known: Optional[Dict[str, Any]] = None

                # Seed last_known from the most recent is_latest row BEFORE from_date.
                seed = impala_manager.execute_query(
                    f"""
                    SELECT position_id, quantity,
                           average_cost_fc, average_cost_lc,
                           total_cost_fc, total_cost_lc,
                           realized_pnl_fc, realized_pnl_lc,
                           unrealized_pnl_fc, unrealized_pnl_lc,
                           market_price, market_value_fc, market_value_lc,
                           dividend_fc, dividend_lc,
                           provision_fc, provision_lc,
                           uncall_fc, uncall_lc,
                           pipeline_fc, pipeline_lc,
                           trade_id, trade_type, status,
                           security_currency, portfolio_currency, fx_rate,
                           position_type
                    FROM {self.DATABASE}.cis_trade_position
                    WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                      AND security_label       = '{self._escape(security_id)}'
                      AND position_basis        = '{basis}'
                      AND position_date         < '{from_date}'
                      AND is_latest = true
                    ORDER BY position_date DESC
                    LIMIT 1
                    """,
                    database=self.DATABASE,
                )
                if seed:
                    last_known = seed[0]

                for biz_date in biz_dates:
                    if biz_date in existing_by_basis[basis]:
                        # Position already written for this date — update last_known from DB.
                        row_today = impala_manager.execute_query(
                            f"""
                            SELECT position_id, quantity,
                                   average_cost_fc, average_cost_lc,
                                   total_cost_fc, total_cost_lc,
                                   realized_pnl_fc, realized_pnl_lc,
                                   unrealized_pnl_fc, unrealized_pnl_lc,
                                   market_price, market_value_fc, market_value_lc,
                                   dividend_fc, dividend_lc,
                                   provision_fc, provision_lc,
                                   uncall_fc, uncall_lc,
                                   pipeline_fc, pipeline_lc,
                                   trade_id, trade_type, status,
                                   security_currency, portfolio_currency, fx_rate,
                                   position_type
                            FROM {self.DATABASE}.cis_trade_position
                            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                              AND security_label       = '{self._escape(security_id)}'
                              AND position_basis        = '{basis}'
                              AND position_date         = '{biz_date}'
                              AND is_latest = true
                            LIMIT 1
                            """,
                            database=self.DATABASE,
                        )
                        if row_today:
                            last_known = row_today[0]
                        continue

                    # Gap day — carry forward if we have a prior position.
                    if last_known:
                        try:
                            written_row = self._write_carry_forward_position(
                                last_known, basis, biz_date,
                                portfolio_id, security_id, updated_by,
                                isin=cf_isin,
                            )
                            counters['recalculated'] += 1
                            # Chain from the re-priced row, not the stale seed, so the
                            # NEXT gap day recomputes on top of this date's real fx_rate.
                            last_known = written_row or last_known
                            existing_by_basis[basis].add(biz_date)
                            logger.info(
                                f"Carry-forward: wrote {basis} position for {biz_date} "
                                f"(portfolio={portfolio_id}, security={security_id})"
                            )
                        except Exception as cf_err:
                            logger.warning(
                                f"Carry-forward write failed for {basis}/{biz_date}: {cf_err}"
                            )

        except Exception as e:
            logger.warning(f"_fill_carry_forward_positions failed (non-fatal): {e}")

    def _write_carry_forward_position(
        self,
        source: Dict[str, Any],
        basis: str,
        position_date: str,
        portfolio_id: str,
        security_id: str,
        updated_by: str,
        isin: str = None,
    ) -> Dict[str, Any]:
        """
        Write a single carry-forward position row for `position_date`, re-pricing
        LC values from `source` (the preceding position dict) using this date's
        own FX rate rather than copying them verbatim.
        Uses the same versioned UPSERT pattern as _save_position:
        mark old versions not-latest, then insert new version with is_latest=true.

        Returns the row as actually written, so callers can chain the next gap
        day's carry-forward from the re-priced values instead of the stale seed.
        """
        from trade.services.position_id_service import position_id as _calc_position_id

        # version_id is a BIGINT column (cis_trade_position/cis_position) — must be a
        # bare numeric literal, not a quoted hex-string UUID.
        version_id = self._generate_id()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        position_id = _calc_position_id(
            portfolio_id, security_id, basis, position_date, 'CIS'
        )

        # Re-derive LC values for THIS gap day rather than copying `source` verbatim.
        # Without this, a carry-forward row's cost_lc/market_value_lc stay frozen at
        # whatever fx_rate was in effect on the last actual trade day, so a TRADED
        # carry-forward row and a same-date SETTLED row (computed fresh via
        # _save_position) end up with different cost_lc for the identical date —
        # exactly the mismatch seen live between TRADED and SETTLED on 2026-03-03.
        # Mirrors _save_position's REVALUED/NON-REVALUED branching exactly.
        security_currency = source.get('security_currency')
        portfolio_currency = source.get('portfolio_currency')
        average_cost_fc = source.get('average_cost_fc')
        total_cost_fc = source.get('total_cost_fc')
        market_value_fc = source.get('market_value_fc')
        fx_rate = self.position_service._get_fx_rate(
            security_currency, portfolio_currency, rate_date=position_date,
            fallback_rate=Decimal(str(source.get('fx_rate'))) if source.get('fx_rate') else None,
        ) if security_currency and portfolio_currency else Decimal(str(source.get('fx_rate') or 1))

        reval_status = self.position_service._get_portfolio_revaluation_status(portfolio_id)
        is_equity_method = self.position_service._is_equity_method_security(security_id)

        market_value_lc = float(market_value_fc or 0) * float(fx_rate)
        if reval_status == 'NON-REVALUED':
            average_cost_lc = source.get('average_cost_lc')
            total_cost_lc = source.get('total_cost_lc')
        else:
            average_cost_lc = float(average_cost_fc or 0) * float(fx_rate)
            total_cost_lc = float(total_cost_fc or 0) * float(fx_rate)
        unrealized_pnl_lc = 0.0 if is_equity_method else (market_value_lc - float(total_cost_lc or 0))

        def _f(val):
            if val is None:
                return 'NULL'
            try:
                return f"CAST({float(val)} AS DECIMAL(20,8))"
            except (ValueError, TypeError):
                return 'NULL'

        def _s(val):
            if val is None:
                return 'NULL'
            return f"'{str(val).replace(chr(39), chr(39)*2)}'"

        # Mark any existing versions for this date/basis as not-latest
        self._mark_old_versions_not_latest_in_settlement(
            portfolio_id, security_id, position_date, basis, timestamp
        )

        query = f"""
        UPSERT INTO {self.DATABASE}.cis_trade_position
        (version_id, position_id, position_date, position_basis,
         portfolio_short_name, security_label,
         quantity,
         average_cost_fc, total_cost_fc,
         average_cost_lc, total_cost_lc,
         realized_pnl_fc, unrealized_pnl_fc,
         realized_pnl_lc, unrealized_pnl_lc,
         market_price, market_value_fc, market_value_lc,
         dividend_fc, dividend_lc,
         trade_id, trade_type,
         lots_held, custodian, sub_custodian,
         security_currency, portfolio_currency, fx_rate,
         status, is_active, is_latest,
         uncall_fc, uncall_lc,
         pipeline_fc, pipeline_lc,
         provision_fc, provision_lc,
         position_type,
         created_by, created_at, updated_by, updated_at)
        VALUES (
         {version_id},
         {position_id},
         '{position_date}',
         '{basis}',
         '{self._escape(portfolio_id)}',
         '{self._escape(security_id)}',
         {_f(source.get('quantity'))},
         {_f(average_cost_fc)}, {_f(total_cost_fc)},
         {_f(average_cost_lc)}, {_f(total_cost_lc)},
         {_f(source.get('realized_pnl_fc'))}, {_f(source.get('unrealized_pnl_fc'))},
         {_f(source.get('realized_pnl_lc'))}, {_f(unrealized_pnl_lc)},
         {_f(source.get('market_price'))},
         {_f(market_value_fc)}, {_f(market_value_lc)},
         {_f(source.get('dividend_fc'))}, {_f(source.get('dividend_lc'))},
         {source['trade_id'] if source.get('trade_id') else 'NULL'},
         {_s(source.get('trade_type'))},
         NULL, NULL, NULL,
         {_s(source.get('security_currency'))},
         {_s(source.get('portfolio_currency'))},
         {_f(fx_rate)},
         {_s(source.get('status') or 'OPEN')},
         true, true,
         {_f(source.get('uncall_fc'))}, {_f(source.get('uncall_lc'))},
         {_f(source.get('pipeline_fc'))}, {_f(source.get('pipeline_lc'))},
         {_f(source.get('provision_fc'))}, {_f(source.get('provision_lc'))},
         {_s(source.get('position_type') or 'INT')},
         '{self._escape(updated_by)}', '{timestamp}',
         '{self._escape(updated_by)}', '{timestamp}'
        )
        """
        impala_manager.execute_write(query, database=self.DATABASE)

        # Reflects what was actually written above (re-priced LC values), not the
        # stale `source` — used both for the cis_position sync below and returned
        # to the caller so the NEXT gap day's carry-forward chains from the
        # correctly re-priced row instead of re-copying yesterday's fx_rate again.
        updated_row = dict(source)
        updated_row.update({
            'average_cost_fc': average_cost_fc,
            'total_cost_fc': total_cost_fc,
            'average_cost_lc': average_cost_lc,
            'total_cost_lc': total_cost_lc,
            'market_value_fc': market_value_fc,
            'market_value_lc': market_value_lc,
            'unrealized_pnl_lc': unrealized_pnl_lc,
            'fx_rate': float(fx_rate),
            'position_date': position_date,
            'isin': isin,
        })

        # Sync to cis_position (gold/master table) — mirrors _sync_to_cis_position in
        # position_service.py. Without this, a carry-forward gap date never gets an
        # is_latest=true row in cis_position at all, since only cis_trade_position was
        # written above. position_id is date-inclusive (see position_id_service.py), so
        # this UPSERT only ever targets this exact date's row for this position_type —
        # it cannot collide with or clear EOD/SOD/CORR rows for the same date.
        self._sync_carry_forward_to_cis_position(
            source=updated_row, basis=basis, position_date=position_date,
            portfolio_id=portfolio_id, security_id=security_id,
            position_id=position_id, updated_by=updated_by, timestamp=timestamp,
            isin=isin,
        )

        return updated_row

    def _sync_carry_forward_to_cis_position(
        self,
        source: Dict[str, Any],
        basis: str,
        position_date: str,
        portfolio_id: str,
        security_id: str,
        position_id: int,
        updated_by: str,
        timestamp: str,
        isin: str = None,
    ) -> None:
        """
        Sync a carry-forward position to cis_position (gold/master table).

        Scoped to the exact (position_id, position_type) PK for this date — never
        touches other dates or other position_types (EOD/SOD/CORR) for this key.
        """
        position_type = source.get('position_type') or 'INT'

        def _f(val):
            if val is None:
                return 'NULL'
            try:
                return f"CAST({float(val)} AS DECIMAL(30,8))"
            except (ValueError, TypeError):
                return 'NULL'

        # net_book_value = cost + unrealized_pnl - provision — same formula
        # _process_buy/_process_sell use. cis_trade_position (source of `source`)
        # has no net_book_value column of its own, so it must be recomputed here
        # rather than copied — this UPSERT previously omitted these two columns
        # entirely, which silently defaulted every carry-forward row's NBV to 0
        # in cis_position regardless of its actual cost/market value.
        nbv_fc = (float(source.get('total_cost_fc') or 0)
                  + float(source.get('unrealized_pnl_fc') or 0)
                  - float(source.get('provision_fc') or 0))
        nbv_lc = (float(source.get('total_cost_lc') or 0)
                  + float(source.get('unrealized_pnl_lc') or 0)
                  - float(source.get('provision_lc') or 0))

        try:
            query = f"""
            UPSERT INTO {self.DATABASE}.cis_position
            (position_id, version_id, portfolio, security_label, position_basis,
             position_date, src_system, processing_date, quantity,
             average_cost_fc, cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc,
             average_cost_lc, cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc,
             provision_fc, provision_lc, dividend_fc, dividend_lc,
             realized_pnl_fc, realized_pnl_lc,
             uncall_fc, uncall_lc, pipeline_fc, pipeline_lc,
             isin, source_table, processing_timestamp, position_type, is_latest)
            VALUES (
             {position_id},
             {self._generate_id()},
             '{self._escape(portfolio_id)}',
             '{self._escape(security_id)}',
             '{basis}',
             '{position_date}',
             'CIS',
             '{position_date}',
             {_f(source.get('quantity'))},
             {_f(source.get('average_cost_fc'))}, {_f(source.get('total_cost_fc'))},
             {_f(source.get('market_value_fc'))}, {_f(nbv_fc)}, {_f(source.get('unrealized_pnl_fc'))},
             {_f(source.get('average_cost_lc'))}, {_f(source.get('total_cost_lc'))},
             {_f(source.get('market_value_lc'))}, {_f(nbv_lc)}, {_f(source.get('unrealized_pnl_lc'))},
             {_f(source.get('provision_fc'))}, {_f(source.get('provision_lc'))},
             {_f(source.get('dividend_fc'))}, {_f(source.get('dividend_lc'))},
             {_f(source.get('realized_pnl_fc'))}, {_f(source.get('realized_pnl_lc'))},
             {_f(source.get('uncall_fc'))}, {_f(source.get('uncall_lc'))},
             {_f(source.get('pipeline_fc'))}, {_f(source.get('pipeline_lc'))},
             {f"'{self._escape(isin)}'" if isin else 'NULL'},
             'cis_trade_position_carry_forward',
             '{timestamp}',
             '{position_type}',
             true
            )
            """
            impala_manager.execute_write(query, database=self.DATABASE)
            logger.info(
                f"Carry-forward synced to cis_position: {portfolio_id}/{security_id} "
                f"basis={basis} date={position_date} type={position_type}"
            )
        except Exception as e:
            logger.warning(
                f"Carry-forward cis_position sync failed (non-fatal) for "
                f"{portfolio_id}/{security_id} date={position_date}: {e}"
            )

    def _mark_old_versions_not_latest_in_settlement(
        self,
        portfolio_id: str,
        security_id: str,
        position_date: str,
        basis: str,
        timestamp: str,
    ) -> None:
        """Mark existing is_latest=true rows for this date/basis as false before inserting carry-forward."""
        try:
            impala_manager.execute_write(
                f"""
                UPDATE {self.DATABASE}.cis_trade_position
                SET is_latest  = false,
                    updated_at = '{timestamp}'
                WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
                  AND security_label       = '{self._escape(security_id)}'
                  AND position_date        = '{position_date}'
                  AND position_basis       = '{basis}'
                  AND is_latest = true
                """,
                database=self.DATABASE,
            )
        except Exception as e:
            logger.warning(f"_mark_old_versions_not_latest_in_settlement failed (non-fatal): {e}")

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

    def _get_security_isin_and_name(self, security_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetch (isin, security_name) for a security from cis_security.

        cis_trade doesn't store isin — it's only ever resolved from cis_security
        at trade-entry time and threaded through as a calculate_position() kwarg.
        Chain recalc and carry-forward both replay/derive positions long after
        entry time and have no other way to get it, so they need this same
        lookup rather than silently passing isin=None.
        """
        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT isin, security_name
                FROM {self.DATABASE}.cis_security
                WHERE security_name = '{self._escape(security_id)}'
                LIMIT 1
                """,
                database=self.DATABASE,
            )
            if rows:
                return rows[0].get('isin'), rows[0].get('security_name')
        except Exception as e:
            logger.warning(f"Could not fetch isin/security_name for {security_id}: {e}")
        return None, None

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
