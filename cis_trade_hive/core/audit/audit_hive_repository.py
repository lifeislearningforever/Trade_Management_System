"""
Audit Log Hive Repository
Handles audit log operations with Hive database.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pyhive import hive
import logging
import os
import tempfile
import uuid
import subprocess

logger = logging.getLogger(__name__)


class HiveConnection:
    """Manages Hive database connections for audit logging."""

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """
        Execute Hive query and return results.

        Args:
            query: SQL query to execute

        Returns:
            List of dictionaries with query results
        """
        conn = None
        cursor = None
        try:
            # Add connection timeout
            conn = hive.Connection(
                host='localhost',
                port=10000,
                database='cis',
                auth='NOSASL',
                configuration={'hive.server2.thrift.client.connect.timeout': '10000',
                              'hive.server2.thrift.client.socketTimeout': '60000'}
            )
            cursor = conn.cursor()
            cursor.execute(query)

            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # Fetch all results
            rows = cursor.fetchall()

            # Convert to list of dictionaries
            results = []
            for row in rows:
                # Handle qualified column names (table.column -> column)
                row_dict = {}
                for i, col in enumerate(columns):
                    col_name = col.split('.')[-1] if '.' in col else col
                    row_dict[col_name] = row[i]
                results.append(row_dict)

            if cursor:
                cursor.close()
            if conn:
                conn.close()

            logger.info(f"Audit query executed successfully: {len(results)} records")
            return results

        except Exception as e:
            logger.error(f"Error executing audit query: {str(e)}")
            # Clean up connections
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass
            return []

    @staticmethod
    def load_data_to_table(table_name: str, data_line: str) -> bool:
        """
        Load data into Hive table using beeline and LOAD DATA LOCAL INPATH.
        This works around PyHive connection issues with Hive 4.x.

        Args:
            table_name: Name of the table to load data into
            data_line: Pipe-delimited data line to load

        Returns:
            True if successful, False otherwise
        """
        temp_file = None

        try:
            # Create temporary file with data
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                delete=False
            )
            temp_file.write(data_line)
            temp_file.close()

            # Use beeline to execute LOAD DATA command
            load_query = f"LOAD DATA LOCAL INPATH '{temp_file.name}' INTO TABLE {table_name};"

            # Execute via beeline subprocess (use full path to avoid Anaconda's beeline)
            result = subprocess.run(
                [
                    '/usr/local/bin/beeline',
                    '-u', 'jdbc:hive2://localhost:10000/cis',
                    '-e', load_query,
                    '--silent=true'
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Data loaded successfully into {table_name}")
                return True
            else:
                logger.error(f"Beeline error loading data: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Beeline timeout loading data into {table_name}")
            return False
        except Exception as e:
            logger.error(f"Error loading data into {table_name}: {str(e)}")
            return False

        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass


class AuditLogHiveRepository:
    """
    Repository for audit log operations with Hive.
    Handles reading and writing audit logs from cis.cis_audit_log table.
    """

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
        Log an action to Hive audit log table.

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

            # Helper to format values for pipe-delimited file
            def format_val(v):
                if v is None:
                    return ''
                # Replace pipes with escaped version to avoid delimiter conflict
                return str(v).replace('|', '\\|')

            # Generate unique audit_id (timestamp-based)
            audit_id = int(now.timestamp() * 1000)

            # Build pipe-delimited data line (all 30 columns)
            data_line = '|'.join([
                str(audit_id),
                format_val(audit_timestamp),
                format_val(user_id),
                format_val(username),
                format_val(kwargs.get('user_email')),
                format_val(action_type),
                format_val(kwargs.get('action_category', 'DATA')),
                format_val(action_description),
                format_val(entity_type),
                format_val(entity_id),
                format_val(entity_name),
                format_val(field_name),
                format_val(old_value),
                format_val(new_value),
                format_val(request_method),
                format_val(request_path),
                format_val(kwargs.get('request_params')),
                format_val(status),
                str(kwargs.get('status_code', 200) or ''),
                format_val(error_message),
                format_val(kwargs.get('error_traceback')),
                format_val(kwargs.get('session_id')),
                format_val(ip_address),
                format_val(user_agent),
                format_val(kwargs.get('module_name')),
                format_val(kwargs.get('function_name')),
                str(kwargs.get('duration_ms') or ''),
                format_val(kwargs.get('tags')),
                format_val(kwargs.get('metadata')),
                format_val(audit_date)
            ])

            # Use LOAD DATA to insert into Hive
            return HiveConnection.load_data_to_table('cis_audit_log', data_line)

        except Exception as e:
            logger.error(f"Error creating audit log: {str(e)}")
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
        Retrieve audit logs from Hive with filters.

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

            # Build query - PyHive doesn't support ORDER BY well, so we skip it
            query = f"""
            SELECT *
            FROM cis_audit_log
            WHERE {where_clause}
            LIMIT {limit}
            """

            results = HiveConnection.execute_query(query)

            # Sort in Python since Hive ORDER BY has issues with PyHive
            if results:
                results.sort(key=lambda x: x.get('audit_timestamp', ''), reverse=True)

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
            FROM cis_audit_log
            WHERE entity_type = '{entity_type}'
            AND entity_id = '{entity_id}'
            LIMIT 1000
            """

            results = HiveConnection.execute_query(query)

            # Sort by timestamp
            if results:
                results.sort(key=lambda x: x.get('audit_timestamp', ''), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error retrieving entity history: {str(e)}")
            return []

    @staticmethod
    def get_statistics(days: int = 30) -> Dict[str, Any]:
        """
        Get audit log statistics for the last N days.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with statistics
        """
        try:
            from datetime import timedelta
            date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get total count
            count_query = f"""
            SELECT COUNT(*) as total_count
            FROM cis_audit_log
            WHERE audit_date >= '{date_from}'
            """

            count_result = HiveConnection.execute_query(count_query)
            total_count = count_result[0]['total_count'] if count_result else 0

            # Get action type breakdown
            action_query = f"""
            SELECT action_type, COUNT(*) as count
            FROM cis_audit_log
            WHERE audit_date >= '{date_from}'
            GROUP BY action_type
            """

            action_breakdown = HiveConnection.execute_query(action_query)

            # Get entity type breakdown
            entity_query = f"""
            SELECT entity_type, COUNT(*) as count
            FROM cis_audit_log
            WHERE audit_date >= '{date_from}'
            GROUP BY entity_type
            """

            entity_breakdown = HiveConnection.execute_query(entity_query)

            return {
                'total_count': total_count,
                'days': days,
                'action_breakdown': action_breakdown,
                'entity_breakdown': entity_breakdown
            }

        except Exception as e:
            logger.error(f"Error getting audit statistics: {str(e)}")
            return {'total_count': 0, 'days': days, 'action_breakdown': [], 'entity_breakdown': []}


# Singleton instance
audit_log_repository = AuditLogHiveRepository()
