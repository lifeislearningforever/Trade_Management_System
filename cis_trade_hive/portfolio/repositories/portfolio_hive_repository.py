"""
Portfolio Repository (Hive ORC + ACID)

Fetches portfolio data from Hive cis_portfolio table.
Implements Maker-Checker workflow with statuses:
  - DRAFT: New portfolio created (Maker)
  - PENDING_APPROVAL: Submitted for validation (awaiting Checker)
  - APPROVED: Approved by Checker
  - REJECTED: Rejected by Checker
  - ACTIVE: Final active state
  - INACTIVE: Deactivated portfolio
  - CLOSED: Closed portfolio
"""

from typing import List, Dict, Any, Optional
import logging
import uuid
import json
from datetime import datetime
from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


class PortfolioHiveRepository(HiveBaseRepository):
    """Repository for portfolio operations with Hive managed tables (ORC + ACID)."""

    # Workflow Status Constants (Maker-Checker)
    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'
    STATUS_CLOSED = 'CLOSED'

    # Backward compatibility aliases (old status names -> new workflow)
    STATUS_INITIAL = 'DRAFT'
    STATUS_MODIFIED = 'DRAFT'  # Re-edited drafts
    STATUS_PENDING_VALIDATION = 'PENDING_APPROVAL'
    STATUS_VALIDATED = 'APPROVED'
    STATUS_SETTLED = 'ACTIVE'
    STATUS_CANCELLED = 'INACTIVE'

    # Status groups for filtering
    MAKER_EDITABLE_STATUSES = [STATUS_DRAFT, STATUS_REJECTED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_PENDING_APPROVAL]

    @property
    def table_name(self) -> str:
        return 'cis_portfolio'

    @property
    def primary_key(self) -> str:
        return 'portfolio_id'

    @property
    def columns(self) -> List[str]:
        return [
            'portfolio_id', 'portfolio_short_name', 'portfolio_name', 'portfolio_type',
            'currency', 'base_currency', 'manager_name', 'custodian', 'inception_date',
            'description', 'status', 'is_active', 'created_at', 'created_by',
            'updated_at', 'updated_by', 'deleted_at'
        ]

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_all_portfolios(
        self,
        limit: int = 1000,
        status: Optional[str] = None,
        currency: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve portfolios from Hive with filters.
        """
        try:
            where_clauses = []

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            if status:
                status_escaped = status.replace("'", "''")
                where_clauses.append(f"status = '{status_escaped}'")

            if currency:
                currency_escaped = currency.replace("'", "''")
                where_clauses.append(f"currency = '{currency_escaped}'")

            if search:
                search_term = search.replace("'", "''").lower()
                where_clauses.append(
                    f"(LOWER(portfolio_name) LIKE '%{search_term}%' OR "
                    f"LOWER(portfolio_short_name) LIKE '%{search_term}%' OR "
                    f"LOWER(description) LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
                SELECT portfolio_id, portfolio_short_name, portfolio_name, portfolio_type,
                       currency, base_currency, manager_name, custodian, inception_date,
                       description, status, is_active, created_at, created_by,
                       updated_at, updated_by
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving portfolios: {str(e)}")
            return []

    def get_portfolios_by_status(self, statuses: List[str], limit: int = 1000) -> List[Dict[str, Any]]:
        """Get portfolios filtered by multiple statuses."""
        try:
            status_list = ", ".join([f"'{s}'" for s in statuses])
            query = f"""
                SELECT portfolio_id, portfolio_short_name, portfolio_name, portfolio_type,
                       currency, base_currency, manager_name, custodian, inception_date,
                       description, status, is_active, created_at, updated_at
                FROM {self._get_full_table_name()}
                WHERE status IN ({status_list})
                  AND deleted_at IS NULL
                LIMIT {limit}
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []
        except Exception as e:
            logger.error(f"Error retrieving portfolios by status: {str(e)}")
            return []

    def get_pending_approval_portfolios(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get portfolios pending approval (for Checker)."""
        return self.get_portfolios_by_status([self.STATUS_PENDING_APPROVAL], limit)

    # Backward compatibility alias
    def get_pending_validation_portfolios(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Alias for get_pending_approval_portfolios (backward compatibility)."""
        return self.get_pending_approval_portfolios(limit)

    def get_active_portfolios(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get active portfolios."""
        return self.get_portfolios_by_status([self.STATUS_ACTIVE], limit)

    def get_portfolio_by_id(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Get portfolio by ID."""
        return self.find_by_id(portfolio_id)

    def get_portfolio_by_short_name(self, short_name: str) -> Optional[Dict[str, Any]]:
        """Get portfolio by short name."""
        try:
            short_name_escaped = short_name.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE portfolio_short_name = '{short_name_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting portfolio by short name: {str(e)}")
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """Alias for get_portfolio_statistics for consistency."""
        return self.get_portfolio_statistics()

    def get_portfolio_statistics(self) -> Dict[str, Any]:
        """Get portfolio statistics."""
        try:
            query = f"""
                SELECT status, currency
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            all_result = self.conn_manager.execute_query(query, database=self.database)

            total_portfolios = len(all_result) if all_result else 0

            # Count by status
            status_counts = {}
            currency_counts = {}
            for row in all_result:
                status = row.get('status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

                if row.get('status') == self.STATUS_ACTIVE:
                    curr = row.get('currency', 'Unknown')
                    currency_counts[curr] = currency_counts.get(curr, 0) + 1

            return {
                'total_portfolios': total_portfolios,
                'active_portfolios': status_counts.get(self.STATUS_ACTIVE, 0),
                'pending_approval': status_counts.get(self.STATUS_PENDING_APPROVAL, 0),
                'draft': status_counts.get(self.STATUS_DRAFT, 0),
                'status_breakdown': status_counts,
                'currency_breakdown': [
                    {'currency': k, 'count': v}
                    for k, v in sorted(currency_counts.items())
                ]
            }

        except Exception as e:
            logger.error(f"Error getting portfolio statistics: {str(e)}")
            return {
                'total_portfolios': 0,
                'active_portfolios': 0,
                'pending_approval': 0,
                'draft': 0,
                'status_breakdown': {},
                'currency_breakdown': []
            }

    def get_currencies(self) -> List[str]:
        """Get list of unique currencies from portfolios."""
        try:
            query = f"""
                SELECT DISTINCT currency
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
                  AND currency IS NOT NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            currencies = [row['currency'] for row in results if row.get('currency')]
            return sorted(currencies)
        except Exception as e:
            logger.error(f"Error getting currencies: {str(e)}")
            return []

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def create_portfolio(self, portfolio_data: Dict[str, Any], created_by: str) -> Optional[str]:
        """
        Create a new portfolio with DRAFT status.
        Maker action: Create -> DRAFT

        Returns:
            Portfolio ID if successful, None otherwise
        """
        try:
            portfolio_id = self._generate_id('PF')
            now = datetime.now()

            data = {
                'portfolio_id': portfolio_id,
                'portfolio_short_name': portfolio_data.get('portfolio_short_name'),
                'portfolio_name': portfolio_data.get('portfolio_name'),
                'portfolio_type': portfolio_data.get('portfolio_type'),
                'currency': portfolio_data.get('currency'),
                'base_currency': portfolio_data.get('base_currency', portfolio_data.get('currency')),
                'manager_name': portfolio_data.get('manager_name'),
                'custodian': portfolio_data.get('custodian'),
                'inception_date': portfolio_data.get('inception_date'),
                'description': portfolio_data.get('description'),
                'status': self.STATUS_DRAFT,
                'is_active': False,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(data):
                logger.info(f"Created portfolio {portfolio_id} with DRAFT status")

                # Create history record
                self.create_history_record_async(
                    portfolio_id, 'CREATE', None, data, created_by
                )

                return portfolio_id
            return None

        except Exception as e:
            logger.error(f"Error creating portfolio: {str(e)}")
            return None

    def update_portfolio(self, portfolio_id: str, portfolio_data: Dict[str, Any],
                        updated_by: str) -> bool:
        """
        Update portfolio data.
        Sets status to DRAFT if currently in DRAFT or REJECTED.
        """
        try:
            # Get current data for history
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                logger.error(f"Portfolio {portfolio_id} not found")
                return False

            # Prepare update data
            update_data = {}
            updatable_fields = [
                'portfolio_short_name', 'portfolio_name', 'portfolio_type',
                'currency', 'base_currency', 'manager_name', 'custodian',
                'inception_date', 'description'
            ]

            for field in updatable_fields:
                if field in portfolio_data:
                    update_data[field] = portfolio_data[field]

            update_data['updated_by'] = updated_by

            # Reset to DRAFT if currently editable
            if old_data.get('status') in self.MAKER_EDITABLE_STATUSES:
                update_data['status'] = self.STATUS_DRAFT

            success = self.update(portfolio_id, update_data)

            if success:
                logger.info(f"Updated portfolio {portfolio_id}")

                # Create history record asynchronously
                self.create_history_record_async(
                    portfolio_id, 'UPDATE', old_data, update_data, updated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error updating portfolio: {str(e)}")
            return False

    def submit_for_approval(self, portfolio_id: str, submitted_by: str) -> bool:
        """
        Submit portfolio for approval.
        Maker action: Submit -> PENDING_APPROVAL
        """
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_PENDING_APPROVAL,
                'updated_by': submitted_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} submitted for approval by {submitted_by}")

                self.create_history_record_async(
                    portfolio_id, 'SUBMIT_FOR_APPROVAL',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_PENDING_APPROVAL},
                    submitted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error submitting portfolio for approval: {str(e)}")
            return False

    def approve_portfolio(self, portfolio_id: str, approved_by: str,
                         comments: str = '') -> bool:
        """
        Approve portfolio.
        Checker action: Approve -> APPROVED
        """
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_APPROVED,
                'updated_by': approved_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} approved by {approved_by}")

                self.create_history_record_async(
                    portfolio_id, 'APPROVE',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_APPROVED, 'comments': comments},
                    approved_by
                )

            return success

        except Exception as e:
            logger.error(f"Error approving portfolio: {str(e)}")
            return False

    def reject_portfolio(self, portfolio_id: str, rejected_by: str,
                        reason: str = '') -> bool:
        """
        Reject portfolio.
        Checker action: Reject -> REJECTED
        """
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_REJECTED,
                'updated_by': rejected_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} rejected by {rejected_by}")

                self.create_history_record_async(
                    portfolio_id, 'REJECT',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_REJECTED, 'reason': reason},
                    rejected_by
                )

            return success

        except Exception as e:
            logger.error(f"Error rejecting portfolio: {str(e)}")
            return False

    def activate_portfolio(self, portfolio_id: str, activated_by: str) -> bool:
        """
        Activate portfolio (final active state).
        Checker action: Activate -> ACTIVE
        """
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_ACTIVE,
                'is_active': True,
                'updated_by': activated_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} activated by {activated_by}")

                self.create_history_record_async(
                    portfolio_id, 'ACTIVATE',
                    {'status': old_data.get('status'), 'is_active': old_data.get('is_active')},
                    {'status': self.STATUS_ACTIVE, 'is_active': True},
                    activated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error activating portfolio: {str(e)}")
            return False

    def deactivate_portfolio(self, portfolio_id: str, deactivated_by: str,
                            reason: str = '') -> bool:
        """
        Deactivate portfolio.
        """
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_INACTIVE,
                'is_active': False,
                'updated_by': deactivated_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} deactivated by {deactivated_by}")

                self.create_history_record_async(
                    portfolio_id, 'DEACTIVATE',
                    {'status': old_data.get('status'), 'is_active': old_data.get('is_active')},
                    {'status': self.STATUS_INACTIVE, 'is_active': False, 'reason': reason},
                    deactivated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error deactivating portfolio: {str(e)}")
            return False

    def delete_portfolio(self, portfolio_id: str, deleted_by: str) -> bool:
        """Soft delete a portfolio."""
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.soft_delete(portfolio_id, deleted_by)

            if success:
                logger.info(f"Portfolio {portfolio_id} deleted by {deleted_by}")

                self.create_history_record_async(
                    portfolio_id, 'DELETE', old_data, None, deleted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error deleting portfolio: {str(e)}")
            return False

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    def search_portfolios(self, search_term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search portfolios by name, short name, or description."""
        return self.search(
            search_term,
            ['portfolio_name', 'portfolio_short_name', 'description', 'manager_name']
        )[:limit]

    # =========================================================================
    # BACKWARD COMPATIBILITY ALIASES
    # =========================================================================

    def get_portfolio_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Alias for get_portfolio_by_short_name (backward compatibility)."""
        return self.get_portfolio_by_short_name(code)

    def get_validated_portfolios(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get approved portfolios (alias for backward compatibility)."""
        return self.get_portfolios_by_status([self.STATUS_APPROVED], limit)

    def insert_portfolio(self, portfolio_data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Alias for create_portfolio (backward compatibility)."""
        return self.create_portfolio(portfolio_data, created_by)

    def submit_for_validation(self, portfolio_id: str, submitted_by: str) -> bool:
        """Alias for submit_for_approval (backward compatibility)."""
        return self.submit_for_approval(portfolio_id, submitted_by)

    def validate_portfolio(self, portfolio_id: str, validated_by: str,
                          comments: str = '') -> bool:
        """Alias for approve_portfolio (backward compatibility)."""
        return self.approve_portfolio(portfolio_id, validated_by, comments)

    def cancel_portfolio(self, portfolio_id: str, cancelled_by: str,
                        reason: str = '') -> bool:
        """Cancel/deactivate portfolio (backward compatibility)."""
        return self.deactivate_portfolio(portfolio_id, cancelled_by, reason)

    def settle_portfolio(self, portfolio_id: str, settled_by: str) -> bool:
        """Settle/activate portfolio (backward compatibility)."""
        return self.activate_portfolio(portfolio_id, settled_by)

    def reactivate_portfolio(self, portfolio_id: str, reactivated_by: str) -> bool:
        """Reactivate cancelled portfolio (backward compatibility)."""
        try:
            old_data = self.find_by_id(portfolio_id)
            if not old_data:
                return False

            success = self.update(portfolio_id, {
                'status': self.STATUS_DRAFT,
                'is_active': False,
                'updated_by': reactivated_by
            })

            if success:
                logger.info(f"Portfolio {portfolio_id} reactivated by {reactivated_by}")

                self.create_history_record_async(
                    portfolio_id, 'REACTIVATE',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_DRAFT},
                    reactivated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error reactivating portfolio: {str(e)}")
            return False


# Singleton instance
portfolio_hive_repository = PortfolioHiveRepository()
