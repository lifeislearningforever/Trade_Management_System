"""
Django-free stand-in for django.core.cache.cache.

A simple thread-safe in-process TTL cache implementing the three methods
actually used by the forked services in this package -- get/set/delete
(system_date_service.py, trade_dropdown_service.py). Each of these
standalone scripts is a short-lived batch process invoked once per
Control-M job, so a per-process, non-persistent cache is equivalent in
effect to Django's LocMemCache for this use case: no cross-process or
cross-run sharing was ever relied upon by the original callers either.
"""
import threading
import time
from typing import Any, Optional


class _SimpleTTLCache:
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            value, expires_at = entry
            if expires_at is not None and time.time() >= expires_at:
                del self._store[key]
                return default
            return value

    def set(self, key: str, value: Any, timeout: Optional[int] = 300) -> None:
        expires_at = (time.time() + timeout) if timeout is not None else None
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


cache = _SimpleTTLCache()
