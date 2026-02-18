"""
Trade Hive Repository (ORC + ACID)

Data access layer for trade operations using Hive managed tables.
Implements:
- CRUD operations for trades
- Four-Eyes (Maker-Checker) workflow
- Audit trail with field-level change tracking
- Position management

Trade Types:
- BUY, SELL, ADD_LONG, DELIVER_LONG
- REDUCTION_BASIS, INCOME, SPLIT_TRANSACTION
"""

import logging
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


class TradeHiveRepository(HiveBaseRepository):
    """Repository for trade operations with Hive managed tables (ORC + ACID)"""

    # Trade Types
    TRADE_TYPE_BUY = 'BUY'
    TRADE_TYPE_SELL = 'SELL'
    TRADE_TYPE_ADD_LONG = 'ADD_LONG'
    TRADE_TYPE_DELIVER_LONG = 'DELIVER_LONG'
    TRADE_TYPE_REDUCTION_BASIS = 'REDUCTION_BASIS'
    TRADE_TYPE_INCOME = 'INCOME'
    TRADE_TYPE_SPLIT_TRANSACTION = 'SPLIT_TRANSACTION'

    ALL_TRADE_TYPES = [
        TRADE_TYPE_BUY, TRADE_TYPE_SELL, TRADE_TYPE_ADD_LONG,
        TRADE_TYPE_DELIVER_LONG, TRADE_TYPE_REDUCTION_BASIS,
        TRADE_TYPE_INCOME, TRADE_TYPE_SPLIT_TRANSACTION
    ]

    # Workflow Status Constants
    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_SETTLED = 'SETTLED'

    # Status groups
    MAKER_EDITABLE_STATUSES = [STATUS_DRAFT, STATUS_REJECTED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_PENDING_APPROVAL, STATUS_APPROVED]

    @property
    def table_name(self) -> str:
        return 'cis_trade'

    @property
    def primary_key(self) -> str:
        return 'trade_id'

    @property
    def columns(self) -> List[str]:
        return [
            'trade_id', 'portfolio_id', 'portfolio_short_name', 'security_id',
            'security_name', 'trade_type', 'trade_action', 'quantity', 'price',
            'trade_amount', 'currency', 'trade_date', 'settlement_date', 'value_date',
            'counterparty_id', 'counterparty_name', 'broker_id', 'broker_name',
            'commission', 'fees', 'net_amount', 'status', 'notes', 'is_active',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    def to_decimal(self, val: Any, default: float = 0) -> str:
        """Convert value to decimal string for SQL (no quotes)."""
        if val is None or val == '':
            return str(default)
        try:
            if isinstance(val, str):
                val = val.strip()
                if val == '':
                    return str(default)
                return str(float(val))
            return str(float(val))
        except (ValueError, TypeError):
            return str(default)

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_all_trades(
        self,
        limit: int = 1000,
        trade_type: Optional[str] = None,
        status: Optional[str] = None,
        portfolio_id: Optional[str] = None,
        security_id: Optional[str] = None,
        search: Optional[str] = None,
        trade_date_from: Optional[str] = None,
        trade_date_to: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieve trades from Hive with filters."""
        try:
            where_clauses = []

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            if trade_type:
                where_clauses.append(f"trade_type = '{trade_type}'")

            if status:
                where_clauses.append(f"status = '{status}'")

            if portfolio_id:
                where_clauses.append(f"portfolio_id = '{portfolio_id}'")

            if security_id:
                where_clauses.append(f"security_id = '{security_id}'")

            if search:
                search_escaped = search.replace("'", "''").lower()
                where_clauses.append(
                    f"(LOWER(trade_id) LIKE '%{search_escaped}%' OR "
                    f"LOWER(security_name) LIKE '%{search_escaped}%' OR "
                    f"LOWER(portfolio_short_name) LIKE '%{search_escaped}%')"
                )

            if trade_date_from:
                where_clauses.append(f"trade_date >= '{trade_date_from}'")

            if trade_date_to:
                where_clauses.append(f"trade_date <= '{trade_date_to}'")

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
            logger.error(f"Error retrieving trades: {str(e)}")
            return []

    def get_trade_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get trade by ID."""
        return self.find_by_id(trade_id)

    def get_trades_by_status(self, statuses: List[str], limit: int = 1000) -> List[Dict[str, Any]]:
        """Get trades filtered by multiple statuses."""
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
            logger.error(f"Error retrieving trades by status: {str(e)}")
            return []

    def get_pending_approval_trades(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get trades pending approval."""
        return self.get_trades_by_status([self.STATUS_PENDING_APPROVAL], limit)

    def get_pending_settlement_trades(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get approved trades pending settlement."""
        return self.get_trades_by_status([self.STATUS_APPROVED], limit)

    def get_trade_statistics(self) -> Dict[str, Any]:
        """Get trade statistics for dashboard."""
        try:
            query = f"""
                SELECT status, trade_type
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            stats = {
                'total_trades': 0,
                'pending_approval': 0,
                'pending_settlement': 0,
                'settled': 0,
                'status_breakdown': {},
                'type_breakdown': {}
            }

            if results:
                stats['total_trades'] = len(results)
                for row in results:
                    status = row.get('status', 'Unknown')
                    trade_type = row.get('trade_type', 'Unknown')

                    stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + 1
                    stats['type_breakdown'][trade_type] = stats['type_breakdown'].get(trade_type, 0) + 1

                    if status == self.STATUS_PENDING_APPROVAL:
                        stats['pending_approval'] += 1
                    elif status == self.STATUS_APPROVED:
                        stats['pending_settlement'] += 1
                    elif status == self.STATUS_SETTLED:
                        stats['settled'] += 1

            return stats

        except Exception as e:
            logger.error(f"Error getting trade statistics: {str(e)}")
            return {
                'total_trades': 0,
                'pending_approval': 0,
                'pending_settlement': 0,
                'settled': 0,
                'status_breakdown': {},
                'type_breakdown': {}
            }

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def create_trade(self, trade_data: Dict[str, Any], created_by: str) -> Optional[str]:
        """
        Create a new trade with DRAFT status.
        Returns trade_id if successful, None otherwise.
        """
        try:
            trade_id = self._generate_id('TR')
            now = datetime.now()

            # Calculate net amount
            quantity = float(trade_data.get('quantity', 0) or 0)
            price = float(trade_data.get('price', 0) or 0)
            commission = float(trade_data.get('commission', 0) or 0)
            fees = float(trade_data.get('fees', 0) or 0)
            trade_amount = quantity * price
            net_amount = trade_amount - commission - fees

            data = {
                'trade_id': trade_id,
                'portfolio_id': trade_data.get('portfolio_id'),
                'portfolio_short_name': trade_data.get('portfolio_short_name'),
                'security_id': trade_data.get('security_id'),
                'security_name': trade_data.get('security_name'),
                'trade_type': trade_data.get('trade_type'),
                'trade_action': trade_data.get('trade_action', trade_data.get('trade_type')),
                'quantity': quantity,
                'price': price,
                'trade_amount': trade_amount,
                'currency': trade_data.get('currency'),
                'trade_date': trade_data.get('trade_date'),
                'settlement_date': trade_data.get('settlement_date'),
                'value_date': trade_data.get('value_date'),
                'counterparty_id': trade_data.get('counterparty_id'),
                'counterparty_name': trade_data.get('counterparty_name'),
                'broker_id': trade_data.get('broker_id'),
                'broker_name': trade_data.get('broker_name'),
                'commission': commission,
                'fees': fees,
                'net_amount': net_amount,
                'status': self.STATUS_DRAFT,
                'notes': trade_data.get('notes'),
                'is_active': False,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(data):
                logger.info(f"Created trade {trade_id} with DRAFT status")

                # Create history record asynchronously
                self.create_history_record_async(
                    trade_id, 'CREATE', None, data, created_by
                )

                return trade_id
            return None

        except Exception as e:
            logger.error(f"Error creating trade: {str(e)}")
            return None

    def update_trade(self, trade_id: str, trade_data: Dict[str, Any],
                    updated_by: str) -> bool:
        """
        Update trade data.
        Sets status to DRAFT if currently in editable status.
        """
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                logger.error(f"Trade {trade_id} not found")
                return False

            current_status = old_data.get('status', '')
            if current_status not in self.MAKER_EDITABLE_STATUSES:
                logger.error(f"Cannot edit trade with status '{current_status}'")
                return False

            # Prepare update data
            update_data = {}
            updatable_fields = [
                'portfolio_id', 'portfolio_short_name', 'security_id', 'security_name',
                'trade_type', 'trade_action', 'quantity', 'price', 'currency',
                'trade_date', 'settlement_date', 'value_date',
                'counterparty_id', 'counterparty_name', 'broker_id', 'broker_name',
                'commission', 'fees', 'notes'
            ]

            for field in updatable_fields:
                if field in trade_data:
                    update_data[field] = trade_data[field]

            # Recalculate amounts if quantity or price changed
            if 'quantity' in update_data or 'price' in update_data:
                quantity = float(update_data.get('quantity', old_data.get('quantity', 0)) or 0)
                price = float(update_data.get('price', old_data.get('price', 0)) or 0)
                commission = float(update_data.get('commission', old_data.get('commission', 0)) or 0)
                fees = float(update_data.get('fees', old_data.get('fees', 0)) or 0)
                update_data['trade_amount'] = quantity * price
                update_data['net_amount'] = update_data['trade_amount'] - commission - fees

            update_data['updated_by'] = updated_by
            update_data['status'] = self.STATUS_DRAFT

            success = self.update(trade_id, update_data)

            if success:
                logger.info(f"Updated trade {trade_id}")
                self.create_history_record_async(
                    trade_id, 'UPDATE', old_data, update_data, updated_by
                )

            return success

        except Exception as e:
            logger.error(f"Error updating trade: {str(e)}")
            return False

    def delete_trade(self, trade_id: str, deleted_by: str, reason: str = '') -> bool:
        """Soft delete a trade."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            success = self.soft_delete(trade_id, deleted_by)

            if success:
                logger.info(f"Trade {trade_id} deleted by {deleted_by}")
                self.create_history_record_async(
                    trade_id, 'DELETE', old_data,
                    {'reason': reason}, deleted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error deleting trade: {str(e)}")
            return False

    # =========================================================================
    # WORKFLOW OPERATIONS
    # =========================================================================

    def submit_for_approval(self, trade_id: str, submitted_by: str) -> bool:
        """Submit trade for approval (DRAFT -> PENDING_APPROVAL)."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            current_status = old_data.get('status', '')
            if current_status not in [self.STATUS_DRAFT]:
                logger.error(f"Cannot submit trade with status '{current_status}'")
                return False

            success = self.update(trade_id, {
                'status': self.STATUS_PENDING_APPROVAL,
                'updated_by': submitted_by
            })

            if success:
                logger.info(f"Trade {trade_id} submitted for approval by {submitted_by}")
                self.create_history_record_async(
                    trade_id, 'SUBMIT_FOR_APPROVAL',
                    {'status': current_status},
                    {'status': self.STATUS_PENDING_APPROVAL},
                    submitted_by
                )

            return success

        except Exception as e:
            logger.error(f"Error submitting trade: {str(e)}")
            return False

    def approve_trade(self, trade_id: str, approved_by: str, comments: str = '') -> bool:
        """Approve trade (PENDING_APPROVAL -> APPROVED)."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            current_status = old_data.get('status', '')
            if current_status != self.STATUS_PENDING_APPROVAL:
                logger.error(f"Cannot approve trade with status '{current_status}'")
                return False

            success = self.update(trade_id, {
                'status': self.STATUS_APPROVED,
                'updated_by': approved_by
            })

            if success:
                logger.info(f"Trade {trade_id} approved by {approved_by}")
                self.create_history_record_async(
                    trade_id, 'APPROVE',
                    {'status': current_status},
                    {'status': self.STATUS_APPROVED, 'comments': comments},
                    approved_by
                )

            return success

        except Exception as e:
            logger.error(f"Error approving trade: {str(e)}")
            return False

    def reject_trade(self, trade_id: str, rejected_by: str, reason: str = '') -> bool:
        """Reject trade (PENDING_APPROVAL -> REJECTED)."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            current_status = old_data.get('status', '')
            if current_status != self.STATUS_PENDING_APPROVAL:
                logger.error(f"Cannot reject trade with status '{current_status}'")
                return False

            success = self.update(trade_id, {
                'status': self.STATUS_REJECTED,
                'updated_by': rejected_by
            })

            if success:
                logger.info(f"Trade {trade_id} rejected by {rejected_by}")
                self.create_history_record_async(
                    trade_id, 'REJECT',
                    {'status': current_status},
                    {'status': self.STATUS_REJECTED, 'reason': reason},
                    rejected_by
                )

            return success

        except Exception as e:
            logger.error(f"Error rejecting trade: {str(e)}")
            return False

    def settle_trade(self, trade_id: str, settled_by: str, comments: str = '') -> bool:
        """Settle trade (APPROVED -> SETTLED)."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            current_status = old_data.get('status', '')
            if current_status != self.STATUS_APPROVED:
                logger.error(f"Cannot settle trade with status '{current_status}'")
                return False

            success = self.update(trade_id, {
                'status': self.STATUS_SETTLED,
                'is_active': True,
                'updated_by': settled_by
            })

            if success:
                logger.info(f"Trade {trade_id} settled by {settled_by}")
                self.create_history_record_async(
                    trade_id, 'SETTLE',
                    {'status': current_status, 'is_active': False},
                    {'status': self.STATUS_SETTLED, 'is_active': True, 'comments': comments},
                    settled_by
                )

            return success

        except Exception as e:
            logger.error(f"Error settling trade: {str(e)}")
            return False

    def cancel_trade(self, trade_id: str, cancelled_by: str, reason: str = '') -> bool:
        """Cancel trade."""
        try:
            old_data = self.find_by_id(trade_id)
            if not old_data:
                return False

            success = self.update(trade_id, {
                'status': self.STATUS_CANCELLED,
                'is_active': False,
                'updated_by': cancelled_by
            })

            if success:
                logger.info(f"Trade {trade_id} cancelled by {cancelled_by}")
                self.create_history_record_async(
                    trade_id, 'CANCEL',
                    {'status': old_data.get('status')},
                    {'status': self.STATUS_CANCELLED, 'reason': reason},
                    cancelled_by
                )

            return success

        except Exception as e:
            logger.error(f"Error cancelling trade: {str(e)}")
            return False

    # =========================================================================
    # TRADE NOTES
    # =========================================================================

    def add_trade_note(self, trade_id: str, note_type: str, note_text: str,
                      created_by: str) -> Optional[str]:
        """Add a note to a trade."""
        try:
            note_id = self._generate_id('TN')
            now = datetime.now()

            query = f"""
                INSERT INTO {self.database}.cis_trade_note
                (note_id, trade_id, note_type, note_text,
                 created_at, created_by, updated_at, updated_by, deleted_at)
                VALUES (
                    '{note_id}',
                    '{trade_id}',
                    {self._format_value(note_type)},
                    {self._format_value(note_text)},
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    '{created_by}',
                    NULL
                )
            """

            if self.conn_manager.execute_write(query, database=self.database):
                logger.info(f"Added note {note_id} to trade {trade_id}")
                return note_id
            return None

        except Exception as e:
            logger.error(f"Error adding trade note: {str(e)}")
            return None

    def get_trade_notes(self, trade_id: str) -> List[Dict[str, Any]]:
        """Get all notes for a trade."""
        try:
            query = f"""
                SELECT note_id, trade_id, note_type, note_text,
                       created_at, created_by, updated_at, updated_by
                FROM {self.database}.cis_trade_note
                WHERE trade_id = '{trade_id}'
                  AND deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting trade notes: {str(e)}")
            return []

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    def search_trades(self, search_term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search trades by ID, security name, or portfolio."""
        return self.search(
            search_term,
            ['trade_id', 'security_name', 'portfolio_short_name', 'counterparty_name']
        )[:limit]


# Singleton instance
trade_hive_repository = TradeHiveRepository()
