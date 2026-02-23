#!/usr/bin/env python3
"""
HybridConnectionManager for CML Environment
============================================

This module demonstrates the glibc/SASL connectivity issue in CML Docker containers
and provides the solution using REST Proxy.

PROBLEM:
--------
CML Docker containers have glibc version mismatch with Cloudera's native SASL libraries.
When PyHive/impyla tries to use Kerberos authentication, it fails with:

    Error: "version `GLIBC_2.29' not found"
    Or: "Could not start SASL: None of the mechanisms listed meet all required properties"

This happens because:
1. CML containers use different glibc version than edge nodes
2. Kerberos/SASL native libraries are compiled against specific glibc
3. Docker isolation prevents using host's native libraries

SOLUTION:
---------
Use REST Proxy (app_v2.py) deployed on edge node:
- Edge node has correct glibc and native libraries
- REST Proxy handles beeline/Hive connections
- CML app communicates via HTTP (no native dependencies)

Usage:
------
    from hybrid_connection import HybridConnectionManager, CMLConfig

    # Configure for your environment
    config = CMLConfig(
        rest_proxy_url="http://edge-node.sg.uobnet.com:5000",
        hive_database="mrw_ima"
    )

    manager = HybridConnectionManager(config)

    # Execute queries via REST Proxy
    results = manager.execute_query("SELECT * FROM portfolio_hive LIMIT 10")

    # Execute writes
    manager.execute_write("INSERT INTO portfolio_hive (...) VALUES (...)")
"""

import os
import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hybrid_connection')

# =============================================================================
# Configuration
# =============================================================================

@dataclass
class CMLConfig:
    """Configuration for CML Hybrid Connection."""

    # REST Proxy URL (edge node where app_v2.py is deployed)
    rest_proxy_url: str = field(
        default_factory=lambda: os.environ.get(
            'HIVE_REST_PROXY_URL',
            'http://localhost:5000'
        )
    )

    # Default Hive database
    hive_database: str = field(
        default_factory=lambda: os.environ.get('HIVE_DATABASE', 'mrw_ima')
    )

    # API Key for REST Proxy authentication
    api_key: str = field(
        default_factory=lambda: os.environ.get('HIVE_PROXY_API_KEY', '')
    )

    # Request timeout (seconds)
    timeout: int = field(
        default_factory=lambda: int(os.environ.get('HIVE_TIMEOUT', '300'))
    )

    # Retry configuration
    max_retries: int = 3
    retry_backoff: float = 0.5

    # Connection pool size
    pool_size: int = 10

    # Enable direct connection attempt (will fail in CML, useful for debugging)
    try_direct_connection: bool = False


# =============================================================================
# Exception Classes
# =============================================================================

class HiveConnectionError(Exception):
    """Base exception for Hive connection errors."""
    pass


class GlibcCompatibilityError(HiveConnectionError):
    """
    Raised when glibc version mismatch prevents native library loading.

    This is the error we're trying to replicate and solve.
    """
    pass


class SASlAuthenticationError(HiveConnectionError):
    """Raised when SASL authentication fails due to missing mechanisms."""
    pass


class RestProxyError(HiveConnectionError):
    """Raised when REST Proxy communication fails."""
    pass


# =============================================================================
# Direct Connection Attempt (Will Fail in CML)
# =============================================================================

def attempt_direct_pyhive_connection(
    host: str,
    port: int = 10000,
    database: str = 'default',
    auth: str = 'KERBEROS',
    kerberos_service_name: str = 'hive'
) -> Tuple[bool, str]:
    """
    Attempt direct PyHive connection to HiveServer2.

    This will FAIL in CML Docker containers due to glibc/SASL issues.
    Use this to demonstrate/replicate the error.

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    logger.info(f"Attempting direct PyHive connection to {host}:{port}")
    logger.warning("This will likely FAIL in CML containers due to glibc issues!")

    try:
        # Try to import PyHive
        from pyhive import hive
        logger.info("PyHive imported successfully")

    except ImportError as e:
        error_msg = f"PyHive not installed: {e}"
        logger.error(error_msg)
        return False, error_msg

    # Check for SASL libraries
    try:
        import sasl
        import thrift_sasl
        logger.info("SASL libraries imported successfully")
    except ImportError as e:
        error_msg = f"SASL libraries missing: {e}. Install: pip install sasl thrift-sasl"
        logger.error(error_msg)
        return False, error_msg

    # Attempt connection
    try:
        logger.info(f"Connecting with auth={auth}...")

        conn_params = {
            'host': host,
            'port': port,
            'database': database,
        }

        if auth.upper() == 'KERBEROS':
            conn_params['auth'] = 'KERBEROS'
            conn_params['kerberos_service_name'] = kerberos_service_name
        elif auth.upper() == 'NOSASL':
            conn_params['auth'] = 'NOSASL'
        else:
            conn_params['auth'] = auth

        conn = hive.Connection(**conn_params)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        logger.info(f"Connection successful! Result: {result}")
        return True, "Connection successful"

    except Exception as e:
        error_str = str(e)

        # Check for specific glibc errors
        if 'GLIBC' in error_str:
            raise GlibcCompatibilityError(
                f"GLIBC version mismatch detected!\n"
                f"Error: {error_str}\n"
                f"This is the expected error in CML containers.\n"
                f"Solution: Use REST Proxy instead of direct connection."
            )

        # Check for SASL errors
        if 'SASL' in error_str or 'mechanisms' in error_str.lower():
            raise SASlAuthenticationError(
                f"SASL authentication failed!\n"
                f"Error: {error_str}\n"
                f"This typically occurs when Kerberos/SASL libraries are incompatible.\n"
                f"Solution: Use REST Proxy instead of direct connection."
            )

        logger.error(f"Connection failed: {error_str}")
        return False, error_str


def attempt_direct_impyla_connection(
    host: str,
    port: int = 21050,
    database: str = 'default',
    auth_mechanism: str = 'GSSAPI'
) -> Tuple[bool, str]:
    """
    Attempt direct impyla connection to Impala.

    This will FAIL in CML Docker containers due to glibc/SASL issues.

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    logger.info(f"Attempting direct impyla connection to {host}:{port}")
    logger.warning("This will likely FAIL in CML containers due to glibc issues!")

    try:
        from impala.dbapi import connect
        logger.info("impyla imported successfully")

    except ImportError as e:
        error_msg = f"impyla not installed: {e}"
        logger.error(error_msg)
        return False, error_msg

    try:
        logger.info(f"Connecting with auth_mechanism={auth_mechanism}...")

        conn = connect(
            host=host,
            port=port,
            database=database,
            auth_mechanism=auth_mechanism,
            use_ssl=True
        )

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        logger.info(f"Connection successful! Result: {result}")
        return True, "Connection successful"

    except Exception as e:
        error_str = str(e)

        if 'GLIBC' in error_str:
            raise GlibcCompatibilityError(
                f"GLIBC version mismatch in impyla!\n"
                f"Error: {error_str}\n"
                f"Solution: Use REST Proxy."
            )

        if 'SASL' in error_str or 'GSSAPI' in error_str:
            raise SASlAuthenticationError(
                f"SASL/GSSAPI authentication failed in impyla!\n"
                f"Error: {error_str}\n"
                f"Solution: Use REST Proxy."
            )

        logger.error(f"Connection failed: {error_str}")
        return False, error_str


# =============================================================================
# REST Proxy Client
# =============================================================================

class RestProxyClient:
    """
    HTTP client for communicating with Hive REST Proxy.

    This is the SOLUTION to the glibc problem - communicate via HTTP
    instead of native Hive/Impala protocols.
    """

    def __init__(self, config: CMLConfig):
        self.config = config
        self.base_url = config.rest_proxy_url.rstrip('/')
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry logic."""
        session = requests.Session()

        # Configure retries
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.config.pool_size,
            pool_maxsize=self.config.pool_size
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        if self.config.api_key:
            session.headers['X-API-Key'] = self.config.api_key
        session.headers['Content-Type'] = 'application/json'

        return session

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        timeout: int = None
    ) -> Dict:
        """Make HTTP request to REST Proxy."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        timeout = timeout or self.config.timeout

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, timeout=timeout)
            else:
                response = self.session.post(url, json=data, timeout=timeout)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            raise RestProxyError(
                f"Cannot connect to REST Proxy at {self.base_url}\n"
                f"Error: {e}\n"
                f"Ensure app_v2.py is running on the edge node."
            )
        except requests.exceptions.Timeout as e:
            raise RestProxyError(f"Request timeout after {timeout}s: {e}")
        except requests.exceptions.HTTPError as e:
            raise RestProxyError(f"HTTP error: {e}")
        except json.JSONDecodeError as e:
            raise RestProxyError(f"Invalid JSON response: {e}")

    def health_check(self) -> Dict:
        """Check REST Proxy health."""
        return self._request('GET', '/health')

    def test_connection(self) -> Dict:
        """Test Hive connection via proxy."""
        return self._request('GET', '/test')

    def execute_query(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> Dict:
        """Execute SELECT query."""
        return self._request('POST', '/query', {
            'sql': sql,
            'database': database or self.config.hive_database,
            'timeout': timeout or self.config.timeout
        }, timeout)

    def execute_write(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> Dict:
        """Execute write query (INSERT/UPDATE/DELETE)."""
        return self._request('POST', '/execute', {
            'sql': sql,
            'database': database or self.config.hive_database,
            'timeout': timeout or self.config.timeout
        }, timeout)

    def insert(
        self,
        table: str,
        data: Dict,
        database: str = None
    ) -> Dict:
        """Dynamic INSERT with automatic type casting."""
        db = database or self.config.hive_database
        endpoint = f"/insert/{db}.{table}"
        return self._request('POST', endpoint, {'data': data})

    def update(
        self,
        table: str,
        where: Dict,
        data: Dict,
        database: str = None
    ) -> Dict:
        """Dynamic UPDATE with automatic type casting."""
        db = database or self.config.hive_database
        endpoint = f"/update/{db}.{table}"
        return self._request('POST', endpoint, {'where': where, 'data': data})

    def delete(
        self,
        table: str,
        where: Dict,
        soft_delete: bool = True,
        database: str = None
    ) -> Dict:
        """Dynamic DELETE (soft or hard)."""
        db = database or self.config.hive_database
        endpoint = f"/delete/{db}.{table}"
        return self._request('POST', endpoint, {
            'where': where,
            'soft_delete': soft_delete
        })

    def batch_insert(
        self,
        table: str,
        records: List[Dict],
        database: str = None
    ) -> Dict:
        """Batch INSERT multiple records."""
        db = database or self.config.hive_database
        endpoint = f"/batch/insert/{db}.{table}"
        return self._request('POST', endpoint, {'records': records})

    def get_schema(self, table: str, database: str = None) -> Dict:
        """Get table schema."""
        db = database or self.config.hive_database
        return self._request('GET', f"/schema/{db}.{table}")


# =============================================================================
# Hybrid Connection Manager
# =============================================================================

class HybridConnectionManager:
    """
    Hybrid Connection Manager for CML Environment.

    Automatically detects environment and uses appropriate connection method:
    - Edge Node: Can use direct PyHive/impyla (optional)
    - CML Container: Uses REST Proxy (required due to glibc issues)

    Usage:
        config = CMLConfig(rest_proxy_url="http://edge-node:5000")
        manager = HybridConnectionManager(config)

        # All operations go through REST Proxy
        results = manager.execute_query("SELECT * FROM my_table")
        manager.insert("my_table", {"col1": "value1", "col2": 123})
    """

    def __init__(self, config: CMLConfig = None):
        self.config = config or CMLConfig()
        self.proxy_client = RestProxyClient(self.config)
        self._is_cml = self._detect_cml_environment()
        self._connection_tested = False

        logger.info(f"HybridConnectionManager initialized")
        logger.info(f"  REST Proxy URL: {self.config.rest_proxy_url}")
        logger.info(f"  Database: {self.config.hive_database}")
        logger.info(f"  Environment: {'CML Container' if self._is_cml else 'Edge Node'}")

    def _detect_cml_environment(self) -> bool:
        """Detect if running in CML Docker container."""
        # CML sets specific environment variables
        cml_indicators = [
            'CDSW_PROJECT',
            'CDSW_DOMAIN',
            'CDSW_APP_PORT',
            'ML_RUNTIME_EDITION'
        ]

        for var in cml_indicators:
            if os.environ.get(var):
                logger.info(f"Detected CML environment (found {var})")
                return True

        # Check for Docker container
        if os.path.exists('/.dockerenv'):
            logger.info("Detected Docker container")
            return True

        return False

    def test_direct_connection(self, host: str, port: int = 10000) -> Dict:
        """
        Test direct connection to Hive (for debugging).

        This will FAIL in CML containers with glibc error.
        """
        logger.info("Testing direct connection (expect failure in CML)...")

        result = {
            'direct_connection': False,
            'error': None,
            'error_type': None,
            'solution': None
        }

        try:
            success, message = attempt_direct_pyhive_connection(
                host=host,
                port=port,
                database=self.config.hive_database
            )
            result['direct_connection'] = success
            if not success:
                result['error'] = message

        except GlibcCompatibilityError as e:
            result['error'] = str(e)
            result['error_type'] = 'GLIBC_COMPATIBILITY'
            result['solution'] = 'Use REST Proxy (app_v2.py on edge node)'
            logger.error(f"GLIBC Error (expected in CML): {e}")

        except SASlAuthenticationError as e:
            result['error'] = str(e)
            result['error_type'] = 'SASL_AUTHENTICATION'
            result['solution'] = 'Use REST Proxy (app_v2.py on edge node)'
            logger.error(f"SASL Error (expected in CML): {e}")

        except Exception as e:
            result['error'] = str(e)
            result['error_type'] = 'UNKNOWN'
            logger.error(f"Connection error: {e}")

        return result

    def test_proxy_connection(self) -> Dict:
        """Test connection to REST Proxy."""
        logger.info("Testing REST Proxy connection...")

        try:
            health = self.proxy_client.health_check()

            if health.get('success'):
                self._connection_tested = True
                logger.info("REST Proxy connection successful!")
                return {
                    'success': True,
                    'proxy_version': health.get('version'),
                    'database': health.get('config', {}).get('database'),
                    'stats': health.get('stats')
                }
            else:
                return {
                    'success': False,
                    'error': health.get('error', 'Unknown error')
                }

        except RestProxyError as e:
            logger.error(f"REST Proxy connection failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def execute_query(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> List[Dict]:
        """
        Execute SELECT query.

        Returns list of row dictionaries.
        """
        result = self.proxy_client.execute_query(sql, database, timeout)

        if result.get('success'):
            return result.get('data', [])
        else:
            raise HiveConnectionError(f"Query failed: {result.get('error')}")

    def execute_write(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> Dict:
        """
        Execute write query (INSERT/UPDATE/DELETE).

        Returns result dictionary.
        """
        result = self.proxy_client.execute_write(sql, database, timeout)

        if result.get('success'):
            return result
        else:
            raise HiveConnectionError(f"Write failed: {result.get('error')}")

    def insert(
        self,
        table: str,
        data: Dict,
        database: str = None
    ) -> Dict:
        """Insert a record with automatic type casting."""
        result = self.proxy_client.insert(table, data, database)

        if result.get('success'):
            return result
        else:
            raise HiveConnectionError(f"Insert failed: {result.get('error')}")

    def update(
        self,
        table: str,
        where: Dict,
        data: Dict,
        database: str = None
    ) -> Dict:
        """Update records with automatic type casting."""
        result = self.proxy_client.update(table, where, data, database)

        if result.get('success'):
            return result
        else:
            raise HiveConnectionError(f"Update failed: {result.get('error')}")

    def delete(
        self,
        table: str,
        where: Dict,
        soft_delete: bool = True,
        database: str = None
    ) -> Dict:
        """Delete records (soft or hard delete)."""
        result = self.proxy_client.delete(table, where, soft_delete, database)

        if result.get('success'):
            return result
        else:
            raise HiveConnectionError(f"Delete failed: {result.get('error')}")

    def batch_insert(
        self,
        table: str,
        records: List[Dict],
        database: str = None
    ) -> Dict:
        """Batch insert multiple records."""
        result = self.proxy_client.batch_insert(table, records, database)

        if result.get('success'):
            return result
        else:
            raise HiveConnectionError(f"Batch insert failed: {result.get('error')}")

    def get_schema(self, table: str, database: str = None) -> Dict:
        """Get table schema."""
        result = self.proxy_client.get_schema(table, database)

        if result.get('success'):
            return result.get('schema', {})
        else:
            raise HiveConnectionError(f"Schema fetch failed: {result.get('error')}")


# =============================================================================
# Convenience Functions
# =============================================================================

# Global manager instance
_manager: Optional[HybridConnectionManager] = None


def get_manager() -> HybridConnectionManager:
    """Get or create global HybridConnectionManager instance."""
    global _manager
    if _manager is None:
        _manager = HybridConnectionManager()
    return _manager


def execute_query(sql: str, database: str = None) -> List[Dict]:
    """Execute SELECT query using global manager."""
    return get_manager().execute_query(sql, database)


def execute_write(sql: str, database: str = None) -> Dict:
    """Execute write query using global manager."""
    return get_manager().execute_write(sql, database)


def insert(table: str, data: Dict, database: str = None) -> Dict:
    """Insert record using global manager."""
    return get_manager().insert(table, data, database)


def update(table: str, where: Dict, data: Dict, database: str = None) -> Dict:
    """Update records using global manager."""
    return get_manager().update(table, where, data, database)


def delete(table: str, where: Dict, soft_delete: bool = True, database: str = None) -> Dict:
    """Delete records using global manager."""
    return get_manager().delete(table, where, soft_delete, database)
