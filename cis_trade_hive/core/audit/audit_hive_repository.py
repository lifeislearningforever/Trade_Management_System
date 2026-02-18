"""
Audit Log Hive Repository (ORC + ACID)

Handles audit log operations with Hive managed tables.
Uses the new HiveConnectionManager for ACID transaction support.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import uuid
import json

from core.repositories.hive_connection import hive_manager

logger = logging.getLogger(__name__)


class AuditLogHiveRepository:
    """
    Repository for audit log operations with Hive ACID tables.
    Handles reading and writing audit logs from gmp_cis.cis_audit_log table.
    """

    def __init__(self):
        """Initialize audit repository."""
        self.conn_manager = hive_manager
        self.database = 'gmp_cis'
        self.table_name = 'cis_audit_log'

    def _format_value(self, value: Any) -> str:
        """Format value for SQL query."""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        else:
            return str(value)

    def _generate_id(self, prefix: str = 'A') -> str:
        """Generate a unique audit ID."""
        unique_part = str(uuid.uuid4())[:12].upper().replace('-', '')
        return f"{prefix}{unique_part}"

    def log_action(
        self,
        user_id: str,
        username: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Log an action to Hive audit log table (synchronous).

        Args:
            user_id: User ID performing action
            username: Username
            action: Action type (CREATE, UPDATE, DELETE, VIEW, etc.)
            entity_type: Type of entity (PORTFOLIO, TRADE, UDF, etc.)
            entity_id: ID of the entity
            old_value: Previous value (for updates) as JSON string
            new_value: New value (for updates) as JSON string
            ip_address: IP address
            user_agent: User agent string
            **kwargs: Additional fields

        Returns:
            True if logged successfully
        """
        try:
            audit_id = self._generate_id()
            now = datetime.now()

            # Convert dict values to JSON strings if needed
            if old_value and isinstance(old_value, dict):
                old_value = json.dumps(old_value)
            if new_value and isinstance(new_value, dict):
                new_value = json.dumps(new_value)

            query = f"""
                INSERT INTO {self.database}.{self.table_name}
                (audit_id, entity_type, entity_id, action, old_value, new_value,
                 user_id, username, ip_address, user_agent, created_at)
                VALUES (
                    '{audit_id}',
                    {self._format_value(entity_type)},
                    {self._format_value(entity_id)},
                    {self._format_value(action)},
                    {self._format_value(old_value)},
                    {self._format_value(new_value)},
                    {self._format_value(user_id)},
                    {self._format_value(username)},
                    {self._format_value(ip_address)},
                    {self._format_value(user_agent)},
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}'
                )
            """

            success = self.conn_manager.execute_write(query, database=self.database)
            if success:
                logger.debug(f"Audit log created: {action} on {entity_type}/{entity_id}")
            return success

        except Exception as e:
            logger.error(f"Error creating audit log: {str(e)}")
            return False

    def log_action_async(
        self,
        user_id: str,
        username: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Log an action to Hive audit log table (asynchronous/non-blocking).

        Same as log_action but runs in background thread.
        """
        try:
            audit_id = self._generate_id()
            now = datetime.now()

            # Convert dict values to JSON strings if needed
            if old_value and isinstance(old_value, dict):
                old_value = json.dumps(old_value)
            if new_value and isinstance(new_value, dict):
                new_value = json.dumps(new_value)

            query = f"""
                INSERT INTO {self.database}.{self.table_name}
                (audit_id, entity_type, entity_id, action, old_value, new_value,
                 user_id, username, ip_address, user_agent, created_at)
                VALUES (
                    '{audit_id}',
                    {self._format_value(entity_type)},
                    {self._format_value(entity_id)},
                    {self._format_value(action)},
                    {self._format_value(old_value)},
                    {self._format_value(new_value)},
                    {self._format_value(user_id)},
                    {self._format_value(username)},
                    {self._format_value(ip_address)},
                    {self._format_value(user_agent)},
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}'
                )
            """

            logger.debug(f"Queuing async audit log: {action} on {entity_type}/{entity_id}")
            self.conn_manager.execute_write_async(query, database=self.database)

        except Exception as e:
            logger.error(f"Error queuing async audit log: {str(e)}")

    def get_all_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs from Hive with filters.

        Args:
            limit: Maximum number of records
            offset: Number of records to skip
            action: Filter by action type
            entity_type: Filter by entity type
            user_id: Filter by user
            date_from: Filter from date (YYYY-MM-DD)
            date_to: Filter to date (YYYY-MM-DD)
            search: Search term for entity_id/username

        Returns:
            List of audit log records
        """
        try:
            where_clauses = []

            if action:
                where_clauses.append(f"action = '{action}'")

            if entity_type:
                where_clauses.append(f"entity_type = '{entity_type}'")

            if user_id:
                where_clauses.append(f"user_id = '{user_id}'")

            if date_from:
                where_clauses.append(f"created_at >= '{date_from} 00:00:00'")

            if date_to:
                where_clauses.append(f"created_at <= '{date_to} 23:59:59'")

            if search:
                search_term = search.replace("'", "''")
                where_clauses.append(
                    f"(entity_id LIKE '%{search_term}%' OR "
                    f"username LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
                SELECT audit_id, entity_type, entity_id, action, old_value, new_value,
                       user_id, username, ip_address, user_agent, created_at
                FROM {self.database}.{self.table_name}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort in Python by created_at (descending)
            if results:
                results.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error retrieving audit logs: {str(e)}")
            return []

    def get_entity_history(self, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        """
        Get audit history for a specific entity.

        Args:
            entity_type: Type of entity (PORTFOLIO, TRADE, etc.)
            entity_id: Entity ID

        Returns:
            List of audit records for the entity
        """
        try:
            query = f"""
                SELECT audit_id, entity_type, entity_id, action, old_value, new_value,
                       user_id, username, ip_address, user_agent, created_at
                FROM {self.database}.{self.table_name}
                WHERE entity_type = '{entity_type}'
                  AND entity_id = '{entity_id}'
                LIMIT 1000
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by timestamp descending
            if results:
                results.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error retrieving entity history: {str(e)}")
            return []

    def get_user_activity(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get activity for a specific user.

        Args:
            user_id: User ID
            days: Number of days to look back

        Returns:
            List of audit records for the user
        """
        try:
            date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            query = f"""
                SELECT audit_id, entity_type, entity_id, action, old_value, new_value,
                       user_id, username, ip_address, user_agent, created_at
                FROM {self.database}.{self.table_name}
                WHERE user_id = '{user_id}'
                  AND created_at >= '{date_from} 00:00:00'
                LIMIT 1000
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by timestamp descending
            if results:
                results.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error retrieving user activity: {str(e)}")
            return []

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get audit log statistics for the last N days.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with statistics
        """
        try:
            date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get all records for the period
            query = f"""
                SELECT action, entity_type
                FROM {self.database}.{self.table_name}
                WHERE created_at >= '{date_from} 00:00:00'
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Calculate statistics in Python
            total_count = len(results)
            action_counts = {}
            entity_counts = {}

            for row in results:
                action = row.get('action', 'Unknown')
                entity = row.get('entity_type', 'Unknown')

                action_counts[action] = action_counts.get(action, 0) + 1
                entity_counts[entity] = entity_counts.get(entity, 0) + 1

            return {
                'total_count': total_count,
                'days': days,
                'action_breakdown': [
                    {'action': k, 'count': v}
                    for k, v in sorted(action_counts.items(), key=lambda x: x[1], reverse=True)
                ],
                'entity_breakdown': [
                    {'entity_type': k, 'count': v}
                    for k, v in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)
                ]
            }

        except Exception as e:
            logger.error(f"Error getting audit statistics: {str(e)}")
            return {
                'total_count': 0,
                'days': days,
                'action_breakdown': [],
                'entity_breakdown': []
            }

    def get_recent_changes(self, entity_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent changes (CREATE, UPDATE, DELETE actions).

        Args:
            entity_type: Optional filter by entity type
            limit: Maximum records to return

        Returns:
            List of recent change records
        """
        try:
            where_clause = "action IN ('CREATE', 'UPDATE', 'DELETE')"
            if entity_type:
                where_clause += f" AND entity_type = '{entity_type}'"

            query = f"""
                SELECT audit_id, entity_type, entity_id, action, old_value, new_value,
                       user_id, username, ip_address, created_at
                FROM {self.database}.{self.table_name}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            if results:
                results.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error getting recent changes: {str(e)}")
            return []


# Singleton instance
audit_log_repository = AuditLogHiveRepository()
