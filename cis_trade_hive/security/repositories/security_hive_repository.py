"""
Security Hive Repository

Data access layer for security master data in Kudu tables.
All queries execute via Impala (no Django ORM).
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class SecurityHiveRepository:
    """Repository for security operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_security'
    HISTORY_TABLE = 'cis_security_history'

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
        # String - escape backslashes and single quotes
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def get_all_securities(
        limit: int = 1000,
        status: Optional[str] = None,
        search: Optional[str] = None,
        currency: Optional[str] = None,
        security_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all securities from Kudu with optional filters.

        Args:
            limit: Maximum number of records to return
            status: Filter by status (DRAFT, PENDING_APPROVAL, ACTIVE, etc.)
            search: Search term for security_name or ISIN
            currency: Filter by currency_code
            security_type: Filter by security_type

        Returns:
            List of security dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE 1=1
            """

            # Apply filters
            if status:
                query += f" AND status = {SecurityHiveRepository.escape_value(status)}"

            if search:
                search_term = f"%{search}%"
                query += f" AND (LOWER(security_name) LIKE LOWER({SecurityHiveRepository.escape_value(search_term)}) "
                query += f"OR LOWER(isin) LIKE LOWER({SecurityHiveRepository.escape_value(search_term)}))"

            if currency:
                query += f" AND currency_code = {SecurityHiveRepository.escape_value(currency)}"

            if security_type:
                query += f" AND security_type = {SecurityHiveRepository.escape_value(security_type)}"

            # Order by most recent first
            query += " ORDER BY created_at DESC"

            # Apply limit
            query += f" LIMIT {limit}"

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching securities: {str(e)}")
            return []

    @staticmethod
    def get_security_by_id(security_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single security by ID.

        Args:
            security_id: Security ID

        Returns:
            Security dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE security_id = {security_id}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching security {security_id}: {str(e)}")
            return None

    @staticmethod
    def get_security_by_isin(isin: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single security by ISIN.

        Args:
            isin: International Securities Identification Number

        Returns:
            Security dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE isin = {SecurityHiveRepository.escape_value(isin)}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching security by ISIN {isin}: {str(e)}")
            return None

    @staticmethod
    def insert_security(security_data: Dict[str, Any], created_by: str) -> bool:
        """
        Insert a new security record into Kudu.

        Args:
            security_data: Dictionary of security fields
            created_by: Username creating the security

        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate security_id (timestamp-based)
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            security_id = timestamp_ms

            # Build column and value lists
            columns = ['security_id']
            values = [str(security_id)]

            # Add all business fields from security_data
            field_mapping = {
                'security_name': str,
                'isin': str,
                'security_description': str,
                'issuer': str,
                'ticker': str,
                'industry': str,
                'security_type': str,
                'investment_type': str,
                'issuer_type': str,
                'quoted_unquoted': str,
                'country_of_incorporation': str,
                'country_of_exchange': str,
                'country_of_issue': str,
                'country_of_primary_exchange': str,
                'exchange_code': str,
                'currency_code': str,
                'price': float,
                'price_date': str,
                'price_source': str,
                'shares_outstanding': int,
                'beta': float,
                'par_value': float,
                'shareholding_entity_1': float,
                'shareholding_entity_2': float,
                'shareholding_entity_3': float,
                'shareholding_aggregated': float,
                'substantial_10_pct': str,
                'bwciif': int,
                'bwciif_others': int,
                'cels': str,
                'approved_s32': str,
                'basel_iv_fund': str,
                'mas_643_entity_type': str,
                'mas_6d_code': str,
                'fin_nonfin_ind': str,
                'business_unit_head': str,
                'person_in_charge': str,
                'core_noncore': str,
                'fund_index_fund': str,
                'management_limit_classification': str,
                'relative_index': str,
            }

            for field, field_type in field_mapping.items():
                if field in security_data:
                    columns.append(field)
                    values.append(SecurityHiveRepository.escape_value(security_data[field]))

            # Add workflow fields
            columns.extend(['status', 'submitted_for_approval_at', 'submitted_by',
                           'reviewed_at', 'reviewed_by', 'review_comments'])
            values.extend([
                SecurityHiveRepository.escape_value(security_data.get('status', 'DRAFT')),
                'NULL',
                'NULL',
                'NULL',
                'NULL',
                'NULL'
            ])

            # Add audit fields
            columns.extend(['is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'])
            values.extend([
                'true',
                SecurityHiveRepository.escape_value(created_by),
                str(timestamp_ms),
                SecurityHiveRepository.escape_value(created_by),
                str(timestamp_ms)
            ])

            # Build UPSERT statement
            upsert_sql = f"""
            UPSERT INTO {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted security {security_id}")

            return success

        except Exception as e:
            logger.error(f"Error inserting security: {str(e)}")
            return False

    @staticmethod
    def update_security(security_id: int, security_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update an existing security record in Kudu.

        Args:
            security_id: Security ID to update
            security_data: Dictionary of fields to update
            updated_by: Username updating the security

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

            # Build SET clause
            set_clauses = []

            # Update business fields if provided
            updatable_fields = [
                'security_name', 'isin', 'security_description', 'issuer', 'ticker',
                'industry', 'security_type', 'investment_type', 'issuer_type', 'quoted_unquoted',
                'country_of_incorporation', 'country_of_exchange', 'country_of_issue',
                'country_of_primary_exchange', 'exchange_code', 'currency_code',
                'price', 'price_date', 'price_source', 'shares_outstanding', 'beta', 'par_value',
                'shareholding_entity_1', 'shareholding_entity_2', 'shareholding_entity_3',
                'shareholding_aggregated', 'substantial_10_pct', 'bwciif', 'bwciif_others',
                'cels', 'approved_s32', 'basel_iv_fund', 'mas_643_entity_type', 'mas_6d_code',
                'fin_nonfin_ind', 'business_unit_head', 'person_in_charge', 'core_noncore',
                'fund_index_fund', 'management_limit_classification', 'relative_index'
            ]

            for field in updatable_fields:
                if field in security_data:
                    set_clauses.append(f"{field} = {SecurityHiveRepository.escape_value(security_data[field])}")

            # Always update audit fields
            set_clauses.append(f"updated_by = {SecurityHiveRepository.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = {timestamp_ms}")

            if not set_clauses:
                logger.warning(f"No fields to update for security {security_id}")
                return False

            # Build UPDATE statement
            update_sql = f"""
            UPDATE {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE security_id = {security_id}
            """

            success = impala_manager.execute_write(update_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated security {security_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating security {security_id}: {str(e)}")
            return False

    @staticmethod
    def update_security_status(
        security_id: int,
        status: str,
        updated_by: str,
        submitted_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        review_comments: Optional[str] = None
    ) -> bool:
        """
        Update security status and workflow fields.

        Args:
            security_id: Security ID
            status: New status
            updated_by: Username updating
            submitted_by: Username who submitted (for PENDING_APPROVAL)
            reviewed_by: Username who reviewed (for APPROVE/REJECT)
            review_comments: Reviewer comments

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

            set_clauses = [
                f"status = {SecurityHiveRepository.escape_value(status)}",
                f"updated_by = {SecurityHiveRepository.escape_value(updated_by)}",
                f"updated_at = {timestamp_ms}"
            ]

            if status == 'PENDING_APPROVAL' and submitted_by:
                set_clauses.append(f"submitted_for_approval_at = {timestamp_ms}")
                set_clauses.append(f"submitted_by = {SecurityHiveRepository.escape_value(submitted_by)}")

            if status in ['APPROVED', 'ACTIVE', 'REJECTED'] and reviewed_by:
                set_clauses.append(f"reviewed_at = {timestamp_ms}")
                set_clauses.append(f"reviewed_by = {SecurityHiveRepository.escape_value(reviewed_by)}")
                if review_comments:
                    set_clauses.append(f"review_comments = {SecurityHiveRepository.escape_value(review_comments)}")

            if status in ['APPROVED', 'ACTIVE']:
                set_clauses.append("is_active = true")
            elif status in ['REJECTED', 'INACTIVE']:
                set_clauses.append("is_active = false")

            update_sql = f"""
            UPDATE {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE security_id = {security_id}
            """

            success = impala_manager.execute_write(update_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated security {security_id} status to {status}")

            return success

        except Exception as e:
            logger.error(f"Error updating security status {security_id}: {str(e)}")
            return False

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get security statistics for dashboard.

        Returns:
            Dictionary of statistics
        """
        try:
            # Count by status
            status_query = f"""
            SELECT status, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY status
            """
            status_results = impala_manager.execute_query(status_query, database=SecurityHiveRepository.DATABASE)

            status_counts = {}
            total_securities = 0
            active_securities = 0
            pending_approvals = 0

            if status_results:
                for row in status_results:
                    status = row.get('status', 'Unknown')
                    count = row.get('count', 0)
                    status_counts[status] = count
                    total_securities += count

                    if status in ['ACTIVE', 'APPROVED']:
                        active_securities += count
                    elif status == 'PENDING_APPROVAL':
                        pending_approvals = count

            # Count by security type
            type_query = f"""
            SELECT security_type, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE status IN ('ACTIVE', 'APPROVED')
            GROUP BY security_type
            ORDER BY count DESC
            LIMIT 10
            """
            type_results = impala_manager.execute_query(type_query, database=SecurityHiveRepository.DATABASE)

            security_types = []
            if type_results:
                security_types = [{'type': row.get('security_type', 'Unknown'), 'count': row.get('count', 0)}
                                 for row in type_results]

            # Count by currency
            currency_query = f"""
            SELECT currency_code, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE status IN ('ACTIVE', 'APPROVED')
            GROUP BY currency_code
            ORDER BY count DESC
            LIMIT 10
            """
            currency_results = impala_manager.execute_query(currency_query, database=SecurityHiveRepository.DATABASE)

            currencies = []
            if currency_results:
                currencies = [{'currency': row.get('currency_code', 'Unknown'), 'count': row.get('count', 0)}
                             for row in currency_results]

            return {
                'total_securities': total_securities,
                'active_securities': active_securities,
                'pending_approvals': pending_approvals,
                'status_breakdown': status_counts,
                'security_types': security_types,
                'currencies': currencies
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total_securities': 0,
                'active_securities': 0,
                'pending_approvals': 0,
                'status_breakdown': {},
                'security_types': [],
                'currencies': []
            }

    @staticmethod
    def insert_security_history(
        security_id: int,
        security_name: str,
        isin: str,
        action: str,
        status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """
        Insert a security history record.

        Args:
            security_id: Security ID
            security_name: Security name (denormalized)
            isin: ISIN (denormalized)
            action: Action type (CREATE, UPDATE, SUBMIT, APPROVE, REJECT)
            status: Status after action
            changes: Dictionary of changes
            comments: User comments
            performed_by: Username who performed action

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            history_id = timestamp_ms

            # Convert changes dict to JSON string
            changes_json = json.dumps(changes) if changes else '{}'

            insert_sql = f"""
            UPSERT INTO {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.HISTORY_TABLE}
            (history_id, security_id, security_name, isin, action, status, changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {security_id},
                {SecurityHiveRepository.escape_value(security_name)},
                {SecurityHiveRepository.escape_value(isin)},
                {SecurityHiveRepository.escape_value(action)},
                {SecurityHiveRepository.escape_value(status)},
                {SecurityHiveRepository.escape_value(changes_json)},
                {SecurityHiveRepository.escape_value(comments)},
                {SecurityHiveRepository.escape_value(performed_by)},
                {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted history for security {security_id}, action {action}")

            return success

        except Exception as e:
            logger.error(f"Error inserting security history: {str(e)}")
            return False

    @staticmethod
    def get_security_history(security_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history records for a security.

        Args:
            security_id: Security ID
            limit: Maximum number of records

        Returns:
            List of history dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.HISTORY_TABLE}
            WHERE security_id = {security_id}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching security history {security_id}: {str(e)}")
            return []


# Create singleton instance
security_hive_repository = SecurityHiveRepository()
