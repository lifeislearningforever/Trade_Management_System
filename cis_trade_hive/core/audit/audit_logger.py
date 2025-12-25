"""
Audit logger implementation following SOLID principles.

- Single Responsibility: Each class has one clear purpose
- Open/Closed: Open for extension via inheritance, closed for modification
- Liskov Substitution: Any AuditLogger implementation can be substituted
- Interface Segregation: Clean interface with only necessary methods
- Dependency Inversion: Depends on abstractions (AuditLogger interface)
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import logging
import time

from django.conf import settings

from .audit_models import AuditEntry
from ..repositories.hive_connection import HiveConnectionManager

logger = logging.getLogger(__name__)


class AuditLogger(ABC):
    """
    Abstract base class for audit loggers.
    Follows Interface Segregation and Dependency Inversion principles.
    """

    @abstractmethod
    def log(self, audit_entry: AuditEntry) -> bool:
        """
        Log a single audit entry.

        Args:
            audit_entry: AuditEntry object to log

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def log_batch(self, audit_entries: List[AuditEntry]) -> bool:
        """
        Log multiple audit entries in batch.

        Args:
            audit_entries: List of AuditEntry objects

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def query(self, filters: dict, limit: int = 100) -> List[dict]:
        """
        Query audit logs with filters.

        Args:
            filters: Dictionary of filter criteria
            limit: Maximum number of results

        Returns:
            List of audit log dictionaries
        """
        pass


class HiveAuditLogger(AuditLogger):
    """
    Concrete implementation of AuditLogger using Hive.
    Follows Single Responsibility Principle.
    """

    def __init__(self, table_name: str = 'cis_audit_log'):
        """
        Initialize Hive audit logger.

        Args:
            table_name: Name of the Hive audit table
        """
        self.table_name = table_name
        self.connection_manager = HiveConnectionManager()
        self._audit_id_counter = int(time.time() * 1000)  # Simple ID generation

    def _get_next_audit_id(self) -> int:
        """Generate next audit ID (simple increment)."""
        self._audit_id_counter += 1
        return self._audit_id_counter

    def log(self, audit_entry: AuditEntry) -> bool:
        """
        Log a single audit entry to Hive.

        Args:
            audit_entry: AuditEntry object to log

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Set audit ID if not provided
            if audit_entry.audit_id is None:
                audit_entry.audit_id = self._get_next_audit_id()

            # Get connection
            conn = self.connection_manager.get_connection()
            if not conn:
                logger.error("Failed to get Hive connection for audit logging")
                return False

            cursor = conn.cursor()

            # Prepare INSERT statement
            values = audit_entry.to_hive_values()
            placeholders = ', '.join(['%s'] * len(values))

            insert_sql = f"""
                INSERT INTO TABLE {self.table_name}
                VALUES ({placeholders})
            """

            # Execute insert
            cursor.execute(insert_sql, values)
            logger.info(f"Audit log entry created: {audit_entry.action_type.value} by {audit_entry.username}")

            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Failed to log audit entry: {str(e)}")
            logger.exception(e)
            return False

    def log_batch(self, audit_entries: List[AuditEntry]) -> bool:
        """
        Log multiple audit entries to Hive in batch.

        Args:
            audit_entries: List of AuditEntry objects

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not audit_entries:
                return True

            conn = self.connection_manager.get_connection()
            if not conn:
                logger.error("Failed to get Hive connection for batch audit logging")
                return False

            cursor = conn.cursor()

            # Prepare batch insert
            for entry in audit_entries:
                if entry.audit_id is None:
                    entry.audit_id = self._get_next_audit_id()

                values = entry.to_hive_values()
                placeholders = ', '.join(['%s'] * len(values))

                insert_sql = f"""
                    INSERT INTO TABLE {self.table_name}
                    VALUES ({placeholders})
                """

                cursor.execute(insert_sql, values)

            logger.info(f"Batch audit log: {len(audit_entries)} entries created")

            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Failed to log batch audit entries: {str(e)}")
            logger.exception(e)
            return False

    def query(self, filters: dict = None, limit: int = 100) -> List[dict]:
        """
        Query audit logs from Hive with filters.

        Args:
            filters: Dictionary of filter criteria
                     e.g., {'username': 'john', 'action_type': 'CREATE'}
            limit: Maximum number of results

        Returns:
            List of audit log dictionaries
        """
        try:
            conn = self.connection_manager.get_connection()
            if not conn:
                logger.error("Failed to get Hive connection for audit query")
                return []

            cursor = conn.cursor()

            # Build query
            query = f"SELECT * FROM {self.table_name}"

            # Add filters
            where_clauses = []
            params = []

            if filters:
                for key, value in filters.items():
                    where_clauses.append(f"{key} = %s")
                    params.append(value)

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            # Add ordering and limit
            query += " ORDER BY audit_timestamp DESC"
            query += f" LIMIT {limit}"

            # Execute query
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Fetch results
            columns = [desc[0] for desc in cursor.description]
            results = []

            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            cursor.close()
            return results

        except Exception as e:
            logger.error(f"Failed to query audit logs: {str(e)}")
            logger.exception(e)
            return []

    def get_user_activity(self, username: str, days: int = 7, limit: int = 100) -> List[dict]:
        """
        Get recent activity for a specific user.

        Args:
            username: Username to query
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            List of audit log dictionaries
        """
        from datetime import datetime, timedelta

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

        try:
            conn = self.connection_manager.get_connection()
            if not conn:
                return []

            cursor = conn.cursor()

            query = f"""
                SELECT *
                FROM {self.table_name}
                WHERE username = %s
                  AND audit_date >= %s
                ORDER BY audit_timestamp DESC
                LIMIT {limit}
            """

            cursor.execute(query, (username, cutoff_date))

            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]

            cursor.close()
            return results

        except Exception as e:
            logger.error(f"Failed to get user activity: {str(e)}")
            return []

    def get_entity_history(self, entity_type: str, entity_id: str, limit: int = 50) -> List[dict]:
        """
        Get change history for a specific entity.

        Args:
            entity_type: Type of entity (e.g., 'PORTFOLIO', 'TRADE')
            entity_id: ID of the entity
            limit: Maximum number of results

        Returns:
            List of audit log dictionaries
        """
        return self.query(
            filters={'entity_type': entity_type, 'entity_id': entity_id},
            limit=limit
        )


class ConsoleAuditLogger(AuditLogger):
    """
    Simple console audit logger for development/testing.
    Follows Single Responsibility Principle.
    """

    def log(self, audit_entry: AuditEntry) -> bool:
        """Log to console."""
        print(f"[AUDIT] {audit_entry.audit_timestamp} | "
              f"{audit_entry.action_type.value} | "
              f"{audit_entry.username} | "
              f"{audit_entry.entity_type.value if audit_entry.entity_type else 'N/A'} | "
              f"{audit_entry.status.value}")
        return True

    def log_batch(self, audit_entries: List[AuditEntry]) -> bool:
        """Log batch to console."""
        for entry in audit_entries:
            self.log(entry)
        return True

    def query(self, filters: dict = None, limit: int = 100) -> List[dict]:
        """Console logger doesn't support querying."""
        logger.warning("ConsoleAuditLogger doesn't support querying")
        return []


# Singleton instance
_audit_logger_instance: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get singleton audit logger instance.
    Factory pattern implementation.

    Returns:
        AuditLogger instance
    """
    global _audit_logger_instance

    if _audit_logger_instance is None:
        # Determine which logger to use based on settings
        logger_type = getattr(settings, 'AUDIT_LOGGER_TYPE', 'hive')

        if logger_type == 'hive':
            _audit_logger_instance = HiveAuditLogger()
        elif logger_type == 'console':
            _audit_logger_instance = ConsoleAuditLogger()
        else:
            # Default to Hive
            _audit_logger_instance = HiveAuditLogger()

        logger.info(f"Initialized audit logger: {logger_type}")

    return _audit_logger_instance
