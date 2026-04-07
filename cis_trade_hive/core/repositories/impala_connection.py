"""
Impala/Kudu Connection Manager

Handles connections to Impala/Kudu database following the Repository pattern.
Implements connection pooling and error handling.
Uses Impala Python library for connectivity (supports Kudu writes).

Performance Features:
- Connection pooling with configurable pool size
- Async write support for non-blocking audit/history operations
- Thread-safe implementation
"""

import logging
import threading
import time
from typing import Optional, Any, List, Dict, Callable
from contextlib import contextmanager
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from django.conf import settings

logger = logging.getLogger('core')

# Import Impala DB-API conditionally to handle environments where it's not available
try:
    from impala.dbapi import connect as impala_connect
    IMPALA_AVAILABLE = True
except ImportError:
    IMPALA_AVAILABLE = False
    logger.warning("Impala Python library not available. Impala/Kudu features will be disabled.")


class ImpalaConnectionManager:
    """
    Connection pool manager for Impala/Kudu database (Production-ready).

    Features:
    - Connection pooling with configurable pool size
    - Connection validation before use
    - Thread-safe implementation
    - Automatic connection recycling
    - Graceful degradation
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            # Get pool size from settings, default to 35 for production (4 workers x 4 threads + margin)
            from django.conf import settings
            max_pool_size = getattr(settings, 'IMPALA_POOL_SIZE', 35)

            self._pool = Queue(maxsize=max_pool_size)
            self._pool_lock = threading.Lock()
            self._connection_count = 0
            self._max_connections = max_pool_size
            self._connection_timeout = 3600  # 1 hour in seconds

            # Thread pool for async writes (audit logs, history, event queue)
            # Using 15 workers to handle event queue throughput during high trade volume
            self._async_executor = ThreadPoolExecutor(max_workers=15, thread_name_prefix='kudu_async_')
            self._async_futures = []

            self._initialized = True
            logger.info(f"Impala connection pool initialized (max: {max_pool_size} connections, async workers: 15)")

    def _create_connection(self, database: Optional[str] = None):
        """
        Create a new Impala connection.

        Args:
            database: Optional database name

        Returns:
            Connection object or None
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Impala connection requested but Impala library not available")
            return None

        try:
            config = settings.IMPALA_CONFIG
            db_name = database or config['DATABASE']
            auth_mode = config.get('AUTH_MECHANISM', config.get('AUTH', 'NOSASL'))
            use_ssl = config.get('USE_SSL', False)

            # Log SSL config for debugging
            import os
            logger.info(f"IMPALA_CONFIG USE_SSL={use_ssl}, env IMPALA_USE_SSL={os.environ.get('IMPALA_USE_SSL', 'NOT_SET')}, CIS_ENV={os.environ.get('CIS_ENV', 'NOT_SET')}")

            # Build connection parameters
            conn_params = {
                'host': config['HOST'],
                'port': config['PORT'],
                'database': db_name,
                'auth_mechanism': auth_mode,
            }

            # Add SSL if enabled (for Work/CML environments)
            if use_ssl:
                conn_params['use_ssl'] = True

            # Add Kerberos service name if using GSSAPI
            if auth_mode == 'GSSAPI' and config.get('KERBEROS_SERVICE_NAME'):
                conn_params['kerberos_service_name'] = config['KERBEROS_SERVICE_NAME']

            # Add credentials for auth modes that require them
            if auth_mode in ['LDAP', 'CUSTOM']:
                conn_params['user'] = config.get('USERNAME', '')
                conn_params['password'] = config.get('PASSWORD', '')

            # Log connection params for debugging
            logger.info(f"Impala connection params: {conn_params}")

            # Create connection
            connection = impala_connect(**conn_params)

            # Store creation time for recycling
            connection._created_at = time.time()
            connection._database = db_name

            logger.info(f"Created new Impala connection to database: {db_name}")
            return connection

        except Exception as e:
            logger.error(f"Failed to create Impala connection: {str(e)}")
            return None

    # Skip validation for connections used within this many seconds
    # Reduced from 30s to 10s for better connection reuse without overhead
    VALIDATION_SKIP_THRESHOLD = 10

    # Performance monitoring counters (for long-running apps)
    _pool_wait_count = 0
    _pool_wait_total_time = 0
    _connection_reuse_count = 0
    _connection_create_count = 0
    _validation_skip_count = 0
    _validation_ping_count = 0

    def _validate_connection(self, connection, force_ping: bool = False) -> bool:
        """
        Validate if connection is still alive and not expired.
        Optimized to skip SELECT 1 ping for recently-used connections.

        Args:
            connection: Connection to validate
            force_ping: If True, always perform SELECT 1 ping

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if connection is too old (recycle after 1 hour)
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    logger.debug("Connection expired (age: {:.0f}s), will recycle".format(age))
                    return False

            # Skip ping for recently-used connections (performance optimization)
            if not force_ping and hasattr(connection, '_last_used'):
                idle_time = time.time() - connection._last_used
                if idle_time < self.VALIDATION_SKIP_THRESHOLD:
                    # Connection was used recently, assume it's still valid
                    ImpalaConnectionManager._validation_skip_count += 1
                    return True

            # Ping the connection (only for idle connections or forced)
            ImpalaConnectionManager._validation_ping_count += 1
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True

        except Exception as e:
            logger.debug(f"Connection validation failed: {str(e)}")
            return False

    def get_connection(self, database: Optional[str] = None):
        """
        Get a connection from the pool.

        Args:
            database: Optional database name

        Returns:
            Connection object from pool
        """
        if not IMPALA_AVAILABLE:
            return None

        # Try to get connection from pool
        try:
            connection = self._pool.get(block=False)
            ImpalaConnectionManager._connection_reuse_count += 1

            # Validate connection (skip ping if recently used)
            if self._validate_connection(connection):
                connection._last_used = time.time()
                return connection
            else:
                # Connection is stale, close it
                try:
                    connection.close()
                except:
                    pass
                with self._pool_lock:
                    self._connection_count -= 1

        except Empty:
            pass  # Pool is empty, create new connection

        # Create new connection if under limit
        with self._pool_lock:
            if self._connection_count < self._max_connections:
                connection = self._create_connection(database)
                if connection:
                    self._connection_count += 1
                    ImpalaConnectionManager._connection_create_count += 1
                    logger.debug(f"Pool stats: {self._connection_count}/{self._max_connections} connections")
                return connection
            else:
                # Wait for connection from pool
                wait_start = time.time()
                logger.warning(f"Connection pool exhausted ({self._connection_count}/{self._max_connections}), waiting...")
                ImpalaConnectionManager._pool_wait_count += 1
                try:
                    connection = self._pool.get(timeout=30)
                    wait_time = time.time() - wait_start
                    ImpalaConnectionManager._pool_wait_total_time += wait_time
                    if wait_time > 5:
                        logger.warning(f"Pool wait took {wait_time:.1f}s - consider increasing pool size")
                    if self._validate_connection(connection):
                        connection._last_used = time.time()
                        return connection
                    else:
                        # Stale connection, create new one
                        try:
                            connection.close()
                        except:
                            pass
                        self._connection_count -= 1
                        return self._create_connection(database)
                except Empty:
                    wait_time = time.time() - wait_start
                    ImpalaConnectionManager._pool_wait_total_time += wait_time
                    logger.error(f"Timeout ({wait_time:.1f}s) waiting for connection from pool")
                    return None

    def return_connection(self, connection):
        """
        Return a connection to the pool.

        Args:
            connection: Connection to return
        """
        if connection is None:
            return

        try:
            # Mark connection as just used and return to pool
            # Skip full validation (ping) since we just used it
            connection._last_used = time.time()
            if self._validate_connection(connection):
                self._pool.put(connection, block=False)
            else:
                # Connection is bad, close it
                try:
                    connection.close()
                except:
                    pass
                with self._pool_lock:
                    self._connection_count -= 1

        except Exception as e:
            logger.debug(f"Failed to return connection to pool: {str(e)}")
            try:
                connection.close()
            except:
                pass
            with self._pool_lock:
                self._connection_count -= 1

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """
        Context manager for Impala cursor (with connection pooling).

        Usage:
            with impala_manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        connection = None
        cursor = None
        try:
            connection = self.get_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                yield None
        except Exception as e:
            logger.error(f"Error in Impala cursor: {str(e)}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            # Return connection to pool instead of closing
            if connection:
                self.return_connection(connection)

    def execute_query(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as list of dictionaries.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            List of dictionaries with column names as keys
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute query: Impala library not available")
            return []

        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # Get column names
                columns = [desc[0] for desc in cursor.description]

                # Fetch all results
                rows = cursor.fetchall()

                # Convert to list of dictionaries
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to execute query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> bool:
        """
        Execute a write query (INSERT, UPDATE, DELETE) with connection pooling.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            True if successful, False otherwise
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute write: Impala library not available")
            return False

        connection = None
        cursor = None
        try:
            connection = self.get_connection(database)
            if connection is None:
                return False

            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Commit the transaction - critical for Kudu writes to persist
            connection.commit()

            logger.info("Write query executed and committed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            if connection:
                try:
                    connection.rollback()
                except:
                    pass
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            # Return connection to pool instead of closing
            if connection:
                self.return_connection(connection)

    def test_connection(self) -> bool:
        """Test if Impala connection is available"""
        if not IMPALA_AVAILABLE:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
            return False
        except Exception as e:
            logger.error(f"Impala connection test failed: {str(e)}")
            return False

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in the database"""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                return tables
        except Exception as e:
            logger.error(f"Failed to get tables: {str(e)}")
            return []

    def describe_table(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get table schema information"""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                cursor.execute(f"DESCRIBE {table_name}")
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to describe table {table_name}: {str(e)}")
            return []

    # =========================================================================
    # ASYNC WRITE OPERATIONS (Non-blocking for audit/history)
    # =========================================================================

    def execute_write_async(self, query: str, params: Optional[List] = None,
                            database: Optional[str] = None,
                            callback: Optional[Callable[[bool], None]] = None) -> None:
        """
        Execute a write query asynchronously (non-blocking).
        Ideal for audit logs, history records that don't need immediate confirmation.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name
            callback: Optional callback function called with success status

        Returns:
            None (fire-and-forget, use callback if you need result)
        """
        def _async_write():
            try:
                success = self.execute_write(query, params, database)
                if callback:
                    callback(success)
                return success
            except Exception as e:
                logger.error(f"Async write failed: {str(e)}")
                if callback:
                    callback(False)
                return False

        try:
            future = self._async_executor.submit(_async_write)
            # Clean up completed futures periodically
            self._cleanup_futures()
            self._async_futures.append(future)
            logger.debug("Queued async write operation")
        except Exception as e:
            logger.error(f"Failed to queue async write: {str(e)}")
            # Fallback to sync write if async queue fails
            self.execute_write(query, params, database)

    def _cleanup_futures(self):
        """Remove completed futures from tracking list."""
        self._async_futures = [f for f in self._async_futures if not f.done()]

    def wait_for_async_writes(self, timeout: float = 30.0) -> int:
        """
        Wait for all pending async writes to complete.
        Call this before application shutdown.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Number of writes that completed
        """
        completed = 0
        for future in self._async_futures:
            try:
                future.result(timeout=timeout)
                completed += 1
            except Exception as e:
                logger.error(f"Async write failed during wait: {str(e)}")
        self._async_futures.clear()
        return completed

    def get_async_queue_size(self) -> int:
        """Get number of pending async write operations."""
        self._cleanup_futures()
        return len(self._async_futures)

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get connection pool health statistics for monitoring.
        Call this periodically in long-running applications.
        """
        return {
            'pool_size': self._max_connections,
            'active_connections': self._connection_count,
            'pool_available': self._pool.qsize(),
            'pool_utilization_pct': (self._connection_count / self._max_connections) * 100 if self._max_connections > 0 else 0,
            'async_queue_size': self.get_async_queue_size(),
            # Counters since startup
            'connection_reuse_count': ImpalaConnectionManager._connection_reuse_count,
            'connection_create_count': ImpalaConnectionManager._connection_create_count,
            'validation_skip_count': ImpalaConnectionManager._validation_skip_count,
            'validation_ping_count': ImpalaConnectionManager._validation_ping_count,
            'pool_wait_count': ImpalaConnectionManager._pool_wait_count,
            'pool_wait_avg_time': (
                ImpalaConnectionManager._pool_wait_total_time / ImpalaConnectionManager._pool_wait_count
                if ImpalaConnectionManager._pool_wait_count > 0 else 0
            ),
        }

    def log_pool_stats(self):
        """Log pool statistics for monitoring (call periodically)."""
        stats = self.get_pool_stats()
        logger.info(
            f"[POOL_STATS] active={stats['active_connections']}/{stats['pool_size']} "
            f"utilization={stats['pool_utilization_pct']:.1f}% "
            f"reuse={stats['connection_reuse_count']} "
            f"create={stats['connection_create_count']} "
            f"skip_ping={stats['validation_skip_count']} "
            f"ping={stats['validation_ping_count']} "
            f"waits={stats['pool_wait_count']} "
            f"avg_wait={stats['pool_wait_avg_time']:.2f}s "
            f"async_queue={stats['async_queue_size']}"
        )

    def reset_stats(self):
        """Reset performance counters (call periodically for fresh metrics)."""
        ImpalaConnectionManager._pool_wait_count = 0
        ImpalaConnectionManager._pool_wait_total_time = 0
        ImpalaConnectionManager._connection_reuse_count = 0
        ImpalaConnectionManager._connection_create_count = 0
        ImpalaConnectionManager._validation_skip_count = 0
        ImpalaConnectionManager._validation_ping_count = 0
        logger.info("[POOL_STATS] Counters reset")

    def recycle_idle_connections(self, max_idle_seconds: int = 300):
        """
        Recycle connections that have been idle too long.
        Call this periodically in long-running applications to prevent stale connections.
        """
        recycled = 0
        temp_connections = []

        # Drain pool and check each connection
        while True:
            try:
                connection = self._pool.get(block=False)
                if hasattr(connection, '_last_used'):
                    idle_time = time.time() - connection._last_used
                    if idle_time > max_idle_seconds:
                        # Connection too old, close it
                        try:
                            connection.close()
                        except:
                            pass
                        with self._pool_lock:
                            self._connection_count -= 1
                        recycled += 1
                        continue
                temp_connections.append(connection)
            except Empty:
                break

        # Put back valid connections
        for conn in temp_connections:
            try:
                self._pool.put(conn, block=False)
            except:
                pass

        if recycled > 0:
            logger.info(f"[POOL_RECYCLE] Recycled {recycled} idle connections")
        return recycled


# Global instance
impala_manager = ImpalaConnectionManager()


# =========================================================================
# CACHING UTILITIES FOR DROPDOWN DATA
# =========================================================================

class QueryCache:
    """
    Simple time-based cache for expensive queries (dropdown data).
    Thread-safe with configurable TTL.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._cache = {}
            self._cache_lock = threading.Lock()
            self._default_ttl = 300  # 5 minutes default TTL
            self._initialized = True

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._cache_lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    logger.debug(f"Cache hit for key: {key}")
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        ttl = ttl or self._default_ttl
        expiry = time.time() + ttl
        with self._cache_lock:
            self._cache[key] = (value, expiry)
            logger.debug(f"Cache set for key: {key} (TTL: {ttl}s)")

    def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]

    def invalidate_pattern(self, pattern: str) -> int:
        """Remove all keys matching pattern (simple prefix match)."""
        removed = 0
        with self._cache_lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
        return removed

    def clear(self) -> None:
        """Clear entire cache."""
        with self._cache_lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            now = time.time()
            valid_count = sum(1 for _, (_, expiry) in self._cache.items() if now < expiry)
            return {
                'total_keys': len(self._cache),
                'valid_keys': valid_count,
                'expired_keys': len(self._cache) - valid_count
            }


# Global cache instance
query_cache = QueryCache()
