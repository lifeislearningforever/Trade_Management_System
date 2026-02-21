"""
Base Repository for Hive Managed Tables

Provides common CRUD operations for Hive tables with ORC format.
Implements soft delete using deleted_at timestamp.

Supports two connection modes (controlled by USE_REST_PROXY env var):
1. Direct Connection (default for local): Uses HybridConnectionManager
   - Impala: Fast reads (SELECT queries)
   - Hive: ACID writes (INSERT, UPDATE, DELETE)

2. REST Proxy (for CML environments): Uses HiveProxyRepository
   - All operations via REST API to edge node
   - Required when direct Hive/Impala connections fail
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger('hive_poc')

# Check if we should use REST proxy (for CML environments)
USE_REST_PROXY = os.environ.get('USE_REST_PROXY', 'false').lower() == 'true'
HIVE_PROXY_URL = os.environ.get('HIVE_PROXY_URL', 'http://localhost:5000')

if USE_REST_PROXY:
    logger.info(f"Using REST Proxy mode: {HIVE_PROXY_URL}")
    # Import requests for REST proxy
    try:
        import requests
        REQUESTS_AVAILABLE = True
    except ImportError:
        REQUESTS_AVAILABLE = False
        logger.error("requests library not available for REST proxy - pip install requests")
else:
    logger.info("Using direct Hive/Impala connection mode")
    # Import hybrid connection manager from core
    try:
        from core.repositories.hybrid_connection import hybrid_manager
    except ImportError:
        hybrid_manager = None
        logger.warning("hybrid_manager not available")


class HiveBaseRepository(ABC):
    """
    Abstract base repository for Hive managed tables.

    Features:
    - CRUD operations on Hive ACID tables with ORC format
    - Supports both direct connection and REST proxy modes
    - Soft delete support via deleted_at timestamp
    - Query builder patterns for consistency
    """

    def __init__(self):
        self.use_proxy = USE_REST_PROXY
        self.database = os.environ.get('HIVE_DATABASE', 'mrw_ima')

        if self.use_proxy:
            self.proxy_url = HIVE_PROXY_URL
            self.api_key = os.environ.get('HIVE_PROXY_API_KEY', '')
            self.timeout = int(os.environ.get('HIVE_TIMEOUT', '300'))
            self._session = None
            self.conn_manager = None
        else:
            self.conn_manager = hybrid_manager
            self._session = None

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Return the Hive table name (e.g., 'portfolio_hive')"""
        pass

    @property
    @abstractmethod
    def primary_key(self) -> str:
        """Return the primary key column name"""
        pass

    @property
    @abstractmethod
    def columns(self) -> List[str]:
        """Return list of all column names"""
        pass

    def _get_full_table_name(self) -> str:
        """Get fully qualified table name"""
        return f"{self.database}.{self.table_name}"

    def _format_value(self, value: Any) -> str:
        """Format value for SQL query"""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            # Escape single quotes
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        else:
            return str(value)

    # ==================== REST PROXY METHODS ====================

    @property
    def session(self) -> 'requests.Session':
        """Get or create HTTP session for REST proxy."""
        if not self.use_proxy:
            raise RuntimeError("REST proxy not enabled")

        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'Content-Type': 'application/json',
                'X-User': os.environ.get('USER', 'hive_poc')
            })
            if self.api_key:
                self._session.headers['X-API-Key'] = self.api_key

        return self._session

    def _make_proxy_request(self, endpoint: str, method: str = 'GET',
                            data: dict = None, timeout: int = None) -> Dict:
        """Make HTTP request to REST proxy."""
        url = f"{self.proxy_url}{endpoint}"
        request_timeout = timeout or self.timeout

        try:
            if method == 'GET':
                response = self.session.get(url, timeout=request_timeout + 10)
            else:
                response = self.session.post(url, json=data, timeout=request_timeout + 10)

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
            elif 'ConnectionError' in str(type(e).__name__):
                raise RuntimeError(f"Connection failed: {str(e)[:50]}")
            raise

    def _execute_proxy_query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SELECT query via REST proxy."""
        result = self._make_proxy_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })
        return result.get('data', [])

    # ==================== READ OPERATIONS ====================

    def find_all(self, include_deleted: bool = False, limit: int = None) -> List[Dict[str, Any]]:
        """
        Find all records from the table.

        Args:
            include_deleted: If True, include soft-deleted records
            limit: Maximum number of records to return

        Returns:
            List of dictionaries representing records
        """
        where_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        limit_clause = f"LIMIT {limit}" if limit else ""

        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            {where_clause}
            {limit_clause}
        """

        if self.use_proxy:
            return self._execute_proxy_query(query)
        else:
            return self.conn_manager.execute_query(query)

    def find_by_id(self, record_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Find a record by primary key.

        Args:
            record_id: Primary key value
            include_deleted: If True, include soft-deleted records

        Returns:
            Dictionary representing the record, or None if not found
        """
        where_clause = f"WHERE {self.primary_key} = '{record_id}'"
        if not include_deleted:
            where_clause += " AND deleted_at IS NULL"

        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            {where_clause}
        """

        if self.use_proxy:
            results = self._execute_proxy_query(query)
        else:
            results = self.conn_manager.execute_query(query)

        return results[0] if results else None

    def count(self, include_deleted: bool = False) -> int:
        """
        Count records in the table.

        Args:
            include_deleted: If True, include soft-deleted records

        Returns:
            Number of records
        """
        where_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        query = f"SELECT COUNT(*) as cnt FROM {self._get_full_table_name()} {where_clause}"

        if self.use_proxy:
            results = self._execute_proxy_query(query)
        else:
            results = self.conn_manager.execute_query(query)

        if results:
            row = results[0]
            return int(row.get('cnt', row.get('_c0', 0)))
        return 0

    def exists(self, record_id: str) -> bool:
        """
        Check if a record exists (not soft-deleted).

        Args:
            record_id: Primary key value

        Returns:
            True if exists, False otherwise
        """
        query = f"""
            SELECT 1 FROM {self._get_full_table_name()}
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
            LIMIT 1
        """

        if self.use_proxy:
            results = self._execute_proxy_query(query)
        else:
            results = self.conn_manager.execute_query(query)

        return len(results) > 0

    def find_deleted(self) -> List[Dict[str, Any]]:
        """
        Find all soft-deleted records.

        Returns:
            List of soft-deleted records
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE deleted_at IS NOT NULL
        """

        if self.use_proxy:
            return self._execute_proxy_query(query)
        else:
            return self.conn_manager.execute_query(query)

    # ==================== WRITE OPERATIONS ====================

    def _execute_acid_write(self, query: str) -> bool:
        """
        Execute a write query via Hive for ACID support (direct connection mode only).
        """
        if self.use_proxy:
            raise RuntimeError("Use proxy-specific methods for writes in proxy mode")
        return self.conn_manager.execute_write(query, use_mr_engine=True)

    def _convert_datetime_to_string(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime objects to strings for JSON serialization."""
        result = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif value is None:
                result[key] = None
            else:
                result[key] = value
        return result

    def create(self, data: Dict[str, Any]) -> bool:
        """
        Create a new record.

        Args:
            data: Dictionary of column names to values

        Returns:
            True if successful, False otherwise
        """
        # Ensure required audit fields
        now = datetime.now()
        if 'created_at' not in data:
            data['created_at'] = now
        if 'updated_at' not in data:
            data['updated_at'] = now
        if 'deleted_at' not in data:
            data['deleted_at'] = None

        logger.info(f"Creating record in {self.table_name}")

        if self.use_proxy:
            # Use REST proxy
            proxy_data = self._convert_datetime_to_string(data)
            result = self._make_proxy_request(
                f'/insert/{self._get_full_table_name()}',
                method='POST',
                data={'data': proxy_data}
            )
            logger.info(f"Created record via proxy: {result.get('elapsed_ms')}ms")
            return True
        else:
            # Direct connection mode
            columns = list(data.keys())
            values = [self._format_value(data[col]) for col in columns]

            query = f"""
                INSERT INTO {self._get_full_table_name()} ({', '.join(columns)})
                VALUES ({', '.join(values)})
            """
            return self._execute_acid_write(query)

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing record.

        Args:
            record_id: Primary key value
            data: Dictionary of column names to new values

        Returns:
            True if successful, False otherwise
        """
        data['updated_at'] = datetime.now()
        logger.info(f"Updating record {record_id} in {self.table_name}")

        if self.use_proxy:
            proxy_data = self._convert_datetime_to_string(data)
            result = self._make_proxy_request(
                f'/update/{self._get_full_table_name()}',
                method='POST',
                data={
                    'where': {self.primary_key: record_id},
                    'data': proxy_data
                }
            )
            logger.info(f"Updated via proxy: {result.get('elapsed_ms')}ms")
            return True
        else:
            set_clauses = [f"{col} = {self._format_value(val)}" for col, val in data.items()]
            query = f"""
                UPDATE {self._get_full_table_name()}
                SET {', '.join(set_clauses)}
                WHERE {self.primary_key} = '{record_id}'
                AND deleted_at IS NULL
            """
            return self._execute_acid_write(query)

    def soft_delete(self, record_id: str, deleted_by: str = 'system') -> bool:
        """
        Soft delete a record by setting deleted_at timestamp.

        Args:
            record_id: Primary key value
            deleted_by: Username of person performing delete

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Soft deleting record {record_id} from {self.table_name}")

        if self.use_proxy:
            result = self._make_proxy_request(
                f'/delete/{self._get_full_table_name()}',
                method='POST',
                data={
                    'where': {self.primary_key: record_id},
                    'soft_delete': True,
                    'soft_delete_column': 'deleted_at',
                    'deleted_by': deleted_by
                }
            )
            logger.info(f"Soft deleted via proxy: {result.get('elapsed_ms')}ms")
            return True
        else:
            now = datetime.now()
            query = f"""
                UPDATE {self._get_full_table_name()}
                SET deleted_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    updated_by = '{deleted_by}'
                WHERE {self.primary_key} = '{record_id}'
                AND deleted_at IS NULL
            """
            return self._execute_acid_write(query)

    def restore(self, record_id: str, restored_by: str = 'system') -> bool:
        """
        Restore a soft-deleted record.

        Args:
            record_id: Primary key value
            restored_by: Username of person performing restore

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Restoring record {record_id} in {self.table_name}")

        if self.use_proxy:
            result = self._make_proxy_request(
                f'/update/{self._get_full_table_name()}',
                method='POST',
                data={
                    'where': {self.primary_key: record_id},
                    'data': {'deleted_at': None, 'updated_by': restored_by}
                }
            )
            logger.info(f"Restored via proxy: {result.get('elapsed_ms')}ms")
            return True
        else:
            now = datetime.now()
            query = f"""
                UPDATE {self._get_full_table_name()}
                SET deleted_at = NULL,
                    updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    updated_by = '{restored_by}'
                WHERE {self.primary_key} = '{record_id}'
                AND deleted_at IS NOT NULL
            """
            return self._execute_acid_write(query)

    def hard_delete(self, record_id: str) -> bool:
        """
        Permanently delete a record (use with caution).

        Args:
            record_id: Primary key value

        Returns:
            True if successful, False otherwise
        """
        logger.warning(f"Hard deleting record {record_id} from {self.table_name}")

        if self.use_proxy:
            result = self._make_proxy_request(
                f'/delete/{self._get_full_table_name()}',
                method='POST',
                data={
                    'where': {self.primary_key: record_id},
                    'soft_delete': False
                }
            )
            logger.info(f"Hard deleted via proxy: {result.get('elapsed_ms')}ms")
            return True
        else:
            query = f"""
                DELETE FROM {self._get_full_table_name()}
                WHERE {self.primary_key} = '{record_id}'
            """
        return self._execute_acid_write(query)
