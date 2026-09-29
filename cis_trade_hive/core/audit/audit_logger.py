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

from django.conf import settings

from .audit_models import AuditEntry

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


class ImpalaAuditLogger(AuditLogger):
    """
    Concrete implementation of AuditLogger using Impala/Kudu.
    Uses AuditLogKuduRepository with proper connection pooling.
    Follows Single Responsibility Principle.
    """

    def __init__(self):
        """
        Initialize Impala audit logger.
        Uses the existing AuditLogKuduRepository which handles connection pooling.
        """
        from .audit_kudu_repository import audit_log_kudu_repository
        self.repository = audit_log_kudu_repository

    def log(self, audit_entry: AuditEntry) -> bool:
        """
        Log a single audit entry to Kudu using Impala.

        Args:
            audit_entry: AuditEntry object to log

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert AuditEntry to repository method parameters
            return self.repository.log_action(
                user_id=audit_entry.user_id or '',
                username=audit_entry.username,
                action_type=audit_entry.action_type.value,
                entity_type=audit_entry.entity_type.value if audit_entry.entity_type else '',
                entity_id=audit_entry.entity_id,
                entity_name=audit_entry.entity_name,
                action_description=audit_entry.action_description,
                old_value=audit_entry.old_value,
                new_value=audit_entry.new_value,
                field_name=audit_entry.field_name,
                ip_address=audit_entry.ip_address,
                user_agent=audit_entry.user_agent,
                request_path=audit_entry.request_path,
                request_method=audit_entry.request_method,
                status=audit_entry.status.value,
                error_message=audit_entry.error_message,
                # Additional fields
                user_email=audit_entry.user_email,
                action_category=audit_entry.action_category.value,
                request_params=str(audit_entry.request_params) if audit_entry.request_params else None,
                status_code=audit_entry.status_code,
                error_traceback=audit_entry.error_traceback,
                session_id=audit_entry.session_id,
                module_name=audit_entry.module_name,
                function_name=audit_entry.function_name,
                duration_ms=audit_entry.duration_ms,
                tags=','.join(audit_entry.tags) if audit_entry.tags else None,
                metadata=str(audit_entry.metadata) if audit_entry.metadata else None
            )

        except Exception as e:
            logger.error(f"Failed to log audit entry: {str(e)}")
            logger.exception(e)
            return False

    def log_batch(self, audit_entries: List[AuditEntry]) -> bool:
        """
        Log multiple audit entries to Kudu in batch.

        Args:
            audit_entries: List of AuditEntry objects

        Returns:
            bool: True if all successful, False otherwise
        """
        try:
            if not audit_entries:
                return True

            success_count = 0
            for entry in audit_entries:
                if self.log(entry):
                    success_count += 1

            logger.info(f"Batch audit log: {success_count}/{len(audit_entries)} entries created")
            return success_count == len(audit_entries)

        except Exception as e:
            logger.error(f"Failed to log batch audit entries: {str(e)}")
            logger.exception(e)
            return False

    def query(self, filters: dict = None, limit: int = 100) -> List[dict]:
        """
        Query audit logs from Kudu with filters.

        Args:
            filters: Dictionary of filter criteria
                     e.g., {'username': 'john', 'action_type': 'CREATE'}
            limit: Maximum number of results

        Returns:
            List of audit log dictionaries
        """
        try:
            from .audit_kudu_repository import ImpalaAuditConnection, AuditLogKuduRepository

            # Build query
            query = f"SELECT * FROM {ImpalaAuditConnection.DATABASE}.{AuditLogKuduRepository.GENERAL_AUDIT_TABLE}"

            # Add filters
            where_clauses = []
            if filters:
                for key, value in filters.items():
                    # Escape single quotes in values
                    escaped_value = str(value).replace("'", "\\'")
                    where_clauses.append(f"{key} = '{escaped_value}'")

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            # Add ordering and limit
            query += " ORDER BY audit_timestamp DESC"
            query += f" LIMIT {limit}"

            # Execute query using repository
            results = ImpalaAuditConnection.execute_query(query)
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
        from .audit_kudu_repository import ImpalaAuditConnection, AuditLogKuduRepository

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

        try:
            # Escape username
            escaped_username = username.replace("'", "\\'")

            query = f"""
                SELECT *
                FROM {ImpalaAuditConnection.DATABASE}.{AuditLogKuduRepository.GENERAL_AUDIT_TABLE}
                WHERE username = '{escaped_username}'
                  AND audit_date >= '{cutoff_date}'
                ORDER BY audit_timestamp DESC
                LIMIT {limit}
            """

            results = ImpalaAuditConnection.execute_query(query)
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
        logger_type = getattr(settings, 'AUDIT_LOGGER_TYPE', 'impala')

        if logger_type == 'impala':
            _audit_logger_instance = ImpalaAuditLogger()
        elif logger_type == 'console':
            _audit_logger_instance = ConsoleAuditLogger()
        else:
            # Default to Impala (recommended for production)
            _audit_logger_instance = ImpalaAuditLogger()

        logger.info(f"Initialized audit logger: {logger_type}")

    return _audit_logger_instance
