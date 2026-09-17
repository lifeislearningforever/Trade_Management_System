"""
Performance Monitoring Middleware

Provides request timing, slow query detection, and connection pool health
monitoring for long-running Cloudera applications.

Features:
- Request duration logging (warns if > 5s)
- Periodic connection pool stats logging
- Memory usage tracking
- Slow request identification
"""

import logging
import time
import threading
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)

# Performance thresholds
SLOW_REQUEST_THRESHOLD_MS = 5000  # 5 seconds
POOL_STATS_INTERVAL_SECONDS = 300  # Log pool stats every 5 minutes


class PerformanceMonitoringMiddleware:
    """
    Middleware for performance monitoring in long-running applications.

    Usage:
        Add to MIDDLEWARE in settings.py:
        'core.middleware.performance_middleware.PerformanceMonitoringMiddleware'
    """

    # Class-level state for periodic tasks
    _last_pool_stats_time = 0
    _request_count = 0
    _slow_request_count = 0
    _total_request_time_ms = 0
    _lock = threading.Lock()

    def __init__(self, get_response):
        self.get_response = get_response
        # Log startup
        logger.info("[PERF] Performance monitoring middleware initialized")

    def __call__(self, request):
        # Start timing
        start_time = time.time()

        # Process request
        response = self.get_response(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Update stats
        with self._lock:
            PerformanceMonitoringMiddleware._request_count += 1
            PerformanceMonitoringMiddleware._total_request_time_ms += duration_ms

            if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
                PerformanceMonitoringMiddleware._slow_request_count += 1

        # Log slow requests
        if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
            self._log_slow_request(request, duration_ms)

        # Add timing header for debugging
        response['X-Request-Duration-Ms'] = f'{duration_ms:.2f}'

        # Periodic pool stats logging
        self._maybe_log_pool_stats()

        return response

    def _log_slow_request(self, request, duration_ms):
        """Log details about slow requests."""
        user = request.session.get('user_login', 'anonymous')
        path = request.path
        method = request.method

        logger.warning(
            f"[PERF] SLOW REQUEST: {method} {path} took {duration_ms:.0f}ms "
            f"(threshold: {SLOW_REQUEST_THRESHOLD_MS}ms) user={user}"
        )

        # Log additional context for POST requests (potential trade creation)
        if method == 'POST' and '/trade/' in path:
            logger.warning(
                f"[PERF] Trade POST details: path={path}, "
                f"content_length={request.META.get('CONTENT_LENGTH', 0)}"
            )

    def _maybe_log_pool_stats(self):
        """Periodically log connection pool statistics."""
        current_time = time.time()

        with self._lock:
            time_since_last = current_time - PerformanceMonitoringMiddleware._last_pool_stats_time

            if time_since_last >= POOL_STATS_INTERVAL_SECONDS:
                PerformanceMonitoringMiddleware._last_pool_stats_time = current_time
                self._log_pool_stats()

    def _log_pool_stats(self):
        """Log connection pool and application statistics."""
        try:
            from core.repositories.impala_connection import impala_manager

            # Get pool stats
            stats = impala_manager.get_pool_stats()

            # Calculate averages
            avg_request_time = 0
            if PerformanceMonitoringMiddleware._request_count > 0:
                avg_request_time = (
                    PerformanceMonitoringMiddleware._total_request_time_ms /
                    PerformanceMonitoringMiddleware._request_count
                )

            logger.info(
                f"[PERF] Pool Stats: "
                f"active={stats.get('active_connections', 0)}/{stats.get('pool_size', 0)}, "
                f"available={stats.get('pool_available', 0)}, "
                f"utilization={stats.get('pool_utilization_pct', 0):.1f}%, "
                f"reuse={stats.get('connection_reuse_count', 0)}, "
                f"creates={stats.get('connection_create_count', 0)}, "
                f"validation_skips={stats.get('validation_skip_count', 0)}, "
                f"validation_pings={stats.get('validation_ping_count', 0)}"
            )

            logger.info(
                f"[PERF] Request Stats: "
                f"total={PerformanceMonitoringMiddleware._request_count}, "
                f"slow={PerformanceMonitoringMiddleware._slow_request_count}, "
                f"avg_time={avg_request_time:.0f}ms"
            )

            # Log async queue stats
            async_queue_size = stats.get('async_queue_size', 0)
            if async_queue_size > 0:
                logger.info(f"[PERF] Async queue size: {async_queue_size}")

            # Check for pool exhaustion warning
            utilization = stats.get('pool_utilization_pct', 0)
            if utilization > 80:
                logger.warning(
                    f"[PERF] HIGH POOL UTILIZATION: {utilization:.1f}% "
                    f"({stats.get('active_connections', 0)}/{stats.get('pool_size', 0)})"
                )

            # Recycle idle connections for long-running apps
            impala_manager.recycle_idle_connections(max_idle_seconds=300)

        except Exception as e:
            logger.error(f"[PERF] Error logging pool stats: {e}")

    @classmethod
    def get_stats_summary(cls) -> dict:
        """Get current performance statistics (for health check endpoints)."""
        with cls._lock:
            avg_request_time = 0
            if cls._request_count > 0:
                avg_request_time = cls._total_request_time_ms / cls._request_count

            return {
                'request_count': cls._request_count,
                'slow_request_count': cls._slow_request_count,
                'avg_request_time_ms': round(avg_request_time, 2),
                'slow_request_pct': round(
                    (cls._slow_request_count / cls._request_count * 100)
                    if cls._request_count > 0 else 0, 2
                )
            }

    @classmethod
    def reset_stats(cls):
        """Reset performance counters (call periodically for fresh metrics)."""
        with cls._lock:
            cls._request_count = 0
            cls._slow_request_count = 0
            cls._total_request_time_ms = 0
            logger.info("[PERF] Performance stats reset")
