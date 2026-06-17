"""
Corporate Action Repository

Data access layer for corporate actions in Kudu tables.
All queries execute via Impala (no Django ORM).
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import random

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class CorporateActionRepository:
    """Repository for corporate action operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_corporate_actions'
    HISTORY_TABLE = 'cis_corporate_actions_history'

    @staticmethod
    def escape_value(value: Any) -> str:
        """
        Escape value for SQL query.
        Uses backslash escaping for Impala compatibility.
        """
        if value is None or value == '':
            return 'NULL'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            return str(value)
        # Decimal — emit as unquoted numeric literal for Kudu DECIMAL columns
        try:
            from decimal import Decimal
            if isinstance(value, Decimal):
                return str(value)
        except ImportError:
            pass
        # String — if it looks purely numeric, emit unquoted (handles str(Decimal))
        s = str(value).strip()
        if s and s.lstrip('-').replace('.', '', 1).isdigit():
            return s
        # General string — escape backslashes and single quotes
        escaped = s.replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def get_all(
        limit: int = 1000,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
        ca_type: Optional[str] = None,
        security_name: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch all corporate actions from Kudu with optional filters.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            status: Filter by status (INITIAL, MODIFIED, VALIDATED)
            search: Search term for ca_number or security_name
            ca_type: Filter by corporate action type
            security_name: Filter by security name
            include_deleted: Include soft-deleted records

        Returns:
            List of corporate action dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE 1=1
            """

            # Exclude deleted unless requested
            if not include_deleted:
                query += " AND (is_deleted = false OR is_deleted IS NULL)"

            # Apply filters
            if status:
                query += f" AND status = {CorporateActionRepository.escape_value(status)}"

            if search:
                search_term = f"%{search}%"
                query += f" AND (LOWER(ca_number) LIKE LOWER({CorporateActionRepository.escape_value(search_term)}) "
                query += f"OR LOWER(security_name) LIKE LOWER({CorporateActionRepository.escape_value(search_term)}))"

            if ca_type:
                query += f" AND ca_type = {CorporateActionRepository.escape_value(ca_type)}"

            if security_name:
                query += f" AND security_name = {CorporateActionRepository.escape_value(security_name)}"

            # Order by most recent first
            query += " ORDER BY created_at DESC"

            # Apply limit and offset
            if offset > 0:
                query += f" OFFSET {offset}"
            query += f" LIMIT {limit}"

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching corporate actions: {str(e)}")
            return []

    @staticmethod
    def get_by_id(ca_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single corporate action by ID.

        Args:
            ca_id: Corporate Action ID

        Returns:
            Corporate action dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE ca_id = {ca_id}
            """

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching corporate action {ca_id}: {str(e)}")
            return None

    @staticmethod
    def get_by_ca_number(ca_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single corporate action by CA Number.

        Args:
            ca_number: Corporate Action Number

        Returns:
            Corporate action dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE ca_number = {CorporateActionRepository.escape_value(ca_number)}
            """

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching corporate action by number {ca_number}: {str(e)}")
            return None

    @staticmethod
    def get_pending_approvals(limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch corporate actions pending approval (INITIAL or MODIFIED status).

        Args:
            limit: Maximum number of records

        Returns:
            List of corporate action dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE status IN ('INITIAL', 'MODIFIED')
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching pending approvals: {str(e)}")
            return []

    @staticmethod
    def insert(ca_data: Dict[str, Any], created_by: str) -> tuple[bool, Optional[int]]:
        """
        Insert a new corporate action record into Kudu.

        Args:
            ca_data: Dictionary of corporate action fields
            created_by: Username creating the record

        Returns:
            Tuple of (success, ca_id)
        """
        try:
            # Generate ca_id (BIGINT ms PK — intentional)
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            ca_id = timestamp_ms
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build column and value lists
            columns = ['ca_id']
            values = [str(ca_id)]

            # Add all business fields from ca_data
            # Note: portfolio_name removed - CA applies at security level
            field_mapping = {
                'ca_number': str,
                'ca_type': str,
                'security_name': str,
                'announcement_date': str,
                'ex_date': str,
                'record_date': str,
                'payment_date': str,
                'effective_date': str,
                'subscription_start_date': str,
                'subscription_end_date': str,
                'price': float,
                'currency': str,
                'src_system': str,
            }

            for field, field_type in field_mapping.items():
                if field in ca_data and ca_data[field] is not None and ca_data[field] != '':
                    columns.append(field)
                    raw = ca_data[field]
                    # Numeric fields: cast to float rounded to 6dp to match DECIMAL(20,6)
                    if field_type == float:
                        try:
                            raw = round(float(str(raw)), 6)
                        except (ValueError, TypeError):
                            raw = None
                    if raw is None:
                        values.append('NULL')
                    else:
                        values.append(CorporateActionRepository.escape_value(raw))

            # Add status
            columns.append('status')
            values.append(CorporateActionRepository.escape_value(ca_data.get('status', 'INITIAL')))

            # Add src_system - 'CIS' for records created via UI
            if 'src_system' not in ca_data:
                columns.append('src_system')
                values.append("'CIS'")

            # Add audit fields
            columns.extend(['is_active', 'is_deleted', 'created_by', 'created_at', 'updated_by', 'updated_at'])
            values.extend([
                'true',
                'false',
                CorporateActionRepository.escape_value(created_by),
                CorporateActionRepository.escape_value(timestamp_str),
                CorporateActionRepository.escape_value(created_by),
                CorporateActionRepository.escape_value(timestamp_str)
            ])

            # Build UPSERT statement
            upsert_sql = f"""
            UPSERT INTO {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted corporate action {ca_id}")
                return True, ca_id

            return False, None

        except Exception as e:
            logger.error(f"Error inserting corporate action: {str(e)}")
            return False, None

    @staticmethod
    def update(ca_id: int, ca_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update an existing corporate action record in Kudu.

        Args:
            ca_id: Corporate Action ID to update
            ca_data: Dictionary of fields to update
            updated_by: Username updating the record

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build SET clause
            set_clauses = []

            # Update business fields if provided
            # Note: portfolio_name removed - CA applies at security level
            updatable_fields = [
                'ca_number', 'ca_type', 'security_name',
                'announcement_date', 'ex_date', 'record_date', 'payment_date',
                'effective_date', 'subscription_start_date', 'subscription_end_date',
                'price', 'currency', 'status',
            ]

            for field in updatable_fields:
                if field in ca_data:
                    set_clauses.append(f"{field} = {CorporateActionRepository.escape_value(ca_data[field])}")

            # Always update audit fields
            set_clauses.append(f"updated_by = {CorporateActionRepository.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = {CorporateActionRepository.escape_value(timestamp_str)}")

            if not set_clauses:
                logger.warning(f"No fields to update for corporate action {ca_id}")
                return False

            # Build UPDATE statement
            update_sql = f"""
            UPDATE {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE ca_id = {ca_id}
            """

            success = impala_manager.execute_write(update_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated corporate action {ca_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating corporate action {ca_id}: {str(e)}")
            return False

    @staticmethod
    def update_status(
        ca_id: int,
        status: str,
        updated_by: str,
        reviewed_comments: str = None
    ) -> bool:
        """
        Update corporate action status (for maker-checker workflow).

        Args:
            ca_id: Corporate Action ID
            status: New status
            updated_by: Username updating
            reviewed_comments: Reviewer comments

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [
                f"status = {CorporateActionRepository.escape_value(status)}",
                f"updated_by = {CorporateActionRepository.escape_value(updated_by)}",
                f"updated_at = {CorporateActionRepository.escape_value(timestamp_str)}",
                f"reviewed_by = {CorporateActionRepository.escape_value(updated_by)}",
                f"reviewed_at = {CorporateActionRepository.escape_value(timestamp_str)}",
            ]

            if reviewed_comments:
                set_clauses.append(f"reviewed_comments = {CorporateActionRepository.escape_value(reviewed_comments)}")

            if status == 'VALIDATED':
                set_clauses.append("is_active = true")

            update_sql = f"""
            UPDATE {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE ca_id = {ca_id}
            """

            success = impala_manager.execute_write(update_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated corporate action {ca_id} status to {status}")

            return success

        except Exception as e:
            logger.error(f"Error updating corporate action status {ca_id}: {str(e)}")
            return False

    @staticmethod
    def soft_delete(ca_id: int, deleted_by: str) -> bool:
        """
        Soft delete a corporate action.

        Args:
            ca_id: Corporate Action ID
            deleted_by: Username deleting

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            update_sql = f"""
            UPDATE {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            SET is_deleted = true,
                is_active = false,
                updated_by = {CorporateActionRepository.escape_value(deleted_by)},
                updated_at = {CorporateActionRepository.escape_value(timestamp_str)}
            WHERE ca_id = {ca_id}
            """

            success = impala_manager.execute_write(update_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully soft deleted corporate action {ca_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting corporate action {ca_id}: {str(e)}")
            return False

    @staticmethod
    def restore(ca_id: int, restored_by: str) -> bool:
        """
        Restore a soft-deleted corporate action.

        Args:
            ca_id: Corporate Action ID
            restored_by: Username restoring

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            update_sql = f"""
            UPDATE {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            SET is_deleted = false,
                is_active = true,
                status = 'MODIFIED',
                updated_by = {CorporateActionRepository.escape_value(restored_by)},
                updated_at = {CorporateActionRepository.escape_value(timestamp_str)}
            WHERE ca_id = {ca_id}
            """

            success = impala_manager.execute_write(update_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully restored corporate action {ca_id}")

            return success

        except Exception as e:
            logger.error(f"Error restoring corporate action {ca_id}: {str(e)}")
            return False

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get corporate action statistics for dashboard.

        Returns:
            Dictionary of statistics
        """
        try:
            # Count by status
            status_query = f"""
            SELECT status, COUNT(*) as count
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE (is_deleted = false OR is_deleted IS NULL)
            GROUP BY status
            """
            status_results = impala_manager.execute_query(status_query, database=CorporateActionRepository.DATABASE)

            status_counts = {}
            total = 0
            validated = 0
            pending = 0

            if status_results:
                for row in status_results:
                    status = row.get('status', 'Unknown')
                    count = row.get('count', 0)
                    status_counts[status] = count
                    total += count

                    if status == 'VALIDATED':
                        validated += count
                    elif status in ['INITIAL', 'MODIFIED']:
                        pending += count

            # Count by CA type
            type_query = f"""
            SELECT ca_type, COUNT(*) as count
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE (is_deleted = false OR is_deleted IS NULL)
            GROUP BY ca_type
            ORDER BY count DESC
            LIMIT 10
            """
            type_results = impala_manager.execute_query(type_query, database=CorporateActionRepository.DATABASE)

            ca_types = []
            if type_results:
                ca_types = [{'ca_type': row.get('ca_type', 'Unknown'), 'count': row.get('count', 0)}
                           for row in type_results]

            return {
                'total': total,
                'validated': validated,
                'pending_approval': pending,
                'status_breakdown': status_counts,
                'by_type': ca_types,
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total': 0,
                'validated': 0,
                'pending_approval': 0,
                'status_breakdown': {},
                'by_type': [],
            }

    @staticmethod
    def insert_history(
        ca_id: int,
        ca_number: str,
        security_name: str,
        action: str,
        status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """
        Insert a corporate action history record.

        Args:
            ca_id: Corporate Action ID
            ca_number: CA Number (denormalized)
            security_name: Security name (denormalized)
            action: Action type (CREATE, UPDATE, VALIDATE, REJECT, DELETE)
            status: Status after action
            changes: Dictionary of changes
            comments: User comments
            performed_by: Username who performed action

        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.now()
            timestamp_ms = int(now.timestamp() * 1000)
            # Embed ca_id in upper bits and add random salt to avoid collisions when
            # multiple history rows are written within the same millisecond for the same CA.
            history_id = (ca_id % 10**6) * 10**10 + timestamp_ms * 10**3 + random.randint(0, 999)

            # Convert changes dict to JSON string
            changes_json = json.dumps(changes) if changes else '{}'

            insert_sql = f"""
            UPSERT INTO {CorporateActionRepository.DATABASE}.{CorporateActionRepository.HISTORY_TABLE}
            (history_id, ca_id, ca_number, security_name, action, status, changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {ca_id},
                {CorporateActionRepository.escape_value(ca_number)},
                {CorporateActionRepository.escape_value(security_name)},
                {CorporateActionRepository.escape_value(action)},
                {CorporateActionRepository.escape_value(status)},
                {CorporateActionRepository.escape_value(changes_json)},
                {CorporateActionRepository.escape_value(comments)},
                {CorporateActionRepository.escape_value(performed_by)},
                {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=CorporateActionRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted history for corporate action {ca_id}, action {action}")

            return success

        except Exception as e:
            logger.error(f"Error inserting corporate action history: {str(e)}")
            return False

    @staticmethod
    def get_history(ca_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history records for a corporate action.

        Args:
            ca_id: Corporate Action ID
            limit: Maximum number of records

        Returns:
            List of history dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.HISTORY_TABLE}
            WHERE ca_id = {ca_id}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching corporate action history {ca_id}: {str(e)}")
            return []

    @staticmethod
    def generate_ca_number() -> str:
        """
        Generate a unique Corporate Action number.

        Returns:
            Generated CA number (format: CA-YYYYMMDD-XXXXX)
        """
        try:
            today = datetime.now().strftime('%Y%m%d')
            prefix = f"CA-{today}-"

            # Get the latest CA number for today
            query = f"""
            SELECT ca_number
            FROM {CorporateActionRepository.DATABASE}.{CorporateActionRepository.TABLE_NAME}
            WHERE ca_number LIKE '{prefix}%'
            ORDER BY ca_number DESC
            LIMIT 1
            """

            result = impala_manager.execute_query(query, database=CorporateActionRepository.DATABASE)

            if result and len(result) > 0:
                last_number = result[0].get('ca_number', '')
                if last_number:
                    # Extract the sequence number and increment
                    try:
                        seq = int(last_number.split('-')[-1])
                        new_seq = seq + 1
                    except (ValueError, IndexError):
                        new_seq = 1
                else:
                    new_seq = 1
            else:
                new_seq = 1

            return f"{prefix}{new_seq:05d}"

        except Exception as e:
            logger.error(f"Error generating CA number: {str(e)}")
            # Fallback to timestamp-based number
            timestamp = int(datetime.now().timestamp() * 1000)
            return f"CA-{timestamp}"


# Create singleton instance
corporate_action_repository = CorporateActionRepository()
