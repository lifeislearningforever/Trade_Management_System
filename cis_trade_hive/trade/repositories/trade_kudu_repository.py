"""
Trade Kudu Repository

Data access layer for trade operations using Kudu via Impala.
Implements:
- CRUD operations for trades
- Four-Eyes (Maker-Checker) workflow
- Audit trail with field-level change tracking
- Position management (versioned snapshots)

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
    TRADE_POSITION_TABLE = 'cis_trade_position'
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

    @staticmethod
    def to_decimal(val: Any, default: float = 0) -> str:
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
            # Check trade details exists with sufficient quantity
            trade_detail = self.get_trade_detail(
                trade_data.get('portfolio_short_name', ''),
                trade_data.get('security_label', '')
            )
            if not trade_detail:
                errors.append(f"No trade detail found for {trade_data.get('security_label')} in portfolio {trade_data.get('portfolio_short_name')}")
            elif trade_detail.get('quantity', 0) < float(trade_data.get('quantity', 0)):
                errors.append(f"Insufficient quantity. Available: {trade_detail.get('quantity', 0)}, Requested: {trade_data.get('quantity', 0)}")

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
        Retrieve trades from Kudu with filters (single portfolio/security).
        """
        return self.get_all_trades_multi_filter(
            limit=limit,
            trade_type=trade_type,
            status=status,
            portfolios=[portfolio] if portfolio else None,
            securities=[security] if security else None,
            search=search,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to
        )

    def get_all_trades_multi_filter(
        self,
        limit: int = 1000,
        trade_type: Optional[str] = None,
        status: Optional[str] = None,
        portfolios: Optional[List[str]] = None,
        securities: Optional[List[str]] = None,
        search: Optional[str] = None,
        trade_date_from: Optional[str] = None,
        trade_date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve trades from Kudu with multi-select filters.
        Portfolios and Securities use OR logic within their groups.

        Args:
            limit: Maximum records to return
            trade_type: Single trade type filter
            status: Single status filter
            portfolios: List of portfolio names (OR logic)
            securities: List of security labels (OR logic)
            search: Text search in deal_number, security_label, portfolio_short_name
            trade_date_from: Start date filter (YYYY-MM-DD)
            trade_date_to: End date filter (YYYY-MM-DD)

        Returns:
            List of trade dictionaries
        """
        try:
            where_clauses = ["(is_deleted = false OR is_deleted IS NULL)"]

            if trade_type:
                where_clauses.append(f"trade_type = {self.escape_value(trade_type)}")

            if status:
                where_clauses.append(f"status = {self.escape_value(status)}")

            # Multi-select portfolios with OR logic
            if portfolios and len(portfolios) > 0:
                portfolio_values = ", ".join([self.escape_value(p) for p in portfolios if p])
                if portfolio_values:
                    where_clauses.append(f"portfolio_short_name IN ({portfolio_values})")

            # Multi-select securities with OR logic
            if securities and len(securities) > 0:
                security_values = ", ".join([self.escape_value(s) for s in securities if s])
                if security_values:
                    where_clauses.append(f"security_label IN ({security_values})")

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
            logger.error(f"Error retrieving trades with multi-filter: {str(e)}")
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
                'currency_code',
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
                self.escape_value(trade_data.get('currency_code', '')),
                self.escape_value(trade_data.get('trade_status', '')),
                self.escape_value(trade_data.get('trade_date')),
                self.escape_value(trade_data.get('settle_date', '')),
                # Numeric fields - use to_decimal (no quotes)
                self.to_decimal(trade_data.get('quantity'), 0),
                self.to_decimal(trade_data.get('face_value'), 0),
                self.to_decimal(trade_data.get('lot'), 0),
                self.to_decimal(trade_data.get('price'), 0),
                self.to_decimal(trade_data.get('commission'), 0),
                self.to_decimal(trade_data.get('accrued_interest'), 0),
                self.to_decimal(trade_data.get('sec_fee'), 0),
                self.to_decimal(trade_data.get('other_charges'), 0),
                self.to_decimal(trade_data.get('total_amount'), 0),
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
                # More numeric fields
                self.to_decimal(trade_data.get('open_fx_rate'), 0),
                self.to_decimal(trade_data.get('curr_dealing'), 0),
                self.to_decimal(trade_data.get('open_dealing'), 0),
                self.to_decimal(trade_data.get('input_tax_oth'), 0),
                self.to_decimal(trade_data.get('qty_entitled'), 0),
                self.escape_value(trade_data.get('selling_rule', '')),
                self.to_decimal(trade_data.get('cash_balance'), 0),
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

                # Auto-create/update position from trade
                trade_for_position = {
                    'portfolio_short_name': trade_data.get('portfolio_short_name', ''),
                    'security_label': trade_data.get('security_label', ''),
                    'trade_type': trade_data.get('trade_type', ''),
                    'quantity': trade_data.get('quantity', 0),
                    'price': trade_data.get('price', 0),
                    'total_amount': trade_data.get('total_amount', 0),
                    'trade_id': trade_id,
                    'trade_date': trade_data.get('trade_date', ''),
                }
                self.update_position_from_trade(trade_for_position, created_by)

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
                'currency_code', 'trade_status', 'trade_date', 'settle_date',
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
    # POSITION MANAGEMENT (Versioned Snapshots)
    # =========================================================================

    def get_position(self, portfolio_name: str, security_label: str) -> Optional[Dict[str, Any]]:
        """Get current position (latest version) for portfolio-security combination."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE}
            WHERE portfolio_short_name = {self.escape_value(portfolio_name)}
              AND security_label = {self.escape_value(security_label)}
              AND status = 'OPEN'
              AND is_active = true
            ORDER BY version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting position: {str(e)}")
            return None

    def get_trade_detail(self, portfolio_name: str, security_label: str) -> Optional[Dict[str, Any]]:
        """Alias for backward compatibility - used by validation."""
        return self.get_position(portfolio_name, security_label)

    def get_position_by_id(self, position_id: int) -> Optional[Dict[str, Any]]:
        """Get latest version of a position by position_id."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE}
            WHERE position_id = {position_id}
            ORDER BY version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting position by ID: {str(e)}")
            return None

    def get_all_positions(self, status: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Get all positions (latest version per position_id)."""
        try:
            where_clauses = []
            if status:
                where_clauses.append(f"p.status = {self.escape_value(status)}")

            where_clause = f"AND {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            SELECT p.*
            FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE} p
            INNER JOIN (
                SELECT position_id, MAX(version_id) as max_version
                FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE}
                GROUP BY position_id
            ) latest ON p.position_id = latest.position_id AND p.version_id = latest.max_version
            WHERE 1=1 {where_clause}
            ORDER BY p.created_at DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return []

    def get_position_versions(self, position_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all version snapshots for a position (the versions ARE the history)."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE}
            WHERE position_id = {position_id}
            ORDER BY version_id DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting position versions: {str(e)}")
            return []

    def get_position_statistics(self) -> Dict[str, Any]:
        """Get position statistics for the position list page."""
        try:
            query = f"""
            SELECT
                COUNT(*) as total_positions,
                SUM(CASE WHEN p.market_value IS NOT NULL THEN p.market_value ELSE 0 END) as total_market_value,
                SUM(CASE WHEN p.unrealized_pnl IS NOT NULL THEN p.unrealized_pnl ELSE 0 END) as total_unrealized_pnl,
                SUM(CASE WHEN p.realized_pnl IS NOT NULL THEN p.realized_pnl ELSE 0 END) as total_realized_pnl
            FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE} p
            INNER JOIN (
                SELECT position_id, MAX(version_id) as max_version
                FROM {self.DATABASE}.{self.TRADE_POSITION_TABLE}
                GROUP BY position_id
            ) latest ON p.position_id = latest.position_id AND p.version_id = latest.max_version
            WHERE p.status = 'OPEN' AND p.is_active = true
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0]:
                row = results[0]
                return {
                    'total_positions': row.get('total_positions', 0),
                    'total_market_value': float(row.get('total_market_value', 0) or 0),
                    'total_unrealized_pnl': float(row.get('total_unrealized_pnl', 0) or 0),
                    'total_realized_pnl': float(row.get('total_realized_pnl', 0) or 0),
                }
            return {'total_positions': 0, 'total_market_value': 0, 'total_unrealized_pnl': 0, 'total_realized_pnl': 0}
        except Exception as e:
            logger.error(f"Error getting position statistics: {str(e)}")
            return {'total_positions': 0, 'total_market_value': 0, 'total_unrealized_pnl': 0, 'total_realized_pnl': 0}

    def _get_equity_price(self, security_label: str) -> Optional[float]:
        """Fetch latest equity price for a security from cis_equity_price_kudu or cis_security_kudu."""
        try:
            query = f"""
            SELECT main_closing_price
            FROM {self.DATABASE}.cis_equity_price_kudu
            WHERE security_label = {self.escape_value(security_label)}
              AND is_active = true
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('main_closing_price') is not None:
                return float(results[0]['main_closing_price'])

            # Fallback to security master price
            fallback_query = f"""
            SELECT price
            FROM {self.DATABASE}.cis_security_kudu
            WHERE security_name = {self.escape_value(security_label)}
            LIMIT 1
            """
            fallback_results = impala_manager.execute_query(fallback_query, database=self.DATABASE)
            if fallback_results and fallback_results[0].get('price') is not None:
                return float(fallback_results[0]['price'])

            return None
        except Exception as e:
            logger.error(f"Error fetching equity price for {security_label}: {str(e)}")
            return None

    def update_position_from_trade(self, trade: Dict[str, Any], updated_by: str) -> bool:
        """
        Create a new position version snapshot based on trade.
        Uses INSERT-only pattern - each trade creates a new version row.
        Implements full P&L calculations matching SA spreadsheet design.
        """
        try:
            portfolio = trade.get('portfolio_short_name', '')
            security = trade.get('security_label', '')
            trade_type = trade.get('trade_type', '')
            trade_qty = float(trade.get('quantity', 0))
            trade_price = float(trade.get('price', 0))
            trade_total_amt = float(trade.get('total_amount', 0) or (trade_qty * trade_price))
            trade_id = trade.get('trade_id')
            trade_date = trade.get('trade_date', datetime.now().strftime('%Y-%m-%d'))

            # Get latest position version for this portfolio+security
            current_position = self.get_position(portfolio, security)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Fetch current equity price for market value calculation
            equity_price = self._get_equity_price(security)

            # Generate new version_id (always)
            version_id = self.get_next_id('position_version_id')

            if trade_type in [self.TRADE_TYPE_BUY, self.TRADE_TYPE_ADD_LONG]:
                if current_position:
                    # Add to existing position - new version with updated values
                    position_id = current_position.get('position_id')
                    old_qty = float(current_position.get('quantity', 0))
                    old_avg_cost = float(current_position.get('average_cost', 0))
                    old_realized_pnl = float(current_position.get('realized_pnl', 0) or 0)

                    new_qty = old_qty + trade_qty
                    new_avg_cost = ((old_qty * old_avg_cost) + (trade_qty * trade_price)) / new_qty if new_qty > 0 else 0
                    new_total_cost = new_qty * new_avg_cost

                    current_price = equity_price if equity_price is not None else trade_price
                    market_value = new_qty * current_price
                    unrealized_pnl = market_value - new_total_cost

                    return self._insert_position_version(
                        version_id=version_id, position_id=position_id,
                        position_date=trade_date, portfolio=portfolio, security=security,
                        quantity=new_qty, average_cost=new_avg_cost, total_cost=new_total_cost,
                        realized_pnl=old_realized_pnl, current_price=current_price,
                        market_value=market_value, unrealized_pnl=unrealized_pnl,
                        trade_id=trade_id, trade_type=trade_type,
                        status='OPEN', is_active=True, created_by=updated_by
                    )
                else:
                    # New position - generate new position_id
                    position_id = self.get_next_id('position_id')
                    new_total_cost = trade_qty * trade_price

                    current_price = equity_price if equity_price is not None else trade_price
                    market_value = trade_qty * current_price
                    unrealized_pnl = market_value - new_total_cost

                    return self._insert_position_version(
                        version_id=version_id, position_id=position_id,
                        position_date=trade_date, portfolio=portfolio, security=security,
                        quantity=trade_qty, average_cost=trade_price, total_cost=new_total_cost,
                        realized_pnl=0, current_price=current_price,
                        market_value=market_value, unrealized_pnl=unrealized_pnl,
                        trade_id=trade_id, trade_type=trade_type,
                        status='OPEN', is_active=True, created_by=updated_by
                    )

            elif trade_type in [self.TRADE_TYPE_SELL, self.TRADE_TYPE_DELIVER_LONG]:
                if current_position:
                    position_id = current_position.get('position_id')
                    old_qty = float(current_position.get('quantity', 0))
                    old_avg_cost = float(current_position.get('average_cost', 0))
                    old_realized_pnl = float(current_position.get('realized_pnl', 0) or 0)

                    new_qty = old_qty - trade_qty

                    # Realized P&L calculation
                    sell_cost_basis = trade_qty * old_avg_cost
                    realized_pnl_this_trade = trade_total_amt - sell_cost_basis
                    cumulative_realized_pnl = old_realized_pnl + realized_pnl_this_trade

                    if new_qty <= 0:
                        # Close position
                        return self._insert_position_version(
                            version_id=version_id, position_id=position_id,
                            position_date=trade_date, portfolio=portfolio, security=security,
                            quantity=0, average_cost=0, total_cost=0,
                            realized_pnl=cumulative_realized_pnl, current_price=0,
                            market_value=0, unrealized_pnl=0,
                            trade_id=trade_id, trade_type=trade_type,
                            status='CLOSED', is_active=False, created_by=updated_by
                        )
                    else:
                        # Partial sell - avg_cost unchanged
                        new_total_cost = new_qty * old_avg_cost
                        current_price = equity_price if equity_price is not None else trade_price
                        market_value = new_qty * current_price
                        unrealized_pnl = market_value - new_total_cost

                        return self._insert_position_version(
                            version_id=version_id, position_id=position_id,
                            position_date=trade_date, portfolio=portfolio, security=security,
                            quantity=new_qty, average_cost=old_avg_cost, total_cost=new_total_cost,
                            realized_pnl=cumulative_realized_pnl, current_price=current_price,
                            market_value=market_value, unrealized_pnl=unrealized_pnl,
                            trade_id=trade_id, trade_type=trade_type,
                            status='OPEN', is_active=True, created_by=updated_by
                        )

            return True

        except Exception as e:
            logger.error(f"Error updating position from trade: {str(e)}")
            return False

    def _insert_position_version(
        self,
        version_id: int,
        position_id: int,
        position_date: str,
        portfolio: str,
        security: str,
        quantity: float,
        average_cost: float,
        total_cost: float,
        realized_pnl: float,
        current_price: float,
        market_value: float,
        unrealized_pnl: float,
        trade_id: int,
        trade_type: str,
        status: str,
        is_active: bool,
        created_by: str
    ) -> bool:
        """Insert a new position version row into cis_trade_position."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TRADE_POSITION_TABLE}
            (version_id, position_id, position_date, portfolio_short_name, security_label,
             quantity, average_cost, total_cost,
             realized_pnl, current_price, market_value, unrealized_pnl,
             trade_id, trade_type,
             status, is_active,
             created_by, created_at)
            VALUES (
                {version_id}, {position_id}, {self.escape_value(position_date)},
                {self.escape_value(portfolio)}, {self.escape_value(security)},
                {quantity}, {average_cost}, {total_cost},
                {realized_pnl}, {current_price}, {market_value}, {unrealized_pnl},
                {trade_id}, {self.escape_value(trade_type)},
                {self.escape_value(status)}, {str(is_active).lower()},
                {self.escape_value(created_by)}, '{timestamp}'
            )
            """
            return impala_manager.execute_write(query, database=self.DATABASE)
        except Exception as e:
            logger.error(f"Error inserting position version: {str(e)}")
            return False

    def refresh_market_values(self, portfolio_filter: Optional[str] = None) -> Dict[str, int]:
        """Refresh market values for all open positions by inserting new version snapshots."""
        counters = {'updated': 0, 'skipped': 0, 'errors': 0}
        try:
            positions = self.get_all_positions(status='OPEN')
            if portfolio_filter:
                positions = [p for p in positions if p.get('portfolio_short_name') == portfolio_filter]

            for position in positions:
                try:
                    security = position.get('security_label', '')
                    qty = float(position.get('quantity', 0) or 0)
                    total_cost = float(position.get('total_cost', 0) or 0)
                    position_id = position.get('position_id')
                    avg_cost = float(position.get('average_cost', 0) or 0)
                    old_realized_pnl = float(position.get('realized_pnl', 0) or 0)

                    if not qty or not total_cost:
                        counters['skipped'] += 1
                        continue

                    price = self._get_equity_price(security)
                    if price is None:
                        counters['skipped'] += 1
                        continue

                    market_value = qty * price
                    unrealized_pnl = market_value - total_cost

                    version_id = self.get_next_id('position_version_id')
                    success = self._insert_position_version(
                        version_id=version_id, position_id=position_id,
                        position_date=datetime.now().strftime('%Y-%m-%d'),
                        portfolio=position.get('portfolio_short_name', ''),
                        security=security,
                        quantity=qty, average_cost=avg_cost, total_cost=total_cost,
                        realized_pnl=old_realized_pnl, current_price=price,
                        market_value=market_value, unrealized_pnl=unrealized_pnl,
                        trade_id=position.get('trade_id', 0),
                        trade_type='MARKET_REFRESH',
                        status='OPEN', is_active=True,
                        created_by='SYSTEM'
                    )
                    if success:
                        counters['updated'] += 1
                    else:
                        counters['errors'] += 1

                except Exception as e:
                    logger.error(f"Error refreshing position {position.get('position_id')}: {str(e)}")
                    counters['errors'] += 1

            return counters
        except Exception as e:
            logger.error(f"Error in refresh_market_values: {str(e)}")
            return counters

    # =========================================================================
    # HISTORY (Async for performance - non-blocking)
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
        performed_by: str,
        async_write: bool = True
    ) -> bool:
        """
        Insert trade history record.

        Args:
            async_write: If True (default), write asynchronously for better performance.
                        Set to False for critical operations that need immediate confirmation.
        """
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

            if async_write:
                # Non-blocking write for history - improves response time
                impala_manager.execute_write_async(query, database=self.DATABASE)
                logger.debug(f"Queued async history write for trade {trade_id}")
                return True
            else:
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
