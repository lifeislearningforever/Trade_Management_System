"""
Trade Kudu Repository

Data access layer for trade operations using Kudu via Impala.
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

from core.repositories.impala_connection import impala_manager
from trade.repositories.trade_validation_repository import trade_validation_repository

logger = logging.getLogger(__name__)


class TradeKuduRepository:
    """Repository for trade operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_trade'
    HISTORY_TABLE = 'cis_trade_history'
    NOTE_TABLE = 'cis_trade_note'
    POSITION_TABLE = 'cis_position'
    SEQUENCE_TABLE = 'cis_sequence'

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

    # Workflow Status Constants (same as Portfolio)
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_PENDING_VALIDATION = 'PENDING_VALIDATION'
    STATUS_VALIDATED = 'VALIDATED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_SETTLED = 'SETTLED'

    # Status groups
    MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_CANCELLED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_PENDING_VALIDATION, STATUS_VALIDATED]

    @staticmethod
    def escape_value(val: Any) -> str:
        """Escape value for SQL query."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
        if isinstance(val, bool):
            return str(val).lower()
        return str(val)

    # =========================================================================
    # ID GENERATION
    # =========================================================================

    def get_next_id(self, sequence_name: str) -> int:
        """
        Get next ID from sequence table.
        Uses timestamp-based ID if sequence not available.
        """
        try:
            # Generate timestamp-based ID as fallback
            timestamp_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)
            return timestamp_id
        except Exception as e:
            logger.error(f"Error generating ID: {str(e)}")
            return int(datetime.now().timestamp() * 1000)

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate_trade_data(
        self,
        trade_data: Dict[str, Any],
        is_update: bool = False
    ) -> tuple[bool, List[str]]:
        """
        Validate trade data before insert/update.

        Args:
            trade_data: Trade data dictionary
            is_update: True if updating existing trade

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        if not trade_data.get('portfolio_short_name'):
            errors.append("Portfolio is required")

        if not trade_data.get('security_label'):
            errors.append("Security is required")

        if not trade_data.get('trade_type'):
            errors.append("Trade type is required")

        if not trade_data.get('trade_date'):
            errors.append("Trade date is required")

        # Validate references exist
        all_valid, validation_results = trade_validation_repository.validate_trade_references(
            portfolio_name=trade_data.get('portfolio_short_name', ''),
            security_name=trade_data.get('security_label', ''),
            counterparty_name=trade_data.get('counterparty', '')
        )

        if not all_valid:
            errors.extend(trade_validation_repository.get_validation_errors(validation_results))

        # Trade type specific validations
        trade_type = trade_data.get('trade_type', '')

        if trade_type in [self.TRADE_TYPE_BUY, self.TRADE_TYPE_SELL]:
            if not trade_data.get('quantity'):
                errors.append("Quantity is required for Buy/Sell trades")
            if not trade_data.get('price'):
                errors.append("Price is required for Buy/Sell trades")

        if trade_type == self.TRADE_TYPE_SELL:
            # Check position exists with sufficient quantity
            position = self.get_position(
                trade_data.get('portfolio_short_name', ''),
                trade_data.get('security_label', '')
            )
            if not position:
                errors.append(f"No position found for {trade_data.get('security_label')} in portfolio {trade_data.get('portfolio_short_name')}")
            elif position.get('quantity', 0) < float(trade_data.get('quantity', 0)):
                errors.append(f"Insufficient quantity. Available: {position.get('quantity', 0)}, Requested: {trade_data.get('quantity', 0)}")

        return len(errors) == 0, errors

    # =========================================================================
    # TRADE CRUD OPERATIONS
    # =========================================================================

    def get_all_trades(
        self,
        limit: int = 1000,
        trade_type: Optional[str] = None,
        status: Optional[str] = None,
        portfolio: Optional[str] = None,
        security: Optional[str] = None,
        search: Optional[str] = None,
        trade_date_from: Optional[str] = None,
        trade_date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve trades from Kudu with filters.
        """
        try:
            where_clauses = ["(is_deleted = false OR is_deleted IS NULL)"]

            if trade_type:
                where_clauses.append(f"trade_type = {self.escape_value(trade_type)}")

            if status:
                where_clauses.append(f"status = {self.escape_value(status)}")

            if portfolio:
                where_clauses.append(f"portfolio_short_name = {self.escape_value(portfolio)}")

            if security:
                where_clauses.append(f"security_label = {self.escape_value(security)}")

            if search:
                search_escaped = search.replace("'", "''")
                where_clauses.append(
                    f"(deal_number LIKE '%{search_escaped}%' OR "
                    f"security_label LIKE '%{search_escaped}%' OR "
                    f"portfolio_short_name LIKE '%{search_escaped}%')"
                )

            if trade_date_from:
                where_clauses.append(f"trade_date >= {self.escape_value(trade_date_from)}")

            if trade_date_to:
                where_clauses.append(f"trade_date <= {self.escape_value(trade_date_to)}")

            where_clause = " AND ".join(where_clauses)

            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END,
                     created_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving trades: {str(e)}")
            return []

    def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """Get trade by ID."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE trade_id = {trade_id}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting trade by ID: {str(e)}")
            return None

    def get_trade_by_deal_number(self, deal_number: str) -> Optional[Dict[str, Any]]:
        """Get trade by deal number."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE deal_number = {self.escape_value(deal_number)}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting trade by deal number: {str(e)}")
            return None

    def insert_trade(self, trade_data: Dict[str, Any], created_by: str) -> Optional[int]:
        """
        Insert a new trade with INITIAL status.
        Returns trade_id if successful, None otherwise.
        """
        try:
            # Validate first
            is_valid, errors = self.validate_trade_data(trade_data)
            if not is_valid:
                logger.error(f"Trade validation failed: {errors}")
                raise ValueError("; ".join(errors))

            # Generate IDs
            trade_id = self.get_next_id('trade_id')
            deal_number = trade_data.get('deal_number') or f"DEAL-{datetime.now().strftime('%Y%m%d')}-{trade_id % 10000}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get auto-populated fields from validation
            portfolio_details = trade_validation_repository.get_portfolio_details(
                trade_data.get('portfolio_short_name', '')
            )
            security_details = trade_validation_repository.get_security_details(
                trade_data.get('security_label', '')
            )

            # Build column and value lists
            columns = [
                'trade_id', 'trade_type', 'deal_number',
                'portfolio_short_name', 'portfolio_full_name',
                'security_label', 'security_full_name', 'security_type',
                'trade_status', 'trade_date', 'settle_date',
                'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee',
                'other_charges', 'total_amount',
                'open_close_position', 'extension', 'brokers', 'broker_name',
                'gl_fund_type', 'gl_cost_centre', 'gl_account_code',
                'contract_ref', 'fd_receipt', 'org_pur_date',
                'open_fx_rate', 'curr_dealing', 'open_dealing',
                'input_tax_oth', 'qty_entitled',
                'selling_rule', 'cash_balance', 'custodian', 'amor_accr_method',
                'remarks', 'counterparty',
                'udf_fund_type', 'udf_section_31_26', 'udf_sub_custodian',
                'udf_disclosure_req', 'udf_counter_pledged', 'udf_revision_code',
                'udf_uobn_uobn_hk', 'udf_income_exp_type', 'udf_currency_hedge',
                'status', 'is_active', 'is_deleted', 'src_system',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            values = [
                str(trade_id),
                self.escape_value(trade_data.get('trade_type')),
                self.escape_value(deal_number),
                self.escape_value(trade_data.get('portfolio_short_name')),
                self.escape_value(portfolio_details.get('name', '') if portfolio_details else ''),
                self.escape_value(trade_data.get('security_label')),
                self.escape_value(security_details.get('security_name', '') if security_details else ''),
                self.escape_value(security_details.get('security_type', '') if security_details else ''),
                self.escape_value(trade_data.get('trade_status', '')),
                self.escape_value(trade_data.get('trade_date')),
                self.escape_value(trade_data.get('settle_date', '')),
                self.escape_value(trade_data.get('quantity', 0)),
                self.escape_value(trade_data.get('face_value', 0)),
                self.escape_value(trade_data.get('lot', 0)),
                self.escape_value(trade_data.get('price', 0)),
                self.escape_value(trade_data.get('commission', 0)),
                self.escape_value(trade_data.get('accrued_interest', 0)),
                self.escape_value(trade_data.get('sec_fee', 0)),
                self.escape_value(trade_data.get('other_charges', 0)),
                self.escape_value(trade_data.get('total_amount', 0)),
                self.escape_value(trade_data.get('open_close_position', '')),
                self.escape_value(trade_data.get('extension', '')),
                self.escape_value(trade_data.get('brokers', '')),
                self.escape_value(trade_data.get('broker_name', '')),
                self.escape_value(trade_data.get('gl_fund_type', '')),
                self.escape_value(trade_data.get('gl_cost_centre', '')),
                self.escape_value(trade_data.get('gl_account_code', '')),
                self.escape_value(trade_data.get('contract_ref', '')),
                self.escape_value(trade_data.get('fd_receipt', '')),
                self.escape_value(trade_data.get('org_pur_date', '')),
                self.escape_value(trade_data.get('open_fx_rate', 0)),
                self.escape_value(trade_data.get('curr_dealing', 0)),
                self.escape_value(trade_data.get('open_dealing', 0)),
                self.escape_value(trade_data.get('input_tax_oth', 0)),
                self.escape_value(trade_data.get('qty_entitled', 0)),
                self.escape_value(trade_data.get('selling_rule', '')),
                self.escape_value(trade_data.get('cash_balance', 0)),
                self.escape_value(trade_data.get('custodian', '')),
                self.escape_value(trade_data.get('amor_accr_method', '')),
                self.escape_value(trade_data.get('remarks', '')),
                self.escape_value(trade_data.get('counterparty', '')),
                self.escape_value(trade_data.get('udf_fund_type', '')),
                self.escape_value(trade_data.get('udf_section_31_26', '')),
                self.escape_value(trade_data.get('udf_sub_custodian', '')),
                str(trade_data.get('udf_disclosure_req', False)).lower(),
                str(trade_data.get('udf_counter_pledged', False)).lower(),
                self.escape_value(trade_data.get('udf_revision_code', '')),
                self.escape_value(trade_data.get('udf_uobn_uobn_hk', '')),
                self.escape_value(trade_data.get('udf_income_exp_type', '')),
                str(trade_data.get('udf_currency_hedge', False)).lower(),
                f"'{self.STATUS_INITIAL}'",
                'false',  # is_active (not yet settled)
                'false',  # is_deleted
                "'CIS'",  # src_system
                self.escape_value(created_by),
                f"'{timestamp}'",
                self.escape_value(created_by),
                f"'{timestamp}'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                # Insert history record
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=deal_number,
                    action='CREATE',
                    old_status=None,
                    new_status=self.STATUS_INITIAL,
                    changes={},
                    comments='Trade created',
                    performed_by=created_by
                )
                logger.info(f"Created trade {trade_id} ({deal_number}) with INITIAL status")
                return trade_id

            return None

        except Exception as e:
            logger.error(f"Error inserting trade: {str(e)}")
            raise

    def update_trade(self, trade_id: int, trade_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update trade data. Sets status to MODIFIED.
        """
        try:
            # Get current trade for history
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status not in self.MAKER_EDITABLE_STATUSES:
                raise ValueError(f"Cannot edit trade with status '{current_status}'")

            # Validate
            is_valid, errors = self.validate_trade_data(trade_data, is_update=True)
            if not is_valid:
                raise ValueError("; ".join(errors))

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build SET clauses
            set_clauses = []
            changes = {}

            # Updatable fields
            updatable_fields = [
                'trade_status', 'trade_date', 'settle_date',
                'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee',
                'other_charges', 'total_amount',
                'open_close_position', 'extension', 'brokers', 'broker_name',
                'gl_fund_type', 'gl_cost_centre', 'gl_account_code',
                'contract_ref', 'fd_receipt', 'org_pur_date',
                'open_fx_rate', 'curr_dealing', 'open_dealing',
                'input_tax_oth', 'qty_entitled',
                'selling_rule', 'cash_balance', 'custodian', 'amor_accr_method',
                'remarks', 'counterparty',
                'udf_fund_type', 'udf_section_31_26', 'udf_sub_custodian',
                'udf_disclosure_req', 'udf_counter_pledged', 'udf_revision_code',
                'udf_uobn_uobn_hk', 'udf_income_exp_type', 'udf_currency_hedge'
            ]

            for field in updatable_fields:
                if field in trade_data:
                    new_value = trade_data[field]
                    old_value = current_trade.get(field)

                    if str(new_value) != str(old_value):
                        changes[field] = {'old': old_value, 'new': new_value}

                        if field in ['udf_disclosure_req', 'udf_counter_pledged', 'udf_currency_hedge']:
                            set_clauses.append(f"{field} = {str(new_value).lower()}")
                        else:
                            set_clauses.append(f"{field} = {self.escape_value(new_value)}")

            # Always update status and audit fields
            set_clauses.append(f"status = '{self.STATUS_MODIFIED}'")
            set_clauses.append(f"updated_by = {self.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = '{timestamp}'")

            if not set_clauses:
                logger.warning(f"No fields to update for trade {trade_id}")
                return True

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                # Insert history record
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='UPDATE',
                    old_status=current_status,
                    new_status=self.STATUS_MODIFIED,
                    changes=changes,
                    comments='Trade updated',
                    performed_by=updated_by
                )
                logger.info(f"Updated trade {trade_id}, status set to MODIFIED")

            return success

        except Exception as e:
            logger.error(f"Error updating trade: {str(e)}")
            raise

    def soft_delete_trade(self, trade_id: int, deleted_by: str, reason: str = '') -> bool:
        """Soft delete a trade."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET is_deleted = true,
                is_active = false,
                status = '{self.STATUS_CANCELLED}',
                cancelled_by = {self.escape_value(deleted_by)},
                cancelled_at = '{timestamp}',
                cancel_reason = {self.escape_value(reason)},
                updated_by = {self.escape_value(deleted_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='DELETE',
                    old_status=current_trade.get('status', ''),
                    new_status=self.STATUS_CANCELLED,
                    changes={},
                    comments=f'Trade soft deleted. Reason: {reason}',
                    performed_by=deleted_by
                )
                logger.info(f"Soft deleted trade {trade_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting trade: {str(e)}")
            return False

    # =========================================================================
    # WORKFLOW OPERATIONS
    # =========================================================================

    def submit_for_validation(self, trade_id: int, submitted_by: str) -> bool:
        """Submit trade for validation (INITIAL/MODIFIED -> PENDING_VALIDATION)."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                raise ValueError(f"Cannot submit trade with status '{current_status}'")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_PENDING_VALIDATION}',
                submitted_by = {self.escape_value(submitted_by)},
                submitted_at = '{timestamp}',
                updated_by = {self.escape_value(submitted_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='SUBMIT',
                    old_status=current_status,
                    new_status=self.STATUS_PENDING_VALIDATION,
                    changes={},
                    comments='Submitted for validation',
                    performed_by=submitted_by
                )
                logger.info(f"Trade {trade_id} submitted for validation")

            return success

        except Exception as e:
            logger.error(f"Error submitting trade: {str(e)}")
            raise

    def validate_trade(self, trade_id: int, validated_by: str, comments: str = '') -> bool:
        """Validate trade (PENDING_VALIDATION -> VALIDATED)."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status != self.STATUS_PENDING_VALIDATION:
                raise ValueError(f"Cannot validate trade with status '{current_status}'")

            # Four-eyes check
            submitted_by = current_trade.get('submitted_by', '')
            if submitted_by and submitted_by == validated_by:
                raise ValueError("Four-eyes principle: You cannot validate your own submission")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_VALIDATED}',
                validated_by = {self.escape_value(validated_by)},
                validated_at = '{timestamp}',
                validation_comments = {self.escape_value(comments)},
                updated_by = {self.escape_value(validated_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='VALIDATE',
                    old_status=current_status,
                    new_status=self.STATUS_VALIDATED,
                    changes={},
                    comments=comments or 'Trade validated',
                    performed_by=validated_by
                )
                logger.info(f"Trade {trade_id} validated")

            return success

        except Exception as e:
            logger.error(f"Error validating trade: {str(e)}")
            raise

    def reject_trade(self, trade_id: int, rejected_by: str, reason: str = '') -> bool:
        """Reject trade (PENDING_VALIDATION -> CANCELLED)."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status != self.STATUS_PENDING_VALIDATION:
                raise ValueError(f"Cannot reject trade with status '{current_status}'")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_CANCELLED}',
                cancelled_by = {self.escape_value(rejected_by)},
                cancelled_at = '{timestamp}',
                cancel_reason = {self.escape_value(reason)},
                updated_by = {self.escape_value(rejected_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='REJECT',
                    old_status=current_status,
                    new_status=self.STATUS_CANCELLED,
                    changes={},
                    comments=f'Trade rejected. Reason: {reason}',
                    performed_by=rejected_by
                )
                logger.info(f"Trade {trade_id} rejected")

            return success

        except Exception as e:
            logger.error(f"Error rejecting trade: {str(e)}")
            raise

    def settle_trade(self, trade_id: int, settled_by: str, comments: str = '') -> bool:
        """Settle trade (VALIDATED -> SETTLED). Updates position."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status != self.STATUS_VALIDATED:
                raise ValueError(f"Cannot settle trade with status '{current_status}'")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_SETTLED}',
                is_active = true,
                settled_by = {self.escape_value(settled_by)},
                settled_at = '{timestamp}',
                settlement_comments = {self.escape_value(comments)},
                updated_by = {self.escape_value(settled_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                # Update position
                self.update_position_from_trade(current_trade, settled_by)

                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='SETTLE',
                    old_status=current_status,
                    new_status=self.STATUS_SETTLED,
                    changes={},
                    comments=comments or 'Trade settled',
                    performed_by=settled_by
                )
                logger.info(f"Trade {trade_id} settled")

            return success

        except Exception as e:
            logger.error(f"Error settling trade: {str(e)}")
            raise

    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================

    def get_position(self, portfolio_name: str, security_label: str) -> Optional[Dict[str, Any]]:
        """Get current position for portfolio-security combination."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = {self.escape_value(portfolio_name)}
              AND security_label = {self.escape_value(security_label)}
              AND status = 'OPEN'
              AND is_active = true
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting position: {str(e)}")
            return None

    def update_position_from_trade(self, trade: Dict[str, Any], updated_by: str) -> bool:
        """Update position based on settled trade."""
        try:
            portfolio = trade.get('portfolio_short_name', '')
            security = trade.get('security_label', '')
            trade_type = trade.get('trade_type', '')
            quantity = float(trade.get('quantity', 0))
            price = float(trade.get('price', 0))

            current_position = self.get_position(portfolio, security)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if trade_type == self.TRADE_TYPE_BUY:
                if current_position:
                    # Update existing position
                    old_qty = float(current_position.get('quantity', 0))
                    old_cost = float(current_position.get('average_cost', 0))
                    new_qty = old_qty + quantity
                    new_avg_cost = ((old_qty * old_cost) + (quantity * price)) / new_qty if new_qty > 0 else 0

                    query = f"""
                    UPDATE {self.DATABASE}.{self.POSITION_TABLE}
                    SET quantity = {new_qty},
                        average_cost = {new_avg_cost},
                        total_cost = {new_qty * new_avg_cost},
                        last_trade_id = {trade.get('trade_id')},
                        last_trade_date = '{trade.get('trade_date', '')}',
                        updated_at = '{timestamp}'
                    WHERE position_id = {current_position.get('position_id')}
                    """
                else:
                    # Create new position
                    position_id = self.get_next_id('position_id')
                    query = f"""
                    UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE}
                    (position_id, portfolio_short_name, security_label, quantity, average_cost, total_cost,
                     status, is_active, last_trade_id, last_trade_date, created_at, updated_at)
                    VALUES (
                        {position_id}, {self.escape_value(portfolio)}, {self.escape_value(security)},
                        {quantity}, {price}, {quantity * price}, 'OPEN', true,
                        {trade.get('trade_id')}, '{trade.get('trade_date', '')}', '{timestamp}', '{timestamp}'
                    )
                    """

                return impala_manager.execute_write(query, database=self.DATABASE)

            elif trade_type == self.TRADE_TYPE_SELL:
                if current_position:
                    old_qty = float(current_position.get('quantity', 0))
                    new_qty = old_qty - quantity

                    if new_qty <= 0:
                        # Close position
                        query = f"""
                        UPDATE {self.DATABASE}.{self.POSITION_TABLE}
                        SET quantity = 0,
                            status = 'CLOSED',
                            is_active = false,
                            last_trade_id = {trade.get('trade_id')},
                            last_trade_date = '{trade.get('trade_date', '')}',
                            updated_at = '{timestamp}'
                        WHERE position_id = {current_position.get('position_id')}
                        """
                    else:
                        query = f"""
                        UPDATE {self.DATABASE}.{self.POSITION_TABLE}
                        SET quantity = {new_qty},
                            total_cost = {new_qty * float(current_position.get('average_cost', 0))},
                            last_trade_id = {trade.get('trade_id')},
                            last_trade_date = '{trade.get('trade_date', '')}',
                            updated_at = '{timestamp}'
                        WHERE position_id = {current_position.get('position_id')}
                        """

                    return impala_manager.execute_write(query, database=self.DATABASE)

            return True

        except Exception as e:
            logger.error(f"Error updating position: {str(e)}")
            return False

    # =========================================================================
    # HISTORY
    # =========================================================================

    def insert_trade_history(
        self,
        trade_id: int,
        deal_number: str,
        action: str,
        old_status: Optional[str],
        new_status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """Insert trade history record."""
        try:
            history_id = self.get_next_id('trade_history_id')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            changes_json = json.dumps(changes).replace("'", "''") if changes else '{}'

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.HISTORY_TABLE}
            (history_id, trade_id, deal_number, action, old_status, new_status,
             changes, comments, performed_by, performed_at)
            VALUES (
                {history_id}, {trade_id}, {self.escape_value(deal_number)},
                {self.escape_value(action)}, {self.escape_value(old_status)},
                {self.escape_value(new_status)}, '{changes_json}',
                {self.escape_value(comments)}, {self.escape_value(performed_by)},
                '{timestamp}'
            )
            """

            return impala_manager.execute_write(query, database=self.DATABASE)

        except Exception as e:
            logger.error(f"Error inserting trade history: {str(e)}")
            return False

    def get_trade_history(self, trade_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get history records for a trade."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.HISTORY_TABLE}
            WHERE trade_id = {trade_id}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting trade history: {str(e)}")
            return []

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_trade_statistics(self) -> Dict[str, Any]:
        """Get trade statistics for dashboard."""
        try:
            query = f"""
            SELECT status, trade_type, COUNT(*) as count
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE is_deleted = false OR is_deleted IS NULL
            GROUP BY status, trade_type
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            stats = {
                'total_trades': 0,
                'pending_validation': 0,
                'pending_settlement': 0,
                'settled': 0,
                'status_breakdown': {},
                'type_breakdown': {}
            }

            if results:
                for row in results:
                    status = row.get('status', 'Unknown')
                    trade_type = row.get('trade_type', 'Unknown')
                    count = row.get('count', 0)

                    stats['total_trades'] += count
                    stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + count
                    stats['type_breakdown'][trade_type] = stats['type_breakdown'].get(trade_type, 0) + count

                    if status == self.STATUS_PENDING_VALIDATION:
                        stats['pending_validation'] += count
                    elif status == self.STATUS_VALIDATED:
                        stats['pending_settlement'] += count
                    elif status == self.STATUS_SETTLED:
                        stats['settled'] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting trade statistics: {str(e)}")
            return {
                'total_trades': 0,
                'pending_validation': 0,
                'pending_settlement': 0,
                'settled': 0,
                'status_breakdown': {},
                'type_breakdown': {}
            }

    def get_pending_validation_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get trades pending validation."""
        return self.get_all_trades(limit=limit, status=self.STATUS_PENDING_VALIDATION)

    def get_pending_settlement_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get validated trades pending settlement."""
        return self.get_all_trades(limit=limit, status=self.STATUS_VALIDATED)


# Singleton instance
trade_kudu_repository = TradeKuduRepository()
