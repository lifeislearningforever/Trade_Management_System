"""
Circuit Breaker Pattern for Audit Logging

Prevents cascading failures when Kudu is unavailable.
Implements the standard circuit breaker pattern with three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, requests fail fast
- HALF_OPEN: Testing if service recovered

Author: CisTrade Team
Last Updated: 2026-01-25
"""

import threading
import time
import logging
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"       # Normal - allowing requests
    OPEN = "OPEN"           # Tripped - failing fast
    HALF_OPEN = "HALF_OPEN" # Testing - allowing limited requests


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for protecting against cascading failures.

    When failures exceed the threshold, the circuit "opens" and fails fast
    for a recovery period. After the recovery timeout, it enters "half-open"
    state to test if the service has recovered.

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        if breaker.can_execute():
            try:
                result = risky_operation()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
        else:
            # Use fallback
            fallback_operation()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        name: str = "default"
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying again (half-open)
            success_threshold: Consecutive successes needed to close circuit
            name: Name for logging purposes
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.time()
        self._lock = threading.Lock()

        # Statistics
        self._total_failures = 0
        self._total_successes = 0
        self._times_opened = 0

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self.state == CircuitState.OPEN

    def can_execute(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns:
            True if request should proceed, False if should fail fast
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            elif self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self._last_failure_time is None:
                    return True

                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # Transition to half-open
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    self._last_state_change = time.time()
                    logger.info(
                        f"CircuitBreaker '{self.name}' transitioning to HALF_OPEN "
                        f"after {elapsed:.1f}s recovery timeout"
                    )
                    return True
                return False

            else:  # HALF_OPEN
                # Allow limited requests to test recovery
                return True

    def record_success(self):
        """Record a successful execution."""
        with self._lock:
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Service recovered, close circuit
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._last_state_change = time.time()
                    logger.info(
                        f"CircuitBreaker '{self.name}' CLOSED after "
                        f"{self._success_count} consecutive successes"
                    )

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self):
        """Record a failed execution."""
        with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failed during test, reopen circuit
                self._state = CircuitState.OPEN
                self._last_state_change = time.time()
                logger.warning(
                    f"CircuitBreaker '{self.name}' reopened (failed in HALF_OPEN state)"
                )

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Threshold exceeded, open circuit
                    self._state = CircuitState.OPEN
                    self._times_opened += 1
                    self._last_state_change = time.time()
                    logger.warning(
                        f"CircuitBreaker '{self.name}' OPENED after "
                        f"{self._failure_count} failures (total opens: {self._times_opened})"
                    )

    def reset(self):
        """Manually reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_state_change = time.time()
            logger.info(f"CircuitBreaker '{self.name}' manually reset to CLOSED")

    def get_stats(self) -> dict:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary with circuit breaker stats
        """
        with self._lock:
            return {
                'name': self.name,
                'state': self._state.value,
                'failure_count': self._failure_count,
                'success_count': self._success_count,
                'total_failures': self._total_failures,
                'total_successes': self._total_successes,
                'times_opened': self._times_opened,
                'last_failure_time': self._last_failure_time,
                'last_state_change': self._last_state_change,
                'time_in_current_state': time.time() - self._last_state_change
            }

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name='{self.name}', state={self._state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
