"""
Async Audit Queue - Thread-Based Asynchronous Audit Logging

This module provides non-blocking audit logging using Python threading.
Perfect for environments where Celery/Redis is not available (like CML).

Features:
- Thread-safe bounded queue (prevents memory exhaustion)
- Multiple worker threads for parallel processing
- Graceful shutdown (processes remaining items before exit)
- Fallback to sync logging on queue full (prevents data loss)
- Production-ready with proper error handling
"""

import threading
import logging
import time
from queue import Queue, Full, Empty
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class AsyncAuditQueue:
    """
    Thread-based async audit queue for non-blocking audit logging.

    Usage:
        # In middleware or service
        if async_audit_queue.enqueue(audit_entry):
            # Audit queued successfully
            pass
        else:
            # Queue full, fallback to sync
            audit_logger.log(audit_entry)
    """

    def __init__(self, max_workers: int = 4, max_queue_size: int = 1000):
        """
        Initialize async audit queue with worker threads.

        Args:
            max_workers: Number of worker threads (default: 4)
            max_queue_size: Maximum queue size (default: 1000)
        """
        self.queue = Queue(maxsize=max_queue_size)
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.workers = []
        self.shutdown_event = threading.Event()
        self.started = False

        # Statistics
        self._processed_count = 0
        self._error_count = 0
        self._fallback_count = 0

        logger.info(f"AsyncAuditQueue initialized (workers: {max_workers}, queue size: {max_queue_size})")

    def start(self):
        """
        Start worker threads.
        Should be called once during application startup.
        """
        if self.started:
            logger.warning("AsyncAuditQueue already started")
            return

        # Start worker threads
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"AuditWorker-{i}",
                daemon=False  # Not daemon - allows graceful shutdown
            )
            worker.start()
            self.workers.append(worker)

        self.started = True
        logger.info(f"AsyncAuditQueue started with {len(self.workers)} workers")

    def enqueue(self, audit_entry) -> bool:
        """
        Enqueue audit entry for async processing.

        Args:
            audit_entry: AuditEntry object to log

        Returns:
            True if enqueued successfully, False if queue is full
        """
        if not self.started:
            logger.warning("AsyncAuditQueue not started, starting now")
            self.start()

        try:
            # Try to put in queue without blocking
            self.queue.put(audit_entry, block=False)
            return True

        except Full:
            # Queue is full - return False to signal fallback to sync
            self._fallback_count += 1
            logger.warning(
                f"Audit queue full ({self.queue.qsize()}/{self.max_queue_size}), "
                f"fallback to sync (total fallbacks: {self._fallback_count})"
            )
            return False

    def _worker_loop(self):
        """
        Worker thread main loop.
        Processes audit entries from the queue until shutdown.
        """
        worker_name = threading.current_thread().name
        logger.info(f"{worker_name} started")

        while not self.shutdown_event.is_set():
            try:
                # Wait for item with timeout to allow checking shutdown event
                try:
                    audit_entry = self.queue.get(timeout=1)
                except Empty:
                    # No item available, check shutdown and loop
                    continue

                # Process audit entry
                try:
                    self._process_audit_entry(audit_entry)
                    self._processed_count += 1

                except Exception as e:
                    self._error_count += 1
                    logger.error(f"{worker_name} error processing audit entry: {str(e)}")
                    logger.exception(e)

                finally:
                    # Mark task as done
                    self.queue.task_done()

            except Exception as e:
                logger.error(f"{worker_name} unexpected error: {str(e)}")
                logger.exception(e)
                # Continue loop to prevent worker death

        logger.info(f"{worker_name} shutting down")

    def _process_audit_entry(self, audit_entry):
        """
        Process a single audit entry.

        Args:
            audit_entry: AuditEntry object to log
        """
        from .audit_logger import get_audit_logger

        # Get audit logger (uses singleton pattern)
        audit_logger = get_audit_logger()

        # Log the entry (uses Impala connection pool)
        success = audit_logger.log(audit_entry)

        if not success:
            logger.error(f"Failed to log audit entry: {audit_entry.action_type.value} by {audit_entry.username}")

    def shutdown(self, timeout: int = 10):
        """
        Gracefully shutdown the queue.

        This method:
        1. Signals workers to stop
        2. Waits for queue to be processed
        3. Joins worker threads

        Args:
            timeout: Maximum seconds to wait for shutdown (default: 10)
        """
        if not self.started:
            return

        logger.info(f"AsyncAuditQueue shutting down (queue size: {self.queue.qsize()})")

        # Signal workers to stop
        self.shutdown_event.set()

        # Wait for queue to be empty (with timeout)
        start_time = time.time()
        while not self.queue.empty() and (time.time() - start_time) < timeout:
            remaining = self.queue.qsize()
            logger.info(f"Waiting for queue to empty ({remaining} items remaining)")
            time.sleep(0.5)

        # Join all worker threads
        for worker in self.workers:
            worker.join(timeout=max(1, timeout // len(self.workers)))

        logger.info(
            f"AsyncAuditQueue shutdown complete "
            f"(processed: {self._processed_count}, errors: {self._error_count}, "
            f"fallbacks: {self._fallback_count})"
        )

        self.started = False

    def get_stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue stats
        """
        return {
            'started': self.started,
            'workers': len(self.workers),
            'queue_size': self.queue.qsize(),
            'max_queue_size': self.max_queue_size,
            'processed_count': self._processed_count,
            'error_count': self._error_count,
            'fallback_count': self._fallback_count,
            'queue_utilization': (self.queue.qsize() / self.max_queue_size) * 100
        }


# Global singleton instance
# Initialized with settings from Django
def _get_queue_config():
    """Get queue configuration from Django settings"""
    return {
        'max_workers': getattr(settings, 'AUDIT_ASYNC_WORKERS', 4),
        'max_queue_size': getattr(settings, 'AUDIT_QUEUE_SIZE', 1000)
    }


# Create singleton instance
_queue_instance: Optional[AsyncAuditQueue] = None


def get_async_audit_queue() -> AsyncAuditQueue:
    """
    Get singleton async audit queue instance.

    Returns:
        AsyncAuditQueue instance
    """
    global _queue_instance

    if _queue_instance is None:
        config = _get_queue_config()
        _queue_instance = AsyncAuditQueue(**config)

    return _queue_instance


# Module-level convenience variable
async_audit_queue = get_async_audit_queue()
