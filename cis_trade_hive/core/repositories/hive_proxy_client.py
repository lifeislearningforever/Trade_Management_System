"""
Hive Proxy Client for Django Integration

This module provides a client to connect to the Hive REST Proxy
running on the edge node. It's designed to be a drop-in replacement
for direct Hive connections when native SASL libraries are unavailable.

Usage:
    from core.repositories.hive_proxy_client import hive_proxy_client

    # Execute SELECT query
    results = hive_proxy_client.execute_query(
        "SELECT * FROM cis_user WHERE deleted_at IS NULL LIMIT 10"
    )

    # Execute write query
    hive_proxy_client.execute_write(
        "INSERT INTO cis_audit_log (...) VALUES (...)"
    )
"""

import os
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests library not available - install with: pip install requests")


class HiveProxyClient:
    """
    Client for Hive REST Proxy.

    Provides a clean interface for executing Hive queries via the
    REST Proxy deployed on the edge node.
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        database: str = 'gmp_cis',
        timeout: int = 120,
        retry_count: int = 2
    ):
        """
        Initialize the Hive Proxy Client.

        Args:
            base_url: URL of the REST Proxy (e.g., http://edge-node:5000)
            api_key: API key for authentication (if configured on proxy)
            database: Default database to use
            timeout: Query timeout in seconds
            retry_count: Number of retries on connection failure
        """
        self.base_url = (base_url or os.environ.get('HIVE_PROXY_URL', 'http://localhost:5000')).rstrip('/')
        self.api_key = api_key or os.environ.get('HIVE_PROXY_API_KEY', '')
        self.database = database or os.environ.get('HIVE_DATABASE', 'gmp_cis')
        self.timeout = timeout
        self.retry_count = retry_count
        self._session = None

    @property
    def session(self) -> 'requests.Session':
        """Get or create a requests session."""
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library not available")

        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({'Content-Type': 'application/json'})
            if self.api_key:
                self._session.headers.update({'X-API-Key': self.api_key})

        return self._session

    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: Dict = None,
        timeout: int = None
    ) -> Tuple[bool, Dict]:
        """
        Make an HTTP request to the proxy.

        Args:
            endpoint: API endpoint (e.g., /query)
            method: HTTP method (GET or POST)
            data: JSON data for POST requests
            timeout: Request timeout (defaults to self.timeout)

        Returns:
            Tuple of (success: bool, result: dict)
        """
        url = f"{self.base_url}{endpoint}"
        request_timeout = timeout or self.timeout

        last_error = None

        for attempt in range(self.retry_count + 1):
            try:
                if method == 'GET':
                    response = self.session.get(url, timeout=request_timeout + 10)
                else:
                    response = self.session.post(url, json=data, timeout=request_timeout + 10)

                result = response.json()

                if response.status_code == 200:
                    return True, result
                elif response.status_code == 429:
                    # Too many concurrent queries - wait and retry
                    import time
                    time.sleep(1)
                    continue
                else:
                    return False, result

            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection failed: {str(e)}"
                logger.warning(f"Attempt {attempt + 1}: {last_error}")
            except requests.exceptions.Timeout:
                last_error = "Request timed out"
                logger.warning(f"Attempt {attempt + 1}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Attempt {attempt + 1}: {last_error}")

        return False, {'error': last_error}

    def health_check(self) -> Dict[str, Any]:
        """
        Check proxy health.

        Returns:
            Health status dict
        """
        success, result = self._make_request('/health')
        if success:
            return result
        raise ConnectionError(f"Health check failed: {result.get('error')}")

    def test_connection(self) -> bool:
        """
        Test Hive connection via proxy.

        Returns:
            True if connection works
        """
        success, result = self._make_request('/test')
        if success and result.get('status') == 'connected':
            return True
        raise ConnectionError(f"Connection test failed: {result.get('error')}")

    def execute_query(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query.

        Args:
            sql: SQL query (must be SELECT, SHOW, or DESCRIBE)
            database: Database to use (defaults to self.database)
            timeout: Query timeout in seconds

        Returns:
            List of result rows as dictionaries

        Raises:
            ValueError: If query is not a read query
            RuntimeError: If query execution fails
        """
        sql = sql.strip()
        sql_upper = sql.upper()

        if not (sql_upper.startswith('SELECT') or
                sql_upper.startswith('SHOW') or
                sql_upper.startswith('DESCRIBE')):
            raise ValueError("Only SELECT, SHOW, DESCRIBE queries allowed. Use execute_write() for writes.")

        success, result = self._make_request(
            '/query',
            method='POST',
            data={
                'sql': sql,
                'database': database or self.database,
                'timeout': timeout or self.timeout
            },
            timeout=timeout or self.timeout
        )

        if success and result.get('success'):
            logger.debug(f"Query executed: {result.get('rows', 0)} rows in {result.get('elapsed_ms', 0)}ms")
            return result.get('data', [])
        else:
            error = result.get('error', 'Unknown error')
            raise RuntimeError(f"Query failed: {error}")

    def execute_write(
        self,
        sql: str,
        database: str = None,
        timeout: int = None
    ) -> bool:
        """
        Execute a write query (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL statement
            database: Database to use (defaults to self.database)
            timeout: Query timeout in seconds

        Returns:
            True if successful

        Raises:
            RuntimeError: If write execution fails
        """
        sql = sql.strip()

        success, result = self._make_request(
            '/execute',
            method='POST',
            data={
                'sql': sql,
                'database': database or self.database,
                'timeout': timeout or self.timeout
            },
            timeout=timeout or self.timeout
        )

        if success and result.get('success'):
            logger.debug(f"Write executed in {result.get('elapsed_ms', 0)}ms")
            return True
        else:
            error = result.get('error', 'Unknown error')
            raise RuntimeError(f"Write failed: {error}")

    def execute_batch(
        self,
        queries: List[Dict[str, str]],
        database: str = None,
        stop_on_error: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple queries in a batch.

        Args:
            queries: List of query dicts with 'sql' and optional 'type' ('read' or 'write')
            database: Database to use
            stop_on_error: Stop on first error

        Returns:
            List of results for each query

        Example:
            results = client.execute_batch([
                {'sql': 'INSERT INTO ...', 'type': 'write'},
                {'sql': 'SELECT ...', 'type': 'read'}
            ])
        """
        success, result = self._make_request(
            '/batch',
            method='POST',
            data={
                'queries': queries,
                'database': database or self.database,
                'stop_on_error': stop_on_error
            },
            timeout=self.timeout * len(queries)  # Scale timeout with query count
        )

        if success:
            return result.get('results', [])
        else:
            error = result.get('error', 'Unknown error')
            raise RuntimeError(f"Batch execution failed: {error}")

    def list_databases(self) -> List[str]:
        """
        List all databases.

        Returns:
            List of database names
        """
        success, result = self._make_request('/databases')

        if success and result.get('success'):
            data = result.get('data', [])
            # Handle both list of dicts and list of strings
            if data and isinstance(data[0], dict):
                return [list(d.values())[0] for d in data]
            return data
        else:
            error = result.get('error', 'Unknown error')
            raise RuntimeError(f"Failed to list databases: {error}")

    def list_tables(self, database: str = None) -> List[str]:
        """
        List tables in a database.

        Args:
            database: Database name (defaults to self.database)

        Returns:
            List of table names
        """
        db = database or self.database
        success, result = self._make_request(f'/tables?database={db}')

        if success and result.get('success'):
            data = result.get('data', [])
            # Handle both list of dicts and list of strings
            if data and isinstance(data[0], dict):
                return [list(d.values())[0] for d in data]
            return data
        else:
            error = result.get('error', 'Unknown error')
            raise RuntimeError(f"Failed to list tables: {error}")

    def close(self):
        """Close the session."""
        if self._session:
            self._session.close()
            self._session = None


# Singleton instance
_hive_proxy_client = None


def get_hive_proxy_client() -> HiveProxyClient:
    """
    Get the singleton HiveProxyClient instance.

    Returns:
        HiveProxyClient instance
    """
    global _hive_proxy_client

    if _hive_proxy_client is None:
        _hive_proxy_client = HiveProxyClient()

    return _hive_proxy_client


# Convenience alias
hive_proxy_client = property(lambda self: get_hive_proxy_client())


# Module-level functions for backward compatibility
def execute_query(sql: str, database: str = None) -> List[Dict[str, Any]]:
    """Execute a SELECT query via the proxy."""
    return get_hive_proxy_client().execute_query(sql, database)


def execute_write(sql: str, database: str = None) -> bool:
    """Execute a write query via the proxy."""
    return get_hive_proxy_client().execute_write(sql, database)
