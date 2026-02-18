"""
Base Repository for Hive Managed Tables (ORC + ACID)

Provides common CRUD operations for Hive ACID tables.
All entity repositories should inherit from this base class.

Features:
- INSERT, UPDATE, DELETE with ACID support
- Soft delete using deleted_at timestamp
- Audit trail support (created_at, updated_at, created_by, updated_by)
- Query builder patterns
- History table support for audit trail
"""

import logging
import uuid
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from abc import ABC, abstractmethod

from .hive_connection import hive_manager

logger = logging.getLogger('core')


class HiveJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for Hive data types."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)


class HiveBaseRepository(ABC):
    """
    Abstract base repository for Hive managed tables with ORC format.

    All entity repositories should inherit from this class and implement:
    - table_name: Name of the Hive table
    - primary_key: Primary key column name
    - columns: List of all column names

    Features:
    - Full ACID transaction support (INSERT, UPDATE, DELETE)
    - Soft delete via deleted_at timestamp
    - Automatic audit fields (created_at, updated_at, created_by, updated_by)
    - History table support for audit trail
    - Connection pooling via HiveConnectionManager
    """

    def __init__(self):
        self.conn_manager = hive_manager
        self.database = 'gmp_cis'

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Return the Hive table name (e.g., 'cis_portfolio')"""
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

    @property
    def history_table_name(self) -> Optional[str]:
        """Return the history table name (if applicable)"""
        return f"{self.table_name}_history"

    def _get_full_table_name(self) -> str:
        """Get fully qualified table name"""
        return f"{self.database}.{self.table_name}"

    def _get_full_history_table_name(self) -> str:
        """Get fully qualified history table name"""
        return f"{self.database}.{self.history_table_name}"

    def _format_value(self, value: Any) -> str:
        """Format value for SQL query"""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif hasattr(value, 'isoformat'):  # date objects
            return f"'{value.isoformat()}'"
        else:
            return str(value)

    def _generate_id(self, prefix: str = '') -> str:
        """Generate a unique ID with optional prefix"""
        unique_part = str(uuid.uuid4())[:8].upper()
        return f"{prefix}{unique_part}" if prefix else unique_part

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def find_all(self, include_deleted: bool = False, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find all records from the table.

        Args:
            include_deleted: If True, include soft-deleted records
            limit: Optional limit on number of records

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
        results = self.conn_manager.execute_query(query)
        return results[0] if results else None

    def exists(self, record_id: str) -> bool:
        """Check if a record exists (not soft-deleted)."""
        query = f"""
            SELECT 1 FROM {self._get_full_table_name()}
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
            LIMIT 1
        """
        results = self.conn_manager.execute_query(query)
        return len(results) > 0

    def count(self, include_deleted: bool = False) -> int:
        """Count records in the table."""
        records = self.find_all(include_deleted=include_deleted)
        return len(records)

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Find records by status."""
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE status = '{status}'
            AND deleted_at IS NULL
        """
        return self.conn_manager.execute_query(query)

    def find_deleted(self) -> List[Dict[str, Any]]:
        """Find all soft-deleted records."""
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE deleted_at IS NOT NULL
        """
        return self.conn_manager.execute_query(query)

    # =========================================================================
    # WRITE OPERATIONS (ACID)
    # =========================================================================

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

        # Build INSERT query
        columns = list(data.keys())
        values = [self._format_value(data[col]) for col in columns]

        query = f"""
            INSERT INTO {self._get_full_table_name()} ({', '.join(columns)})
            VALUES ({', '.join(values)})
        """

        logger.info(f"Creating record in {self.table_name}")
        return self.conn_manager.execute_write(query)

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing record.

        Args:
            record_id: Primary key value
            data: Dictionary of column names to new values

        Returns:
            True if successful, False otherwise
        """
        # Update timestamp
        data['updated_at'] = datetime.now()

        # Build SET clause
        set_clauses = [f"{col} = {self._format_value(val)}" for col, val in data.items()]

        query = f"""
            UPDATE {self._get_full_table_name()}
            SET {', '.join(set_clauses)}
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
        """

        logger.info(f"Updating record {record_id} in {self.table_name}")
        return self.conn_manager.execute_write(query)

    def soft_delete(self, record_id: str, deleted_by: str = 'system') -> bool:
        """
        Soft delete a record by setting deleted_at timestamp.

        Args:
            record_id: Primary key value
            deleted_by: Username of person performing delete

        Returns:
            True if successful, False otherwise
        """
        now = datetime.now()
        query = f"""
            UPDATE {self._get_full_table_name()}
            SET deleted_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_by = '{deleted_by}'
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
        """

        logger.info(f"Soft deleting record {record_id} from {self.table_name}")
        return self.conn_manager.execute_write(query)

    def restore(self, record_id: str, restored_by: str = 'system') -> bool:
        """
        Restore a soft-deleted record.

        Args:
            record_id: Primary key value
            restored_by: Username of person performing restore

        Returns:
            True if successful, False otherwise
        """
        now = datetime.now()
        query = f"""
            UPDATE {self._get_full_table_name()}
            SET deleted_at = NULL,
                updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_by = '{restored_by}'
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NOT NULL
        """

        logger.info(f"Restoring record {record_id} in {self.table_name}")
        return self.conn_manager.execute_write(query)

    def hard_delete(self, record_id: str) -> bool:
        """
        Permanently delete a record (use with caution).

        Args:
            record_id: Primary key value

        Returns:
            True if successful, False otherwise
        """
        query = f"""
            DELETE FROM {self._get_full_table_name()}
            WHERE {self.primary_key} = '{record_id}'
        """

        logger.warning(f"Hard deleting record {record_id} from {self.table_name}")
        return self.conn_manager.execute_write(query)

    def update_status(self, record_id: str, status: str, updated_by: str = 'system') -> bool:
        """
        Update record status.

        Args:
            record_id: Primary key value
            status: New status value
            updated_by: Username

        Returns:
            True if successful
        """
        return self.update(record_id, {
            'status': status,
            'updated_by': updated_by
        })

    # =========================================================================
    # HISTORY / AUDIT OPERATIONS
    # =========================================================================

    def create_history_record(self, record_id: str, action: str,
                              old_data: Optional[Dict] = None,
                              new_data: Optional[Dict] = None,
                              user: str = 'system') -> bool:
        """
        Create a history record for audit trail.

        Args:
            record_id: ID of the main record
            action: Action type (CREATE, UPDATE, DELETE, etc.)
            old_data: Previous state (for updates)
            new_data: New state (for creates/updates)
            user: Username performing the action

        Returns:
            True if successful
        """
        history_id = self._generate_id('H')
        now = datetime.now()

        old_value = json.dumps(old_data, cls=HiveJSONEncoder) if old_data else None
        new_value = json.dumps(new_data, cls=HiveJSONEncoder) if new_data else None

        query = f"""
            INSERT INTO {self._get_full_history_table_name()} 
            (history_id, {self.primary_key}, action, old_value, new_value, 
             changed_by, changed_at, created_at)
            VALUES (
                '{history_id}',
                '{record_id}',
                '{action}',
                {self._format_value(old_value)},
                {self._format_value(new_value)},
                '{user}',
                '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                '{now.strftime('%Y-%m-%d %H:%M:%S')}'
            )
        """

        logger.info(f"Creating history record for {self.table_name}: {action}")
        return self.conn_manager.execute_write(query)

    def create_history_record_async(self, record_id: str, action: str,
                                    old_data: Optional[Dict] = None,
                                    new_data: Optional[Dict] = None,
                                    user: str = 'system') -> None:
        """
        Create a history record asynchronously (non-blocking).

        Same as create_history_record but runs in background thread.
        """
        history_id = self._generate_id('H')
        now = datetime.now()

        old_value = json.dumps(old_data, cls=HiveJSONEncoder) if old_data else None
        new_value = json.dumps(new_data, cls=HiveJSONEncoder) if new_data else None

        query = f"""
            INSERT INTO {self._get_full_history_table_name()} 
            (history_id, {self.primary_key}, action, old_value, new_value, 
             changed_by, changed_at, created_at)
            VALUES (
                '{history_id}',
                '{record_id}',
                '{action}',
                {self._format_value(old_value)},
                {self._format_value(new_value)},
                '{user}',
                '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                '{now.strftime('%Y-%m-%d %H:%M:%S')}'
            )
        """

        logger.debug(f"Queuing async history record for {self.table_name}: {action}")
        self.conn_manager.execute_write_async(query)

    def get_history(self, record_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history records for a specific entity.

        Args:
            record_id: Primary key value
            limit: Maximum number of records to return

        Returns:
            List of history records
        """
        query = f"""
            SELECT * FROM {self._get_full_history_table_name()}
            WHERE {self.primary_key} = '{record_id}'
            LIMIT {limit}
        """
        return self.conn_manager.execute_query(query)

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def bulk_create(self, records: List[Dict[str, Any]]) -> bool:
        """
        Create multiple records in a single INSERT.

        Args:
            records: List of dictionaries with column data

        Returns:
            True if successful
        """
        if not records:
            return True

        now = datetime.now()

        # Ensure audit fields for all records
        for record in records:
            if 'created_at' not in record:
                record['created_at'] = now
            if 'updated_at' not in record:
                record['updated_at'] = now
            if 'deleted_at' not in record:
                record['deleted_at'] = None

        columns = list(records[0].keys())
        values_list = []

        for record in records:
            values = [self._format_value(record.get(col)) for col in columns]
            values_list.append(f"({', '.join(values)})")

        query = f"""
            INSERT INTO {self._get_full_table_name()} ({', '.join(columns)})
            VALUES {', '.join(values_list)}
        """

        logger.info(f"Bulk creating {len(records)} records in {self.table_name}")
        return self.conn_manager.execute_write(query)

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    def search(self, search_term: str, search_columns: List[str]) -> List[Dict[str, Any]]:
        """
        Search records by term across specified columns.

        Args:
            search_term: Term to search for
            search_columns: List of column names to search

        Returns:
            List of matching records
        """
        term = search_term.lower()
        conditions = [f"LOWER({col}) LIKE '%{term}%'" for col in search_columns]

        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE ({' OR '.join(conditions)})
            AND deleted_at IS NULL
        """
        return self.conn_manager.execute_query(query)
