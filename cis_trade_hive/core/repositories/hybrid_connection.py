"""
Hybrid Connection Manager
=========================

SOLID-compliant connection manager that routes queries to the appropriate backend:
- Impala (port 21050): For Kudu table reads and writes
- Hive (port 10000): For Hive external/managed table writes

Design Principles:
- Single Responsibility: Each class handles one type of connection
- Open/Closed: Easy to extend with new connection types
- Liskov Substitution: All connection handlers implement same interface
- Interface Segregation: Separate interfaces for read and write operations
- Dependency Inversion: High-level modules depend on abstractions

Usage:
    from core.repositories.hybrid_connection import hybrid_manager

    # Kudu operations (via Impala)
    results = hybrid_manager.kudu_read("SELECT * FROM kudu_table")
    success = hybrid_manager.kudu_write("UPSERT INTO kudu_table VALUES (...)")

    # Hive external table operations
    success = hybrid_manager.hive_write("INSERT INTO external_table VALUES (...)")

    # Auto-routing based on table type
    results = hybrid_manager.execute_query("SELECT * FROM any_table")
    success = hybrid_manager.execute_write("INSERT INTO any_table VALUES (...)", table_type='hive')
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Any, List, Dict, Tuple, Callable
from contextlib import contextmanager
from queue import Queue, Empty, Full
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from django.conf import settings

logger = logging.getLogger('core')


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
    conn_type: str  # 'impala' or 'hive'
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
# Abstract Base Classes (Interface Segregation)
# =============================================================================

class IConnectionReader(ABC):
    """Interface for read operations."""

    @abstractmethod
    def execute_query(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a read query and return results."""
        pass


class IConnectionWriter(ABC):
    """Interface for write operations."""

    @abstractmethod
    def execute_write(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> bool:
        """Execute a write query and return success status."""
        pass


class IConnectionPool(ABC):
    """Interface for connection pool management."""

    @abstractmethod
    def get_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get a connection from the pool."""
        pass

    @abstractmethod
    def return_connection(self, conn: PooledConnection) -> None:
        """Return a connection to the pool."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if connection is available."""
        pass


# =============================================================================
# Impala Connection Handler (Single Responsibility - Kudu Operations)
# =============================================================================

class ImpalaConnectionHandler(IConnectionReader, IConnectionWriter, IConnectionPool):
    """
    Handles Impala connections for Kudu table operations.

    Responsibilities:
    - Connection pooling for Impala
    - Read and write operations on Kudu tables
    - Connection validation and recycling
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._pool: Queue = Queue(maxsize=config.get('POOL_SIZE', 10))
        self._pool_lock = threading.Lock()
        self._connection_count = 0
        self._max_connections = config.get('POOL_SIZE', 10)
        self._connection_timeout = config.get('CONNECTION_MAX_AGE', 3600)

        # Check for impyla availability
        self._impyla_available = False
        try:
            from impala.dbapi import connect
            self._impyla_connect = connect
            self._impyla_available = True
        except ImportError:
            logger.warning("impyla not available for Impala connections")

        logger.info(
            f"ImpalaConnectionHandler initialized: "
            f"{config.get('HOST')}:{config.get('PORT')} "
            f"[pool_size={self._max_connections}]"
        )

    def _create_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Create a new Impala connection."""
        if not self._impyla_available:
            return None

        try:
            db_name = database or self._config.get('DATABASE', 'default')
            # Support both AUTH and AUTH_MECHANISM keys for compatibility
            auth_mode = self._config.get('AUTH') or self._config.get('AUTH_MECHANISM', 'NOSASL')

            conn_params = {
                'host': self._config['HOST'],
                'port': self._config['PORT'],
                'database': db_name,
                'auth_mechanism': auth_mode,
            }

            # Add credentials for auth modes that require them
            if auth_mode in ['LDAP', 'CUSTOM', 'GSSAPI']:
                if auth_mode == 'GSSAPI':
                    conn_params['kerberos_service_name'] = self._config.get('KERBEROS_SERVICE_NAME', 'impala')
                else:
                    conn_params['user'] = self._config.get('USERNAME', '')
                    conn_params['password'] = self._config.get('PASSWORD', '')

            # SSL
            if self._config.get('USE_SSL'):
                conn_params['use_ssl'] = True

            conn = self._impyla_connect(**conn_params)

            pooled = PooledConnection(
                connection=conn,
                created_at=time.time(),
                last_used=time.time(),
                database=db_name,
                conn_type='impala',
            )

            logger.debug(f"Created new Impala connection to {db_name}")
            return pooled

        except Exception as e:
            logger.error(f"Failed to create Impala connection: {e}")
            return None

    def _validate_connection(self, pooled: PooledConnection) -> bool:
        """Validate if connection is still alive."""
        try:
            if pooled.age_seconds() > self._connection_timeout:
                return False

            cursor = pooled.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def _close_connection(self, pooled: PooledConnection):
        """Safely close a connection."""
        if pooled and pooled.connection:
            try:
                pooled.connection.close()
            except Exception:
                pass

    def get_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get connection from pool or create new one."""
        # Try to get from pool
        try:
            pooled = self._pool.get(block=False)
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
        except Empty:
            pass

        # Create new connection if under limit
        with self._pool_lock:
            if self._connection_count < self._max_connections:
                pooled = self._create_connection(database)
                if pooled:
                    self._connection_count += 1
                return pooled

        # Wait for available connection
        try:
            pooled = self._pool.get(timeout=30)
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
                return self._create_connection(database)
        except Empty:
            logger.error("Timeout waiting for Impala connection")
            return None

    def return_connection(self, pooled: PooledConnection) -> None:
        """Return connection to pool."""
        if pooled is None:
            return

        try:
            if self._validate_connection(pooled):
                try:
                    self._pool.put(pooled, block=False)
                except Full:
                    self._close_connection(pooled)
                    with self._pool_lock:
                        self._connection_count -= 1
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
        except Exception:
            self._close_connection(pooled)
            with self._pool_lock:
                self._connection_count -= 1

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """Context manager for Impala cursor."""
        pooled = None
        cursor = None
        try:
            pooled = self.get_connection(database)
            if pooled:
                cursor = pooled.connection.cursor()
                yield cursor
            else:
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_connection(pooled)

    def execute_query(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a read query via Impala."""
        if not self._impyla_available:
            logger.warning("Cannot execute query: impyla not available")
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
            logger.error(f"Impala query failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> bool:
        """Execute a write query via Impala (for Kudu tables)."""
        if not self._impyla_available:
            logger.warning("Cannot execute write: impyla not available")
            return False

        pooled = None
        cursor = None
        try:
            pooled = self.get_connection(database)
            if pooled is None:
                return False

            cursor = pooled.connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Commit for Kudu writes
            pooled.connection.commit()

            logger.debug("Impala write executed successfully")
            return True

        except Exception as e:
            logger.error(f"Impala write failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            if pooled and pooled.connection:
                try:
                    pooled.connection.rollback()
                except Exception:
                    pass
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_connection(pooled)

    def test_connection(self) -> bool:
        """Test if Impala connection is available."""
        if not self._impyla_available:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    return True
            return False
        except Exception as e:
            logger.error(f"Impala connection test failed: {e}")
            return False


# =============================================================================
# Hive Connection Handler (Single Responsibility - External Table Operations)
# =============================================================================

class HiveConnectionHandler(IConnectionReader, IConnectionWriter, IConnectionPool):
    """
    Handles Hive connections for external/managed table operations.

    Responsibilities:
    - Connection pooling for HiveServer2
    - Write operations on Hive external tables
    - DDL operations (CREATE EXTERNAL TABLE, etc.)
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._pool: Queue = Queue(maxsize=config.get('POOL_SIZE', 10))
        self._pool_lock = threading.Lock()
        self._connection_count = 0
        self._max_connections = config.get('POOL_SIZE', 10)
        self._connection_timeout = config.get('CONNECTION_MAX_AGE', 3600)

        # Check for pyhive or impyla availability
        self._hive_available = False
        self._use_impyla = False

        # Try impyla first (supports Kerberos better)
        try:
            from impala.dbapi import connect
            self._hive_connect = connect
            self._hive_available = True
            self._use_impyla = True
            logger.info("Using impyla for Hive connections")
        except ImportError:
            # Fall back to pyhive
            try:
                from pyhive import hive
                self._hive_connect = hive.Connection
                self._hive_available = True
                logger.info("Using pyhive for Hive connections")
            except ImportError:
                logger.warning("Neither impyla nor pyhive available for Hive connections")

        logger.info(
            f"HiveConnectionHandler initialized: "
            f"{config.get('HOST')}:{config.get('PORT')} "
            f"[pool_size={self._max_connections}]"
        )

    def _create_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Create a new Hive connection."""
        if not self._hive_available:
            return None

        try:
            db_name = database or self._config.get('DATABASE', 'default')
            # Support both AUTH and AUTH_MECHANISM keys for compatibility
            auth_mode = self._config.get('AUTH') or self._config.get('AUTH_MECHANISM', 'NOSASL')

            if self._use_impyla:
                # impyla connection
                conn_params = {
                    'host': self._config['HOST'],
                    'port': self._config['PORT'],
                    'database': db_name,
                    'auth_mechanism': auth_mode,
                }

                if auth_mode == 'GSSAPI':
                    conn_params['kerberos_service_name'] = self._config.get('KERBEROS_SERVICE_NAME', 'hive')
                elif auth_mode in ['LDAP', 'CUSTOM']:
                    conn_params['user'] = self._config.get('USERNAME', '')
                    conn_params['password'] = self._config.get('PASSWORD', '')

                if self._config.get('USE_SSL'):
                    conn_params['use_ssl'] = True

                conn = self._hive_connect(**conn_params)
            else:
                # pyhive connection
                conn_params = {
                    'host': self._config['HOST'],
                    'port': self._config['PORT'],
                    'database': db_name,
                    'auth': auth_mode if auth_mode != 'NOSASL' else 'NONE',
                }

                if auth_mode in ['LDAP', 'CUSTOM']:
                    conn_params['username'] = self._config.get('USERNAME', '')
                    conn_params['password'] = self._config.get('PASSWORD', '')

                conn = self._hive_connect(**conn_params)

            pooled = PooledConnection(
                connection=conn,
                created_at=time.time(),
                last_used=time.time(),
                database=db_name,
                conn_type='hive',
            )

            logger.debug(f"Created new Hive connection to {db_name}")
            return pooled

        except Exception as e:
            logger.error(f"Failed to create Hive connection: {e}")
            return None

    def _validate_connection(self, pooled: PooledConnection) -> bool:
        """Validate if connection is still alive."""
        try:
            if pooled.age_seconds() > self._connection_timeout:
                return False

            cursor = pooled.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def _close_connection(self, pooled: PooledConnection):
        """Safely close a connection."""
        if pooled and pooled.connection:
            try:
                pooled.connection.close()
            except Exception:
                pass

    def get_connection(self, database: Optional[str] = None) -> Optional[PooledConnection]:
        """Get connection from pool or create new one."""
        # Try to get from pool
        try:
            pooled = self._pool.get(block=False)
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
        except Empty:
            pass

        # Create new connection if under limit
        with self._pool_lock:
            if self._connection_count < self._max_connections:
                pooled = self._create_connection(database)
                if pooled:
                    self._connection_count += 1
                return pooled

        # Wait for available connection
        try:
            pooled = self._pool.get(timeout=30)
            if self._validate_connection(pooled):
                pooled.touch()
                return pooled
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
                return self._create_connection(database)
        except Empty:
            logger.error("Timeout waiting for Hive connection")
            return None

    def return_connection(self, pooled: PooledConnection) -> None:
        """Return connection to pool."""
        if pooled is None:
            return

        try:
            if self._validate_connection(pooled):
                try:
                    self._pool.put(pooled, block=False)
                except Full:
                    self._close_connection(pooled)
                    with self._pool_lock:
                        self._connection_count -= 1
            else:
                self._close_connection(pooled)
                with self._pool_lock:
                    self._connection_count -= 1
        except Exception:
            self._close_connection(pooled)
            with self._pool_lock:
                self._connection_count -= 1

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """Context manager for Hive cursor."""
        pooled = None
        cursor = None
        try:
            pooled = self.get_connection(database)
            if pooled:
                cursor = pooled.connection.cursor()
                yield cursor
            else:
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_connection(pooled)

    # YARN queue for Hive queries - use EOQ_QUEUE for better performance
    YARN_QUEUE = 'EOQ_QUEUE'

    def execute_query(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a read query via Hive with Tez engine."""
        if not self._hive_available:
            logger.warning("Cannot execute query: Hive not available")
            return []

        pooled = None
        cursor = None
        try:
            pooled = self.get_connection(database)
            if pooled is None:
                return []

            cursor = pooled.connection.cursor()

            # Set Tez execution engine and YARN queue for performance
            try:
                cursor.execute("SET hive.execution.engine=tez")
                cursor.execute(f"SET tez.queue.name={self.YARN_QUEUE}")
            except Exception as e:
                logger.warning(f"Could not set Tez settings, using defaults: {e}")

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
            logger.error(f"Hive query failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            return []
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_connection(pooled)

    def execute_write(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None) -> bool:
        """Execute a write query via Hive (for external tables).

        Uses Tez execution engine and EOQ_QUEUE for optimal performance.
        """
        if not self._hive_available:
            logger.warning("Cannot execute write: Hive not available")
            return False

        pooled = None
        cursor = None
        try:
            pooled = self.get_connection(database)
            if pooled is None:
                return False

            cursor = pooled.connection.cursor()

            # Set Tez execution engine and YARN queue for performance
            try:
                cursor.execute("SET hive.execution.engine=tez")
                cursor.execute(f"SET tez.queue.name={self.YARN_QUEUE}")
            except Exception as e:
                logger.warning(f"Could not set Tez settings, using defaults: {e}")

            logger.info(f"Executing Hive write on {self.YARN_QUEUE} queue")

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            logger.info("Hive write executed successfully")
            return True

        except Exception as e:
            logger.error(f"Hive write failed: {e}")
            logger.error(f"Query: {query[:200]}...")
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if pooled:
                self.return_connection(pooled)

    def test_connection(self) -> bool:
        """Test if Hive connection is available."""
        if not self._hive_available:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    return True
            return False
        except Exception as e:
            logger.error(f"Hive connection test failed: {e}")
            return False


# =============================================================================
# Hybrid Connection Manager (Facade Pattern + Dependency Inversion)
# =============================================================================

class HybridConnectionManager:
    """
    Facade for hybrid Impala/Hive connection management.

    Routes operations to the appropriate backend:
    - Kudu tables: Impala (port 21050)
    - Hive external tables: HiveServer2 (port 10000)

    This class depends on abstractions (IConnectionReader, IConnectionWriter)
    rather than concrete implementations, following Dependency Inversion Principle.
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

        # Get configuration from Django settings
        impala_config = getattr(settings, 'IMPALA_CONFIG', {
            'HOST': 'localhost',
            'PORT': 21050,
            'DATABASE': 'gmp_cis',
            'AUTH': 'NOSASL',
            'POOL_SIZE': 10,
            'CONNECTION_MAX_AGE': 3600,
        })

        hive_config = getattr(settings, 'HIVE_CONFIG', {
            'HOST': 'localhost',
            'PORT': 10000,
            'DATABASE': 'gmp_cis',
            'AUTH': 'NOSASL',
            'POOL_SIZE': 10,
            'CONNECTION_MAX_AGE': 3600,
        })

        # Initialize connection handlers (Dependency Injection)
        self._impala_handler = ImpalaConnectionHandler(impala_config)
        self._hive_handler = HiveConnectionHandler(hive_config)

        # Async executor for non-blocking writes
        self._async_executor = ThreadPoolExecutor(
            max_workers=5,
            thread_name_prefix='hybrid_async_'
        )
        self._async_futures: List[Future] = []
        self._async_lock = threading.Lock()

        self._initialized = True

        logger.info(
            f"HybridConnectionManager initialized:\n"
            f"  Impala (Kudu): {impala_config.get('HOST')}:{impala_config.get('PORT')}\n"
            f"  Hive (External): {hive_config.get('HOST')}:{hive_config.get('PORT')}"
        )

    # =========================================================================
    # Kudu Operations (via Impala)
    # =========================================================================

    def kudu_read(self, query: str, params: Optional[List] = None,
                  database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a read query on Kudu tables via Impala."""
        return self._impala_handler.execute_query(query, params, database)

    def kudu_write(self, query: str, params: Optional[List] = None,
                   database: Optional[str] = None) -> bool:
        """Execute a write query on Kudu tables via Impala."""
        return self._impala_handler.execute_write(query, params, database)

    # =========================================================================
    # Hive External Table Operations
    # =========================================================================

    def hive_read(self, query: str, params: Optional[List] = None,
                  database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a read query on Hive tables."""
        return self._hive_handler.execute_query(query, params, database)

    def hive_write(self, query: str, params: Optional[List] = None,
                   database: Optional[str] = None) -> bool:
        """Execute a write query on Hive external tables."""
        return self._hive_handler.execute_write(query, params, database)

    # =========================================================================
    # Generic Operations (Auto-routing)
    # =========================================================================

    def execute_query(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None,
                      use_hive: bool = False) -> List[Dict[str, Any]]:
        """
        Execute a read query.

        Args:
            query: SQL query
            params: Optional query parameters
            database: Database name
            use_hive: If True, use Hive; otherwise use Impala (default)

        Returns:
            List of dictionaries with query results
        """
        if use_hive:
            return self._hive_handler.execute_query(query, params, database)
        else:
            return self._impala_handler.execute_query(query, params, database)

    def execute_write(self, query: str, params: Optional[List] = None,
                      database: Optional[str] = None,
                      table_type: str = 'kudu') -> bool:
        """
        Execute a write query.

        Args:
            query: SQL query
            params: Optional query parameters
            database: Database name
            table_type: 'kudu' for Impala, 'hive' for HiveServer2

        Returns:
            True if successful, False otherwise
        """
        if table_type.lower() == 'hive':
            return self._hive_handler.execute_write(query, params, database)
        else:
            return self._impala_handler.execute_write(query, params, database)

    # =========================================================================
    # Async Operations
    # =========================================================================

    def execute_write_async(self, query: str, params: Optional[List] = None,
                            database: Optional[str] = None,
                            table_type: str = 'kudu',
                            callback: Optional[Callable[[bool], None]] = None) -> Future:
        """
        Execute a write query asynchronously.

        Args:
            query: SQL query
            params: Optional query parameters
            database: Database name
            table_type: 'kudu' or 'hive'
            callback: Optional callback function(success: bool)

        Returns:
            Future object for tracking completion
        """
        def _async_write():
            try:
                success = self.execute_write(query, params, database, table_type)
                if callback:
                    callback(success)
                return success
            except Exception as e:
                logger.error(f"Async write failed: {e}")
                if callback:
                    callback(False)
                return False

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

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def test_connections(self) -> Dict[str, bool]:
        """Test both Impala and Hive connections."""
        return {
            'impala': self._impala_handler.test_connection(),
            'hive': self._hive_handler.test_connection(),
        }

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            'impala': {
                'active_connections': self._impala_handler._connection_count,
                'max_connections': self._impala_handler._max_connections,
            },
            'hive': {
                'active_connections': self._hive_handler._connection_count,
                'max_connections': self._hive_handler._max_connections,
            },
            'async_pending': len([f for f in self._async_futures if not f.done()]),
        }

    # =========================================================================
    # Context Managers
    # =========================================================================

    @contextmanager
    def get_impala_cursor(self, database: Optional[str] = None):
        """Context manager for Impala cursor (Kudu operations)."""
        with self._impala_handler.get_cursor(database) as cursor:
            yield cursor

    @contextmanager
    def get_hive_cursor(self, database: Optional[str] = None):
        """Context manager for Hive cursor (external table operations)."""
        with self._hive_handler.get_cursor(database) as cursor:
            yield cursor


# =============================================================================
# Global Instances
# =============================================================================

hybrid_manager = HybridConnectionManager()

# Backward compatibility aliases
impala_manager = hybrid_manager  # For existing code using impala_manager
hive_manager = hybrid_manager    # For existing code using hive_manager

__all__ = [
    'hybrid_manager',
    'impala_manager',
    'hive_manager',
    'HybridConnectionManager',
    'ImpalaConnectionHandler',
    'HiveConnectionHandler',
]
