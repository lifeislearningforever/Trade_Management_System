"""
Position Queue Service - Async Background Processing for AVP

Phase 3: Async background processing with:
- Queue-based position calculation (decouple from trade save)
- Background worker with retry logic
- SLA: < 5 minutes from trade save to position update
- Error handling and dead letter queue

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
import threading
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import uuid

from core.repositories.impala_connection import impala_manager
from trade.services.position_service import position_service, PositionService
from core.notifications import notify_user, notify_admins
from core.notifications.constants import (
    EVT_AVP_PROCESSING, EVT_AVP_COMPLETED, EVT_AVP_FAILED,
    EVT_AVP_DEAD_LETTER, EVT_AVP_SLA_BREACH,
)

logger = logging.getLogger(__name__)


class PositionQueueService:
    """
    Async queue service for position calculation.

    Features:
    - Decouples position calculation from trade save
    - Background worker processes queue
    - Retry logic for failed items (max 3 retries)
    - SLA monitoring (< 5 minutes)
    - Dead letter queue for permanent failures
    """

    DATABASE = 'gmp_cis'
    QUEUE_TABLE = 'cis_position_queue'

    # Queue status
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_DEAD_LETTER = 'DEAD_LETTER'

    # Configuration
    MAX_RETRIES = 3
    BATCH_SIZE = 100
    POLL_INTERVAL = 10  # seconds
    SLA_SECONDS = 300  # 5 minutes

    def __init__(self, position_svc: PositionService = None):
        """Initialize queue service."""
        self.position_service = position_svc or position_service
        self._worker_running = False
        self._worker_thread = None
        self._in_memory_queue = Queue()
        self._executor = ThreadPoolExecutor(max_workers=4)

    # =========================================================================
    # QUEUE PRODUCER (Called by Trade Service)
    # =========================================================================

    def enqueue_position_calculation(
        self,
        trade_id: int,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        settle_date: str,
        queued_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        use_db_queue: bool = True,
        chain_recalc_metadata: str = None,
        position_basis: str = 'TRADE_DATE',
        position_date: str = None,
        deal_number: str = ''
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Add trade to position calculation queue.

        Args:
            trade_id: Trade ID
            portfolio_id: Portfolio short name
            security_id: Security label
            trade_type: BUY or SELL
            quantity: Trade quantity
            price: Trade price
            charges: Total charges
            settle_date: Settlement date
            queued_by: User who queued
            use_db_queue: If True, persist to database. If False, use in-memory queue.

        Returns:
            Tuple of (success, message, queue_id)
        """
        try:
            queue_id = self._generate_id()
            timestamp = datetime.now()

            # position_date: the actual date for this position record.
            # For TRADE_DATE basis: position_date = trade_date (passed by caller)
            # For SETTLE_DATE basis: position_date = settle_date (default)
            effective_position_date = position_date or settle_date

            queue_item = {
                'queue_id': queue_id,
                'trade_id': trade_id,
                'deal_number': deal_number,
                'portfolio_id': portfolio_id,
                'security_id': security_id,
                'trade_type': trade_type,
                'quantity': float(quantity),
                'price': float(price),
                'charges': float(charges),
                'settle_date': settle_date,
                'position_date': effective_position_date,
                'position_basis': position_basis,
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'status': self.STATUS_PENDING,
                'retry_count': 0,
                'queued_at': timestamp,
                'queued_by': queued_by,
                'error_message': chain_recalc_metadata  # CHAIN_RECALC metadata for backdated trades
            }

            if use_db_queue:
                # Persist to database queue
                success = self._insert_queue_item(queue_item)
            else:
                # Use in-memory queue (faster, but not persistent)
                self._in_memory_queue.put(queue_item)
                success = True

            if success:
                logger.info(f"Enqueued position calculation for trade {trade_id} (queue_id={queue_id})")
                return True, f"Position calculation queued (ID: {queue_id})", queue_id
            else:
                return False, "Failed to enqueue position calculation", None

        except Exception as e:
            logger.error(f"Error enqueueing position calculation: {str(e)}")
            return False, f"Queue error: {str(e)}", None

    def _insert_queue_item(self, item: Dict[str, Any]) -> bool:
        """Insert queue item into database."""
        try:
            timestamp = item['queued_at'].strftime('%Y-%m-%d %H:%M:%S')
            processing_date = item['queued_at'].strftime('%Y%m%d')

            # Cast decimal values to avoid precision errors
            quantity = f"CAST({item['quantity']} AS DECIMAL(30,8))"
            price = f"CAST({item['price']} AS DECIMAL(30,8))"
            charges = f"CAST({item['charges']} AS DECIMAL(30,8))"

            # Include error_message for CHAIN_RECALC metadata (for backdated trades)
            error_message = item.get('error_message')
            error_message_sql = f"'{self._escape(error_message)}'" if error_message else 'NULL'

            position_basis = item.get('position_basis', 'TRADE_DATE')
            position_date = item.get('position_date') or item['settle_date']

            query = f"""
            INSERT INTO {self.DATABASE}.{self.QUEUE_TABLE}
            (queue_id, trade_id, portfolio_id, security_id, trade_type,
             quantity, price, charges, settle_date, position_date, position_basis,
             security_currency, portfolio_currency, isin, security_name,
             status, retry_count, queued_at, queued_by, processing_date, error_message)
            VALUES (
                {item['queue_id']}, {item['trade_id']},
                '{self._escape(item['portfolio_id'])}',
                '{self._escape(item['security_id'])}',
                '{item['trade_type']}',
                {quantity}, {price}, {charges},
                '{item['settle_date']}',
                '{position_date}',
                '{position_basis}',
                {self._null_or_str(item.get('security_currency'))},
                {self._null_or_str(item.get('portfolio_currency'))},
                {self._null_or_str(item.get('isin'))},
                {self._null_or_str(item.get('security_name'))},
                '{self.STATUS_PENDING}', CAST(0 AS INT),
                '{timestamp}', '{self._escape(item['queued_by'])}',
                '{processing_date}', {error_message_sql}
            )
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error inserting queue item: {str(e)}")
            return False

    # =========================================================================
    # QUEUE CONSUMER (Background Worker)
    # =========================================================================

    def start_worker(self):
        """Start the background worker thread."""
        if self._worker_running:
            logger.warning("Worker is already running")
            return

        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Position queue worker started")

    def stop_worker(self):
        """Stop the background worker thread."""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=30)
        logger.info("Position queue worker stopped")

    def _worker_loop(self):
        """Main worker loop - continuously process queue items."""
        logger.info("Worker loop started")

        while self._worker_running:
            try:
                # Process database queue
                processed = self._process_batch()

                # Process in-memory queue
                self._process_in_memory_queue()

                # Sleep if no items were processed
                if processed == 0:
                    time.sleep(self.POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")
                time.sleep(self.POLL_INTERVAL)

    def _process_batch(self) -> int:
        """Process a batch of pending items from database queue."""
        try:
            pending = self.get_pending_items(limit=self.BATCH_SIZE)

            if not pending:
                return 0

            logger.info(f"Processing batch of {len(pending)} items")

            for item in pending:
                self._process_item(item)

            return len(pending)

        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")
            return 0

    def _process_in_memory_queue(self):
        """Process items from in-memory queue."""
        processed = 0
        while not self._in_memory_queue.empty() and processed < self.BATCH_SIZE:
            try:
                item = self._in_memory_queue.get_nowait()
                self._process_item(item, is_db_queue=False)
                processed += 1
            except Empty:
                break
            except Exception as e:
                logger.error(f"Error processing in-memory item: {str(e)}")

    def _process_item(self, item: Dict[str, Any], is_db_queue: bool = True):
        """Process a single queue item."""
        queue_id = item.get('queue_id')
        trade_id = item.get('trade_id')

        try:
            # Mark as processing
            if is_db_queue:
                self._update_status(queue_id, self.STATUS_PROCESSING)

            queued_by = item.get('queued_by', '')
            deal_number = item.get('deal_number') or str(trade_id)
            _notif_base = {
                'queue_id':    queue_id,
                'trade_id':    trade_id,
                'deal_number': deal_number,
                'portfolio':   item.get('portfolio_id', ''),
                'security':    item.get('security_name') or item.get('security_id', ''),
                'isin':        item.get('isin', ''),
                'position_basis': item.get('position_basis', 'TRADE_DATE'),
            }

            # Notify user: AVP processing started
            notify_user(queued_by, EVT_AVP_PROCESSING, {
                **_notif_base,
                'message': f'AVP calculation started for trade {deal_number}',
            })

            # Check SLA
            queued_at = item.get('queued_at')
            elapsed = 0
            if queued_at:
                if isinstance(queued_at, str):
                    queued_at = datetime.strptime(queued_at, '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - queued_at).total_seconds()
                if elapsed > self.SLA_SECONDS:
                    logger.warning(
                        f"SLA breach for queue_id={queue_id}: {elapsed:.0f}s > {self.SLA_SECONDS}s"
                    )
                    notify_user(queued_by, EVT_AVP_SLA_BREACH, {
                        **_notif_base,
                        'elapsed_seconds': int(elapsed),
                        'sla_seconds': self.SLA_SECONDS,
                        'message': f'AVP SLA breach: trade {deal_number} waiting {int(elapsed)}s (SLA={self.SLA_SECONDS}s)',
                    })
                    notify_admins(EVT_AVP_SLA_BREACH, {
                        **_notif_base,
                        'queued_by': queued_by,
                        'elapsed_seconds': int(elapsed),
                        'sla_seconds': self.SLA_SECONDS,
                        'message': f'AVP SLA breach: queue_id={queue_id} trade={deal_number} user={queued_by} elapsed={int(elapsed)}s',
                    })

            # Check if this is a backdated trade requiring chain recalculation
            # error_message field may contain:
            # 1. CHAIN_RECALC metadata (original)
            # 2. Error message from previous retry (check for embedded CHAIN_RECALC)
            # 3. Combined: "Previous error. CHAIN_RECALC:..." or "Max retries exceeded. Last error: ..."
            error_message = item.get('error_message', '') or ''
            logger.info(f"Processing queue item: trade_id={trade_id}, error_message='{error_message}'")
            chain_recalc_info = self._parse_chain_recalc_metadata(error_message)

            # For BACKDATED trades: Skip individual calculation, let chain recalculation handle ALL trades
            # This avoids the issue of creating a position that gets immediately deleted
            if chain_recalc_info:
                logger.info(f"Parsed chain_recalc_info: {chain_recalc_info}")
                logger.info(
                    f"Backdated trade detected for queue_id={queue_id}, trade_id={trade_id}. "
                    f"Using chain recalculation from {chain_recalc_info['from_date']}"
                )
                recalc_result = self._process_chain_recalculation(chain_recalc_info)

                # Check for errors first
                if recalc_result['errors'] > 0:
                    self._handle_failure(
                        item,
                        f"Chain recalculation had {recalc_result['errors']} errors",
                        is_db_queue
                    )
                    return

                # Check if any positions were actually recalculated
                if recalc_result['recalculated'] == 0:
                    # No trades found - this is an error condition
                    self._handle_failure(
                        item,
                        f"No trades found for chain recalculation from {chain_recalc_info['from_date']}. "
                        f"Portfolio={chain_recalc_info['portfolio_id']}, Security={chain_recalc_info['security_id']}",
                        is_db_queue
                    )
                    return

                # Success - positions were recalculated
                if is_db_queue:
                    self._update_status(queue_id, self.STATUS_COMPLETED)
                logger.info(
                    f"Successfully processed backdated trade queue_id={queue_id}, "
                    f"recalculated {recalc_result['recalculated']} positions"
                )
                notify_user(queued_by, EVT_AVP_COMPLETED, {
                    **_notif_base,
                    'recalculated': recalc_result['recalculated'],
                    'elapsed_seconds': int(elapsed),
                    'message': (
                        f'AVP complete (backdated): {recalc_result["recalculated"]} position(s) '
                        f'recalculated for trade {deal_number}'
                    ),
                })
                return

            # For T+0 / TRADE_DATE basis: Calculate position directly
            # position_date comes from queue (trade_date for TRADE_DATE basis,
            # settle_date for SETTLE_DATE basis)
            position_basis = item.get('position_basis', 'TRADE_DATE')
            position_date = item.get('position_date') or item['settle_date']

            success, message, position = self.position_service.calculate_position(
                portfolio_id=item['portfolio_id'],
                security_id=item['security_id'],
                trade_type=item['trade_type'],
                quantity=Decimal(str(item['quantity'])),
                price=Decimal(str(item['price'])),
                charges=Decimal(str(item.get('charges', 0) or 0)),
                position_date=position_date,
                trade_id=trade_id,
                updated_by='SYSTEM',
                security_currency=item.get('security_currency'),
                portfolio_currency=item.get('portfolio_currency'),
                isin=item.get('isin'),
                security_name=item.get('security_name'),
                position_basis=position_basis
            )

            if success:
                if is_db_queue:
                    self._update_status(queue_id, self.STATUS_COMPLETED)
                logger.info(f"Successfully processed queue_id={queue_id}, trade_id={trade_id}")
                notify_user(queued_by, EVT_AVP_COMPLETED, {
                    **_notif_base,
                    'elapsed_seconds': int(elapsed),
                    'message': f'AVP calculation complete for trade {deal_number}',
                })
            else:
                self._handle_failure(item, message, is_db_queue)

        except Exception as e:
            logger.error(f"Error processing queue_id={queue_id}: {str(e)}")
            self._handle_failure(item, str(e), is_db_queue)

    def _parse_chain_recalc_metadata(self, metadata: str) -> Optional[Dict[str, str]]:
        """
        Parse chain recalculation metadata from error_message field.
        Supports two formats:
        - Colon format: CHAIN_RECALC:portfolio_id:security_id:from_date
        - Space format: CHAIN_RECALC portfolio_id security_id from_date
        """
        if not metadata or not metadata.startswith('CHAIN_RECALC'):
            return None

        try:
            # Try colon format first (preferred)
            if metadata.startswith('CHAIN_RECALC:'):
                parts = metadata.split(':')
                if len(parts) >= 4:
                    return {
                        'portfolio_id': parts[1],
                        'security_id': parts[2],
                        'from_date': parts[3]
                    }

            # Try space format (legacy/alternate)
            # Format: CHAIN_RECALC portfolio_id security_id from_date
            parts = metadata.split()
            if len(parts) >= 4 and parts[0] == 'CHAIN_RECALC':
                return {
                    'portfolio_id': parts[1],
                    'security_id': parts[2],
                    'from_date': parts[3]
                }

            logger.warning(f"Could not parse CHAIN_RECALC metadata: {metadata}")
        except Exception as e:
            logger.error(f"Error parsing CHAIN_RECALC metadata '{metadata}': {e}")

        return None

    def _process_chain_recalculation(self, chain_info: Dict[str, str]) -> Dict[str, int]:
        """
        Recalculate position chain for backdated trades.

        This handles the scenario where a user enters a backdated trade that affects
        subsequent positions. For example:
        - T1 entered on 5th March (settle 5th March) - Position: qty=100, avg=130
        - T3 entered on 5th March (settle 3rd March - BACKDATED) - Must recalculate T1

        Steps:
        1. Get position BEFORE the backdated date (base position)
        2. Get ALL trades from backdated date onwards (including the backdated trade)
        3. Delete existing position versions from backdated date onwards
        4. Recalculate all positions in chronological order
        """
        counters = {'recalculated': 0, 'errors': 0, 'deleted': 0}

        try:
            portfolio_id = chain_info['portfolio_id']
            security_id = chain_info['security_id']
            from_date_raw = chain_info['from_date']
            today = datetime.now().date()

            # Normalize from_date to YYYY-MM-DD format
            # Handle various formats: YYYY-MM-DD, YYYYMMDD, or datetime string
            from_date = from_date_raw
            if len(from_date_raw) == 8 and from_date_raw.isdigit():
                # YYYYMMDD format
                from_date = f"{from_date_raw[:4]}-{from_date_raw[4:6]}-{from_date_raw[6:8]}"
            elif 'T' in from_date_raw:
                # ISO format with time
                from_date = from_date_raw.split('T')[0]
            # Else assume already YYYY-MM-DD

            logger.info(
                f"Chain recalc: from_date_raw='{from_date_raw}', normalized='{from_date}'"
            )

            logger.info(
                f"Starting chain recalculation for {portfolio_id}/{security_id} "
                f"from {from_date} to {today}"
            )

            # VERSION-BASED APPROACH: No deletes, create new versions
            # The position_service._save_position() method will:
            # 1. Mark existing versions for each date as is_latest=false
            # 2. Insert new version with is_latest=true
            # This maintains full audit trail

            # Step 1: Get ALL trades from backdated date onwards (>= not >)
            # This INCLUDES the backdated trade itself
            # Note: security_currency, portfolio_currency, isin, etc. are NOT in cis_trade table
            today_str = today.strftime("%Y-%m-%d")
            query = f"""
            SELECT trade_id, trade_type, quantity, price,
                   COALESCE(commission, 0) + COALESCE(sec_fee, 0) + COALESCE(other_charges, 0) as charges,
                   settle_date
            FROM {self.DATABASE}.cis_trade
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND settle_date >= '{from_date}'
              AND settle_date <= '{today_str}'
              AND (trade_status IN ('INITIAL', 'VALIDATED', 'SETTLED') OR status IN ('INITIAL', 'VALIDATED', 'SETTLED'))
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY settle_date ASC, trade_id ASC
            """

            logger.info(
                f"Chain recalc query: portfolio={portfolio_id}, security={security_id}, "
                f"from_date={from_date}, to_date={today_str}"
            )
            logger.info(f"CHAIN_RECALC QUERY: {query}")

            trades = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Found {len(trades) if trades else 0} trades for chain recalculation")

            if trades:
                for t in trades:
                    logger.info(f"  Trade found: id={t.get('trade_id')}, settle_date={t.get('settle_date')}, type={t.get('trade_type')}")

            if trades:
                logger.info(f"Recalculating {len(trades)} trades (both bases) from {from_date} to {today}")

                for trade in trades:
                    trade_date = trade.get('trade_date') or trade['settle_date']

                    # Recalculate BOTH position bases per trade so each chain stays correct.
                    # TRADE_DATE basis uses trade_date as position_date.
                    # SETTLE_DATE basis uses settle_date as position_date.
                    for basis, pos_date in [
                        ('TRADE_DATE', trade_date),
                        ('SETTLE_DATE', trade['settle_date'])
                    ]:
                        try:
                            success, msg, _ = self.position_service.calculate_position(
                                portfolio_id=portfolio_id,
                                security_id=security_id,
                                trade_type=trade['trade_type'],
                                quantity=Decimal(str(trade['quantity'])),
                                price=Decimal(str(trade['price'])),
                                charges=Decimal(str(trade.get('charges', 0) or 0)),
                                position_date=pos_date,
                                trade_id=trade['trade_id'],
                                updated_by='SYSTEM',
                                security_currency=trade.get('security_currency'),
                                portfolio_currency=trade.get('portfolio_currency'),
                                isin=trade.get('isin'),
                                security_name=trade.get('security_name'),
                                custodian=trade.get('custodian'),
                                sub_custodian=trade.get('sub_custodian'),
                                is_chain_recalc=True,
                                position_basis=basis
                            )

                            if success:
                                counters['recalculated'] += 1
                                logger.info(
                                    f"Recalculated trade {trade['trade_id']} "
                                    f"basis={basis} date={pos_date}"
                                )
                            else:
                                counters['errors'] += 1
                                logger.error(
                                    f"Failed to recalculate trade {trade['trade_id']} "
                                    f"basis={basis}: {msg}"
                                )

                        except Exception as e:
                            logger.error(
                                f"Error recalculating trade {trade['trade_id']} basis={basis}: {str(e)}"
                            )
                            counters['errors'] += 1
            else:
                logger.warning(f"No trades found for recalculation from {from_date}")

            logger.info(
                f"Chain recalculation complete: {counters['recalculated']} recalculated, "
                f"{counters['errors']} errors"
            )
            return counters

        except Exception as e:
            logger.error(f"Error in chain recalculation: {str(e)}")
            return counters

    def _handle_failure(self, item: Dict[str, Any], error_message: str, is_db_queue: bool = True):
        """Handle failed processing with retry logic."""
        queue_id  = item.get('queue_id')
        trade_id  = item.get('trade_id')
        deal_number = item.get('deal_number') or str(trade_id)
        queued_by = item.get('queued_by', '')
        retry_count = item.get('retry_count', 0)

        _notif_base = {
            'queue_id':   queue_id,
            'trade_id':   trade_id,
            'deal_number': deal_number,
            'portfolio':  item.get('portfolio_id', ''),
            'security':   item.get('security_name') or item.get('security_id', ''),
            'isin':       item.get('isin', ''),
        }

        if retry_count < self.MAX_RETRIES:
            # Retry later
            if is_db_queue:
                self._update_status(
                    queue_id, self.STATUS_PENDING,
                    error_message=error_message,
                    increment_retry=True
                )
            else:
                item['retry_count'] = retry_count + 1
                self._in_memory_queue.put(item)

            logger.warning(
                f"Queue item {queue_id} failed, will retry. "
                f"Retry {retry_count + 1}/{self.MAX_RETRIES}"
            )
            notify_user(queued_by, EVT_AVP_FAILED, {
                **_notif_base,
                'error': error_message,
                'retry': retry_count + 1,
                'max_retries': self.MAX_RETRIES,
                'message': (
                    f'AVP failed for trade {deal_number} — retrying '
                    f'({retry_count + 1}/{self.MAX_RETRIES})'
                ),
            })
        else:
            # Move to dead letter queue
            if is_db_queue:
                self._update_status(
                    queue_id, self.STATUS_DEAD_LETTER,
                    error_message=f"Max retries exceeded. Last error: {error_message}"
                )
            logger.error(
                f"Queue item {queue_id} moved to dead letter queue after {self.MAX_RETRIES} retries"
            )
            notify_user(queued_by, EVT_AVP_DEAD_LETTER, {
                **_notif_base,
                'error': error_message,
                'message': (
                    f'AVP permanently failed for trade {deal_number} after '
                    f'{self.MAX_RETRIES} retries — requires manual intervention'
                ),
            })
            notify_admins(EVT_AVP_DEAD_LETTER, {
                **_notif_base,
                'queued_by': queued_by,
                'error': error_message,
                'message': (
                    f'Dead letter: queue_id={queue_id} trade={deal_number} '
                    f'user={queued_by} — {error_message[:200]}'
                ),
            })

    # =========================================================================
    # QUEUE MANAGEMENT
    # =========================================================================

    def get_pending_items(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending items from database queue."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.QUEUE_TABLE}
            WHERE status = '{self.STATUS_PENDING}'
            ORDER BY queued_at ASC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting pending items: {str(e)}")
            return []

    def _update_status(
        self,
        queue_id: int,
        status: str,
        error_message: str = None,
        increment_retry: bool = False
    ) -> bool:
        """Update queue item status."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [f"status = '{status}'", f"updated_at = '{timestamp}'"]

            if error_message:
                set_clauses.append(f"error_message = '{self._escape(error_message)}'")

            if status in [self.STATUS_COMPLETED, self.STATUS_FAILED, self.STATUS_DEAD_LETTER]:
                set_clauses.append(f"processed_at = '{timestamp}'")

            if increment_retry:
                set_clauses.append("retry_count = CAST(retry_count + 1 AS INT)")

            query = f"""
            UPDATE {self.DATABASE}.{self.QUEUE_TABLE}
            SET {', '.join(set_clauses)}
            WHERE queue_id = {queue_id}
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error updating queue status: {str(e)}")
            return False

    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            query = f"""
            SELECT
                status,
                COUNT(*) as count,
                AVG(retry_count) as avg_retries
            FROM {self.DATABASE}.{self.QUEUE_TABLE}
            GROUP BY status
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            stats = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0,
                'dead_letter': 0,
                'total': 0
            }

            if results:
                for row in results:
                    status = row.get('status', '').lower().replace('_', '')
                    if status == 'deadletter':
                        status = 'dead_letter'
                    count = row.get('count', 0)
                    stats[status] = count
                    stats['total'] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting queue statistics: {str(e)}")
            return {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'dead_letter': 0, 'total': 0}

    def retry_failed_items(self) -> Dict[str, int]:
        """Retry all failed items including those that hit max retries."""
        try:
            query = f"""
            UPDATE {self.DATABASE}.{self.QUEUE_TABLE}
            SET status = '{self.STATUS_PENDING}',
                retry_count = 0,
                error_message = NULL,
                updated_at = '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'
            WHERE status = '{self.STATUS_FAILED}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            return {'retried': 1 if success else 0}

        except Exception as e:
            logger.error(f"Error retrying failed items: {str(e)}")
            return {'retried': 0}

    def purge_completed(self, days_old: int = 7) -> Dict[str, int]:
        """Purge completed items older than specified days."""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_old)).strftime('%Y-%m-%d')

            query = f"""
            DELETE FROM {self.DATABASE}.{self.QUEUE_TABLE}
            WHERE status = '{self.STATUS_COMPLETED}'
              AND processed_at < '{cutoff_date}'
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            return {'purged': 1 if success else 0}

        except Exception as e:
            logger.error(f"Error purging completed items: {str(e)}")
            return {'purged': 0}

    # =========================================================================
    # SYNCHRONOUS PROCESSING (for testing/immediate needs)
    # =========================================================================

    def process_immediately(
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
        position_basis: str = 'TRADE_DATE',
        position_date: str = None,
        **kwargs
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Process position calculation immediately (synchronous).
        Use this when you need immediate results.
        """
        return self.position_service.calculate_position(
            portfolio_id=portfolio_id,
            security_id=security_id,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            charges=charges,
            position_date=position_date or settle_date,
            trade_id=trade_id,
            updated_by=updated_by,
            security_currency=kwargs.get('security_currency'),
            portfolio_currency=kwargs.get('portfolio_currency'),
            isin=kwargs.get('isin'),
            security_name=kwargs.get('security_name'),
            position_basis=position_basis
        )

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self) -> int:
        """Generate unique ID."""
        return int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def _escape(self, value: str) -> str:
        """Escape string for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")

    def _null_or_str(self, value: str) -> str:
        """Return NULL or quoted string."""
        if value is None or value == '':
            return 'NULL'
        return f"'{self._escape(value)}'"


# Need to import timedelta
from datetime import timedelta

# Singleton instance
position_queue_service = PositionQueueService()
