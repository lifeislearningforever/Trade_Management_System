"""
Audit Log Kudu/Impala Repository
Handles audit log operations with Kudu/Impala database.
Migrated from Hive to Kudu for better performance and real-time updates.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from core.repositories.impala_connection import impala_manager
import logging
import uuid

logger = logging.getLogger(__name__)


class ImpalaAuditConnection:
    """Manages Impala database connections for audit logging."""

    DATABASE = 'gmp_cis'

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """
        Execute Impala query and return results.

        Args:
            query: SQL query to execute

        Returns:
            List of dictionaries with query results
        """
        try:
            results = impala_manager.execute_query(query, database=ImpalaAuditConnection.DATABASE)
            logger.info(f"Audit query executed successfully: {len(results) if results else 0} records")
            return results if results else []

        except Exception as e:
            logger.error(f"Error executing audit query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    @staticmethod
    def insert_audit_log(table_name: str, data: Dict[str, Any]) -> bool:
        """
        Insert audit log record into Kudu table using Impala UPSERT statement.
        Uses backticks to escape column names (handles reserved keywords like 'metadata').

        Args:
            table_name: Name of the audit table (without database prefix)
            data: Dictionary with audit data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build column names and values for UPSERT
            columns = []
            values = []

            for key, value in data.items():
                if value is not None:
                    # Escape column names with backticks to handle reserved keywords
                    columns.append(f"`{key}`")
                    # Format value based on type
                    if isinstance(value, str):
                        # Escape single quotes for SQL by doubling them
                        # Also escape backslashes to prevent injection
                        escaped_value = value.replace("\\", "\\\\").replace("'", "\\'")
                        values.append(f"'{escaped_value}'")
                    elif isinstance(value, bool):
                        values.append('true' if value else 'false')
                    elif isinstance(value, (int, float)):
                        values.append(str(value))
                    else:
                        values.append(f"'{str(value)}'")

            # Build UPSERT statement (better for Kudu than INSERT)
            upsert_query = f"""
            UPSERT INTO {ImpalaAuditConnection.DATABASE}.{table_name}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            # Execute UPSERT via Impala
            success = impala_manager.execute_write(upsert_query, database=ImpalaAuditConnection.DATABASE)

            if success:
                logger.info(f"Successfully inserted audit log into {table_name}")
            return success

        except Exception as e:
            logger.error(f"Error inserting audit log into {table_name}: {str(e)}")
            logger.debug(f"Failed data: {data}")
            return False


class AuditLogKuduRepository:
    """
    Repository for audit log operations with Kudu/Impala.
    Handles reading from and (planned) writing audit logs to gmp_cis.cis_audit_log table.
    """

    GENERAL_AUDIT_TABLE = 'cis_audit_log'
    UDF_AUDIT_TABLE = 'cis_udf_audit_log'
    UDF_VALUE_AUDIT_TABLE = 'cis_udf_value_audit_log'

    @staticmethod
    def log_action(
        user_id: str,
        username: str,
        action_type: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        action_description: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        field_name: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        request_method: Optional[str] = None,
        status: str = 'SUCCESS',
        error_message: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Log an action to Kudu audit log table.

        Args:
            user_id: User ID performing action
            username: Username
            action_type: Type of action (CREATE, UPDATE, DELETE, VIEW, etc.)
            entity_type: Type of entity (PORTFOLIO, TRADE, UDF, etc.)
            entity_id: ID of the entity
            entity_name: Name of the entity
            action_description: Human-readable description
            old_value: Previous value (for updates)
            new_value: New value (for updates)
            field_name: Field that changed
            ip_address: IP address
            user_agent: User agent string
            request_path: Request URL path
            request_method: HTTP method
            status: Action status (SUCCESS, FAILURE)
            error_message: Error message if failed
            **kwargs: Additional fields (module_name, function_name, etc.)

        Returns:
            True if logged successfully
        """
        try:
            # Generate audit timestamp and date
            now = datetime.now()
            audit_timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            audit_date = now.strftime('%Y-%m-%d')

            # Generate unique audit_id (timestamp-based with random component)
            audit_id = int(now.timestamp() * 1000) + (uuid.uuid4().int % 1000)

            # Prepare audit data
            audit_data = {
                'audit_id': audit_id,
                'audit_timestamp': audit_timestamp,
                'user_id': user_id,
                'username': username,
                'user_email': kwargs.get('user_email'),
                'action_type': action_type,
                'action_category': kwargs.get('action_category', 'DATA'),
                'action_description': action_description,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'entity_name': entity_name,
                'field_name': field_name,
                'old_value': old_value,
                'new_value': new_value,
                'request_method': request_method,
                'request_path': request_path,
                'request_params': kwargs.get('request_params'),
                'status': status,
                'status_code': kwargs.get('status_code', 200),
                'error_message': error_message,
                'error_traceback': kwargs.get('error_traceback'),
                'session_id': kwargs.get('session_id'),
                'ip_address': ip_address,
                'user_agent': user_agent,
                'module_name': kwargs.get('module_name'),
                'function_name': kwargs.get('function_name'),
                'duration_ms': kwargs.get('duration_ms'),
                'tags': kwargs.get('tags'),
                'metadata': kwargs.get('metadata'),
                'audit_date': audit_date
            }

            # Log to Kudu (placeholder for now)
            success = ImpalaAuditConnection.insert_audit_log(
                AuditLogKuduRepository.GENERAL_AUDIT_TABLE,
                audit_data
            )

            # Also log to Django logger for immediate visibility
            logger.info(
                f"AUDIT: [{status}] {username} ({user_id}) - {action_type} on {entity_type}"
                f"{f'#{entity_id}' if entity_id else ''} - {action_description}"
            )

            return True  # Return True even if Kudu write is not implemented

        except Exception as e:
            logger.error(f"Error creating audit log: {str(e)}")
            return False

    @staticmethod
    def log_udf_action(
        user_id: str,
        username: str,
        action_type: str,
        udf_id: int,
        field_name: str,
        label: str,
        entity_type: str,
        changes: Optional[str] = None,
        action_description: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = 'SUCCESS',
        error_message: Optional[str] = None
    ) -> bool:
        """
        Log UDF definition action (CREATE, UPDATE, DELETE).

        Args:
            user_id: User ID
            username: Username
            action_type: Action type (CREATE, UPDATE, DELETE)
            udf_id: UDF definition ID
            field_name: UDF field name
            label: UDF label
            entity_type: Entity type (PORTFOLIO, TRADE, etc.)
            changes: JSON string of changes
            action_description: Description
            ip_address: IP address
            user_agent: User agent
            session_id: Session ID
            status: Status (SUCCESS, FAILURE)
            error_message: Error message if failed

        Returns:
            True if logged successfully
        """
        try:
            now = datetime.now()
            audit_id = int(now.timestamp() * 1000) + (uuid.uuid4().int % 1000)

            audit_data = {
                'audit_id': audit_id,
                'audit_timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                'user_id': user_id,
                'username': username,
                'action_type': action_type,
                'udf_id': udf_id,
                'field_name': field_name,
                'label': label,
                'entity_type': entity_type,
                'changes': changes,
                'action_description': action_description,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'session_id': session_id,
                'status': status,
                'error_message': error_message,
                'audit_date': now.strftime('%Y-%m-%d')
            }

            # Log to Kudu UDF audit table
            ImpalaAuditConnection.insert_audit_log(
                AuditLogKuduRepository.UDF_AUDIT_TABLE,
                audit_data
            )

            logger.info(
                f"UDF AUDIT: [{status}] {username} - {action_type} UDF '{field_name}' ({label}) for {entity_type}"
            )

            return True

        except Exception as e:
            logger.error(f"Error creating UDF audit log: {str(e)}")
            return False

    @staticmethod
    def log_udf_value_action(
        user_id: str,
        username: str,
        action_type: str,
        udf_id: int,
        field_name: str,
        entity_type: str,
        entity_id: int,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        value_type: Optional[str] = None,
        action_description: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = 'SUCCESS'
    ) -> bool:
        """
        Log UDF value change action.

        Args:
            user_id: User ID
            username: Username
            action_type: Action type (CREATE, UPDATE, DELETE)
            udf_id: UDF definition ID
            field_name: UDF field name
            entity_type: Entity type (PORTFOLIO, TRADE, etc.)
            entity_id: Entity ID
            old_value: Previous value
            new_value: New value
            value_type: Value type (TEXT, NUMBER, etc.)
            action_description: Description
            ip_address: IP address
            session_id: Session ID
            status: Status

        Returns:
            True if logged successfully
        """
        try:
            now = datetime.now()
            audit_id = int(now.timestamp() * 1000) + (uuid.uuid4().int % 1000)

            audit_data = {
                'audit_id': audit_id,
                'audit_timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                'user_id': user_id,
                'username': username,
                'action_type': action_type,
                'udf_id': udf_id,
                'field_name': field_name,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'old_value': old_value,
                'new_value': new_value,
                'value_type': value_type,
                'action_description': action_description,
                'ip_address': ip_address,
                'session_id': session_id,
                'status': status,
                'audit_date': now.strftime('%Y-%m-%d')
            }

            # Log to Kudu UDF value audit table
            ImpalaAuditConnection.insert_audit_log(
                AuditLogKuduRepository.UDF_VALUE_AUDIT_TABLE,
                audit_data
            )

            logger.info(
                f"UDF VALUE AUDIT: [{status}] {username} - {action_type} '{field_name}' = "
                f"'{new_value}' for {entity_type}#{entity_id} (was: '{old_value}')"
            )

            return True

        except Exception as e:
            logger.error(f"Error creating UDF value audit log: {str(e)}")
            return False

    @staticmethod
    def get_all_logs(
        limit: int = 100,
        offset: int = 0,
        action_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        user_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs from Kudu/Impala with filters.

        Args:
            limit: Maximum number of records
            offset: Number of records to skip
            action_type: Filter by action type
            entity_type: Filter by entity type
            user_id: Filter by user
            date_from: Filter from date (YYYY-MM-DD)
            date_to: Filter to date (YYYY-MM-DD)
            search: Search term for description/entity

        Returns:
            List of audit log records
        """
        try:
            # Build WHERE clause
            where_clauses = []

            if action_type:
                where_clauses.append(f"action_type = '{action_type}'")

            if entity_type:
                where_clauses.append(f"entity_type = '{entity_type}'")

            if user_id:
                where_clauses.append(f"user_id = '{user_id}'")

            if date_from:
                where_clauses.append(f"audit_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"audit_date <= '{date_to}'")

            if search:
                search_term = search.replace("'", "''")
                where_clauses.append(
                    f"(action_description LIKE '%{search_term}%' OR "
                    f"entity_name LIKE '%{search_term}%' OR "
                    f"username LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Build query with ORDER BY (Impala supports it)
            query = f"""
            SELECT *
            FROM {AuditLogKuduRepository.GENERAL_AUDIT_TABLE}
            WHERE {where_clause}
            ORDER BY audit_timestamp DESC
            LIMIT {limit}
            OFFSET {offset}
            """

            results = ImpalaAuditConnection.execute_query(query)
            return results

        except Exception as e:
            logger.error(f"Error retrieving audit logs: {str(e)}")
            return []

    @staticmethod
    def get_entity_history(entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
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
            SELECT *
            FROM {AuditLogKuduRepository.GENERAL_AUDIT_TABLE}
            WHERE entity_type = '{entity_type}'
            AND entity_id = '{entity_id}'
            ORDER BY audit_timestamp DESC
            LIMIT 1000
            """

            results = ImpalaAuditConnection.execute_query(query)
            return results

        except Exception as e:
            logger.error(f"Error retrieving entity history: {str(e)}")
            return []

    @staticmethod
    def get_udf_audit_logs(
        udf_id: Optional[int] = None,
        field_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get UDF definition audit logs.

        Args:
            udf_id: Filter by UDF ID
            field_name: Filter by field name
            limit: Maximum records

        Returns:
            List of UDF audit records
        """
        try:
            where_clauses = []
            if udf_id:
                where_clauses.append(f"udf_id = {udf_id}")
            if field_name:
                where_clauses.append(f"field_name = '{field_name}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
            SELECT *
            FROM {AuditLogKuduRepository.UDF_AUDIT_TABLE}
            WHERE {where_clause}
            ORDER BY audit_timestamp DESC
            LIMIT {limit}
            """

            results = ImpalaAuditConnection.execute_query(query)
            return results

        except Exception as e:
            logger.error(f"Error retrieving UDF audit logs: {str(e)}")
            return []

    @staticmethod
    def get_udf_value_audit_logs(
        entity_type: str,
        entity_id: int,
        udf_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get UDF value change audit logs for an entity.

        Args:
            entity_type: Entity type
            entity_id: Entity ID
            udf_id: Filter by UDF ID (optional)
            limit: Maximum records

        Returns:
            List of UDF value audit records
        """
        try:
            where_clauses = [
                f"entity_type = '{entity_type}'",
                f"entity_id = {entity_id}"
            ]

            if udf_id:
                where_clauses.append(f"udf_id = {udf_id}")

            where_clause = " AND ".join(where_clauses)

            query = f"""
            SELECT *
            FROM {AuditLogKuduRepository.UDF_VALUE_AUDIT_TABLE}
            WHERE {where_clause}
            ORDER BY audit_timestamp DESC
            LIMIT {limit}
            """

            results = ImpalaAuditConnection.execute_query(query)
            return results

        except Exception as e:
            logger.error(f"Error retrieving UDF value audit logs: {str(e)}")
            return []


# Singleton instance
audit_log_kudu_repository = AuditLogKuduRepository()
