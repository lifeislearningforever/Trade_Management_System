"""
Security Hive Repository (ORC + ACID)

Data access layer for security master data in Hive managed tables.
Implements CRUD operations with workflow support.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


class SecurityHiveRepository(HiveBaseRepository):
    """Repository for security operations with Hive managed tables (ORC + ACID)"""

    # Workflow Status Constants
    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'

    MAKER_EDITABLE_STATUSES = [STATUS_DRAFT, STATUS_REJECTED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_PENDING_APPROVAL]

    @property
    def table_name(self) -> str:
        return 'cis_security'

    @property
    def primary_key(self) -> str:
        return 'security_id'

    @property
    def columns(self) -> List[str]:
        return [
            'security_id', 'security_code', 'security_name', 'security_type',
            'asset_class', 'currency', 'exchange_code', 'country', 'sector',
            'industry', 'isin', 'cusip', 'sedol', 'ticker', 'issuer',
            'maturity_date', 'coupon_rate', 'face_value', 'status', 'is_active',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_all_securities(
        self,
        limit: int = 1000,
        status: Optional[str] = None,
        search: Optional[str] = None,
        currency: Optional[str] = None,
        security_type: Optional[str] = None,
        asset_class: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch all securities from Hive with optional filters.
        """
        try:
            where_clauses = []

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            if status:
                where_clauses.append(f"status = '{status}'")

            if search:
                search_term = search.replace("'", "''").lower()
                where_clauses.append(
                    f"(LOWER(security_name) LIKE '%{search_term}%' OR "
                    f"LOWER(isin) LIKE '%{search_term}%' OR "
                    f"LOWER(ticker) LIKE '%{search_term}%' OR "
                    f"LOWER(security_code) LIKE '%{search_term}%')"
                )

            if currency:
                where_clauses.append(f"currency = '{currency}'")

            if security_type:
                where_clauses.append(f"security_type = '{security_type}'")

            if asset_class:
                where_clauses.append(f"asset_class = '{asset_class}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching securities: {str(e)}")
            return []

    def get_security_by_id(self, security_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single security by ID."""
        return self.find_by_id(security_id)

    def get_security_by_isin(self, isin: str) -> Optional[Dict[str, Any]]:
        """Fetch a single security by ISIN."""
        try:
            isin_escaped = isin.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE isin = '{isin_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching security by ISIN {isin}: {str(e)}")
            return None

    def get_security_by_code(self, security_code: str) -> Optional[Dict[str, Any]]:
        """Fetch a single security by security code."""
        try:
            code_escaped = security_code.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE security_code = '{code_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching security by code {security_code}: {str(e)}")
            return None

    def get_securities_by_status(self, statuses: List[str], limit: int = 1000) -> List[Dict[str, Any]]:
        """Get securities filtered by multiple statuses."""
        try:
            status_list = ", ".join([f"'{s}'" for s in statuses])
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE status IN ({status_list})
                  AND deleted_at IS NULL
                LIMIT {limit}
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []
        except Exception as e:
            logger.error(f"Error retrieving securities by status: {str(e)}")
            return []

    def get_pending_approval_securities(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get securities pending approval."""
        return self.get_securities_by_status([self.STATUS_PENDING_APPROVAL], limit)

    def get_active_securities(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get active securities."""
        return self.get_securities_by_status([self.STATUS_ACTIVE], limit)

    def get_statistics(self) -> Dict[str, Any]:
        """Get security statistics for dashboard."""
        try:
            query = f"""
                SELECT status, security_type, currency, asset_class
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            status_counts = {}
            type_counts = {}
            currency_counts = {}
            asset_class_counts = {}

            if results:
                for row in results:
                    # Status breakdown
                    status = row.get('status', 'Unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1

                    # Security type breakdown
                    sec_type = row.get('security_type', 'Unknown')
                    type_counts[sec_type] = type_counts.get(sec_type, 0) + 1

                    # Currency breakdown
                    curr = row.get('currency', 'Unknown')
                    currency_counts[curr] = currency_counts.get(curr, 0) + 1

                    # Asset class breakdown
                    asset = row.get('asset_class', 'Unknown')
                    asset_class_counts[asset] = asset_class_counts.get(asset, 0) + 1

            return {
                'total_securities': total,
                'active_securities': status_counts.get(self.STATUS_ACTIVE, 0),
                'pending_approval': status_counts.get(self.STATUS_PENDING_APPROVAL, 0),
                'draft': status_counts.get(self.STATUS_DRAFT, 0),
                'status_breakdown': status_counts,
                'by_security_type': [
                    {'security_type': k, 'count': v}
                    for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ],
                'by_currency': [
                    {'currency': k, 'count': v}
                    for k, v in sorted(currency_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ],
                'by_asset_class': [
                    {'asset_class': k, 'count': v}
                    for k, v in sorted(asset_class_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ],
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total_securities': 0,
                'active_securities': 0,
                'pending_approval': 0,
                'draft': 0,
                'status_breakdown': {},
                'by_security_type': [],
                'by_currency': [],
                'by_asset_class': [],
            }

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def create_security(self, security_data: Dict[str, Any], created_by: str) -> Optional[str]:
        """
        Create a new security with DRAFT status.
        """
        try:
            security_id = self._generate_id('SEC')
            now = datetime.now()

            data = {
                'security_id': security_id,
                'security_code': security_data.get('security_code'),
                'security_name': security_data.get('security_name'),
                'security_type': security_data.get('security_type'),
                'asset_class': security_data.get('asset_class'),
                'currency': security_data.get('currency'),
                'exchange_code': security_data.get('exchange_code'),
                'country': security_data.get('country'),
                'sector': security_data.get('sector'),
                'industry': security_data.get('industry'),
                'isin': security_data.get('isin'),
                'cusip': security_data.get('cusip'),
                'sedol': security_data.get('sedol'),
                'ticker': security_data.get('ticker'),
                'issuer': security_data.get('issuer'),
                'maturity_date': security_data.get('maturity_date'),
                'coupon_rate': security_data.get('coupon_rate'),
                'face_value': security_data.get('face_value'),
                'status': self.STATUS_DRAFT,
                'is_active': False,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(data):
                logger.info(f"Created security {security_id} with DRAFT status")
                self.create_history_record_async(
                    security_id, 'CREATE', None, data, created_by
                )
                return security_id
            return None

        except Exception as e:
            logger.error(f"Error creating security: {str(e)}")
            return None

    def update_security(self, security_id: str, security_data: Dict[str, Any],
                       updated_by: str) -> bool:
        """Update security data."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                logger.error(f"Security {security_id} not found")
                return False

            update_data = {}
            updatable_fields = [
                'security_code', 'security_name', 'security_type', 'asset_class',
                'currency', 'exchange_code', 'country', 'sector', 'industry',
                'isin', 'cusip', 'sedol', 'ticker', 'issuer',
                'maturity_date', 'coupon_rate', 'face_value'
            ]

            for field in updatable_fields:
                if field in security_data:
                    update_data[field] = security_data[field]

            update_data['updated_by'] = updated_by

            # Reset to DRAFT if editable
            if old_data.get('status') in self.MAKER_EDITABLE_STATUSES:
                update_data['status'] = self.STATUS_DRAFT

            success = self.update(security_id, update_data)

            if success:
                logger.info(f"Updated security {security_id}")
                self.create_history_record_async(
                    security_id, 'UPDATE', old_data, update_data, updated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error updating security: {str(e)}")
            return False

    def delete_security(self, security_id: str, deleted_by: str) -> bool:
        """Soft delete a security."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                return False

            success = self.soft_delete(security_id, deleted_by)

            if success:
                logger.info(f"Security {security_id} deleted by {deleted_by}")
                self.create_history_record_async(
                    security_id, 'DELETE', old_data, None, deleted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error deleting security: {str(e)}")
            return False

    # =========================================================================
    # WORKFLOW OPERATIONS
    # =========================================================================

    def submit_for_approval(self, security_id: str, submitted_by: str) -> bool:
        """Submit security for approval."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                return False

            success = self.update(security_id, {
                'status': self.STATUS_PENDING_APPROVAL,
                'updated_by': submitted_by
            })

            if success:
                logger.info(f"Security {security_id} submitted for approval")
                self.create_history_record_async(
                    security_id, 'SUBMIT_FOR_APPROVAL',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_PENDING_APPROVAL},
                    submitted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error submitting security: {str(e)}")
            return False

    def approve_security(self, security_id: str, approved_by: str,
                        comments: str = '') -> bool:
        """Approve security."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                return False

            success = self.update(security_id, {
                'status': self.STATUS_APPROVED,
                'updated_by': approved_by
            })

            if success:
                logger.info(f"Security {security_id} approved by {approved_by}")
                self.create_history_record_async(
                    security_id, 'APPROVE',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_APPROVED, 'comments': comments},
                    approved_by
                )

            return success

        except Exception as e:
            logger.error(f"Error approving security: {str(e)}")
            return False

    def reject_security(self, security_id: str, rejected_by: str,
                       reason: str = '') -> bool:
        """Reject security."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                return False

            success = self.update(security_id, {
                'status': self.STATUS_REJECTED,
                'updated_by': rejected_by
            })

            if success:
                logger.info(f"Security {security_id} rejected by {rejected_by}")
                self.create_history_record_async(
                    security_id, 'REJECT',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_REJECTED, 'reason': reason},
                    rejected_by
                )

            return success

        except Exception as e:
            logger.error(f"Error rejecting security: {str(e)}")
            return False

    def activate_security(self, security_id: str, activated_by: str) -> bool:
        """Activate security."""
        try:
            old_data = self.find_by_id(security_id)
            if not old_data:
                return False

            success = self.update(security_id, {
                'status': self.STATUS_ACTIVE,
                'is_active': True,
                'updated_by': activated_by
            })

            if success:
                logger.info(f"Security {security_id} activated by {activated_by}")
                self.create_history_record_async(
                    security_id, 'ACTIVATE',
                    {'status': old_data.get('status'), 'is_active': old_data.get('is_active')},
                    {'status': self.STATUS_ACTIVE, 'is_active': True},
                    activated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error activating security: {str(e)}")
            return False

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    def search_securities(self, search_term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search securities by name, ISIN, ticker, or code."""
        return self.search(
            search_term,
            ['security_name', 'isin', 'ticker', 'security_code', 'issuer']
        )[:limit]


# Singleton instance
security_hive_repository = SecurityHiveRepository()
