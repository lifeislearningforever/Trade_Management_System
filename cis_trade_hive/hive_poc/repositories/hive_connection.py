"""
Hive Connection Manager for POC
===============================

Optimized connection management with:
- Connection pooling with configurable size and age-out
- Tez execution engine for fast INSERT/UPDATE operations
- Impala for reads (fast), Hive for writes (ACID)
- Connection validation and automatic reconnection
- Async write support for non-blocking operations

Based on working Cloudera DataViz 7.2.9 connection settings.

Usage:
    from hive_poc.repositories.hive_connection import hive_manager

    # Read (uses Impala - fast)
    results = hive_manager.execute_query("SELECT * FROM table LIMIT 10")

    # Write (uses Hive with Tez - ACID)
    success = hive_manager.execute_write("INSERT INTO table VALUES (...)")

    # Async write (non-blocking)
    hive_manager.execute_write_async("INSERT INTO table VALUES (...)",
                                      callback=lambda ok: print(f"Done: {ok}"))
"""

import logging
import threading
import time
from typing import Optional, Any, List, Dict, Callable, Tuple
from contextlib import contextmanager
from queue import Queue, Empty, Full
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger('hive_poc')

# Import configuration
from hive_poc.hive_config import (
    HIVE_POC_CONFIG,
    HIVE_POC_POOL_CONFIG,
    HIVE_POC_PERFORMANCE_CONFIG,
    IMPALA_READ_CONFIG,
    HIVE_POC_LOGGING,
    get_hive_connect_kwargs,
    get_impala_connect_kwargs,
)

# Check for impyla availability
IMPYLA_AVAILABLE = False
try:
    from impala.dbapi import connect as impyla_connect
    IMPYLA_AVAILABLE = True
    logger.info("impyla available for Hive/Impala connections")
except ImportError:
    logger.error("impyla not available. Install with: pip install impyla")


# =============================================================================
# Connection Wrapper
# =============================================================================

@dataclass
class PooledConnection:
    """Wrapper for pooled connection with metadata."""
    connection: Any
    created_at: float
    last_used: float
    database: str
    conn_type: str  # 'hive' or 'impala'
    is_initialized: bool = False

    def age_seconds(self) -> float:
        """Get connection age in seconds."""
        return time.time() - self.created_at

    def idle_seconds(self) -> float:
        """Get idle time in seconds."""
        return time.time() - self.last_used

    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()


# =============================================================================
# Hive Connection Manager
# =============================================================================

class HiveConnectionManager:
    """
    Optimized Hive/Impala Connection Manager.

    Features:
    - Impala for reads (fast queries via port 21050)
    - Hive for writes (ACID support via port 10000)
    - Connection pooling with age-out
    - Tez execution engine for fast writes
    - Automatic connection validation
    - Async write support
    - Thread-safe implementation
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
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._config = HIVE_POC_CONFIG
        self._pool_config = HIVE_POC_POOL_CONFIG
        self._perf_config = HIVE_POC_PERFORMANCE_CONFIG
        self._impala_config = IMPALA_READ_CONFIG
        self._log_config = HIVE_POC_LOGGING

        # Connection pools
        self._hive_pool: Queue = Queue(maxsize=self._pool_config['POOL_SIZE'])
        self._impala_pool: Queue = Queue(maxsize=self._impala_config['POOL_SIZE'])

        # Pool locks
        self._hive_pool_lock = threading.Lock()
        self._impala_pool_lock = threading.Lock()

        # Connection counts
        self._hive_connection_count = 0
        self._impala_connection_count = 0

        # Async write executor
        self._async_executor = ThreadPoolExecutor(
            max_workers=self._perf_config['ASYNC_WORKERS'],
            thread_name_prefix='hive_async_'
        )
        self._async_futures: List[Future] = []
        self._async_lock = threading.Lock()

        self._initialized = True

        logger.info(
            f"HiveConnectionManager initialized:\n"
            f"  Hive (writes): {self._config['HOST']}:{self._config['PORT']} "
            f"[{self._config['AUTH_MECHANISM']}] SSL={self._config['USE_SSL']}\n"
            f"  Impala (reads): {self._impala_config['HOST']}:{self._impala_config['PORT']} "
            f"[{self._impala_config['AUTH_MECHANISM']}]\n"
            f"  Execution Engine: {self._perf_config['EXECUTION_ENGINE']}\n"
            f"  Pool Size: {self._pool_config['POOL_SIZE']} (Hive), "
            f"{self._impala_config['POOL_SIZE']} (Impala)\n"
            f"  Connection Max Age: {self._pool_config['CONNECTION_MAX_AGE']}s"
        )

        # Pre-warm connections if configured
        if self._pool_config['PRE_WARM']:
            self._pre_warm_connections()

    def _pre_warm_connections(self):
        """Pre-warm connection pool on startup."""
        try:
            min_size = self._pool_config['POOL_MIN_SIZE']
            logger.info(f"Pre-warming {min_size} connections...")

            for _ in range(min_size):
                # Pre-warm Impala connection
                conn = self._create_impala_connection()
                if conn:
                    self._impala_pool.put(conn, block=False)

            logger.info(f"Pre-warmed {self._impala_connection_count} Impala connections")
        except Exception as e:
            logger.warning(f"Pre-warming failed: {e}")

    # =========================================================================
    # Connection Creation
    # =========================================================================

    def _create_connection(self, database: Optional[str] = None, conn_type: str = 'hive') -> Optional[PooledConnection]:
        """
        Create a new connection to HiveServer2 (Kerberos + SSL).

        Args:
            database: Database name (defaults to config)
            conn_type: 'hive' for writes, 'impala' for reads

        Returns:
            PooledConnection wrapper or None on failure
        """
        if not IMPYLA_AVAILABLE:
            logger.warning("Connection requested but impyla is not available.")
            return None

        c = self._config if conn_type == 'hive' else self._impala_config
        db_name = database or c['DATABASE']

        # Build kwargs for connect()
        kwargs = {
            'host': c['HOST'],
            'port': c['PORT'],
            'database': db_name,
            'auth_mechanism': c['AUTH_MECHANISM'],
            'timeout': c['TIMEOUT'],
        }

        # Kerberos authentication
        if c['AUTH_MECHANISM'] == 'GSSAPI':
            kwargs['kerberos_service_name'] = c['KERBEROS_SERVICE_NAME']

        # SSL
        if c.get('USE_SSL'):
            kwargs['use_ssl'] = True

        # Optional SSL CA certificate
        if c.get('CA_CERT'):
            kwargs['ca_cert'] = c['CA_CERT']

        try:
            conn = impyla_connect(**kwargs)
            conn._created_at = time.time()  # type: ignore[attr-defined]
            conn._database = db_name  # type: ignore[attr-defined]

            # Attach metadata
            try:
                conn._last_validated = time.time()  # type: ignore[attr-defined]
            except Exception:
                pass

            logger.info(f"Created new {conn_type} connection to database '{db_name}'")

            pooled = PooledConnection(
                connection=conn,
                created_at=time.time(),
                last_used=time.time(),
                database=db_name,
                conn_type=conn_type,
                is_initialized=False,
            )

            return pooled

        except Exception as e:
            logger.error(f"Failed to create {conn_type} connection: {e}")
            return None

    def _create_hive_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Create Hive connection for writes."""
        return self._create_connection(database, conn_type='hive')

    def _create_impala_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Create Impala connection for reads."""
        return self._create_connection(database, conn_type='impala')

    # =========================================================================
    # Connection Validation
    # =========================================================================

    def _validate_connection(self, pooled: PooledConnection) -> bool:
        """
        Basic sanity check for an open connection.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            # Check age
            if pooled.age_seconds() > self._pool_config['CONNECTION_MAX_AGE']:
                logger.debug(f"Connection aged out ({pooled.age_seconds():.0f}s)")
                return False

            # Quick validation query
            cursor = pooled.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()

            return True

        except Exception as e:
            logger.debug(f"Connection validation failed: {e}")
            return False

    def _close_connection(self, pooled: PooledConnection):
        """Safely close a connection."""
        if pooled and pooled.connection:
            try:
                pooled.connection.close()
            except Exception:
                pass

    # =========================================================================
    # Connection Pool Management
    # =========================================================================

    def _get_from_pool(self, pool: Queue, pool_lock: threading.Lock,
                       create_func: Callable, max_size: int,
                       count_attr: str, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get connection from pool or create new one."""
        # Try to get from pool
        try:
            pooled = pool.get(block=False)
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with pool_lock:
                    setattr(self, count_attr, getattr(self, count_attr) - 1)
        except Empty:
            pass

        # Create new connection if pool not full
        with pool_lock:
            current_count = getattr(self, count_attr)
            if current_count < max_size:
                pooled = create_func(database)
                if pooled:
                    setattr(self, count_attr, current_count + 1)
                return pooled

        # Wait for available connection
        try:
            pooled = pool.get(timeout=self._pool_config['ACQUIRE_TIMEOUT'])
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with pool_lock:
                    setattr(self, count_attr, getattr(self, count_attr) - 1)
                return create_func(database)
        except Empty:
            logger.error("Timeout waiting for connection")
            return None

    def _return_to_pool(self, pooled: PooledConnection, pool: Queue,
                        pool_lock: threading.Lock, count_attr: str):
        """Return connection to pool."""
        if pooled is None:
            return

        try:
            if self._validate_connection(pooled):
                try:
                    pool.put(pooled, block=False)
                except Full:
                    self._close_connection(pooled)
                    with pool_lock:
                        setattr(self, count_attr, getattr(self, count_attr) - 1)
            else:
                self._close_connection(pooled)
                with pool_lock:
                    setattr(self, count_attr, getattr(self, count_attr) - 1)
        except Exception:
            self._close_connection(pooled)
            with pool_lock:
                setattr(self, count_attr, getattr(self, count_attr) - 1)

    def get_hive_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get Hive connection for writes."""
        return self._get_from_pool(
            self._hive_pool,
            self._hive_pool_lock,
            self._create_hive_connection,
            self._pool_config['POOL_SIZE'],
            '_hive_connection_count',
            database
        )

    def return_hive_connection(self, pooled: PooledConnection):
        """Return Hive connection to pool."""
        self._return_to_pool(
            pooled,
            self._hive_pool,
            self._hive_pool_lock,
            '_hive_connection_count'
        )

    def get_impala_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get Impala connection for reads."""
        return self._get_from_pool(
            self._impala_pool,
            self._impala_pool_lock,
            self._create_impala_connection,
            self._impala_config['POOL_SIZE'],
            '_impala_connection_count',
            database
        )

    def return_impala_connection(self, pooled: PooledConnection):
        """Return Impala connection to pool."""
        self._return_to_pool(
            pooled,
            self._impala_pool,
            self._impala_pool_lock,
            '_impala_connection_count'
        )

    # =========================================================================
    # Context Managers
    # =========================================================================

    @contextmanager
    def get_read_cursor(self, database: Optional[str] = None):
        """Context manager for Impala cursor (reads)."""
        pooled = None
        cursor = None
        try:
            pooled = self.get_impala_connection(database)
            if pooled:
                cursor = pooled.connection.cursor()
                yield cursor
            else:
                logger.error("No Impala connection available")
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_impala_connection(pooled)

    @contextmanager
    def get_write_cursor(self, database: Optional[str] = None):
        """Context manager for Hive cursor (writes) with Tez initialization."""
        pooled = None
        cursor = None
        try:
            pooled = self.get_hive_connection(database)
            if pooled:
                cursor = pooled.connection.cursor()

                # Initialize session with Tez engine if not already done
                if not pooled.is_initialized:
                    self._initialize_session(cursor)
                    pooled.is_initialized = True

                yield cursor
            else:
                logger.error("No Hive connection available")
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_hive_connection(pooled)

    def _initialize_session(self, cursor):
        """Initialize Hive session with Tez engine and optimizations.

        Note: Always uses Tez engine regardless of EXECUTION_ENGINE config when
        ALWAYS_USE_TEZ is True (default). This ensures optimal performance.
        """
        try:
            # Always use Tez when ALWAYS_USE_TEZ is configured (default: True)
            engine = 'tez' if self._config.get('ALWAYS_USE_TEZ', True) else self._perf_config['EXECUTION_ENGINE']
            cursor.execute(f"SET hive.execution.engine={engine}")

            # Apply additional initialization statements
            for stmt in self._config.get('INIT_STATEMENTS', []):
                try:
                    cursor.execute(stmt)
                except Exception as e:
                    logger.debug(f"Init statement failed (non-critical): {stmt} - {e}")

            logger.debug("Session initialized with Tez engine")
        except Exception as e:
            logger.warning(f"Session initialization failed: {e}")

    # Backward compatibility alias
    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """Backward compatible cursor (uses Impala for reads)."""
        with self.get_read_cursor(database) as cursor:
            yield cursor

    # =========================================================================
    # Query Execution
    # =========================================================================

    def execute_query(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Execute a READ query via Impala (fast).

        Args:
            query: SQL SELECT query
            params: Optional parameters for query formatting
            database: Database name (optional)

        Returns:
            List of dictionaries with query results
        """
        start_time = time.time()

        # Format query with params
        formatted_query = self._format_query(query, params)

        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    return []

                cursor.execute(formatted_query)

                if cursor.description:
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    results = [dict(zip(columns, row)) for row in rows]
                else:
                    results = []

                elapsed_ms = (time.time() - start_time) * 1000
                self._log_query(formatted_query, elapsed_ms, len(results))

                return results

        except Exception as e:
            logger.error(f"Query failed: {e}")
            logger.error(f"Query: {formatted_query[:200]}...")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> Tuple[bool, float]:
        """
        Execute a WRITE query via Hive with Tez engine.

        Args:
            query: SQL INSERT/UPDATE/DELETE query
            params: Optional parameters for query formatting
            database: Database name (optional)

        Returns:
            Tuple of (success: bool, elapsed_ms: float)
        """
        start_time = time.time()

        # Format query with params
        formatted_query = self._format_query(query, params)

        # Enforce Tez engine if configured
        if self._config.get('ALWAYS_USE_TEZ'):
            formatted_query = formatted_query.replace(
                'hive.execution.engine=mr',
                'hive.execution.engine=tez'
            )

        try:
            with self.get_write_cursor(database) as cursor:
                if cursor is None:
                    return False, 0.0

                cursor.execute(formatted_query)

                elapsed_ms = (time.time() - start_time) * 1000
                self._log_query(formatted_query, elapsed_ms, 0, is_write=True)

                return True, elapsed_ms

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Write failed ({elapsed_ms:.0f}ms): {e}")
            logger.error(f"Query: {formatted_query[:200]}...")
            return False, elapsed_ms

    def _format_query(self, query: str, params: Optional[List] = None) -> str:
        """Format query with parameters."""
        if not params:
            return query

        try:
            formatted_params = tuple(
                f"'{p}'" if isinstance(p, str) else str(p) if p is not None else 'NULL'
                for p in params
            )
            return query % formatted_params
        except Exception:
            return query

    def _log_query(self, query: str, elapsed_ms: float, row_count: int, is_write: bool = False):
        """Log query execution."""
        if self._log_config['LOG_QUERIES']:
            logger.info(f"{'WRITE' if is_write else 'READ'} ({elapsed_ms:.0f}ms, {row_count} rows): {query[:100]}...")

        if self._log_config['LOG_SLOW_QUERIES'] and elapsed_ms > self._log_config['SLOW_QUERY_THRESHOLD_MS']:
            logger.warning(f"SLOW QUERY ({elapsed_ms:.0f}ms): {query[:200]}...")

    # =========================================================================
    # Async Write Operations
    # =========================================================================

    def execute_write_async(self, query: str, params: Optional[List] = None,
                            database: Optional[str] = None,
                            callback: Optional[Callable[[bool, float], None]] = None) -> Future:
        """
        Execute a write query asynchronously (non-blocking).

        Args:
            query: SQL INSERT/UPDATE/DELETE query
            params: Optional parameters
            database: Database name (optional)
            callback: Optional callback function(success: bool, elapsed_ms: float)

        Returns:
            Future object for tracking completion
        """
        def _async_write():
            try:
                success, elapsed_ms = self.execute_write(query, params, database)
                if callback:
                    callback(success, elapsed_ms)
                return success, elapsed_ms
            except Exception as e:
                logger.error(f"Async write failed: {e}")
                if callback:
                    callback(False, 0.0)
                return False, 0.0

        future = self._async_executor.submit(_async_write)

        with self._async_lock:
            self._async_futures = [f for f in self._async_futures if not f.done()]
            self._async_futures.append(future)

        return future

    def wait_for_async_writes(self, timeout: float = 30.0) -> int:
        """Wait for all pending async writes to complete."""
        completed = 0
        with self._async_lock:
            futures = list(self._async_futures)

        for future in futures:
            try:
                future.result(timeout=timeout)
                completed += 1
            except Exception as e:
                logger.error(f"Async write failed: {e}")

        with self._async_lock:
            self._async_futures.clear()

        return completed

    def get_async_queue_size(self) -> int:
        """Get number of pending async write operations."""
        with self._async_lock:
            return len([f for f in self._async_futures if not f.done()])

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def test_connection(self) -> Dict[str, Any]:
        """Test both Impala and Hive connections."""
        results = {
            'impala': False,
            'hive': False,
            'impala_latency_ms': 0,
            'hive_latency_ms': 0,
            'execution_engine': self._perf_config['EXECUTION_ENGINE'],
        }

        # Test Impala
        try:
            start = time.time()
            with self.get_read_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    results['impala'] = True
                    results['impala_latency_ms'] = (time.time() - start) * 1000
                    logger.info(f"Impala connection test: SUCCESS ({results['impala_latency_ms']:.0f}ms)")
        except Exception as e:
            logger.error(f"Impala connection test: FAILED - {e}")

        # Test Hive
        try:
            start = time.time()
            with self.get_write_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    results['hive'] = True
                    results['hive_latency_ms'] = (time.time() - start) * 1000
                    logger.info(f"Hive connection test: SUCCESS ({results['hive_latency_ms']:.0f}ms)")
        except Exception as e:
            logger.error(f"Hive connection test: FAILED - {e}")

        return results

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            'hive': {
                'host': self._config['HOST'],
                'port': self._config['PORT'],
                'database': self._config['DATABASE'],
                'auth': self._config['AUTH_MECHANISM'],
                'ssl': self._config['USE_SSL'],
                'active_connections': self._hive_connection_count,
                'pool_size': self._pool_config['POOL_SIZE'],
                'execution_engine': self._perf_config['EXECUTION_ENGINE'],
            },
            'impala': {
                'host': self._impala_config['HOST'],
                'port': self._impala_config['PORT'],
                'database': self._impala_config['DATABASE'],
                'auth': self._impala_config['AUTH_MECHANISM'],
                'ssl': self._impala_config['USE_SSL'],
                'active_connections': self._impala_connection_count,
                'pool_size': self._impala_config['POOL_SIZE'],
            },
            'async_pending': self.get_async_queue_size(),
            'connection_max_age': self._pool_config['CONNECTION_MAX_AGE'],
        }

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in database."""
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor:
                    cursor.execute("SHOW TABLES")
                    return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tables: {e}")
        return []

    def describe_table(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get table schema information."""
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor:
                    cursor.execute(f"DESCRIBE {table_name}")
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to describe table: {e}")
        return []


# =============================================================================
# Global Instance
# =============================================================================

hive_manager = HiveConnectionManager()

# Backward compatibility aliases
impala_manager = hive_manager
hybrid_manager = hive_manager

__all__ = ['hive_manager', 'impala_manager', 'hybrid_manager', 'HiveConnectionManager']
