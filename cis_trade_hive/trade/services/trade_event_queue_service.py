"""
Trade Event Queue Service - Async Background Processing for Trade Side Effects

Processes queued trade events (HISTORY, SETTLEMENT/AVP) that were queued
during fast trade creation. This allows trade save to return immediately
while side effects are processed asynchronously.

Features:
- Background worker processes cis_trade_event_queue
- Retry logic for failed items (max 3 retries)
- Dead letter queue for permanent failures
- Recovery API for manual reprocessing
- SLA monitoring

Corner Cases Handled:
1. DB connection failure during processing -> Retry with backoff
2. Settlement calculation failure -> Mark FAILED, retry up to 3 times
3. Worker crash -> Events remain PENDING, picked up on restart
4. Duplicate processing -> Idempotent operations (UPSERT)
5. Trade deleted before processing -> Log warning, mark COMPLETED
6. Invalid event data -> Mark FAILED with error message
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class TradeEventQueueService:
    """
    Background processor for trade events queued in cis_trade_event_queue.

    Event Types:
    - HISTORY: Insert trade history record
    - SETTLEMENT: Process settlement and AVP calculation
    - POSITION_MODIFY: Reverse old position and recalculate with new trade values
    - POSITION_CANCEL: Reverse position when trade is cancelled
    """

    DATABASE = 'gmp_cis'
    EVENT_QUEUE_TABLE = 'cis_trade_event_queue'
    TRADE_TABLE = 'cis_trade'
    HISTORY_TABLE = 'cis_trade_history'

    # Status constants
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_DEAD_LETTER = 'DEAD_LETTER'

    # Configuration
    MAX_RETRIES = 3
    BATCH_SIZE = 50
    POLL_INTERVAL_SECONDS = 5
    PROCESSING_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self):
        """Initialize the trade event queue service."""
        self._worker_running = False
        self._worker_thread = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='trade_event_worker')
        self._lock = threading.Lock()
        self._stats = {
            'processed': 0,
            'failed': 0,
            'dead_letter': 0,
            'last_run': None
        }

    # =========================================================================
    # WORKER MANAGEMENT
    # =========================================================================

    def start_worker(self) -> bool:
        """
        Start the background worker thread.

        Returns:
            True if worker started successfully, False if already running.
        """
        with self._lock:
            if self._worker_running:
                logger.warning("Trade event worker already running")
                return False

            self._worker_running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name='TradeEventQueueWorker',
                daemon=True
            )
            self._worker_thread.start()
            logger.info("Trade event queue worker started")
            return True

    def stop_worker(self) -> bool:
        """
        Stop the background worker gracefully.

        Returns:
            True if worker stopped successfully.
        """
        with self._lock:
            if not self._worker_running:
                logger.warning("Trade event worker not running")
                return False

            self._worker_running = False
            logger.info("Stopping trade event queue worker...")

            # Wait for thread to finish (with timeout)
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=30)

            logger.info("Trade event queue worker stopped")
            return True

    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._worker_running

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            **self._stats,
            'is_running': self._worker_running,
            'thread_alive': self._worker_thread.is_alive() if self._worker_thread else False
        }

    def _worker_loop(self):
        """Main worker loop - polls and processes events."""
        logger.info("Trade event worker loop started")

        while self._worker_running:
            try:
                # Fetch pending events
                events = self._fetch_pending_events()

                if events:
                    logger.info(f"Processing {len(events)} pending trade events")
                    for event in events:
                        if not self._worker_running:
                            break
                        self._process_event(event)
                else:
                    # No events, sleep before next poll
                    time.sleep(self.POLL_INTERVAL_SECONDS)

                self._stats['last_run'] = datetime.now().isoformat()

            except Exception as e:
                logger.error(f"Error in trade event worker loop: {e}")
                # Sleep on error to prevent tight loop
                time.sleep(self.POLL_INTERVAL_SECONDS * 2)

        logger.info("Trade event worker loop ended")

    # =========================================================================
    # EVENT FETCHING
    # =========================================================================

    def _fetch_pending_events(self) -> List[Dict]:
        """
        Fetch pending events from queue, ordered by creation time.
        Also picks up stale PROCESSING events (timeout recovery).

        Timeout uses processing_started_at (not created_at) so events that sit
        in the queue for a long time before being picked up are never mistaken
        for stale — only events where the worker itself has been running too long
        are recovered. This prevents double-processing and qty doubling.
        """
        try:
            # Calculate timeout threshold based on when processing STARTED, not created
            timeout_threshold = datetime.now().timestamp() - self.PROCESSING_TIMEOUT_SECONDS
            timeout_str = datetime.fromtimestamp(timeout_threshold).strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            SELECT event_id, trade_id, deal_number, event_type, event_data,
                   status, retry_count, error_message, created_by, created_at,
                   processing_started_at, processed_at
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status = '{self.STATUS_PENDING}'
               OR (status = '{self.STATUS_PROCESSING}'
                   AND processing_started_at IS NOT NULL
                   AND processing_started_at < '{timeout_str}')
            ORDER BY created_at ASC
            LIMIT {self.BATCH_SIZE}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching pending events: {e}")
            return []

    # =========================================================================
    # EVENT PROCESSING
    # =========================================================================

    def _process_event(self, event: Dict) -> bool:
        """
        Process a single event from the queue.

        Args:
            event: Event dictionary from queue

        Returns:
            True if processed successfully, False otherwise.
        """
        event_id = event.get('event_id')
        trade_id = event.get('trade_id')
        event_type = event.get('event_type')
        retry_count = event.get('retry_count', 0) or 0

        logger.info(f"Processing event {event_id}: type={event_type}, trade={trade_id}, retry={retry_count}")

        try:
            # Mark as PROCESSING
            self._update_event_status(event_id, self.STATUS_PROCESSING)

            # Parse event data
            event_data = {}
            if event.get('event_data'):
                try:
                    event_data = json.loads(event['event_data'])
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid event_data JSON: {e}")

            # Verify trade still exists
            trade = self._get_trade(trade_id)
            if not trade:
                logger.warning(f"Trade {trade_id} not found for event {event_id} - marking completed")
                self._update_event_status(event_id, self.STATUS_COMPLETED,
                                         error_message="Trade not found (may have been deleted)")
                return True

            # Process based on event type (normalize to handle whitespace/case)
            event_type_normalized = (event_type or '').strip().upper()

            if event_type_normalized == 'HISTORY':
                success = self._process_history_event(event, event_data, trade)
            elif event_type_normalized == 'SETTLEMENT':
                success = self._process_settlement_event(event, event_data, trade)
            elif event_type_normalized == 'POSITION_MODIFY':
                success = self._process_position_modify_event(event, event_data, trade)
            elif event_type_normalized == 'POSITION_CANCEL':
                success = self._process_position_cancel_event(event, event_data, trade)
            else:
                logger.warning(f"Unknown event type: '{event_type}' (normalized: '{event_type_normalized}')")
                success = False

            if success:
                self._update_event_status(event_id, self.STATUS_COMPLETED)
                self._stats['processed'] += 1
                logger.info(f"Event {event_id} completed successfully")
                return True
            else:
                raise Exception("Processing returned False")

        except Exception as e:
            error_msg = str(e)[:500]  # Truncate long error messages
            logger.error(f"Error processing event {event_id}: {error_msg}")

            # Increment retry count and check if max retries exceeded
            new_retry_count = retry_count + 1
            if new_retry_count >= self.MAX_RETRIES:
                # Move to dead letter queue
                self._update_event_status(
                    event_id,
                    self.STATUS_DEAD_LETTER,
                    retry_count=new_retry_count,
                    error_message=f"Max retries exceeded. Last error: {error_msg}"
                )
                self._stats['dead_letter'] += 1
                logger.error(f"Event {event_id} moved to dead letter queue after {new_retry_count} retries")
            else:
                # Mark as FAILED for retry
                self._update_event_status(
                    event_id,
                    self.STATUS_FAILED,
                    retry_count=new_retry_count,
                    error_message=error_msg
                )
                self._stats['failed'] += 1

                # Reset to PENDING for retry after backoff
                backoff_seconds = 2 ** new_retry_count  # Exponential backoff: 2, 4, 8 seconds
                time.sleep(backoff_seconds)
                self._update_event_status(event_id, self.STATUS_PENDING, retry_count=new_retry_count)

            return False

    def _process_history_event(self, event: Dict, event_data: Dict, trade: Dict) -> bool:
        """
        Process HISTORY event - insert trade history record.

        This is idempotent - if history already exists, it won't duplicate.
        """
        trade_id = event.get('trade_id')
        deal_number = event.get('deal_number', '')
        created_by = event.get('created_by', 'system')

        action = event_data.get('action', 'CREATE')
        old_status = event_data.get('old_status')
        new_status = event_data.get('new_status', 'INITIAL')
        changes = event_data.get('changes', {})
        comments = event_data.get('comments', 'Trade created (async)')

        try:
            # Generate history ID
            history_id = int(datetime.now().timestamp() * 1000)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Check if history already exists for this trade+action (idempotent)
            check_query = f"""
            SELECT history_id FROM {self.DATABASE}.{self.HISTORY_TABLE}
            WHERE trade_id = {trade_id} AND action = '{action}'
            LIMIT 1
            """
            existing = impala_manager.execute_query(check_query, database=self.DATABASE)
            if existing:
                logger.info(f"History already exists for trade {trade_id} action {action} - skipping")
                return True

            # Insert history record
            changes_json = json.dumps(changes) if changes else '{}'
            old_status_val = f"'{old_status}'" if old_status else 'NULL'

            insert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.HISTORY_TABLE}
            (history_id, trade_id, deal_number, action, old_status, new_status,
             changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {trade_id},
                '{self._escape(deal_number)}',
                '{action}',
                {old_status_val},
                '{new_status}',
                '{self._escape(changes_json)}',
                '{self._escape(comments)}',
                '{self._escape(created_by)}',
                '{timestamp}'
            )
            """

            success = impala_manager.execute_write(insert_query, database=self.DATABASE)
            if success:
                logger.info(f"Inserted history record for trade {trade_id}")
            return success

        except Exception as e:
            logger.error(f"Error processing history event for trade {trade_id}: {e}")
            raise

    def _process_settlement_event(self, event: Dict, event_data: Dict, trade: Dict) -> bool:
        """
        Process SETTLEMENT event - calculate AVP and update position.

        Uses existing settlement_service for actual processing.
        """
        trade_id = event.get('trade_id')
        created_by = event.get('created_by', 'system')

        try:
            # Import here to avoid circular imports
            from trade.services.settlement_service import settlement_service

            # Extract data from event
            portfolio_id = event_data.get('portfolio_short_name', '')
            security_id = event_data.get('security_label', '')
            trade_type = event_data.get('trade_type', '')
            quantity = Decimal(str(event_data.get('quantity', 0) or 0))
            price = Decimal(str(event_data.get('price', 0) or 0))
            trade_date = event_data.get('trade_date', '')
            settle_date = event_data.get('settle_date', '')

            # Calculate total charges (manual + auto-calculated)
            manual_charges = (
                Decimal(str(event_data.get('commission', 0) or 0)) +
                Decimal(str(event_data.get('sec_fee', 0) or 0)) +
                Decimal(str(event_data.get('other_charges', 0) or 0))
            )
            auto_charges = (
                Decimal(str(event_data.get('calculated_commission', 0) or 0)) +
                Decimal(str(event_data.get('calculated_clearing_fee', 0) or 0)) +
                Decimal(str(event_data.get('calculated_trading_fee', 0) or 0)) +
                Decimal(str(event_data.get('calculated_gst', 0) or 0)) +
                Decimal(str(event_data.get('calculated_other_fees', 0) or 0))
            )
            total_charges = manual_charges + auto_charges

            # Process settlement (synchronous within worker)
            success, msg, result = settlement_service.process_trade_settlement(
                trade_id=trade_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=trade_type,
                quantity=quantity,
                price=price,
                charges=total_charges,
                trade_date=trade_date,
                settle_date=settle_date,
                updated_by=created_by,
                security_currency=event_data.get('security_currency'),
                portfolio_currency=event_data.get('portfolio_currency'),
                isin=event_data.get('isin'),
                security_name=event_data.get('security_name'),
                custodian=event_data.get('custodian', ''),
                sub_custodian=event_data.get('sub_custodian', ''),
                async_mode=False  # Process synchronously within worker
            )

            if success:
                logger.info(f"Settlement processed for trade {trade_id}: {msg}")
            else:
                logger.warning(f"Settlement note for trade {trade_id}: {msg}")
                # Non-critical warnings (like "queued for future") are still success
                if 'queued' in msg.lower() or 'future' in msg.lower():
                    return True

            return success

        except Exception as e:
            logger.error(f"Error processing settlement event for trade {trade_id}: {e}")
            raise

    def _process_position_modify_event(self, event: Dict, event_data: Dict, trade: Dict) -> bool:
        """
        Process POSITION_MODIFY event - reverse old position (if exists) and recalculate with new values.

        This is used when a trade is modified. Works for any trade status:
        - If position exists (SETTLED): Reverse old position, then apply new values
        - If no position yet (INITIAL/MODIFIED): Just calculate new position directly
        """
        trade_id = event.get('trade_id')
        created_by = event.get('created_by', 'system')

        try:
            from trade.services.settlement_service import settlement_service

            # Get OLD trade values (what was originally calculated)
            old_data = event_data.get('old_trade', {})
            new_data = event_data.get('new_trade', {})

            logger.info(f"POSITION_MODIFY: event_data keys={list(event_data.keys())}")
            logger.info(f"POSITION_MODIFY: old_data type={type(old_data)}, has data={bool(old_data)}")
            logger.info(f"POSITION_MODIFY: new_data type={type(new_data)}, has data={bool(new_data)}")

            if not old_data or not new_data:
                logger.warning(f"POSITION_MODIFY event missing old/new trade data for {trade_id}")
                logger.warning(f"POSITION_MODIFY: raw event_data={str(event_data)[:500]}")
                return True  # Mark as completed to avoid retries

            portfolio_id = old_data.get('portfolio_short_name', '')
            security_id = old_data.get('security_label', '')

            logger.info(f"POSITION_MODIFY: portfolio={portfolio_id}, security={security_id}")

            # Check if position already exists for this trade
            position_exists = self.check_position_exists(trade_id)

            # Step 1: REVERSE the old position for BOTH bases (only if position exists)
            # We must reverse both TRADE_DATE and SETTLE_DATE chains that were originally created.
            if position_exists:
                old_trade_type = old_data.get('trade_type', '')
                reverse_type = 'SELL' if old_trade_type == 'BUY' else 'BUY'
                old_quantity = Decimal(str(old_data.get('quantity', 0) or 0))
                old_price = Decimal(str(old_data.get('price', 0) or 0))
                old_trade_date = old_data.get('trade_date', '')
                old_settle_date = old_data.get('settle_date', '')

                logger.info(f"POSITION_MODIFY: Reversing old {old_trade_type} for trade {trade_id} (both bases)")

                for basis in ['TRADE_DATE', 'SETTLE_DATE']:
                    pos_date = old_trade_date if basis == 'TRADE_DATE' else old_settle_date
                    success_reverse, msg_reverse, _ = settlement_service.process_trade_settlement(
                        trade_id=trade_id,
                        portfolio_id=portfolio_id,
                        security_id=security_id,
                        trade_type=reverse_type,
                        quantity=old_quantity,
                        price=old_price,
                        charges=Decimal('0'),  # No charges on reversal
                        trade_date=old_trade_date,
                        settle_date=old_settle_date,
                        updated_by=created_by,
                        security_currency=old_data.get('security_currency'),
                        portfolio_currency=old_data.get('portfolio_currency'),
                        async_mode=False,
                        position_basis=basis
                    )
                    if not success_reverse:
                        logger.error(
                            f"Failed to reverse {basis} position for trade {trade_id}: {msg_reverse}"
                        )
                        raise Exception(f"Reversal failed ({basis}): {msg_reverse}")
            else:
                logger.info(f"POSITION_MODIFY: No existing position for trade {trade_id}, skipping reversal")

            # Step 2: Apply NEW trade values for BOTH bases
            new_trade_type = new_data.get('trade_type', '')
            new_quantity = Decimal(str(new_data.get('quantity', 0) or 0))
            new_price = Decimal(str(new_data.get('price', 0) or 0))
            new_charges = self._calculate_charges(new_data)
            new_trade_date = new_data.get('trade_date', '')
            new_settle_date = new_data.get('settle_date', '')

            logger.info(f"POSITION_MODIFY: Applying new {new_trade_type} for trade {trade_id} (both bases)")

            # position_basis=None → dual mode (both bases created)
            success_new, msg_new, _ = settlement_service.process_trade_settlement(
                trade_id=trade_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=new_trade_type,
                quantity=new_quantity,
                price=new_price,
                charges=new_charges,
                trade_date=new_trade_date,
                settle_date=new_settle_date,
                updated_by=created_by,
                security_currency=new_data.get('security_currency'),
                portfolio_currency=new_data.get('portfolio_currency'),
                isin=new_data.get('isin'),
                security_name=new_data.get('security_name'),
                custodian=new_data.get('custodian', ''),
                sub_custodian=new_data.get('sub_custodian', ''),
                async_mode=False,
                position_basis=None  # dual — creates both TRADE_DATE and SETTLE_DATE
            )

            if success_new:
                logger.info(f"POSITION_MODIFY completed for trade {trade_id}")
            else:
                logger.warning(f"POSITION_MODIFY new trade note: {msg_new}")
                if 'queued' in msg_new.lower() or 'future' in msg_new.lower():
                    return True

            return success_new

        except Exception as e:
            logger.error(f"Error processing POSITION_MODIFY for trade {trade_id}: {e}")
            raise

    def _process_position_cancel_event(self, event: Dict, event_data: Dict, trade: Dict) -> bool:
        """
        Process POSITION_CANCEL event - reverse position when trade is cancelled.

        Steps:
        1. Get the original trade details
        2. Apply opposite trade (BUY -> SELL, SELL -> BUY) to reverse
        """
        trade_id = event.get('trade_id')
        created_by = event.get('created_by', 'system')

        try:
            from trade.services.settlement_service import settlement_service

            portfolio_id = event_data.get('portfolio_short_name', '')
            security_id = event_data.get('security_label', '')
            original_trade_type = event_data.get('trade_type', '')
            quantity = Decimal(str(event_data.get('quantity', 0) or 0))
            price = Decimal(str(event_data.get('price', 0) or 0))
            trade_date = event_data.get('trade_date', '')
            settle_date = event_data.get('settle_date', '')

            # Determine reversal type
            reverse_type = 'SELL' if original_trade_type == 'BUY' else 'BUY'

            logger.info(
                f"POSITION_CANCEL: Reversing {original_trade_type} with {reverse_type} "
                f"for trade {trade_id} (both bases)"
            )

            # Reverse BOTH bases — mirrors what was created on trade creation.
            # position_basis=None triggers dual mode in process_trade_settlement.
            success, msg, _ = settlement_service.process_trade_settlement(
                trade_id=trade_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=reverse_type,
                quantity=quantity,
                price=price,
                charges=Decimal('0'),  # No charges on cancellation reversal
                trade_date=trade_date,
                settle_date=settle_date,
                updated_by=created_by,
                security_currency=event_data.get('security_currency'),
                portfolio_currency=event_data.get('portfolio_currency'),
                async_mode=False,
                position_basis=None  # dual — reverses both TRADE_DATE and SETTLE_DATE
            )

            if success:
                logger.info(f"POSITION_CANCEL completed for trade {trade_id}")
            else:
                logger.warning(f"POSITION_CANCEL note for trade {trade_id}: {msg}")
                if 'queued' in msg.lower() or 'future' in msg.lower():
                    return True

            return success

        except Exception as e:
            logger.error(f"Error processing POSITION_CANCEL for trade {trade_id}: {e}")
            raise

    def _calculate_charges(self, trade_data: Dict) -> Decimal:
        """Calculate total charges from trade data."""
        manual_charges = (
            Decimal(str(trade_data.get('commission', 0) or 0)) +
            Decimal(str(trade_data.get('sec_fee', 0) or 0)) +
            Decimal(str(trade_data.get('other_charges', 0) or 0))
        )
        auto_charges = (
            Decimal(str(trade_data.get('calculated_commission', 0) or 0)) +
            Decimal(str(trade_data.get('calculated_clearing_fee', 0) or 0)) +
            Decimal(str(trade_data.get('calculated_trading_fee', 0) or 0)) +
            Decimal(str(trade_data.get('calculated_gst', 0) or 0)) +
            Decimal(str(trade_data.get('calculated_other_fees', 0) or 0))
        )
        return manual_charges + auto_charges

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_trade(self, trade_id: int) -> Optional[Dict]:
        """Get trade by ID."""
        try:
            query = f"""
            SELECT trade_id, status, is_deleted
            FROM {self.DATABASE}.{self.TRADE_TABLE}
            WHERE trade_id = {trade_id}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                trade = results[0]
                # Check if trade is deleted
                if trade.get('is_deleted'):
                    return None
                return trade
            return None
        except Exception as e:
            logger.error(f"Error getting trade {trade_id}: {e}")
            return None

    def _update_event_status(
        self,
        event_id: int,
        status: str,
        retry_count: int = None,
        error_message: str = None
    ) -> bool:
        """Update event status in queue."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [f"status = '{status}'"]

            if status == self.STATUS_PROCESSING:
                # Record exactly when worker started — used for stale timeout check
                # (prevents double-processing when event sits in queue > PROCESSING_TIMEOUT_SECONDS)
                set_clauses.append(f"processing_started_at = '{timestamp}'")

            if status == self.STATUS_COMPLETED:
                set_clauses.append(f"processed_at = '{timestamp}'")

            if retry_count is not None:
                set_clauses.append(f"retry_count = {retry_count}")

            if error_message is not None:
                set_clauses.append(f"error_message = '{self._escape(error_message)}'")

            query = f"""
            UPDATE {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            SET {', '.join(set_clauses)}
            WHERE event_id = {event_id}
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error updating event {event_id} status: {e}")
            return False

    def _escape(self, value: str) -> str:
        """Escape single quotes for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    # =========================================================================
    # RECOVERY & MONITORING
    # =========================================================================

    def get_pending_count(self) -> int:
        """Get count of pending events."""
        try:
            query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status = '{self.STATUS_PENDING}'
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0]['cnt'] if results else 0
        except Exception as e:
            logger.error(f"Error getting pending count: {e}")
            return 0

    def get_failed_events(self, limit: int = 100) -> List[Dict]:
        """Get failed and dead-letter events for review."""
        try:
            query = f"""
            SELECT event_id, trade_id, deal_number, event_type,
                   status, retry_count, error_message, created_at
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status IN ('{self.STATUS_FAILED}', '{self.STATUS_DEAD_LETTER}')
            ORDER BY created_at DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting failed events: {e}")
            return []

    def reprocess_event(self, event_id: int) -> Tuple[bool, str]:
        """
        Manually reprocess a failed/dead-letter event.

        Args:
            event_id: Event ID to reprocess

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get event
            query = f"""
            SELECT * FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE event_id = {event_id}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if not results:
                return False, f"Event {event_id} not found"

            event = results[0]

            if event.get('status') not in (self.STATUS_FAILED, self.STATUS_DEAD_LETTER):
                return False, f"Event {event_id} is not in failed/dead-letter status"

            # Reset to PENDING with retry count reset
            self._update_event_status(event_id, self.STATUS_PENDING, retry_count=0, error_message=None)

            logger.info(f"Event {event_id} reset to PENDING for reprocessing")
            return True, f"Event {event_id} queued for reprocessing"

        except Exception as e:
            logger.error(f"Error reprocessing event {event_id}: {e}")
            return False, str(e)

    def reprocess_all_failed(self) -> Tuple[int, int]:
        """
        Reprocess all failed events (not dead-letter).

        Returns:
            Tuple of (success_count, error_count)
        """
        try:
            query = f"""
            SELECT event_id FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status = '{self.STATUS_FAILED}'
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            success_count = 0
            error_count = 0

            for event in (results or []):
                event_id = event.get('event_id')
                success, _ = self.reprocess_event(event_id)
                if success:
                    success_count += 1
                else:
                    error_count += 1

            logger.info(f"Reprocessed {success_count} failed events, {error_count} errors")
            return success_count, error_count

        except Exception as e:
            logger.error(f"Error reprocessing all failed events: {e}")
            return 0, 0

    def cleanup_completed_events(self, days_old: int = 7) -> int:
        """
        Clean up old completed events.

        Args:
            days_old: Delete events older than this many days

        Returns:
            Number of events deleted
        """
        try:
            # Note: Kudu doesn't support DELETE, so we'd need to use a different approach
            # For now, just log the count that would be deleted
            query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE status = '{self.STATUS_COMPLETED}'
            AND created_at < NOW() - INTERVAL {days_old} DAYS
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            count = results[0]['cnt'] if results else 0

            logger.info(f"Found {count} completed events older than {days_old} days")
            # Actual deletion would require recreating the table or using soft delete
            return count

        except Exception as e:
            logger.error(f"Error counting old events: {e}")
            return 0

    def get_queue_health(self) -> Dict[str, Any]:
        """
        Get overall queue health status.

        Returns health metrics for monitoring.
        """
        try:
            query = f"""
            SELECT
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            GROUP BY status
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            status_counts = {}
            oldest_pending = None

            for row in (results or []):
                status = row.get('status', 'UNKNOWN')
                status_counts[status] = row.get('count', 0)
                if status == self.STATUS_PENDING:
                    oldest_pending = row.get('oldest')

            # Calculate SLA breach
            sla_breached = False
            if oldest_pending:
                try:
                    oldest_dt = datetime.strptime(str(oldest_pending)[:19], '%Y-%m-%d %H:%M:%S')
                    age_seconds = (datetime.now() - oldest_dt).total_seconds()
                    sla_breached = age_seconds > self.PROCESSING_TIMEOUT_SECONDS
                except:
                    pass

            return {
                'status_counts': status_counts,
                'pending_count': status_counts.get(self.STATUS_PENDING, 0),
                'failed_count': status_counts.get(self.STATUS_FAILED, 0),
                'dead_letter_count': status_counts.get(self.STATUS_DEAD_LETTER, 0),
                'oldest_pending': str(oldest_pending) if oldest_pending else None,
                'sla_breached': sla_breached,
                'worker_running': self._worker_running,
                'worker_stats': self._stats
            }

        except Exception as e:
            logger.error(f"Error getting queue health: {e}")
            return {
                'error': str(e),
                'worker_running': self._worker_running
            }

    # =========================================================================
    # EVENT QUEUING (for use by views/services)
    # =========================================================================

    def queue_event(
        self,
        trade_id: int,
        deal_number: str,
        event_type: str,
        event_data: Dict,
        created_by: str,
        async_mode: bool = False
    ) -> Tuple[bool, str]:
        """
        Queue a new event for background processing.

        Args:
            trade_id: Trade ID
            deal_number: Deal number for reference
            event_type: HISTORY, SETTLEMENT, POSITION_MODIFY, POSITION_CANCEL
            event_data: JSON-serializable dict with event details
            created_by: User who triggered the event
            async_mode: If True, queue asynchronously (fire-and-forget) for fast UI response

        Returns:
            Tuple of (success, message)
        """
        try:
            event_id = int(datetime.now().timestamp() * 1000000)  # Microsecond precision
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Use default=str to handle Decimal and other non-JSON-serializable types
            event_json = json.dumps(event_data, default=str)

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data,
             status, retry_count, created_by, created_at)
            VALUES (
                {event_id},
                {trade_id},
                '{self._escape(deal_number)}',
                '{event_type}',
                '{self._escape(event_json)}',
                '{self.STATUS_PENDING}',
                0,
                '{self._escape(created_by)}',
                '{timestamp}'
            )
            """

            if async_mode:
                # Fire-and-forget for fast UI response
                def on_failure(success: bool):
                    if not success:
                        logger.error(f"CRITICAL: Failed to queue {event_type} event for trade {trade_id}")

                impala_manager.execute_write_async(query, database=self.DATABASE, callback=on_failure)
                logger.info(f"Queued {event_type} event for trade {trade_id} (async)")
                return True, f"Event {event_id} queued (async)"
            else:
                success = impala_manager.execute_write(query, database=self.DATABASE)

                if success:
                    logger.info(f"Queued {event_type} event for trade {trade_id}")
                    return True, f"Event {event_id} queued"
                else:
                    return False, "Failed to queue event"

        except Exception as e:
            logger.error(f"Error queuing event for trade {trade_id}: {e}")
            return False, str(e)

    def queue_position_modify_event(
        self,
        trade_id: int,
        deal_number: str,
        old_trade_data: Dict,
        new_trade_data: Dict,
        created_by: str
    ) -> Tuple[bool, str]:
        """
        Queue a POSITION_MODIFY event when trade is edited after position calculated.

        Uses async mode for fast UI response - the event is queued in the background.

        Args:
            trade_id: Trade ID
            deal_number: Deal number
            old_trade_data: Original trade values before modification
            new_trade_data: New trade values after modification
            created_by: User who modified the trade

        Returns:
            Tuple of (success, message)
        """
        event_data = {
            'old_trade': old_trade_data,
            'new_trade': new_trade_data
        }
        return self.queue_event(
            trade_id=trade_id,
            deal_number=deal_number,
            event_type='POSITION_MODIFY',
            event_data=event_data,
            created_by=created_by,
            async_mode=True  # Fast UI response
        )

    def queue_position_cancel_event(
        self,
        trade_id: int,
        deal_number: str,
        trade_data: Dict,
        created_by: str
    ) -> Tuple[bool, str]:
        """
        Queue a POSITION_CANCEL event when trade is cancelled after position calculated.

        Uses async mode for fast UI response - the event is queued in the background.

        Args:
            trade_id: Trade ID
            deal_number: Deal number
            trade_data: Original trade values to reverse
            created_by: User who cancelled the trade

        Returns:
            Tuple of (success, message)
        """
        return self.queue_event(
            trade_id=trade_id,
            deal_number=deal_number,
            event_type='POSITION_CANCEL',
            event_data=trade_data,
            created_by=created_by,
            async_mode=True  # Fast UI response
        )

    def check_position_exists(self, trade_id: int) -> bool:
        """
        Check if position has been calculated for a trade.

        Used to determine if we need to reverse on modify/cancel.
        """
        try:
            query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.DATABASE}.cis_trade_position
            WHERE trade_id = {trade_id}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            count = results[0]['cnt'] if results else 0
            return count > 0
        except Exception as e:
            logger.error(f"Error checking position for trade {trade_id}: {e}")
            return False

    def cancel_pending_events(self, trade_id: int) -> Tuple[int, str]:
        """
        Cancel all pending events for a trade (when trade is deleted before processing).

        Uses async write for fast UI response.

        Returns:
            Tuple of (cancelled_count, message)
        """
        try:
            # First get count of pending events
            query = f"""
            SELECT COUNT(*) as cnt
            FROM {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            WHERE trade_id = {trade_id}
            AND status = '{self.STATUS_PENDING}'
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            count = results[0]['cnt'] if results else 0

            if count == 0:
                return 0, "No pending events to cancel"

            # Update pending events to COMPLETED with note (async for fast UI)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_query = f"""
            UPDATE {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            SET status = '{self.STATUS_COMPLETED}',
                processed_at = '{timestamp}',
                error_message = 'Cancelled: Trade was deleted/cancelled before processing'
            WHERE trade_id = {trade_id}
            AND status = '{self.STATUS_PENDING}'
            """

            # Fire-and-forget for fast UI response
            def on_failure(success: bool):
                if not success:
                    logger.error(f"CRITICAL: Failed to cancel pending events for trade {trade_id}")

            impala_manager.execute_write_async(update_query, database=self.DATABASE, callback=on_failure)
            logger.info(f"Cancelled {count} pending events for trade {trade_id} (async)")
            return count, f"Cancelled {count} pending events"

        except Exception as e:
            logger.error(f"Error cancelling pending events for trade {trade_id}: {e}")
            return 0, str(e)


# Singleton instance
trade_event_queue_service = TradeEventQueueService()
