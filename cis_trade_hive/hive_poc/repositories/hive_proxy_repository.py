"""
Hive Proxy Repository - Base class using REST Proxy for Hive operations

Uses the REST Proxy v2 for all database operations:
- Dynamic INSERT/UPDATE/DELETE with automatic type casting
- Schema caching on proxy side
- Audit logging

This is designed for CML environments where direct Hive connections fail.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger('hive_poc')

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests library not available - pip install requests")


class HiveProxyRepository(ABC):
    """
    Abstract base repository using REST Proxy for Hive operations.

    Features:
    - Dynamic CRUD via REST Proxy
    - Automatic schema detection
    - Audit logging (handled by proxy)
    - Soft delete support
    """

    def __init__(self):
        self.proxy_url = os.environ.get('HIVE_PROXY_URL', 'http://localhost:5000')
        self.api_key = os.environ.get('HIVE_PROXY_API_KEY', '')
        self.database = os.environ.get('HIVE_DATABASE', 'mrw_ima')
        self.timeout = int(os.environ.get('HIVE_TIMEOUT', '300'))
        self._session = None

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Return the Hive table name."""
        pass

    @property
    @abstractmethod
    def primary_key(self) -> str:
        """Return the primary key column name."""
        pass

    @property
    def full_table_name(self) -> str:
        """Get fully qualified table name."""
        return f"{self.database}.{self.table_name}"

    @property
    def session(self) -> 'requests.Session':
        """Get or create HTTP session."""
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library not available")

        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'Content-Type': 'application/json',
                'X-User': os.environ.get('USER', 'hive_poc')
            })
            if self.api_key:
                self._session.headers['X-API-Key'] = self.api_key

        return self._session

    def _make_request(self, endpoint: str, method: str = 'GET',
                      data: dict = None, timeout: int = None) -> Dict:
        """Make HTTP request to proxy."""
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

        except requests.exceptions.Timeout:
            raise RuntimeError("Request timeout")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Connection failed: {str(e)[:50]}")

    # ==================== READ OPERATIONS ====================

    def find_all(self, include_deleted: bool = False, limit: int = None) -> List[Dict[str, Any]]:
        """Find all records."""
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        limit_clause = f"LIMIT {limit}" if limit else ""

        sql = f"SELECT * FROM {self.full_table_name} {where} {limit_clause}"

        result = self._make_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })

        return result.get('data', [])

    def find_by_id(self, record_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """Find record by primary key."""
        where = f"WHERE {self.primary_key} = '{record_id}'"
        if not include_deleted:
            where += " AND deleted_at IS NULL"

        sql = f"SELECT * FROM {self.full_table_name} {where}"

        result = self._make_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })

        data = result.get('data', [])
        return data[0] if data else None

    def exists(self, record_id: str) -> bool:
        """Check if record exists."""
        sql = f"""
            SELECT 1 FROM {self.full_table_name}
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
            LIMIT 1
        """

        result = self._make_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })

        return len(result.get('data', [])) > 0

    def count(self, include_deleted: bool = False) -> int:
        """Count records."""
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        sql = f"SELECT COUNT(*) as cnt FROM {self.full_table_name} {where}"

        result = self._make_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })

        data = result.get('data', [])
        if data:
            row = data[0]
            return int(row.get('cnt', row.get('_c0', 0)))
        return 0

    # ==================== WRITE OPERATIONS ====================

    def create(self, data: Dict[str, Any]) -> bool:
        """
        Create a new record using dynamic INSERT.

        Args:
            data: Dictionary of column names to values

        Returns:
            True if successful
        """
        # Add audit fields
        now = datetime.now()
        if 'created_at' not in data:
            data['created_at'] = now.strftime('%Y-%m-%d %H:%M:%S')
        if 'updated_at' not in data:
            data['updated_at'] = now.strftime('%Y-%m-%d %H:%M:%S')

        result = self._make_request(
            f'/insert/{self.full_table_name}',
            method='POST',
            data={'data': data}
        )

        logger.info(f"Created record in {self.table_name}: {result.get('elapsed_ms')}ms")
        return True

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing record using dynamic UPDATE.

        Args:
            record_id: Primary key value
            data: Dictionary of columns to update

        Returns:
            True if successful
        """
        # Add updated_at
        if 'updated_at' not in data:
            data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        result = self._make_request(
            f'/update/{self.full_table_name}',
            method='POST',
            data={
                'where': {self.primary_key: record_id},
                'data': data
            }
        )

        logger.info(f"Updated record {record_id} in {self.table_name}: {result.get('elapsed_ms')}ms")
        return True

    def soft_delete(self, record_id: str, deleted_by: str = 'system') -> bool:
        """
        Soft delete a record by setting deleted_at.

        Args:
            record_id: Primary key value
            deleted_by: Username

        Returns:
            True if successful
        """
        result = self._make_request(
            f'/delete/{self.full_table_name}',
            method='POST',
            data={
                'where': {self.primary_key: record_id},
                'soft_delete': True,
                'soft_delete_column': 'deleted_at',
                'deleted_by': deleted_by
            }
        )

        logger.info(f"Soft deleted record {record_id} from {self.table_name}: {result.get('elapsed_ms')}ms")
        return True

    def hard_delete(self, record_id: str) -> bool:
        """
        Permanently delete a record.

        Args:
            record_id: Primary key value

        Returns:
            True if successful
        """
        result = self._make_request(
            f'/delete/{self.full_table_name}',
            method='POST',
            data={
                'where': {self.primary_key: record_id},
                'soft_delete': False
            }
        )

        logger.warning(f"Hard deleted record {record_id} from {self.table_name}: {result.get('elapsed_ms')}ms")
        return True

    def restore(self, record_id: str, restored_by: str = 'system') -> bool:
        """
        Restore a soft-deleted record.

        Args:
            record_id: Primary key value
            restored_by: Username

        Returns:
            True if successful
        """
        return self.update(record_id, {
            'deleted_at': None,
            'updated_by': restored_by
        })

    # ==================== UTILITY METHODS ====================

    def get_schema(self) -> Dict:
        """Get table schema from proxy."""
        result = self._make_request(f'/schema/{self.full_table_name}')
        return result.get('schema', {})

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute a custom SELECT query."""
        result = self._make_request('/query', method='POST', data={
            'sql': sql,
            'database': self.database
        })
        return result.get('data', [])

    def close(self):
        """Close HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
