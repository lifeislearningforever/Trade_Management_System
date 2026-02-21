"""
Hybrid Connection Manager for CML (Cloudera Machine Learning)

Architecture:
- Impala: Fast reads (SELECT queries) via impyla - port 21050
- Hive: ACID writes (INSERT, UPDATE, DELETE) via beeline subprocess
- REST Proxy: All operations via REST API (best for CML with glibc issues)

Connection Modes (controlled by USE_REST_PROXY env var):
1. USE_REST_PROXY=true: All operations go through REST proxy on edge node
2. USE_REST_PROXY=false (default): Direct Impala/Hive connections

The REST Proxy mode is required in CML because:
1. CML Docker containers have old glibc that breaks native SASL
2. Kerberos/GSSAPI authentication fails with TSocket errors
3. REST proxy on edge node handles all authentication

Requirements:
    pip install pure-sasl thrift-sasl impyla requests

Configuration (settings.py or environment):
    USE_REST_PROXY=true
    HIVE_PROXY_URL=http://edge-node:5000
    HIVE_DATABASE=mrw_ima
"""

import os
import logging
import threading
import time
from typing import Optional, Any, List, Dict, Callable
from contextlib import contextmanager
from queue import Queue, Empty, Full
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('core')

# Check if REST proxy mode is enabled
USE_REST_PROXY = os.environ.get('USE_REST_PROXY', 'false').lower() == 'true'
HIVE_PROXY_URL = os.environ.get('HIVE_PROXY_URL', '')
HIVE_DATABASE = os.environ.get('HIVE_DATABASE', 'mrw_ima')
HIVE_TIMEOUT = int(os.environ.get('HIVE_TIMEOUT', '300'))

# REST proxy client (using requests library)
REQUESTS_AVAILABLE = False
if USE_REST_PROXY:
    try:
        import requests
        REQUESTS_AVAILABLE = True
        logger.info(f"REST Proxy mode enabled: {HIVE_PROXY_URL}")
    except ImportError:
        logger.error("requests library not available for REST proxy mode")

# Try importing impyla (used for Impala reads when not in proxy mode)
IMPYLA_AVAILABLE = False
if not USE_REST_PROXY:
    try:
        from impala.dbapi import connect as impyla_connect
        IMPYLA_AVAILABLE = True
    except ImportError:
        logger.warning("impyla not available. Impala read features will be disabled.")

    # Import beeline executor for Hive writes
    try:
        from core.repositories.hive_beeline_executor import hive_executor
        BEELINE_AVAILABLE = True
    except ImportError:
        BEELINE_AVAILABLE = False
        logger.warning("HiveBeelineExecutor not available.")
else:
    BEELINE_AVAILABLE = False

# Try importing Django settings (may not be available during startup)
try:
    from django.conf import settings
    DJANGO_AVAILABLE = True
except ImportError:
    settings = None
    DJANGO_AVAILABLE = False


class HybridConnectionManager:
    """
    Hybrid Connection Manager for CML environments.

    Supports two modes:
    1. REST Proxy Mode (USE_REST_PROXY=true): All operations via REST API
    2. Direct Mode: Impala for reads, Hive for writes

    Features:
    - REST Proxy mode for CML where native libs don't work
    - Impala for fast reads (via impyla) in direct mode
    - Hive for ACID writes in direct mode
    - Connection pooling and validation
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
        if not hasattr(self, '_initialized'):
            # Check if using REST proxy mode
            self._use_proxy = USE_REST_PROXY
            self._proxy_url = HIVE_PROXY_URL
            self._proxy_timeout = HIVE_TIMEOUT
            self._proxy_database = HIVE_DATABASE
            self._proxy_session = None

            if self._use_proxy:
                # REST Proxy mode - no direct connections needed
                logger.info(
                    f"Hybrid connection manager initialized (REST PROXY MODE):\n"
                    f"  Proxy URL: {self._proxy_url}\n"
                    f"  Database: {self._proxy_database}\n"
                    f"  Timeout: {self._proxy_timeout}s"
                )
                self._initialized = True
                self._async_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='hybrid_async_')
                self._async_futures = []
                return

            # Direct connection mode - read config from Django settings
            impala_config = getattr(settings, 'IMPALA_CONFIG', {}) if DJANGO_AVAILABLE else {}
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

            hive_config = getattr(settings, 'HIVE_CONFIG', {}) if DJANGO_AVAILABLE else {}
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
                f"Hybrid connection manager initialized (DIRECT MODE):\n"
                f"  Impala (reads): {self._impala_config['HOST']}:{self._impala_config['PORT']} "
                f"[{self._impala_config['AUTH_MECHANISM']}]\n"
                f"  Hive (writes): {self._hive_config['HOST']}:{self._hive_config['PORT']} "
                f"[{self._hive_config['AUTH_MECHANISM']}]"
            )

    # ==================== REST PROXY METHODS ====================

    def _get_proxy_session(self):
        """Get or create HTTP session for REST proxy."""
        if self._proxy_session is None:
            import requests
            self._proxy_session = requests.Session()
            self._proxy_session.headers.update({
                'Content-Type': 'application/json',
                'X-User': os.environ.get('USER', 'hybrid_manager')
            })
            api_key = os.environ.get('HIVE_PROXY_API_KEY', '')
            if api_key:
                self._proxy_session.headers['X-API-Key'] = api_key
        return self._proxy_session

    def _proxy_request(self, endpoint: str, method: str = 'GET',
                       data: dict = None, timeout: int = None) -> Dict:
        """Make HTTP request to REST proxy."""
        url = f"{self._proxy_url}{endpoint}"
        request_timeout = timeout or self._proxy_timeout

        try:
            session = self._get_proxy_session()
            if method == 'GET':
                response = session.get(url, timeout=request_timeout + 10)
            else:
                response = session.post(url, json=data, timeout=request_timeout + 10)

            result = response.json()

            if response.status_code == 200 and result.get('success'):
                return result
            else:
                error = result.get('error', f'HTTP {response.status_code}')
                logger.error(f"Proxy request failed: {error}")
                raise RuntimeError(f"Proxy error: {error}")

        except Exception as e:
            if 'Timeout' in str(type(e).__name__):
                raise RuntimeError("Request timeout")
            raise

    def _proxy_execute_query(self, sql: str, database: str = None) -> List[Dict[str, Any]]:
        """Execute SELECT query via REST proxy."""
        result = self._proxy_request('/query', method='POST', data={
            'sql': sql,
            'database': database or self._proxy_database
        })
        return result.get('data', [])

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
        """Context manager for Impala cursor (reads). Not available in proxy mode."""
        if self._use_proxy:
            logger.warning("get_read_cursor called in proxy mode - use execute_query instead")
            yield None
            return

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
        """Context manager for Hive cursor (writes). Not available in proxy mode."""
        if self._use_proxy:
            logger.warning("get_write_cursor called in proxy mode - use execute_write instead")
            yield None
            return

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
        """
        Execute a READ query.

        In REST Proxy mode: Uses REST API for reads
        In Direct mode: Uses Impala for fast reads
        """
        # Format query with params if provided
        if params:
            try:
                formatted_query = query % tuple(
                    f"'{p}'" if isinstance(p, str) else str(p) for p in params
                )
            except Exception:
                formatted_query = query
        else:
            formatted_query = query

        # REST Proxy mode - use proxy for reads
        if self._use_proxy:
            try:
                return self._proxy_execute_query(formatted_query, database or self._proxy_database)
            except Exception as e:
                logger.error(f"REST Proxy query failed: {str(e)}")
                logger.error(f"Query: {formatted_query[:200]}...")
                return []

        # Direct mode - use Impala for fast reads
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    logger.error("No cursor available for read query")
                    return []

                cursor.execute(formatted_query)

                if cursor.description:
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                return []

        except Exception as e:
            logger.error(f"Failed to execute read query: {str(e)}")
            logger.error(f"Query: {formatted_query[:200]}...")
            return []

    def _proxy_execute_write(self, sql: str, database: str = None,
                              operation: str = 'execute') -> bool:
        """
        Execute WRITE query via REST proxy.

        Supports:
        - /execute endpoint for raw SQL (INSERT, UPDATE, DELETE)
        - /insert, /update, /delete endpoints for structured operations
        """
        try:
            result = self._proxy_request('/execute', method='POST', data={
                'sql': sql,
                'database': database or self._proxy_database
            })
            logger.debug(f"REST Proxy write successful: {result.get('elapsed_ms', 'N/A')}ms")
            return True
        except Exception as e:
            logger.error(f"REST Proxy write failed: {str(e)}")
            raise

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None, use_mr_engine: bool = True) -> bool:
        """
        Execute a WRITE query (INSERT, UPDATE, DELETE) via Hive.

        In REST Proxy mode: Uses REST API with YARN queue support
        In Direct mode: Priority order:
            1. Beeline subprocess (good for edge node)
            2. Direct impyla connection (fallback)
        """
        # Format query with params if provided
        if params:
            # Simple parameter substitution (for %s style params)
            try:
                formatted_query = query % tuple(
                    f"'{p}'" if isinstance(p, str) else str(p) for p in params
                )
            except Exception:
                formatted_query = query
        else:
            formatted_query = query

        # REST Proxy mode - use proxy for all writes
        if self._use_proxy:
            try:
                return self._proxy_execute_write(formatted_query, database or self._proxy_database)
            except Exception as e:
                logger.error(f"REST Proxy write failed: {str(e)}")
                return False

        # Direct mode - Try beeline first (for edge node or local)
        if BEELINE_AVAILABLE:
            try:
                return hive_executor.execute_write(formatted_query, database=database)
            except Exception as e:
                logger.warning(f"Beeline write failed, trying direct connection: {str(e)}")

        # Fallback to direct impyla connection
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
                    pass

            cursor.execute(formatted_query)

            logger.debug("Hive write query executed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {formatted_query[:200]}...")
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
        results = {'impala': False, 'hive': False, 'hive_method': 'none', 'mode': 'direct'}

        # REST Proxy mode - test via proxy endpoints
        if self._use_proxy:
            results['mode'] = 'rest_proxy'
            try:
                # Test health endpoint first
                health_result = self._proxy_request('/health', method='GET')
                if health_result.get('success'):
                    results['hive'] = True
                    results['hive_method'] = 'rest_proxy'
                    logger.info("REST Proxy connection test: SUCCESS (health check)")

                    # Also test a simple query
                    query_result = self._proxy_execute_query("SELECT 1 as test_col")
                    if query_result:
                        results['impala'] = True  # Proxy handles reads too
                        logger.info("REST Proxy query test: SUCCESS")
            except Exception as e:
                logger.error(f"REST Proxy connection test failed: {str(e)}")
            return results

        # Direct mode - Test Impala (via impyla)
        if IMPYLA_AVAILABLE:
            try:
                with self.get_read_cursor() as cursor:
                    if cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        results['impala'] = result is not None
                        logger.info("Impala connection test: SUCCESS")
            except Exception as e:
                logger.error(f"Impala connection test failed: {str(e)}")

        # Test Hive via beeline
        if BEELINE_AVAILABLE:
            try:
                results['hive'] = hive_executor.test_connection()
                results['hive_method'] = 'beeline'
                if results['hive']:
                    logger.info("Hive connection test (beeline): SUCCESS")
                else:
                    logger.error("Hive connection test (beeline): FAILED")
            except Exception as e:
                logger.error(f"Hive beeline test failed: {str(e)}")

        # Fallback: Test Hive via direct impyla (usually fails in Cloudera)
        if not results['hive'] and IMPYLA_AVAILABLE:
            try:
                with self.get_write_cursor() as cursor:
                    if cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        results['hive'] = result is not None
                        results['hive_method'] = 'impyla'
                        logger.info("Hive connection test: SUCCESS")
            except Exception as e:
                logger.error(f"Hive connection test failed: {str(e)}")

        return results

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables."""
        db = database or (self._proxy_database if self._use_proxy else None)

        # REST Proxy mode
        if self._use_proxy:
            try:
                results = self._proxy_execute_query("SHOW TABLES", db)
                # Handle different result formats
                if results:
                    first_key = list(results[0].keys())[0] if results[0] else 'tab_name'
                    return [row.get(first_key, '') for row in results]
                return []
            except Exception as e:
                logger.error(f"Failed to get tables via proxy: {str(e)}")
                return []

        # Direct mode - use Impala for speed
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
        db = database or (self._proxy_database if self._use_proxy else None)

        # REST Proxy mode
        if self._use_proxy:
            try:
                query = f"DESCRIBE {table_name}"
                return self._proxy_execute_query(query, db)
            except Exception as e:
                logger.error(f"Failed to describe table {table_name} via proxy: {str(e)}")
                return []

        # Direct mode
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
        # REST Proxy mode - different stats
        if self._use_proxy:
            return {
                'mode': 'rest_proxy',
                'proxy': {
                    'url': self._proxy_url,
                    'database': self._proxy_database,
                    'timeout': self._proxy_timeout,
                    'available': REQUESTS_AVAILABLE,
                },
                'impala': {'available': False, 'reason': 'Using REST proxy'},
                'hive': {'available': False, 'reason': 'Using REST proxy'},
                'async_pending': len([f for f in self._async_futures if not f.done()]),
            }

        # Direct mode stats
        return {
            'mode': 'direct',
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
                'beeline_available': BEELINE_AVAILABLE,
            },
            'proxy': {
                'url': os.environ.get('HIVE_PROXY_URL', 'not configured'),
                'available': False,
            },
            'async_pending': len([f for f in self._async_futures if not f.done()]),
        }


# Global instance
hybrid_manager = HybridConnectionManager()

# Backward compatibility aliases
hive_manager = hybrid_manager
impala_manager = hybrid_manager
