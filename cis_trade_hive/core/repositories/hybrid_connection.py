"""
Hybrid Connection Manager for CML (Cloudera Machine Learning)

Uses impyla for BOTH Impala and Hive connections (more reliable in Cloudera):
- Impala: Fast reads (SELECT queries) - port 21050
- Hive: ACID writes (INSERT, UPDATE, DELETE) - port 10000

Both use Kerberos (GSSAPI) authentication via impyla + pure-sasl.

Requirements:
    pip install pure-sasl thrift-sasl impyla

Configuration (settings.py):
    IMPALA_CONFIG = {
        'HOST': 'impala-host',
        'PORT': 21050,
        'DATABASE': 'gmp_cis',
        'AUTH_MECHANISM': 'GSSAPI',
        'KERBEROS_SERVICE_NAME': 'impala',
    }

    HIVE_CONFIG = {
        'HOST': 'hive-host',
        'PORT': 10000,
        'DATABASE': 'mrw_ima',
        'AUTH': 'GSSAPI',
        'KERBEROS_SERVICE_NAME': 'hive',
    }
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

# Try importing impyla (used for both Impala and Hive)
try:
    from impala.dbapi import connect as impyla_connect
    IMPYLA_AVAILABLE = True
except ImportError:
    IMPYLA_AVAILABLE = False
    logger.warning("impyla not available. Database features will be disabled.")


class HybridConnectionManager:
    """
    Hybrid Connection Manager for CML environments.

    Uses impyla for both Impala (reads) and Hive (writes) connections.
    This is more reliable than pyhive in Cloudera environments.

    Features:
    - Impala for fast reads (via impyla)
    - Hive for ACID writes (via impyla connecting to HiveServer2)
    - Kerberos authentication without native SASL libraries
    - Separate connection pools for each
    - Connection validation and recycling
    - Async write support for audit/history operations
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
        if not hasattr(self, '_initialized'):
            # Read IMPALA_CONFIG from settings
            impala_config = getattr(settings, 'IMPALA_CONFIG', {})
            self._impala_config = {
                'HOST': impala_config.get('HOST', 'localhost'),
                'PORT': int(impala_config.get('PORT', 21050)),
                'DATABASE': impala_config.get('DATABASE', 'gmp_cis'),
                'AUTH_MECHANISM': impala_config.get('AUTH_MECHANISM', impala_config.get('AUTH', 'GSSAPI')),
                'TIMEOUT': int(impala_config.get('TIMEOUT', 120)),
                'POOL_SIZE': int(impala_config.get('POOL_SIZE', 10)),
                'USE_SSL': impala_config.get('USE_SSL', True),
                'KERBEROS_SERVICE_NAME': impala_config.get('KERBEROS_SERVICE_NAME', 'impala'),
            }

            # Read HIVE_CONFIG from settings
            hive_config = getattr(settings, 'HIVE_CONFIG', {})
            self._hive_config = {
                'HOST': hive_config.get('HOST', 'localhost'),
                'PORT': int(hive_config.get('PORT', 10000)),
                'DATABASE': hive_config.get('DATABASE', 'gmp_cis'),
                'AUTH_MECHANISM': hive_config.get('AUTH', 'GSSAPI'),
                'TIMEOUT': int(hive_config.get('TIMEOUT', 120)),
                'POOL_SIZE': int(hive_config.get('POOL_SIZE', 10)),
                'USE_SSL': hive_config.get('USE_SSL', False),
                'KERBEROS_SERVICE_NAME': hive_config.get('KERBEROS_SERVICE_NAME', 'hive'),
            }

            # Separate pools for Impala (reads) and Hive (writes)
            self._impala_pool = Queue(maxsize=self._impala_config['POOL_SIZE'])
            self._hive_pool = Queue(maxsize=self._hive_config['POOL_SIZE'])

            self._impala_pool_lock = threading.Lock()
            self._hive_pool_lock = threading.Lock()

            self._impala_connection_count = 0
            self._hive_connection_count = 0
            self._connection_timeout = 3600  # 1 hour

            # Thread pool for async writes
            self._async_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='hybrid_async_')
            self._async_futures = []

            self._initialized = True
            logger.info(
                f"Hybrid connection manager initialized (using impyla for both):\n"
                f"  Impala (reads): {self._impala_config['HOST']}:{self._impala_config['PORT']} "
                f"[{self._impala_config['AUTH_MECHANISM']}]\n"
                f"  Hive (writes): {self._hive_config['HOST']}:{self._hive_config['PORT']} "
                f"[{self._hive_config['AUTH_MECHANISM']}]"
            )

    # ==================== IMPALA CONNECTIONS (READS) ====================

    def _create_impala_connection(self, database: Optional[str] = None):
        """Create a new Impala connection for reads using impyla."""
        if not IMPYLA_AVAILABLE:
            logger.warning("Impala connection requested but impyla not available")
            return None

        try:
            db_name = database or self._impala_config['DATABASE']
            auth_mechanism = self._impala_config['AUTH_MECHANISM']

            conn_params = {
                'host': self._impala_config['HOST'],
                'port': self._impala_config['PORT'],
                'database': db_name,
                'timeout': self._impala_config['TIMEOUT'],
                'auth_mechanism': auth_mechanism,
            }

            # Kerberos authentication
            if auth_mechanism == 'GSSAPI':
                conn_params['kerberos_service_name'] = self._impala_config['KERBEROS_SERVICE_NAME']
                if self._impala_config['USE_SSL']:
                    conn_params['use_ssl'] = True

            connection = impyla_connect(**conn_params)
            connection._created_at = time.time()
            connection._database = db_name
            connection._conn_type = 'impala'

            logger.debug(f"Created new Impala connection to {db_name} [{auth_mechanism}]")
            return connection

        except Exception as e:
            logger.error(f"Failed to create Impala connection: {str(e)}")
            return None

    def _validate_impala_connection(self, connection) -> bool:
        """Validate if Impala connection is still alive."""
        try:
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    return False

            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def get_impala_connection(self, database: Optional[str] = None):
        """Get an Impala connection for reads."""
        if not IMPYLA_AVAILABLE:
            return None

        # Try to get from pool
        try:
            connection = self._impala_pool.get(block=False)
            if self._validate_impala_connection(connection):
                return connection
            else:
                self._close_connection(connection)
                with self._impala_pool_lock:
                    self._impala_connection_count -= 1
        except Empty:
            pass

        # Create new connection if pool not full
        with self._impala_pool_lock:
            if self._impala_connection_count < self._impala_config['POOL_SIZE']:
                connection = self._create_impala_connection(database)
                if connection:
                    self._impala_connection_count += 1
                return connection
            else:
                # Wait for available connection
                try:
                    connection = self._impala_pool.get(timeout=30)
                    if self._validate_impala_connection(connection):
                        return connection
                    else:
                        self._close_connection(connection)
                        self._impala_connection_count -= 1
                        return self._create_impala_connection(database)
                except Empty:
                    logger.error("Timeout waiting for Impala connection")
                    return None

    def return_impala_connection(self, connection):
        """Return an Impala connection to the pool."""
        if connection is None:
            return

        try:
            if self._validate_impala_connection(connection):
                try:
                    self._impala_pool.put(connection, block=False)
                except Full:
                    self._close_connection(connection)
                    with self._impala_pool_lock:
                        self._impala_connection_count -= 1
            else:
                self._close_connection(connection)
                with self._impala_pool_lock:
                    self._impala_connection_count -= 1
        except Exception:
            self._close_connection(connection)
            with self._impala_pool_lock:
                self._impala_connection_count -= 1

    # ==================== HIVE CONNECTIONS (WRITES) ====================

    def _create_hive_connection(self, database: Optional[str] = None):
        """
        Create a new Hive connection for ACID writes using impyla.

        Connection settings based on working Cloudera DataViz config:
        - Connection mode: Binary
        - Socket type: Normal (no SSL)
        - Authentication: Kerberos (GSSAPI)
        - Kerberos service name: hive
        """
        if not IMPYLA_AVAILABLE:
            logger.warning("Hive connection requested but impyla not available")
            return None

        try:
            db_name = database or self._hive_config['DATABASE']
            auth_mechanism = self._hive_config['AUTH_MECHANISM']

            # Base connection parameters matching Cloudera DataViz settings
            conn_params = {
                'host': self._hive_config['HOST'],
                'port': self._hive_config['PORT'],
                'database': db_name,
                'timeout': self._hive_config['TIMEOUT'],
                'auth_mechanism': auth_mechanism,
                'use_ssl': False,  # Normal socket, not SSL (matching DataViz)
            }

            # Kerberos authentication
            if auth_mechanism == 'GSSAPI':
                conn_params['kerberos_service_name'] = self._hive_config['KERBEROS_SERVICE_NAME']

            logger.info(f"Connecting to Hive: {conn_params['host']}:{conn_params['port']} "
                       f"db={db_name} auth={auth_mechanism} "
                       f"krb_service={conn_params.get('kerberos_service_name', 'N/A')}")

            connection = impyla_connect(**conn_params)
            connection._created_at = time.time()
            connection._database = db_name
            connection._conn_type = 'hive'

            logger.debug(f"Created new Hive connection to {db_name} [{auth_mechanism}]")
            return connection

        except Exception as e:
            logger.error(f"Failed to create Hive connection: {str(e)}")
            logger.error(f"Connection params: host={self._hive_config['HOST']} "
                        f"port={self._hive_config['PORT']} auth={auth_mechanism}")
            return None

    def _validate_hive_connection(self, connection) -> bool:
        """Validate if Hive connection is still alive."""
        try:
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    return False

            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def get_hive_connection(self, database: Optional[str] = None):
        """Get a Hive connection for writes."""
        if not IMPYLA_AVAILABLE:
            return None

        # Try to get from pool
        try:
            connection = self._hive_pool.get(block=False)
            if self._validate_hive_connection(connection):
                return connection
            else:
                self._close_connection(connection)
                with self._hive_pool_lock:
                    self._hive_connection_count -= 1
        except Empty:
            pass

        # Create new connection if pool not full
        with self._hive_pool_lock:
            if self._hive_connection_count < self._hive_config['POOL_SIZE']:
                connection = self._create_hive_connection(database)
                if connection:
                    self._hive_connection_count += 1
                return connection
            else:
                # Wait for available connection
                try:
                    connection = self._hive_pool.get(timeout=30)
                    if self._validate_hive_connection(connection):
                        return connection
                    else:
                        self._close_connection(connection)
                        self._hive_connection_count -= 1
                        return self._create_hive_connection(database)
                except Empty:
                    logger.error("Timeout waiting for Hive connection")
                    return None

    def return_hive_connection(self, connection):
        """Return a Hive connection to the pool."""
        if connection is None:
            return

        try:
            if self._validate_hive_connection(connection):
                try:
                    self._hive_pool.put(connection, block=False)
                except Full:
                    self._close_connection(connection)
                    with self._hive_pool_lock:
                        self._hive_connection_count -= 1
            else:
                self._close_connection(connection)
                with self._hive_pool_lock:
                    self._hive_connection_count -= 1
        except Exception:
            self._close_connection(connection)
            with self._hive_pool_lock:
                self._hive_connection_count -= 1

    # ==================== HELPER METHODS ====================

    def _close_connection(self, connection):
        """Safely close a connection."""
        if connection:
            try:
                connection.close()
            except Exception:
                pass

    @contextmanager
    def get_read_cursor(self, database: Optional[str] = None):
        """Context manager for Impala cursor (reads)."""
        connection = None
        cursor = None
        try:
            connection = self.get_impala_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                # Fallback to Hive if Impala not available
                logger.warning("Impala not available, falling back to Hive for read")
                connection = self.get_hive_connection(database)
                if connection:
                    cursor = connection.cursor()
                    yield cursor
                else:
                    yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection:
                if getattr(connection, '_conn_type', '') == 'impala':
                    self.return_impala_connection(connection)
                else:
                    self.return_hive_connection(connection)

    @contextmanager
    def get_write_cursor(self, database: Optional[str] = None):
        """Context manager for Hive cursor (writes)."""
        connection = None
        cursor = None
        try:
            connection = self.get_hive_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection:
                self.return_hive_connection(connection)

    # Backward compatibility alias
    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """Backward compatible cursor (uses Impala for reads)."""
        with self.get_read_cursor(database) as cursor:
            yield cursor

    # ==================== QUERY EXECUTION ====================

    def execute_query(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a READ query via Impala (fast)."""
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    logger.error("No cursor available for read query")
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
            logger.error(f"Failed to execute read query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None, use_mr_engine: bool = True) -> bool:
        """Execute a WRITE query (INSERT, UPDATE, DELETE) via Hive (ACID)."""
        connection = None
        cursor = None
        try:
            connection = self.get_hive_connection(database)
            if connection is None:
                logger.error("No Hive connection available for write query")
                return False

            cursor = connection.cursor()

            # Set MapReduce engine for ACID operations (if needed)
            if use_mr_engine:
                try:
                    cursor.execute("SET hive.execution.engine=mr")
                except Exception:
                    # Ignore if setting fails (might not be needed)
                    pass

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            logger.debug("Hive write query executed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection:
                self.return_hive_connection(connection)

    # ==================== ASYNC WRITES ====================

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
        except Exception as e:
            logger.error(f"Failed to queue async write: {str(e)}")
            # Fallback to sync
            self.execute_write(query, params, database)

    def _cleanup_futures(self):
        """Remove completed futures."""
        self._async_futures = [f for f in self._async_futures if not f.done()]

    def wait_for_async_writes(self, timeout: float = 30.0) -> int:
        """Wait for all pending async writes to complete."""
        completed = 0
        for future in self._async_futures:
            try:
                future.result(timeout=timeout)
                completed += 1
            except Exception as e:
                logger.error(f"Async write failed: {str(e)}")
        self._async_futures.clear()
        return completed

    def get_async_queue_size(self) -> int:
        """Get number of pending async write operations."""
        self._cleanup_futures()
        return len(self._async_futures)

    # ==================== UTILITY METHODS ====================

    def test_connection(self) -> Dict[str, bool]:
        """Test both Impala and Hive connections."""
        results = {'impala': False, 'hive': False}

        # Test Impala
        if IMPYLA_AVAILABLE:
            try:
                with self.get_read_cursor() as cursor:
                    if cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        results['impala'] = result is not None
                        logger.info(f"Impala connection test: SUCCESS")
            except Exception as e:
                logger.error(f"Impala connection test failed: {str(e)}")

        # Test Hive
        if IMPYLA_AVAILABLE:
            try:
                with self.get_write_cursor() as cursor:
                    if cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        results['hive'] = result is not None
                        logger.info(f"Hive connection test: SUCCESS")
            except Exception as e:
                logger.error(f"Hive connection test failed: {str(e)}")

        return results

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables (via Impala for speed)."""
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    return []
                cursor.execute("SHOW TABLES")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tables: {str(e)}")
            return []

    def describe_table(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get table schema information."""
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    return []
                cursor.execute(f"DESCRIBE {table_name}")
                columns = [desc[0].split('.')[-1] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to describe table {table_name}: {str(e)}")
            return []

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            'impala': {
                'host': self._impala_config['HOST'],
                'port': self._impala_config['PORT'],
                'auth': self._impala_config['AUTH_MECHANISM'],
                'active': self._impala_connection_count,
                'max': self._impala_config['POOL_SIZE'],
                'available': IMPYLA_AVAILABLE,
            },
            'hive': {
                'host': self._hive_config['HOST'],
                'port': self._hive_config['PORT'],
                'auth': self._hive_config['AUTH_MECHANISM'],
                'active': self._hive_connection_count,
                'max': self._hive_config['POOL_SIZE'],
                'available': IMPYLA_AVAILABLE,
            },
            'async_pending': len([f for f in self._async_futures if not f.done()]),
        }


# Global instance
hybrid_manager = HybridConnectionManager()

# Backward compatibility aliases
hive_manager = hybrid_manager
impala_manager = hybrid_manager
