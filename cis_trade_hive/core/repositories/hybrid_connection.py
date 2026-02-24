"""
Hybrid Connection Manager for CML (Cloudera Machine Learning)

Architecture:
- Impala: Fast reads (SELECT queries) via impyla - port 21050 (ALWAYS used for reads)
- Hive/REST Proxy: ACID writes (INSERT, UPDATE, DELETE) with Tez engine

Connection Modes (controlled by USE_REST_PROXY env var):
1. USE_REST_PROXY=true: Impala for reads, REST Proxy for writes
2. USE_REST_PROXY=false (default): Impala for reads, Direct Hive for writes

The REST Proxy mode for WRITES is required in CML because:
1. CML Docker containers have old glibc that breaks native SASL for Hive
2. Kerberos/GSSAPI authentication fails with TSocket errors on Hive
3. REST proxy on edge node handles all Hive authentication

IMPORTANT: Impala reads work fine in CML (different auth mechanism)

Performance Optimization:
- Tez execution engine for fast writes (SET hive.execution.engine=tez)
- Connection pooling with configurable age-out
- Session initialization with optimization flags
- Async write support for non-blocking operations

Requirements:
    pip install pure-sasl thrift-sasl impyla requests

Configuration (settings.py or environment):
    USE_REST_PROXY=true      # Only affects WRITES
    HIVE_PROXY_URL=http://edge-node:5000
    HIVE_DATABASE=mrw_ima
    HIVE_EXECUTION_ENGINE=tez  # or mr for MapReduce
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

# Check if REST proxy mode is enabled (for WRITES only)
USE_REST_PROXY = os.environ.get('USE_REST_PROXY', 'false').lower() == 'true'
HIVE_PROXY_URL = os.environ.get('HIVE_PROXY_URL', '')
HIVE_DATABASE = os.environ.get('HIVE_DATABASE', 'mrw_ima')
HIVE_TIMEOUT = int(os.environ.get('HIVE_TIMEOUT', '300'))

# Execution engine (tez is faster than mr for most operations)
HIVE_EXECUTION_ENGINE = os.environ.get('HIVE_EXECUTION_ENGINE', 'tez')
HIVE_ALWAYS_USE_TEZ = os.environ.get('HIVE_ALWAYS_USE_TEZ', 'true').lower() == 'true'

# Connection pool settings
HIVE_CONNECTION_MAX_AGE = int(os.environ.get('HIVE_CONNECTION_MAX_AGE', '3600'))  # 1 hour
HIVE_POOL_MIN_SIZE = int(os.environ.get('HIVE_POOL_MIN_SIZE', '2'))

# Session initialization statements for Tez optimization
HIVE_INIT_STATEMENTS = [
    f"SET hive.execution.engine={HIVE_EXECUTION_ENGINE}",
    # Additional optimizations can be added here
]

# REST proxy client (using requests library) - for WRITES only
REQUESTS_AVAILABLE = False
if USE_REST_PROXY:
    try:
        import requests
        REQUESTS_AVAILABLE = True
        logger.info(f"REST Proxy mode enabled for WRITES: {HIVE_PROXY_URL}")
    except ImportError:
        logger.error("requests library not available for REST proxy mode")

# ALWAYS try to import impyla - Impala is ALWAYS used for reads
IMPYLA_AVAILABLE = False
try:
    from impala.dbapi import connect as impyla_connect
    IMPYLA_AVAILABLE = True
    logger.info("Impala (impyla) available for READS")
except ImportError:
    logger.warning("impyla not available. Impala read features will be disabled.")

# Import beeline executor for Hive writes (fallback when not using proxy)
BEELINE_AVAILABLE = False
if not USE_REST_PROXY:
    try:
        from core.repositories.hive_beeline_executor import hive_executor
        BEELINE_AVAILABLE = True
    except ImportError:
        logger.warning("HiveBeelineExecutor not available.")

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
            # Check if using REST proxy mode (for WRITES only)
            self._use_proxy = USE_REST_PROXY
            self._proxy_url = HIVE_PROXY_URL
            self._proxy_timeout = HIVE_TIMEOUT
            self._proxy_database = HIVE_DATABASE
            self._proxy_session = None

            # ALWAYS initialize Impala config - Impala is ALWAYS used for reads
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

            # Impala pool for reads (ALWAYS available)
            self._impala_pool = Queue(maxsize=self._impala_config['POOL_SIZE'])
            self._impala_pool_lock = threading.Lock()
            self._impala_connection_count = 0
            self._connection_timeout = HIVE_CONNECTION_MAX_AGE

            # Execution engine configuration
            self._execution_engine = HIVE_EXECUTION_ENGINE
            self._always_use_tez = HIVE_ALWAYS_USE_TEZ
            self._init_statements = HIVE_INIT_STATEMENTS

            # Track initialized connections
            self._initialized_connections = set()

            # Thread pool for async writes
            self._async_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='hybrid_async_')
            self._async_futures = []

            if self._use_proxy:
                # REST Proxy mode for WRITES - Impala still used for reads
                self._hive_config = None
                self._hive_pool = None
                self._hive_pool_lock = None
                self._hive_connection_count = 0

                self._initialized = True
                logger.info(
                    f"Hybrid connection manager initialized (HYBRID MODE):\n"
                    f"  Impala (reads): {self._impala_config['HOST']}:{self._impala_config['PORT']} "
                    f"[{self._impala_config['AUTH_MECHANISM']}]\n"
                    f"  REST Proxy (writes): {self._proxy_url}\n"
                    f"  Database: {self._proxy_database}"
                )
                return

            # Direct connection mode - also initialize Hive for writes
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

            # Hive pool for writes (direct mode only)
            self._hive_pool = Queue(maxsize=self._hive_config['POOL_SIZE'])
            self._hive_pool_lock = threading.Lock()
            self._hive_connection_count = 0

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
        """
        Context manager for Impala cursor (reads).

        ALWAYS uses Impala for reads regardless of USE_REST_PROXY setting.
        REST Proxy is only for writes.
        """
        connection = None
        cursor = None
        try:
            connection = self.get_impala_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                logger.warning("Impala connection not available for read")
                yield None
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection:
                self.return_impala_connection(connection)

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
        Execute a READ query via Impala (ALWAYS).

        Reads ALWAYS go through Impala for speed, regardless of USE_REST_PROXY setting.
        REST Proxy is only used for WRITES.
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

        # ALWAYS use Impala for reads (fast)
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    logger.error("No Impala cursor available for read query")
                    # Fallback to REST proxy only if Impala is not available
                    if self._use_proxy and REQUESTS_AVAILABLE:
                        logger.warning("Falling back to REST proxy for read")
                        return self._proxy_execute_query(formatted_query, database or self._proxy_database)
                    return []

                cursor.execute(formatted_query)

                if cursor.description:
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                return []

        except Exception as e:
            logger.error(f"Impala read query failed: {str(e)}")
            logger.error(f"Query: {formatted_query[:200]}...")
            # Fallback to REST proxy only if Impala fails
            if self._use_proxy and REQUESTS_AVAILABLE:
                logger.warning("Falling back to REST proxy for read after Impala failure")
                try:
                    return self._proxy_execute_query(formatted_query, database or self._proxy_database)
                except Exception as proxy_e:
                    logger.error(f"REST Proxy fallback also failed: {str(proxy_e)}")
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
                     database: Optional[str] = None, use_tez_engine: bool = True) -> bool:
        """
        Execute a WRITE query (INSERT, UPDATE, DELETE) via Hive with Tez engine.

        In REST Proxy mode: Uses REST API with YARN queue support
        In Direct mode: Priority order:
            1. Beeline subprocess (good for edge node)
            2. Direct impyla connection (fallback)

        Args:
            query: SQL INSERT/UPDATE/DELETE query
            params: Optional parameters for query formatting
            database: Database name (optional)
            use_tez_engine: Use Tez execution engine (default: True for faster writes)

        Returns:
            True if write succeeded, False otherwise
        """
        start_time = time.time()

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

        # Enforce Tez engine if configured
        if self._always_use_tez:
            formatted_query = formatted_query.replace(
                'hive.execution.engine=mr',
                f'hive.execution.engine={self._execution_engine}'
            )

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

            # Initialize session with Tez engine if not already done
            conn_id = id(connection)
            if conn_id not in self._initialized_connections:
                self._initialize_session(cursor, use_tez_engine)
                self._initialized_connections.add(conn_id)

            cursor.execute(formatted_query)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(f"Hive write query executed successfully ({elapsed_ms:.0f}ms)")
            return True

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Failed to execute write query ({elapsed_ms:.0f}ms): {str(e)}")
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

    def _initialize_session(self, cursor, use_tez: bool = True):
        """Initialize Hive session with Tez engine and optimizations.

        Note: Always uses Tez engine regardless of use_tez parameter when
        HIVE_ALWAYS_USE_TEZ is True (default). This ensures optimal performance.
        """
        try:
            # Always use Tez engine when ALWAYS_USE_TEZ is configured (default: True)
            # This overrides the use_tez parameter to ensure Tez is always used
            engine = 'tez' if self._always_use_tez else (self._execution_engine if use_tez else 'mr')
            cursor.execute(f"SET hive.execution.engine={engine}")

            # Apply additional initialization statements
            for stmt in self._init_statements:
                try:
                    # Skip engine statement as we already set it
                    if 'execution.engine' not in stmt:
                        cursor.execute(stmt)
                except Exception as e:
                    logger.debug(f"Init statement failed (non-critical): {stmt} - {e}")

            logger.debug(f"Session initialized with {engine} engine")
        except Exception as e:
            logger.warning(f"Session initialization failed: {e}")

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
        """Test Impala (reads) and Hive/Proxy (writes) connections."""
        results = {
            'impala': False,
            'hive': False,
            'hive_method': 'none',
            'mode': 'hybrid' if self._use_proxy else 'direct'
        }

        # ALWAYS test Impala (used for reads regardless of proxy mode)
        if IMPYLA_AVAILABLE:
            try:
                with self.get_read_cursor() as cursor:
                    if cursor:
                        cursor.execute("SELECT 1")
                        result = cursor.fetchone()
                        results['impala'] = result is not None
                        if results['impala']:
                            logger.info("Impala connection test: SUCCESS")
                        else:
                            logger.error("Impala connection test: FAILED (no result)")
            except Exception as e:
                logger.error(f"Impala connection test failed: {str(e)}")

        # Test write connection based on mode
        if self._use_proxy:
            # REST Proxy mode for writes
            try:
                health_result = self._proxy_request('/health', method='GET')
                if health_result.get('success'):
                    results['hive'] = True
                    results['hive_method'] = 'rest_proxy'
                    logger.info("REST Proxy connection test: SUCCESS (health check)")
            except Exception as e:
                logger.error(f"REST Proxy connection test failed: {str(e)}")
        elif BEELINE_AVAILABLE:
            # Direct mode - test Hive via beeline
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
        """Get list of tables (via Impala)."""
        # ALWAYS use Impala for reads
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    # Fallback to REST proxy if Impala not available
                    if self._use_proxy and REQUESTS_AVAILABLE:
                        db = database or self._proxy_database
                        results = self._proxy_execute_query("SHOW TABLES", db)
                        if results:
                            first_key = list(results[0].keys())[0] if results[0] else 'tab_name'
                            return [row.get(first_key, '') for row in results]
                    return []
                cursor.execute("SHOW TABLES")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tables: {str(e)}")
            return []

    def describe_table(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get table schema information (via Impala)."""
        # ALWAYS use Impala for reads
        try:
            with self.get_read_cursor(database) as cursor:
                if cursor is None:
                    # Fallback to REST proxy if Impala not available
                    if self._use_proxy and REQUESTS_AVAILABLE:
                        query = f"DESCRIBE {table_name}"
                        return self._proxy_execute_query(query, database or self._proxy_database)
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
        # Hybrid mode - Impala for reads, REST Proxy for writes
        if self._use_proxy:
            return {
                'mode': 'hybrid',
                'impala': {
                    'host': self._impala_config['HOST'],
                    'port': self._impala_config['PORT'],
                    'auth': self._impala_config['AUTH_MECHANISM'],
                    'active': self._impala_connection_count,
                    'max': self._impala_config['POOL_SIZE'],
                    'available': IMPYLA_AVAILABLE,
                    'purpose': 'reads',
                },
                'proxy': {
                    'url': self._proxy_url,
                    'database': self._proxy_database,
                    'timeout': self._proxy_timeout,
                    'available': REQUESTS_AVAILABLE,
                    'purpose': 'writes',
                },
                'hive': {'available': False, 'reason': 'Using REST proxy for writes'},
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
