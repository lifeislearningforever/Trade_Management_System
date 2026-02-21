"""
Hive Connection Manager for Managed Tables (ORC + ACID)

Handles connections to HiveServer2 for ACID transactions on ORC tables.
Replaces ImpalaConnectionManager for production use with Hive.

Features:
- Connection pooling for HiveServer2
- ACID transaction support (INSERT, UPDATE, DELETE)
- MapReduce engine for transactional operations
- Thread-safe implementation
- Async write support for audit/history operations

Connection: beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira'
"""

import logging
import threading
import time
from typing import Optional, Any, List, Dict, Callable
from contextlib import contextmanager
from queue import Queue, Empty, Full
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings

logger = logging.getLogger('core')

# Import PyHive for Hive connectivity
try:
    from pyhive import hive
    HIVE_AVAILABLE = True
except ImportError:
    HIVE_AVAILABLE = False
    logger.warning("PyHive not available. Hive features will be disabled.")


class HiveConnectionManager:
    """
    Connection pool manager for HiveServer2 (Production-ready).

    Features:
    - Connection pooling with configurable pool size
    - ACID transaction support for ORC tables
    - MapReduce engine for INSERT/UPDATE/DELETE
    - Connection validation before use
    - Thread-safe implementation
    - Automatic connection recycling
    - Async write support for audit/history operations
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
            # Get configuration from settings
            self._config = getattr(settings, 'HIVE_CONFIG', {
                'HOST': 'localhost',
                'PORT': 10000,
                'DATABASE': 'gmp_cis',
                'AUTH': 'NONE',
                'USERNAME': 'prakashhosalli',
                'PASSWORD': '0987!Adhira',
            })

            # Pool size from settings, default to 20 for Hive
            max_pool_size = self._config.get('POOL_SIZE', 20)

            self._pool = Queue(maxsize=max_pool_size)
            self._pool_lock = threading.Lock()
            self._connection_count = 0
            self._max_connections = max_pool_size
            self._connection_timeout = 3600  # 1 hour in seconds

            # Thread pool for async writes (audit logs, history)
            self._async_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='hive_async_')
            self._async_futures = []

            self._initialized = True
            logger.info(f"Hive connection manager initialized (host: {self._config['HOST']}:{self._config['PORT']}, pool: {max_pool_size})")

    def _create_connection(self, database: Optional[str] = None):
        """Create a new Hive connection."""
        if not HIVE_AVAILABLE:
            logger.warning("Hive connection requested but PyHive not available")
            return None

        try:
            db_name = database or self._config['DATABASE']

            conn_params = {
                'host': self._config['HOST'],
                'port': self._config['PORT'],
                'database': db_name,
                'auth': self._config.get('AUTH', 'NONE'),
            }

            if self._config.get('USERNAME'):
                conn_params['username'] = self._config['USERNAME']

            connection = hive.Connection(**conn_params)
            connection._created_at = time.time()
            connection._database = db_name

            logger.info(f"Created new Hive connection to database: {db_name}")
            return connection

        except Exception as e:
            logger.error(f"Failed to create Hive connection: {str(e)}")
            return None

    def _validate_connection(self, connection) -> bool:
        """Validate if connection is still alive and not expired."""
        try:
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    logger.debug(f"Connection expired (age: {age:.0f}s), will recycle")
                    return False

            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True

        except Exception as e:
            logger.debug(f"Connection validation failed: {str(e)}")
            return False

    def get_connection(self, database: Optional[str] = None):
        """Get a connection from the pool."""
        if not HIVE_AVAILABLE:
            return None

        try:
            connection = self._pool.get(block=False)
            if self._validate_connection(connection):
                return connection
            else:
                try:
                    connection.close()
                except:
                    pass
                with self._pool_lock:
                    self._connection_count -= 1
        except Empty:
            pass

        with self._pool_lock:
            if self._connection_count < self._max_connections:
                connection = self._create_connection(database)
                if connection:
                    self._connection_count += 1
                    logger.debug(f"Pool stats: {self._connection_count}/{self._max_connections} connections")
                return connection
            else:
                logger.warning("Connection pool exhausted, waiting for available connection")
                try:
                    connection = self._pool.get(timeout=30)
                    if self._validate_connection(connection):
                        return connection
                    else:
                        try:
                            connection.close()
                        except:
                            pass
                        self._connection_count -= 1
                        return self._create_connection(database)
                except Empty:
                    logger.error("Timeout waiting for connection from pool")
                    return None

    def return_connection(self, connection):
        """Return a connection to the pool."""
        if connection is None:
            return

        try:
            if self._validate_connection(connection):
                try:
                    self._pool.put(connection, block=False)
                except Full:
                    try:
                        connection.close()
                    except:
                        pass
                    with self._pool_lock:
                        self._connection_count -= 1
            else:
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
        """Context manager for Hive cursor (with connection pooling)."""
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
            logger.error(f"Error in Hive cursor: {str(e)}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                self.return_connection(connection)

    def execute_query(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dictionaries."""
        if not HIVE_AVAILABLE:
            logger.warning("Cannot execute query: PyHive not available")
            return []

        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if cursor.description:
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                return []

        except Exception as e:
            logger.error(f"Failed to execute query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None, use_mr_engine: bool = True) -> bool:
        """Execute a write query (INSERT, UPDATE, DELETE) for ACID tables."""
        if not HIVE_AVAILABLE:
            logger.warning("Cannot execute write: PyHive not available")
            return False

        connection = None
        cursor = None
        try:
            connection = self.get_connection(database)
            if connection is None:
                return False

            cursor = connection.cursor()

            # Set MapReduce engine for ACID operations
            if use_mr_engine:
                cursor.execute("SET hive.execution.engine=mr")

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            logger.info("Hive write query executed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                self.return_connection(connection)

    def test_connection(self) -> bool:
        """Test if Hive connection is available."""
        if not HIVE_AVAILABLE:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
            return False
        except Exception as e:
            logger.error(f"Hive connection test failed: {str(e)}")
            return False

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in the database."""
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
        """Get table schema information."""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []
                cursor.execute(f"DESCRIBE {table_name}")
                columns = [desc[0].split('.')[-1] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to describe table {table_name}: {str(e)}")
            return []

    # Async write operations
    def execute_write_async(self, query: str, params: Optional[List] = None,
                            database: Optional[str] = None,
                            callback: Optional[Callable[[bool], None]] = None) -> None:
        """Execute a write query asynchronously (non-blocking)."""
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
            self._cleanup_futures()
            self._async_futures.append(future)
            logger.debug("Queued async write operation")
        except Exception as e:
            logger.error(f"Failed to queue async write: {str(e)}")
            self.execute_write(query, params, database)

    def _cleanup_futures(self):
        """Remove completed futures from tracking list."""
        self._async_futures = [f for f in self._async_futures if not f.done()]

    def wait_for_async_writes(self, timeout: float = 30.0) -> int:
        """Wait for all pending async writes to complete."""
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


# Global instance - use hybrid manager if available (CML), else fallback to Hive-only
try:
    from core.repositories.hybrid_connection import hybrid_manager
    hive_manager = hybrid_manager
    logger.info("Using HybridConnectionManager (Impala reads + Hive writes)")
except ImportError:
    hive_manager = HiveConnectionManager()
    logger.info("Using HiveConnectionManager (Hive-only mode)")


# Query Cache
class QueryCache:
    """Simple time-based cache for expensive queries."""
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
            self._default_ttl = 300
            self._initialized = True

    def get(self, key: str) -> Optional[Any]:
        with self._cache_lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl or self._default_ttl
        expiry = time.time() + ttl
        with self._cache_lock:
            self._cache[key] = (value, expiry)

    def invalidate(self, key: str) -> None:
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]

    def invalidate_pattern(self, pattern: str) -> int:
        removed = 0
        with self._cache_lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
        return removed

    def clear(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        with self._cache_lock:
            now = time.time()
            valid_count = sum(1 for _, (_, expiry) in self._cache.items() if now < expiry)
            return {
                'total_keys': len(self._cache),
                'valid_keys': valid_count,
                'expired_keys': len(self._cache) - valid_count
            }


query_cache = QueryCache()


# Backward compatibility aliases
impala_manager = hive_manager
ImpalaConnectionManager = HiveConnectionManager
