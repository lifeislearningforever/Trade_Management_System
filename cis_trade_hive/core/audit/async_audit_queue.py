"""
Async Audit Queue - Thread-Based Asynchronous Audit Logging

Enhanced version with:
- Circuit breaker pattern for fault tolerance
- Batch processing for efficiency
- File fallback for reliability
- Comprehensive statistics

Author: CisTrade Team
Last Updated: 2026-01-25
"""

import threading
import logging
import time
from queue import Queue, Full, Empty
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)


class AsyncAuditQueue:
    """
    Thread-based async audit queue with circuit breaker and fallback.

    Features:
    - Non-blocking enqueue (fire and forget)
    - Batch processing for efficiency
    - Circuit breaker for fault tolerance
    - File fallback when Kudu is unavailable
    - Graceful shutdown

    Usage:
        # Enqueue audit entry (non-blocking)
        async_audit_queue.enqueue(audit_data)

        # Check stats
        stats = async_audit_queue.get_stats()
    """

    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 2000,
        batch_size: int = 10,
        batch_timeout: float = 2.0
    ):
        """
        Initialize async audit queue.

        Args:
            max_workers: Number of worker threads
            max_queue_size: Maximum queue size
            batch_size: Number of entries per batch
            batch_timeout: Max seconds to wait before flushing partial batch
        """
        self.queue = Queue(maxsize=max_queue_size)
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        self.workers: List[threading.Thread] = []
        self.shutdown_event = threading.Event()
        self.started = False

        # Circuit breaker and fallback (lazy loaded)
        self._circuit_breaker = None
        self._file_logger = None

        # Statistics
        self._stats = {
            'processed': 0,
            'errors': 0,
            'fallbacks': 0,
            'circuit_open_count': 0,
            'batches_written': 0,
            'queue_full_count': 0
        }
        self._stats_lock = threading.Lock()

        logger.info(
            f"AsyncAuditQueue initialized: workers={max_workers}, "
            f"queue_size={max_queue_size}, batch_size={batch_size}"
        )

    @property
    def circuit_breaker(self):
        """Lazy load circuit breaker."""
        if self._circuit_breaker is None:
            from .circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=getattr(settings, 'AUDIT_CIRCUIT_FAILURE_THRESHOLD', 5),
                recovery_timeout=getattr(settings, 'AUDIT_CIRCUIT_RECOVERY_TIMEOUT', 60),
                success_threshold=getattr(settings, 'AUDIT_CIRCUIT_SUCCESS_THRESHOLD', 2),
                name='audit_kudu'
            )
        return self._circuit_breaker

    @property
    def file_logger(self):
        """Lazy load file logger."""
        if self._file_logger is None:
            from .file_audit_logger import get_file_audit_logger
            self._file_logger = get_file_audit_logger()
        return self._file_logger

    def start(self):
        """Start worker threads."""
        if self.started:
            logger.warning("AsyncAuditQueue already started")
            return

        # Reset shutdown event
        self.shutdown_event.clear()

        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"AuditWorker-{i}",
                daemon=False
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"AuditWorker-{i} started")

        self.started = True
        logger.info(f"AsyncAuditQueue started with {len(self.workers)} workers")

    def enqueue(self, audit_data: Dict[str, Any]) -> bool:
        """
        Enqueue audit entry for async processing (non-blocking).

        Args:
            audit_data: Dictionary with audit entry data

        Returns:
            True if enqueued, False if queue is full
        """
        if not self.started:
            self.start()

        try:
            # Non-blocking put
            self.queue.put(audit_data, block=False)
            return True

        except Full:
            with self._stats_lock:
                self._stats['queue_full_count'] += 1

            logger.warning(
                f"Audit queue full ({self.queue.qsize()}/{self.max_queue_size}), "
                f"using file fallback"
            )

            # Write directly to fallback file
            self._write_to_fallback(audit_data)
            return False

    def _worker_loop(self):
        """Worker thread main loop with batching."""
        worker_name = threading.current_thread().name
        batch: List[Dict[str, Any]] = []
        last_flush_time = time.time()

        while not self.shutdown_event.is_set():
            try:
                # Try to get item with timeout
                try:
                    entry = self.queue.get(timeout=0.5)
                    batch.append(entry)
                    self.queue.task_done()
                except Empty:
                    pass

                # Check if we should flush the batch
                should_flush = (
                    len(batch) >= self.batch_size or
                    (batch and time.time() - last_flush_time >= self.batch_timeout)
                )

                if should_flush and batch:
                    self._process_batch(batch)
                    batch = []
                    last_flush_time = time.time()

            except Exception as e:
                logger.error(f"{worker_name} error: {e}", exc_info=True)

        # Flush remaining entries on shutdown
        if batch:
            logger.info(f"{worker_name} flushing {len(batch)} remaining entries")
            self._process_batch(batch)

        logger.info(f"{worker_name} shutdown complete")

    def _process_batch(self, batch: List[Dict[str, Any]]):
        """Process a batch of audit entries."""
        if not batch:
            return

        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            with self._stats_lock:
                self._stats['circuit_open_count'] += 1
                self._stats['fallbacks'] += len(batch)

            # Circuit is open - use fallback
            for entry in batch:
                self._write_to_fallback(entry)
            return

        # Try to write to Kudu
        try:
            success = self._batch_insert_kudu(batch)

            if success:
                self.circuit_breaker.record_success()
                with self._stats_lock:
                    self._stats['processed'] += len(batch)
                    self._stats['batches_written'] += 1
            else:
                raise Exception("Batch insert returned False")

        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            self.circuit_breaker.record_failure()

            with self._stats_lock:
                self._stats['errors'] += len(batch)
                self._stats['fallbacks'] += len(batch)

            # Fallback to file
            for entry in batch:
                self._write_to_fallback(entry)

    def _batch_insert_kudu(self, batch: List[Dict[str, Any]]) -> bool:
        """
        Batch insert audit entries to Kudu.

        Args:
            batch: List of audit entry dictionaries

        Returns:
            True if successful
        """
        if not batch:
            return True

        try:
            from core.repositories.impala_connection import impala_manager

            # Build multi-row VALUES clause
            values_list = []
            for entry in batch:
                values = self._format_audit_values(entry)
                values_list.append(f"({values})")

            # Single UPSERT with multiple rows
            upsert_query = f"""
            UPSERT INTO gmp_cis.cis_audit_log
            (`audit_id`, `audit_timestamp`, `user_id`, `username`, `action_type`,
             `action_category`, `action_description`, `entity_type`, `entity_id`,
             `entity_name`, `old_value`, `new_value`, `status`, `status_code`,
             `duration_ms`, `audit_date`)
            VALUES {', '.join(values_list)}
            """

            success = impala_manager.execute_write(upsert_query, database='gmp_cis')

            if success:
                logger.debug(f"Batch inserted {len(batch)} audit entries")

            return success

        except Exception as e:
            logger.error(f"Kudu batch insert failed: {e}")
            return False

    def _format_audit_values(self, entry: Dict[str, Any]) -> str:
        """Format audit entry as SQL VALUES string."""
        now = datetime.now()

        # Generate unique audit_id
        audit_id = int(now.timestamp() * 1000) + (uuid.uuid4().int % 1000)

        # Helper to escape strings
        def esc(val):
            if val is None:
                return 'NULL'
            val_str = str(val)
            # Escape backslashes and single quotes
            val_str = val_str.replace("\\", "\\\\").replace("'", "\\'")
            # Truncate long values
            if len(val_str) > 4000:
                val_str = val_str[:4000] + '...[truncated]'
            return f"'{val_str}'"

        return ', '.join([
            str(audit_id),                                          # audit_id
            f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'",               # audit_timestamp
            esc(entry.get('user_id', '0')),                         # user_id
            esc(entry.get('username', 'SYSTEM')),                   # username
            esc(entry.get('action_type', 'UNKNOWN')),               # action_type
            esc(entry.get('action_category', 'DATA')),              # action_category
            esc(entry.get('action_description', '')),               # action_description
            esc(entry.get('entity_type', '')),                      # entity_type
            esc(entry.get('entity_id', '')),                        # entity_id
            esc(entry.get('entity_name', '')),                      # entity_name
            esc(entry.get('old_value')),                            # old_value
            esc(entry.get('new_value')),                            # new_value
            esc(entry.get('status', 'SUCCESS')),                    # status
            str(entry.get('status_code', 200)),                     # status_code
            str(entry.get('duration_ms', 0)),                       # duration_ms
            f"'{now.strftime('%Y-%m-%d')}'"                         # audit_date
        ])

    def _write_to_fallback(self, entry: Dict[str, Any]):
        """Write entry to fallback file."""
        try:
            self.file_logger.log(entry)
        except Exception as e:
            logger.error(f"Failed to write to fallback: {e}")

    def shutdown(self, timeout: int = 10):
        """Gracefully shutdown the queue."""
        if not self.started:
            return

        logger.info(f"AsyncAuditQueue shutting down (queue size: {self.queue.qsize()})")

        # Signal workers to stop
        self.shutdown_event.set()

        # Wait for queue to be empty (with timeout)
        start_time = time.time()
        while not self.queue.empty() and (time.time() - start_time) < timeout:
            remaining = self.queue.qsize()
            logger.info(f"Waiting for queue to empty ({remaining} items)")
            time.sleep(0.5)

        # Join worker threads
        for worker in self.workers:
            worker.join(timeout=max(1, timeout // len(self.workers)))

        stats = self.get_stats()
        logger.info(
            f"AsyncAuditQueue shutdown complete: "
            f"processed={stats['processed']}, errors={stats['errors']}, "
            f"fallbacks={stats['fallbacks']}"
        )

        self.started = False
        self.workers = []

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self._stats_lock:
            stats = dict(self._stats)

        stats['started'] = self.started
        stats['workers'] = len(self.workers)
        stats['queue_size'] = self.queue.qsize()
        stats['max_queue_size'] = self.max_queue_size
        stats['queue_utilization'] = (self.queue.qsize() / self.max_queue_size) * 100

        # Add circuit breaker state
        if self._circuit_breaker:
            stats['circuit_state'] = self.circuit_breaker.state.value
        else:
            stats['circuit_state'] = 'NOT_INITIALIZED'

        # Add file logger stats
        if self._file_logger:
            stats['fallback_files'] = self._file_logger.get_stats()

        return stats


# Singleton instance
_queue_instance: Optional[AsyncAuditQueue] = None


def get_async_audit_queue() -> AsyncAuditQueue:
    """Get singleton async audit queue instance."""
    global _queue_instance

    if _queue_instance is None:
        _queue_instance = AsyncAuditQueue(
            max_workers=getattr(settings, 'AUDIT_ASYNC_WORKERS', 4),
            max_queue_size=getattr(settings, 'AUDIT_QUEUE_SIZE', 2000),
            batch_size=getattr(settings, 'AUDIT_BATCH_SIZE', 10),
            batch_timeout=getattr(settings, 'AUDIT_BATCH_TIMEOUT', 2.0)
        )

    return _queue_instance


# Module-level convenience variable
async_audit_queue = get_async_audit_queue()
