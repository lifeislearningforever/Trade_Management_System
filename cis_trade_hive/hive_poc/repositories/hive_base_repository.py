"""
Base Repository for Hive Managed Tables

Provides common CRUD operations for Hive tables with ORC format.
Implements soft delete using deleted_at timestamp.
Uses HiveServer2 for full ACID transaction support (INSERT, UPDATE, DELETE).
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from abc import ABC, abstractmethod

from django.conf import settings
from .hive_connection import HiveConnectionManager

logger = logging.getLogger('hive_poc')


class HiveBaseRepository(ABC):
    """
    Abstract base repository for Hive managed tables.

    Features:
    - CRUD operations on Hive ACID tables with ORC format
    - Full transaction support (INSERT, UPDATE, DELETE)
    - Soft delete support via deleted_at timestamp
    - Query builder patterns for consistency
    """

    def __init__(self):
        self.conn_manager = HiveConnectionManager()
        self.database = settings.IMPALA_CONFIG['DATABASE']

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
            escaped = value.replace('\\', '\\\\').replace("'", "\\'")
            return f"'{escaped}'"
        elif isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        else:
            return str(value)

    def find_all(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Find all records from the table.

        Args:
            include_deleted: If True, include soft-deleted records

        Returns:
            List of dictionaries representing records
        """
        where_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            {where_clause}
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

    def _execute_acid_write(self, query: str) -> bool:
        """
        Execute a write query with MapReduce engine for ACID support.

        Hive ACID tables require MapReduce engine for full transactional support.
        """
        # Set MapReduce engine before ACID operations
        engine_query = "SET hive.execution.engine=mr"
        self.conn_manager.execute_write(engine_query)
        return self.conn_manager.execute_write(query)

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
        return self._execute_acid_write(query)

    def update(self, record_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing record.

        Note: Hive managed tables with ACID support allow UPDATE operations.
        For non-ACID tables, you would need to use INSERT OVERWRITE or
        a merge pattern.

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
        return self._execute_acid_write(query)

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
        return self._execute_acid_write(query)

    def count(self, include_deleted: bool = False) -> int:
        """
        Count records in the table.

        Args:
            include_deleted: If True, include soft-deleted records

        Returns:
            Number of records
        """
        # Use simple query and count in Python (Hive COUNT(*) can be slow)
        records = self.find_all(include_deleted=include_deleted)
        return len(records)

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
        return self.conn_manager.execute_query(query)
