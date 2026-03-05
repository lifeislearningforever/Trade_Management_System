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
        use_db_queue: bool = True
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

            queue_item = {
                'queue_id': queue_id,
                'trade_id': trade_id,
                'portfolio_id': portfolio_id,
                'security_id': security_id,
                'trade_type': trade_type,
                'quantity': float(quantity),
                'price': float(price),
                'charges': float(charges),
                'settle_date': settle_date,
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'status': self.STATUS_PENDING,
                'retry_count': 0,
                'queued_at': timestamp,
                'queued_by': queued_by
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

            query = f"""
            INSERT INTO {self.DATABASE}.{self.QUEUE_TABLE}
            (queue_id, trade_id, portfolio_id, security_id, trade_type,
             quantity, price, charges, settle_date,
             security_currency, portfolio_currency, isin, security_name,
             status, retry_count, queued_at, queued_by, processing_date)
            VALUES (
                {item['queue_id']}, {item['trade_id']},
                '{self._escape(item['portfolio_id'])}',
                '{self._escape(item['security_id'])}',
                '{item['trade_type']}',
                {item['quantity']}, {item['price']}, {item['charges']},
                '{item['settle_date']}',
                {self._null_or_str(item.get('security_currency'))},
                {self._null_or_str(item.get('portfolio_currency'))},
                {self._null_or_str(item.get('isin'))},
                {self._null_or_str(item.get('security_name'))},
                '{self.STATUS_PENDING}', 0,
                '{timestamp}', '{self._escape(item['queued_by'])}',
                '{processing_date}'
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

            # Check SLA
            queued_at = item.get('queued_at')
            if queued_at:
                if isinstance(queued_at, str):
                    queued_at = datetime.strptime(queued_at, '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - queued_at).total_seconds()
                if elapsed > self.SLA_SECONDS:
                    logger.warning(
                        f"SLA breach for queue_id={queue_id}: {elapsed:.0f}s > {self.SLA_SECONDS}s"
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
                trade_id=trade_id,
                updated_by='SYSTEM',
                security_currency=item.get('security_currency'),
                portfolio_currency=item.get('portfolio_currency'),
                isin=item.get('isin'),
                security_name=item.get('security_name')
            )

            if success:
                if is_db_queue:
                    self._update_status(queue_id, self.STATUS_COMPLETED)
                logger.info(f"Successfully processed queue_id={queue_id}, trade_id={trade_id}")
            else:
                self._handle_failure(item, message, is_db_queue)

        except Exception as e:
            logger.error(f"Error processing queue_id={queue_id}: {str(e)}")
            self._handle_failure(item, str(e), is_db_queue)

    def _handle_failure(self, item: Dict[str, Any], error_message: str, is_db_queue: bool = True):
        """Handle failed processing with retry logic."""
        queue_id = item.get('queue_id')
        retry_count = item.get('retry_count', 0)

        if retry_count < self.MAX_RETRIES:
            # Retry later
            if is_db_queue:
                self._update_status(
                    queue_id, self.STATUS_PENDING,
                    error_message=error_message,
                    increment_retry=True
                )
            else:
                # Re-queue in memory
                item['retry_count'] = retry_count + 1
                self._in_memory_queue.put(item)

            logger.warning(
                f"Queue item {queue_id} failed, will retry. "
                f"Retry {retry_count + 1}/{self.MAX_RETRIES}"
            )
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
                set_clauses.append("retry_count = retry_count + 1")

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
        """Retry all failed items (not dead letter)."""
        try:
            query = f"""
            UPDATE {self.DATABASE}.{self.QUEUE_TABLE}
            SET status = '{self.STATUS_PENDING}',
                updated_at = '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'
            WHERE status = '{self.STATUS_FAILED}'
              AND retry_count < {self.MAX_RETRIES}
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
            position_date=settle_date,
            trade_id=trade_id,
            updated_by=updated_by,
            security_currency=kwargs.get('security_currency'),
            portfolio_currency=kwargs.get('portfolio_currency'),
            isin=kwargs.get('isin'),
            security_name=kwargs.get('security_name')
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
