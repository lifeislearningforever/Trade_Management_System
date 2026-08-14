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
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from .impala_connection import impala_manager, query_cache
from .trade_validation_repository import trade_validation_repository
from .config import settings

logger = logging.getLogger(__name__)


class TradeKuduRepository:
    """Repository for trade operations with Kudu via Impala"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_trade'
    HISTORY_TABLE = 'cis_trade_history'
    NOTE_TABLE = 'cis_trade_note'
    TRADE_POSITION_TABLE = 'cis_trade_position'
    EVENT_QUEUE_TABLE = 'cis_trade_event_queue'
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
    # PORTIARP-7610: cancellation of settled trades requires checker approval
    STATUS_PENDING_CANCELLATION = 'PENDING_CANCELLATION'

    # Status groups
    MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_VALIDATED, STATUS_SETTLED]
    # Checker acts on INITIAL/MODIFIED (pending validation) and VALIDATED (pending settlement)
    CHECKER_ACTIONABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_VALIDATED]

    @staticmethod
    def escape_value(val: Any) -> str:
        """Escape value for SQL query. Impala uses C-style \\' escaping, not doubled quotes."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            s = val.replace('\\', '\\\\').replace(chr(39), '\\' + chr(39))
            return f"'{s}'"
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
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate trade data before insert/update.
        Returns validation results along with fetched entity details for reuse.

        Args:
            trade_data: Trade data dictionary
            is_update: True if updating existing trade

        Returns:
            Tuple of (is_valid, list_of_errors, entity_details)
            entity_details contains 'portfolio' and 'security' dicts if validation passed
        """
        errors = []
        entity_details = {'portfolio': None, 'security': None}

        # Required fields
        if not trade_data.get('portfolio_short_name'):
            errors.append("Portfolio is required")

        if not trade_data.get('security_label'):
            errors.append("Security is required")

        if not trade_data.get('trade_type'):
            errors.append("Trade type is required")

        if not trade_data.get('trade_date'):
            errors.append("Trade date is required")

        if not trade_data.get('counterparty'):
            errors.append("Counterparty is required")

        # Validate references exist (including date validation)
        all_valid, validation_results = trade_validation_repository.validate_trade_references(
            portfolio_name=trade_data.get('portfolio_short_name', ''),
            security_name=trade_data.get('security_label', ''),
            counterparty_name=trade_data.get('counterparty', ''),
            trade_date=trade_data.get('trade_date', ''),
            settle_date=trade_data.get('settle_date', '')
        )

        if not all_valid:
            errors.extend(trade_validation_repository.get_validation_errors(validation_results))
        else:
            # Extract entity details from validation results for reuse
            # This avoids duplicate queries in insert_trade()
            for result in validation_results:
                if result.entity_type == 'PORTFOLIO' and result.is_valid and result.details:
                    entity_details['portfolio'] = result.details
                elif result.entity_type == 'SECURITY' and result.is_valid and result.details:
                    entity_details['security'] = result.details

        # Trade type specific validations
        trade_type = trade_data.get('trade_type', '')

        if trade_type in [self.TRADE_TYPE_BUY, self.TRADE_TYPE_SELL]:
            if not trade_data.get('quantity'):
                errors.append("Quantity is required for Buy/Sell trades")
            else:
                try:
                    qty = float(trade_data.get('quantity'))
                    if qty <= 0:
                        errors.append("Quantity must be greater than zero")
                except (ValueError, TypeError):
                    errors.append("Quantity must be a valid number")
            if not trade_data.get('price'):
                errors.append("Price is required for Buy/Sell trades")
            else:
                try:
                    price = float(trade_data.get('price'))
                    if price < 0:
                        errors.append("Price must not be negative")
                except (ValueError, TypeError):
                    errors.append("Price must be a valid number")

            if trade_data.get('open_fx_rate') not in (None, ''):
                try:
                    fx_rate = float(trade_data.get('open_fx_rate'))
                    if fx_rate <= 0:
                        errors.append("FX rate must be greater than zero")
                except (ValueError, TypeError):
                    errors.append("FX rate must be a valid number")
            else:
                # Cross-currency trades must supply an explicit FX rate — leaving it
                # blank silently defaults to 1.0 downstream and corrupts gross_amount_lc.
                security_ccy = (entity_details.get('security') or {}).get('currency_code')
                portfolio_ccy = (entity_details.get('portfolio') or {}).get('currency')
                if security_ccy and portfolio_ccy and security_ccy != portfolio_ccy:
                    errors.append(
                        "FX rate is required when security currency "
                        f"({security_ccy}) differs from portfolio currency ({portfolio_ccy})"
                    )

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

        return len(errors) == 0, errors, entity_details

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
        trade_date_to: Optional[str] = None,
        src_system: Optional[str] = None,
        settle_date_from: Optional[str] = None,
        settle_date_to: Optional[str] = None
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
            src_system: Source system filter (CIS or GMP) - per SA feedback #2
            settle_date_from: Settlement date start filter - per SA feedback #2
            settle_date_to: Settlement date end filter - per SA feedback #2

        Returns:
            List of trade dictionaries
        """
        import hashlib, json as _json
        # Cache simple single-filter queries (status/type only, no text search, no date range)
        # These are the common dashboard click-throughs — cache for 20s to survive the redirect
        _is_simple = (not search and not portfolios and not securities
                      and not trade_date_from and not trade_date_to
                      and not settle_date_from and not settle_date_to
                      and not src_system)
        if _is_simple:
            _ck = f"trade_list_v2:{status or ''}:{trade_type or ''}:{limit}"
            _cached = query_cache.get(_ck)
            if _cached is not None:
                logger.debug(f"[CACHE HIT] trade_list {_ck}")
                return _cached

        try:
            where_clauses = []

            if trade_type:
                where_clauses.append(f"t.trade_type = {self.escape_value(trade_type)}")

            if status:
                # Case-insensitive: get_trade_statistics() buckets rows by
                # status.upper() in Python, so a status value written with
                # different casing (e.g. 'Validated') still counts toward
                # pending_settlement there but was silently excluded here by
                # this literal, case-sensitive Impala string match.
                where_clauses.append(f"UPPER(t.status) = {self.escape_value(status.upper())}")

            # Source system filter (per SA feedback #2)
            if src_system:
                where_clauses.append(f"UPPER(t.src_system) = {self.escape_value(src_system.upper())}")

            # Multi-select portfolios with OR logic
            if portfolios and len(portfolios) > 0:
                portfolio_values = ", ".join([self.escape_value(p) for p in portfolios if p])
                if portfolio_values:
                    where_clauses.append(f"t.portfolio_short_name IN ({portfolio_values})")

            # Multi-select securities with OR logic
            if securities and len(securities) > 0:
                security_values = ", ".join([self.escape_value(s) for s in securities if s])
                if security_values:
                    where_clauses.append(f"t.security_label IN ({security_values})")

            if search:
                search_escaped = search.replace('\\', '\\\\').replace("'", "\\'")
                where_clauses.append(
                    f"(t.deal_number LIKE '%{search_escaped}%' OR "
                    f"t.security_label LIKE '%{search_escaped}%' OR "
                    f"t.portfolio_short_name LIKE '%{search_escaped}%')"
                )

            if trade_date_from:
                where_clauses.append(f"t.trade_date >= {self.escape_value(trade_date_from)}")

            if trade_date_to:
                where_clauses.append(f"t.trade_date <= {self.escape_value(trade_date_to)}")

            # Settlement date filters (per SA feedback #2)
            if settle_date_from:
                where_clauses.append(f"t.settle_date >= {self.escape_value(settle_date_from)}")

            if settle_date_to:
                where_clauses.append(f"t.settle_date <= {self.escape_value(settle_date_to)}")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
            SELECT
                t.trade_id, t.trade_type, t.deal_number,
                t.portfolio_short_name, t.portfolio_full_name,
                t.security_label, t.security_full_name, t.security_type,
                t.currency_code,
                t.trade_status, t.trade_date, t.settle_date, t.expiry_date,
                t.quantity, t.face_value, t.lot, t.price,
                t.commission, t.accrued_interest, t.sec_fee, t.other_charges, t.total_amount,
                t.total_amount_fc, t.total_amount_lc,
                t.gross_amount_fc, t.gross_amount_lc,
                t.open_close_position, t.extension, t.brokers, t.broker_name,
                t.gl_fund_type, t.gl_cost_centre, t.gl_account_code,
                t.contract_ref, t.fd_receipt, t.org_pur_date,
                t.open_fx_rate, t.curr_dealing, t.open_dealing,
                t.input_tax_oth, t.qty_entitled,
                t.selling_rule, t.cash_balance, t.custodian, t.amor_accr_method,
                t.lots_held, t.quantity_held,
                t.remarks,
                t.udf_fund_type, t.udf_section_31_26, t.udf_sub_custodian,
                t.udf_disclosure_req, t.udf_counter_pledged, t.udf_revision_code,
                t.udf_uobn_uobn_hk, t.udf_income_exp_type, t.udf_currency_hedge,
                t.realized_pnl, t.parent_trade_id, t.delivery_type, t.counterparty,
                t.reduction_type, t.reduction_amount, t.units_affected,
                t.income_type, t.ex_date, t.record_date, t.pay_date,
                t.amount_per_unit, t.gross_amount, t.withholding_tax, t.net_amount,
                t.split_type, t.split_ratio_new, t.split_ratio_old, t.effective_date,
                t.status, t.is_active, t.is_deleted, t.src_system,
                t.created_by, t.created_at, t.updated_by, t.updated_at,
                t.submitted_by, t.submitted_at,
                t.validated_by, t.validated_at, t.validation_comments,
                t.settled_by, t.settled_at, t.settlement_comments,
                t.cancelled_by, t.cancelled_at, t.cancel_reason,
                t.internal_ref, t.external_ref,
                t.charge_fee_type, t.charge_exchange, t.charge_country,
                t.charge_fee_rule, t.charge_fee_value,
                t.calculated_commission, t.calculated_clearing_fee,
                t.calculated_trading_fee, t.calculated_gst, t.calculated_other_fees,
                t.total_calculated_charges, t.charges_auto_calculated,
                COALESCE(p.currency, t.currency_code) AS portfolio_currency,
                COALESCE(p.description, '') AS portfolio_description,
                COALESCE(p.manager, '') AS portfolio_manager,
                COALESCE(p.portfolio_client, '') AS portfolio_client_name,
                s.security_id AS security_id,
                COALESCE(s.security_description, '') AS security_description
            FROM {self.DATABASE}.{self.TABLE_NAME} t
            LEFT JOIN {self.DATABASE}.cis_portfolio p ON t.portfolio_short_name = p.name AND (p.is_active = true OR p.is_active IS NULL)
            LEFT JOIN {self.DATABASE}.cis_security s ON t.security_label = s.security_name
            WHERE {where_clause}
            ORDER BY CASE WHEN UPPER(t.src_system) = 'CIS' THEN 0 ELSE 1 END,
                     t.created_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            out = results if results else []
            if _is_simple:
                query_cache.set(_ck, out, 20)  # 20s TTL — short enough to stay fresh
            return out

        except Exception as e:
            logger.error(f"Error retrieving trades with multi-filter: {str(e)}")
            return []

    def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """Get trade by ID with portfolio and security descriptions."""
        try:
            query = f"""
            SELECT
                t.trade_id, t.trade_type, t.deal_number,
                t.portfolio_short_name, t.portfolio_full_name,
                t.security_label, t.security_full_name, t.security_type,
                t.currency_code,
                t.trade_status, t.trade_date, t.settle_date, t.expiry_date,
                t.quantity, t.face_value, t.lot, t.price,
                t.commission, t.accrued_interest, t.sec_fee, t.other_charges, t.total_amount,
                t.total_amount_fc, t.total_amount_lc,
                t.gross_amount_fc, t.gross_amount_lc,
                t.open_close_position, t.extension, t.brokers, t.broker_name,
                t.gl_fund_type, t.gl_cost_centre, t.gl_account_code,
                t.contract_ref, t.fd_receipt, t.org_pur_date,
                t.open_fx_rate, t.curr_dealing, t.open_dealing,
                t.input_tax_oth, t.qty_entitled,
                t.selling_rule, t.cash_balance, t.custodian, t.amor_accr_method,
                t.lots_held, t.quantity_held,
                t.remarks,
                t.udf_fund_type, t.udf_section_31_26, t.udf_sub_custodian,
                t.udf_disclosure_req, t.udf_counter_pledged, t.udf_revision_code,
                t.udf_uobn_uobn_hk, t.udf_income_exp_type, t.udf_currency_hedge,
                t.realized_pnl, t.parent_trade_id, t.delivery_type, t.counterparty,
                t.reduction_type, t.reduction_amount, t.units_affected,
                t.income_type, t.ex_date, t.record_date, t.pay_date,
                t.amount_per_unit, t.gross_amount, t.withholding_tax, t.net_amount,
                t.split_type, t.split_ratio_new, t.split_ratio_old, t.effective_date,
                t.status, t.is_active, t.is_deleted, t.src_system,
                t.created_by, t.created_at, t.updated_by, t.updated_at,
                t.submitted_by, t.submitted_at,
                t.validated_by, t.validated_at, t.validation_comments,
                t.settled_by, t.settled_at, t.settlement_comments,
                t.cancelled_by, t.cancelled_at, t.cancel_reason,
                t.internal_ref, t.external_ref,
                t.charge_fee_type, t.charge_exchange, t.charge_country,
                t.charge_fee_rule, t.charge_fee_value,
                t.calculated_commission, t.calculated_clearing_fee,
                t.calculated_trading_fee, t.calculated_gst, t.calculated_other_fees,
                t.total_calculated_charges, t.charges_auto_calculated,
                COALESCE(p.currency, t.currency_code) AS portfolio_currency,
                COALESCE(p.description, '') AS portfolio_description,
                COALESCE(p.manager, '') AS portfolio_manager,
                COALESCE(p.portfolio_client, '') AS portfolio_client_name,
                s.security_id AS security_id,
                COALESCE(s.security_description, '') AS security_description
            FROM {self.DATABASE}.{self.TABLE_NAME} t
            LEFT JOIN {self.DATABASE}.cis_portfolio p ON t.portfolio_short_name = p.name AND (p.is_active = true OR p.is_active IS NULL)
            LEFT JOIN {self.DATABASE}.cis_security s ON t.security_label = s.security_name
            WHERE t.trade_id = {trade_id}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting trade by ID: {str(e)}")
            return None

    def get_trade_by_deal_number(self, deal_number: str) -> Optional[Dict[str, Any]]:
        """Get trade by deal number with portfolio and security descriptions."""
        try:
            query = f"""
            SELECT
                t.trade_id, t.trade_type, t.deal_number,
                t.portfolio_short_name, t.portfolio_full_name,
                t.security_label, t.security_full_name, t.security_type,
                t.currency_code,
                t.trade_status, t.trade_date, t.settle_date, t.expiry_date,
                t.quantity, t.face_value, t.lot, t.price,
                t.commission, t.accrued_interest, t.sec_fee, t.other_charges, t.total_amount,
                t.total_amount_fc, t.total_amount_lc,
                t.gross_amount_fc, t.gross_amount_lc,
                t.open_close_position, t.extension, t.brokers, t.broker_name,
                t.gl_fund_type, t.gl_cost_centre, t.gl_account_code,
                t.contract_ref, t.fd_receipt, t.org_pur_date,
                t.open_fx_rate, t.curr_dealing, t.open_dealing,
                t.input_tax_oth, t.qty_entitled,
                t.selling_rule, t.cash_balance, t.custodian, t.amor_accr_method,
                t.lots_held, t.quantity_held,
                t.remarks,
                t.udf_fund_type, t.udf_section_31_26, t.udf_sub_custodian,
                t.udf_disclosure_req, t.udf_counter_pledged, t.udf_revision_code,
                t.udf_uobn_uobn_hk, t.udf_income_exp_type, t.udf_currency_hedge,
                t.realized_pnl, t.parent_trade_id, t.delivery_type, t.counterparty,
                t.reduction_type, t.reduction_amount, t.units_affected,
                t.income_type, t.ex_date, t.record_date, t.pay_date,
                t.amount_per_unit, t.gross_amount, t.withholding_tax, t.net_amount,
                t.split_type, t.split_ratio_new, t.split_ratio_old, t.effective_date,
                t.status, t.is_active, t.is_deleted, t.src_system,
                t.created_by, t.created_at, t.updated_by, t.updated_at,
                t.submitted_by, t.submitted_at,
                t.validated_by, t.validated_at, t.validation_comments,
                t.settled_by, t.settled_at, t.settlement_comments,
                t.cancelled_by, t.cancelled_at, t.cancel_reason,
                t.internal_ref, t.external_ref,
                t.charge_fee_type, t.charge_exchange, t.charge_country,
                t.charge_fee_rule, t.charge_fee_value,
                t.calculated_commission, t.calculated_clearing_fee,
                t.calculated_trading_fee, t.calculated_gst, t.calculated_other_fees,
                t.total_calculated_charges, t.charges_auto_calculated,
                COALESCE(p.currency, t.currency_code) AS portfolio_currency,
                COALESCE(p.description, '') AS portfolio_description,
                COALESCE(p.manager, '') AS portfolio_manager,
                COALESCE(p.portfolio_client, '') AS portfolio_client_name,
                s.security_id AS security_id,
                COALESCE(s.security_description, '') AS security_description
            FROM {self.DATABASE}.{self.TABLE_NAME} t
            LEFT JOIN {self.DATABASE}.cis_portfolio p ON t.portfolio_short_name = p.name AND (p.is_active = true OR p.is_active IS NULL)
            LEFT JOIN {self.DATABASE}.cis_security s ON t.security_label = s.security_name
            WHERE t.deal_number = {self.escape_value(deal_number)}
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
            # Validate first - now returns entity details to avoid duplicate queries
            is_valid, errors, entity_details = self.validate_trade_data(trade_data)
            if not is_valid:
                logger.error(f"Trade validation failed: {errors}")
                raise ValueError("; ".join(errors))

            # Generate IDs
            trade_id = self.get_next_id('trade_id')
            deal_number = trade_data.get('deal_number') or f"DEAL-{datetime.now().strftime('%Y%m%d')}-{trade_id % 10000}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Use entity details from validation (avoids duplicate DB queries)
            # Fallback to re-query only if details not available (shouldn't happen)
            portfolio_details = entity_details.get('portfolio')
            security_details = entity_details.get('security')

            if not portfolio_details:
                logger.debug("Portfolio details not in cache, re-fetching")
                portfolio_details = trade_validation_repository.get_portfolio_details(
                    trade_data.get('portfolio_short_name', '')
                )
            if not security_details:
                logger.debug("Security details not in cache, re-fetching")
                security_details = trade_validation_repository.get_security_details(
                    trade_data.get('security_label', '')
                )

            # Build column and value lists
            columns = [
                'trade_id', 'trade_type', 'deal_number',
                'portfolio_short_name', 'portfolio_full_name',
                'security_label', 'security_full_name', 'security_type',
                'currency_code', 'portfolio_currency',
                'trade_status', 'trade_date', 'settle_date',
                'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee',
                'other_charges', 'total_amount',
                'total_amount_fc', 'total_amount_lc',
                'gross_amount_fc', 'gross_amount_lc',
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
                # Charge columns (matches cis_trade_charge_lut structure)
                'charge_fee_type', 'charge_exchange', 'charge_country',
                'charge_fee_rule', 'charge_fee_value',
                'calculated_commission', 'calculated_clearing_fee',
                'calculated_trading_fee', 'calculated_gst', 'calculated_other_fees',
                'total_calculated_charges', 'charges_auto_calculated',
                'status', 'is_active', 'is_deleted', 'src_system',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            # Get currency codes from master data:
            # - currency_code: Security's trading currency (Foreign Currency / FC)
            # - portfolio_currency: Portfolio's base currency (Local Currency / LC)
            security_currency = security_details.get('currency_code', '') if security_details else ''
            portfolio_currency = portfolio_details.get('currency', '') if portfolio_details else ''

            # Debug logging for currency assignment
            logger.debug(f"Portfolio details: {portfolio_details}")
            logger.debug(f"Security details: {security_details}")
            logger.debug(f"Portfolio currency from details: '{portfolio_currency}'")
            logger.debug(f"Security currency from details: '{security_currency}'")

            # Fallback to form input if master data is missing
            if not security_currency:
                security_currency = trade_data.get('currency_code', '')

            # Fallback for portfolio_currency - try to fetch directly if empty
            if not portfolio_currency and portfolio_details:
                # The currency might be stored with different key in different queries
                portfolio_currency = (
                    portfolio_details.get('currency') or
                    portfolio_details.get('currency_code') or
                    portfolio_details.get('base_currency') or
                    ''
                )
                logger.debug(f"Portfolio currency after fallback checks: '{portfolio_currency}'")

            # ALWAYS query portfolio currency directly - guarantees we get the value
            # This bypasses any caching or validation flow issues
            portfolio_name = trade_data.get('portfolio_short_name', '')
            if portfolio_name:
                try:
                    query = f"""
                    SELECT currency FROM {self.DATABASE}.cis_portfolio
                    WHERE name = '{portfolio_name.replace('\\', '\\\\').replace("'", "\\'")}'
                    LIMIT 1
                    """
                    logger.info(f"Querying portfolio currency for: {portfolio_name}")
                    results = impala_manager.execute_query(query, database=self.DATABASE)
                    logger.info(f"Portfolio currency query results: {results}")
                    if results:
                        db_currency = results[0].get('currency')
                        if db_currency:
                            portfolio_currency = db_currency
                            logger.info(f"Portfolio currency set to: {portfolio_currency}")
                        else:
                            logger.warning(f"Portfolio '{portfolio_name}' has NULL/empty currency in database")
                    else:
                        logger.warning(f"Portfolio '{portfolio_name}' not found in cis_portfolio")
                except Exception as e:
                    logger.error(f"Error fetching portfolio currency: {e}")

            values = [
                str(trade_id),
                self.escape_value(trade_data.get('trade_type')),
                self.escape_value(deal_number),
                self.escape_value(trade_data.get('portfolio_short_name')),
                self.escape_value(portfolio_details.get('name', '') if portfolio_details else ''),
                self.escape_value(trade_data.get('security_label')),
                self.escape_value(security_details.get('security_name', '') if security_details else ''),
                self.escape_value(security_details.get('security_type', '') if security_details else ''),
                self.escape_value(security_currency),  # Security currency (FC)
                self.escape_value(portfolio_currency),  # Portfolio currency (LC)
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
                self.to_decimal(trade_data.get('total_amount_fc'), 0),
                self.to_decimal(trade_data.get('total_amount_lc'), 0),
                self.to_decimal(trade_data.get('gross_amount_fc'), 0),
                self.to_decimal(trade_data.get('gross_amount_lc'), 0),
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
                # Charge values (matches cis_trade_charge_lut fee types)
                self.escape_value(trade_data.get('charge_fee_type', '')),
                self.escape_value(trade_data.get('charge_exchange', '')),
                self.escape_value(trade_data.get('charge_country', '')),
                self.escape_value(trade_data.get('charge_fee_rule', '')),
                self.to_decimal(trade_data.get('charge_fee_value'), 0),
                self.to_decimal(trade_data.get('calculated_commission'), 0),  # Brokerage Fee
                self.to_decimal(trade_data.get('calculated_clearing_fee'), 0),  # Clearing Fee
                self.to_decimal(trade_data.get('calculated_trading_fee'), 0),  # Trading Fee
                self.to_decimal(trade_data.get('calculated_gst'), 0),  # GST
                self.to_decimal(trade_data.get('calculated_other_fees'), 0),  # FFP/SGX SI FEE, etc.
                self.to_decimal(trade_data.get('total_calculated_charges'), 0),
                str(trade_data.get('charges_auto_calculated', False)).lower(),
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
                # Insert history record (synchronous for reliability)
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=deal_number,
                    action='CREATE',
                    old_status=None,
                    new_status=self.STATUS_INITIAL,
                    changes={},
                    comments='Trade created',
                    performed_by=created_by,
                    async_write=True  # Async write for fast UI response
                )
                logger.info(f"Created trade {trade_id} ({deal_number}) with INITIAL status")

                # Invalidate statistics cache (new trade changes counts)
                self.invalidate_statistics_cache()

                # Position calculation is queued at SETTLE action (trade_settle view),
                # not here at INITIAL creation. Queuing at creation is wrong because the
                # trade may still be rejected by the checker — we must only calculate
                # positions for fully approved (SETTLED) trades.
                logger.info(f"Trade {trade_id} created with INITIAL status — position queued at settle step")

                return trade_id

            return None

        except Exception as e:
            logger.error(f"Error inserting trade: {str(e)}")
            raise

    def insert_trade_fast(
        self,
        trade_data: Dict[str, Any],
        created_by: str,
        skip_validation: bool = False,
        entity_details: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Fast trade insert - only saves core trade data, queues everything else.

        This method is optimized for speed by:
        1. Optionally skipping validation (if already done in view)
        2. Reusing entity_details from prior validation (no duplicate queries)
        3. Only inserting the trade record (single DB write)
        4. Queuing history, audit, settlement, and AVP for async processing

        Args:
            trade_data: Trade data dictionary
            created_by: Username of creator
            skip_validation: If True, skip DB validation (use when already validated)
            entity_details: Pre-fetched entity details from validate_trade_data()
                           Contains 'portfolio' and 'security' dicts

        Returns trade_id if successful, None otherwise.
        """
        import time
        perf_start = time.time()
        try:
            portfolio_details = {}
            security_details = {}

            if not skip_validation:
                # Validate first - now returns entity details to avoid duplicate queries
                is_valid, errors, fetched_details = self.validate_trade_data(trade_data)
                if not is_valid:
                    logger.error(f"Trade validation failed: {errors}")
                    raise ValueError("; ".join(errors))
                portfolio_details = fetched_details.get('portfolio') or {}
                security_details = fetched_details.get('security') or {}
            elif entity_details:
                # Use pre-fetched entity details from view (FAST PATH - no DB queries)
                portfolio_details = entity_details.get('portfolio') or {}
                security_details = entity_details.get('security') or {}
            else:
                # Basic required field check only (no DB queries)
                errors = []
                if not trade_data.get('portfolio_short_name'):
                    errors.append("Portfolio is required")
                if not trade_data.get('security_label'):
                    errors.append("Security is required")
                if not trade_data.get('trade_type'):
                    errors.append("Trade type is required")
                if not trade_data.get('trade_date'):
                    errors.append("Trade date is required")
                if errors:
                    raise ValueError("; ".join(errors))

            # Generate IDs
            perf_id_start = time.time()
            trade_id = self.get_next_id('trade_id')
            logger.debug(f"[PERF] get_next_id took {(time.time() - perf_id_start)*1000:.0f}ms")
            deal_number = trade_data.get('deal_number') or f"DEAL-{datetime.now().strftime('%Y%m%d')}-{trade_id % 10000}"
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get portfolio currency from entity_details (already fetched during validation)
            # NO DUPLICATE DB QUERY - reuse validation results
            portfolio_currency = portfolio_details.get('currency', '')

            # Build column and value lists
            columns = [
                'trade_id', 'trade_type', 'deal_number',
                'portfolio_short_name', 'portfolio_full_name',
                'security_label', 'security_full_name', 'security_type',
                'currency_code', 'portfolio_currency',
                'trade_status', 'trade_date', 'settle_date',
                'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee',
                'other_charges', 'total_amount',
                'total_amount_fc', 'total_amount_lc',
                'gross_amount_fc', 'gross_amount_lc',
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
                'charge_fee_type', 'charge_exchange', 'charge_country',
                'charge_fee_rule', 'charge_fee_value',
                'calculated_commission', 'calculated_clearing_fee',
                'calculated_trading_fee', 'calculated_gst', 'calculated_other_fees',
                'total_calculated_charges', 'charges_auto_calculated',
                'status', 'is_active', 'is_deleted', 'src_system',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            values = [
                str(trade_id),
                self.escape_value(trade_data.get('trade_type')),
                self.escape_value(deal_number),
                self.escape_value(trade_data.get('portfolio_short_name')),
                self.escape_value(portfolio_details.get('name', '')),
                self.escape_value(trade_data.get('security_label')),
                self.escape_value(security_details.get('security_name', '')),
                self.escape_value(security_details.get('security_type', '')),
                self.escape_value(trade_data.get('currency_code', '')),
                self.escape_value(portfolio_currency),  # Portfolio currency (LC)
                self.escape_value(trade_data.get('trade_status', '')),
                self.escape_value(trade_data.get('trade_date')),
                self.escape_value(trade_data.get('settle_date', '')),
                self.to_decimal(trade_data.get('quantity'), 0),
                self.to_decimal(trade_data.get('face_value'), 0),
                self.to_decimal(trade_data.get('lot'), 0),
                self.to_decimal(trade_data.get('price'), 0),
                self.to_decimal(trade_data.get('commission'), 0),
                self.to_decimal(trade_data.get('accrued_interest'), 0),
                self.to_decimal(trade_data.get('sec_fee'), 0),
                self.to_decimal(trade_data.get('other_charges'), 0),
                self.to_decimal(trade_data.get('total_amount'), 0),
                self.to_decimal(trade_data.get('total_amount_fc'), 0),
                self.to_decimal(trade_data.get('total_amount_lc'), 0),
                self.to_decimal(trade_data.get('gross_amount_fc'), 0),
                self.to_decimal(trade_data.get('gross_amount_lc'), 0),
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
                self.escape_value(trade_data.get('charge_fee_type', '')),
                self.escape_value(trade_data.get('charge_exchange', '')),
                self.escape_value(trade_data.get('charge_country', '')),
                self.escape_value(trade_data.get('charge_fee_rule', '')),
                self.to_decimal(trade_data.get('charge_fee_value'), 0),
                self.to_decimal(trade_data.get('calculated_commission'), 0),
                self.to_decimal(trade_data.get('calculated_clearing_fee'), 0),
                self.to_decimal(trade_data.get('calculated_trading_fee'), 0),
                self.to_decimal(trade_data.get('calculated_gst'), 0),
                self.to_decimal(trade_data.get('calculated_other_fees'), 0),
                self.to_decimal(trade_data.get('total_calculated_charges'), 0),
                str(trade_data.get('charges_auto_calculated', False)).lower(),
                f"'{self.STATUS_INITIAL}'",
                'false',
                'false',
                "'CIS'",
                self.escape_value(created_by),
                f"'{timestamp}'",
                self.escape_value(created_by),
                f"'{timestamp}'"
            ]

            # Single UPSERT for trade - this is the only blocking operation
            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            perf_write_start = time.time()
            success = impala_manager.execute_write(query, database=self.DATABASE)
            logger.debug(f"[PERF] execute_write took {(time.time() - perf_write_start)*1000:.0f}ms")

            if success:
                logger.info(f"Created trade {trade_id} ({deal_number}) with INITIAL status (fast mode) in {(time.time() - perf_start)*1000:.0f}ms")

                # Invalidate statistics cache (new trade changes counts)
                self.invalidate_statistics_cache()

                # Queue all post-trade events asynchronously
                self._queue_trade_events(
                    trade_id=trade_id,
                    deal_number=deal_number,
                    trade_data=trade_data,
                    created_by=created_by,
                    portfolio_details=portfolio_details,
                    security_details=security_details
                )

                return trade_id, deal_number

            return None, None

        except Exception as e:
            logger.error(f"Error in fast trade insert: {str(e)}")
            raise

    def _queue_trade_events(
        self,
        trade_id: int,
        deal_number: str,
        trade_data: Dict[str, Any],
        created_by: str,
        portfolio_details: Dict[str, Any],
        security_details: Dict[str, Any]
    ) -> None:
        """
        Queue trade events for async processing (non-blocking).
        Events: HISTORY, SETTLEMENT (includes AVP)

        Note: Audit is handled separately via log_action_async in views.
        """
        try:
            timestamp = datetime.now()
            base_event_id = int(timestamp.timestamp() * 1000)

            # Prepare event data for settlement/AVP processing
            # Include ALL charges (manual + auto-calculated) for accurate AVP
            event_data = {
                'trade_id': trade_id,
                'deal_number': deal_number,
                'trade_type': trade_data.get('trade_type'),
                'portfolio_short_name': trade_data.get('portfolio_short_name'),
                'security_label': trade_data.get('security_label'),
                'quantity': str(trade_data.get('quantity', 0)),
                'price': str(trade_data.get('price', 0)),
                'trade_date': trade_data.get('trade_date'),
                'settle_date': trade_data.get('settle_date'),
                # Manual charges
                'commission': str(trade_data.get('commission', 0) or 0),
                'sec_fee': str(trade_data.get('sec_fee', 0) or 0),
                'other_charges': str(trade_data.get('other_charges', 0) or 0),
                # Auto-calculated charges (include ALL for accurate AVP)
                'calculated_commission': str(trade_data.get('calculated_commission', 0) or 0),
                'calculated_clearing_fee': str(trade_data.get('calculated_clearing_fee', 0) or 0),
                'calculated_trading_fee': str(trade_data.get('calculated_trading_fee', 0) or 0),
                'calculated_gst': str(trade_data.get('calculated_gst', 0) or 0),
                'calculated_other_fees': str(trade_data.get('calculated_other_fees', 0) or 0),
                'total_calculated_charges': str(trade_data.get('total_calculated_charges', 0) or 0),
                # Other fields
                'custodian': trade_data.get('custodian', ''),
                'sub_custodian': trade_data.get('udf_sub_custodian', ''),
                'security_currency': security_details.get('currency_code'),
                'portfolio_currency': portfolio_details.get('currency'),
                'isin': security_details.get('isin'),
                'security_name': security_details.get('security_name'),
                # LC/FC amounts for NON-REVAL portfolios (user-entered/computed values).
                # gross_amount_fc must be here too, not just gross_amount_lc -- without
                # it, the SETTLEMENT event worker's event_data.get('gross_amount_fc')
                # always reads None and cost_fc silently falls back to being
                # recomputed as quantity * price instead of using the trade's own
                # gross amount (SA feedback, Venkata Narayana Adisetty, 30/07/2026).
                'total_amount_lc': str(trade_data.get('total_amount_lc', '') or ''),
                'gross_amount_lc': str(trade_data.get('gross_amount_lc', '') or ''),
                'gross_amount_fc': str(trade_data.get('gross_amount_fc', '') or ''),
                # FX rate stored on the trade (user may have overridden the API rate)
                'open_fx_rate': str(trade_data.get('open_fx_rate', '') or ''),
            }

            # Queue HISTORY event
            history_query = f"""
            UPSERT INTO {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status, retry_count, created_by, created_at)
            VALUES (
                {base_event_id},
                {trade_id},
                {self.escape_value(deal_number)},
                'HISTORY',
                {self.escape_value(json.dumps({'action': 'CREATE', 'old_status': None, 'new_status': self.STATUS_INITIAL}))},
                'PENDING',
                0,
                {self.escape_value(created_by)},
                '{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'
            )
            """

            # Queue SETTLEMENT event (includes AVP calculation)
            settlement_query = f"""
            UPSERT INTO {self.DATABASE}.{self.EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status, retry_count, created_by, created_at)
            VALUES (
                {base_event_id + 1},
                {trade_id},
                {self.escape_value(deal_number)},
                'SETTLEMENT',
                {self.escape_value(json.dumps(event_data, default=str))},
                'PENDING',
                0,
                {self.escape_value(created_by)},
                '{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'
            )
            """

            # Execute both queue inserts asynchronously with retry callback
            def on_queue_failure(success: bool, event_type: str, tid: int):
                if not success:
                    logger.error(f"CRITICAL: Failed to queue {event_type} event for trade {tid}. "
                                 f"Manual intervention required - check cis_trade_event_queue.")
                    # TODO: Could also write to a dead-letter file or alert system

            impala_manager.execute_write_async(
                history_query,
                database=self.DATABASE,
                callback=lambda s: on_queue_failure(s, 'HISTORY', trade_id)
            )
            impala_manager.execute_write_async(
                settlement_query,
                database=self.DATABASE,
                callback=lambda s: on_queue_failure(s, 'SETTLEMENT', trade_id)
            )

            logger.debug(f"Queued HISTORY and SETTLEMENT events for trade {trade_id}")

        except Exception as e:
            # Log ERROR but don't fail - trade is already saved
            # This is a critical issue that needs manual intervention
            logger.error(f"CRITICAL: Failed to queue trade events for {trade_id}: {str(e)}. "
                         f"Trade saved but background processing will NOT occur. "
                         f"Manual requeue required.")

    def update_trade(self, trade_id: int, trade_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update trade data. Sets status to MODIFIED.
        """
        try:
            # Get current trade for history
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            # CIS trades can be edited in any status (no status restriction)
            current_status = current_trade.get('status', '')

            # Validate (entity_details not needed for update as we don't auto-populate)
            is_valid, errors, _ = self.validate_trade_data(trade_data, is_update=True)
            if not is_valid:
                raise ValueError("; ".join(errors))

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build SET clauses
            set_clauses = []
            changes = {}

            # Updatable fields - grouped by type
            string_fields = [
                'currency_code', 'trade_status', 'trade_date', 'settle_date',
                'open_close_position', 'extension', 'brokers', 'broker_name',
                'gl_fund_type', 'gl_cost_centre', 'gl_account_code',
                'contract_ref', 'fd_receipt', 'org_pur_date',
                'selling_rule', 'custodian', 'amor_accr_method',
                'remarks', 'counterparty',
                'udf_fund_type', 'udf_section_31_26', 'udf_sub_custodian',
                'udf_revision_code', 'udf_uobn_uobn_hk', 'udf_income_exp_type',
                # Charge string fields
                'charge_fee_type', 'charge_exchange', 'charge_country', 'charge_fee_rule'
            ]

            # Decimal fields - must NOT be quoted (decimal(20,6))
            decimal_fields = [
                'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee',
                'other_charges', 'total_amount',
                'total_amount_fc', 'total_amount_lc',  # FC and LC totals (includes charges)
                'gross_amount_fc', 'gross_amount_lc',  # FC and LC gross (qty × price, no charges)
                'open_fx_rate', 'curr_dealing', 'open_dealing',
                'input_tax_oth', 'qty_entitled', 'cash_balance',
                # Charge decimal fields (matches cis_trade_charge_lut fee types)
                'charge_fee_value', 'calculated_commission', 'calculated_clearing_fee',
                'calculated_trading_fee', 'calculated_gst', 'calculated_other_fees',
                'total_calculated_charges'
            ]

            # Boolean fields
            boolean_fields = ['udf_disclosure_req', 'udf_counter_pledged', 'udf_currency_hedge', 'charges_auto_calculated']

            updatable_fields = string_fields + decimal_fields + boolean_fields

            for field in updatable_fields:
                if field in trade_data:
                    new_value = trade_data[field]
                    old_value = current_trade.get(field)

                    if str(new_value) != str(old_value):
                        changes[field] = {'old': old_value, 'new': new_value}

                        if field in boolean_fields:
                            set_clauses.append(f"{field} = {str(new_value).lower()}")
                        elif field in decimal_fields:
                            # Decimal fields must NOT be quoted - use to_decimal for proper NULL/value handling
                            decimal_val = self.to_decimal(new_value, default=0)
                            set_clauses.append(f"{field} = {decimal_val}")
                        else:
                            # String fields - use escape_value (quoted)
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
                # Insert history record (async for fast UI response)
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='UPDATE',
                    old_status=current_status,
                    new_status=self.STATUS_MODIFIED,
                    changes=changes,
                    comments='Trade updated',
                    performed_by=updated_by,
                    async_write=True  # IMPORTANT: Async write for fast UI response
                )

                # Position recalculation is now handled by views.py via queue_position_modify_event
                logger.info(f"Updated trade {trade_id}, status set to MODIFIED")

            return success

        except Exception as e:
            logger.error(f"Error updating trade: {str(e)}")
            raise

    def _queue_position_recalculation(
        self,
        trade_id: int,
        current_trade: Dict[str, Any],
        updated_data: Dict[str, Any],
        updated_by: str
    ) -> None:
        """
        Queue position recalculation when trade qty/price changes.
        This handles the case where a trade is edited after creation.
        """
        try:
            from trade.services.settlement_service import settlement_service
            from decimal import Decimal

            # Use updated values, fall back to current trade values
            quantity = Decimal(str(updated_data.get('quantity', current_trade.get('quantity', 0)) or 0))
            price = Decimal(str(updated_data.get('price', current_trade.get('price', 0)) or 0))
            commission = Decimal(str(updated_data.get('commission', current_trade.get('commission', 0)) or 0))
            sec_fee = Decimal(str(updated_data.get('sec_fee', current_trade.get('sec_fee', 0)) or 0))
            other_charges = Decimal(str(updated_data.get('other_charges', current_trade.get('other_charges', 0)) or 0))
            charges = commission + sec_fee + other_charges

            settle_date = updated_data.get('settle_date') or current_trade.get('settle_date', '')
            trade_date = updated_data.get('trade_date') or current_trade.get('trade_date', '')

            _tlc = updated_data.get('total_amount_lc') or current_trade.get('total_amount_lc')
            _glc = updated_data.get('gross_amount_lc') or current_trade.get('gross_amount_lc')
            _gfc = updated_data.get('gross_amount_fc') or current_trade.get('gross_amount_fc')
            # Queue via settlement service (handles T+0, T+1/T+2, backdated)
            success, message, details = settlement_service.process_trade_settlement(
                trade_id=trade_id,
                portfolio_id=current_trade.get('portfolio_short_name', ''),
                security_id=current_trade.get('security_label', ''),
                trade_type=current_trade.get('trade_type', ''),
                quantity=quantity,
                price=price,
                charges=charges,
                settle_date=settle_date,
                trade_date=trade_date,
                updated_by=updated_by,
                security_currency=current_trade.get('currency_code', ''),
                portfolio_currency=current_trade.get('portfolio_currency', ''),
                isin=current_trade.get('isin', ''),
                security_name=current_trade.get('security_full_name', ''),
                trade_lc=Decimal(str(_tlc)) if _tlc else None,
                gross_amount_lc=Decimal(str(_glc)) if _glc else None,
                gross_amount_fc=Decimal(str(_gfc)) if _gfc else None,
            )

            if success:
                logger.info(f"Position recalculation queued for edited trade {trade_id}: {message}")
            else:
                logger.warning(f"Failed to queue position recalculation for trade {trade_id}: {message}")

        except Exception as e:
            # Log error but don't fail the trade update
            logger.error(f"Error queuing position recalculation for trade {trade_id}: {str(e)}")

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
                    performed_by=deleted_by,
                    async_write=True  # Async write for fast UI response
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
                    performed_by=submitted_by,
                    async_write=True  # Async write for fast UI response
                )
                logger.info(f"Trade {trade_id} submitted for validation")

            return success

        except Exception as e:
            logger.error(f"Error submitting trade: {str(e)}")
            raise

    def validate_trade(self, trade_id: int, validated_by: str, comments: str = '') -> bool:
        """Validate trade (INITIAL/MODIFIED -> VALIDATED). No submit step required."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                raise ValueError(f"Cannot validate trade with status '{current_status}'")

            # Four-eyes check — checker cannot be the same person who created the trade
            created_by = current_trade.get('created_by', '')
            if created_by and created_by == validated_by:
                raise ValueError("Four-eyes principle: You cannot validate your own trade")

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
                    performed_by=validated_by,
                    async_write=True  # Async write for fast UI response
                )
                logger.info(f"Trade {trade_id} validated")

            return success

        except Exception as e:
            logger.error(f"Error validating trade: {str(e)}")
            raise

    def reject_trade(self, trade_id: int, rejected_by: str, reason: str = '') -> bool:
        """Reject trade (INITIAL/MODIFIED -> CANCELLED)."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
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
                    performed_by=rejected_by,
                    async_write=True  # Async write for fast UI response
                )
                logger.info(f"Trade {trade_id} rejected")

            return success

        except Exception as e:
            logger.error(f"Error rejecting trade: {str(e)}")
            raise

    def cancel_trade(self, trade_id: int, cancelled_by: str, reason: str = '') -> bool:
        """Cancel a trade (status -> CANCELLED). Does not soft-delete the record;
        the trade remains visible in trade lists with status=CANCELLED."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_CANCELLED}',
                is_deleted = true,
                is_active = false,
                cancelled_by = {self.escape_value(cancelled_by)},
                cancelled_at = '{timestamp}',
                cancel_reason = {self.escape_value(reason)},
                updated_by = {self.escape_value(cancelled_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='CANCEL',
                    old_status=current_status,
                    new_status=self.STATUS_CANCELLED,
                    changes={},
                    comments=f'Trade cancelled. Reason: {reason}',
                    performed_by=cancelled_by,
                    async_write=True  # Async write for fast UI response
                )
                logger.info(f"Trade {trade_id} cancelled")

            return success

        except Exception as e:
            logger.error(f"Error cancelling trade: {str(e)}")
            raise

    def restore_trade(self, trade_id: int, restored_by: str) -> bool:
        """Restore a CANCELLED trade back to INITIAL so it can be re-validated."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            if current_trade.get('status') != self.STATUS_CANCELLED:
                raise ValueError(f"Only CANCELLED trades can be restored")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_INITIAL}',
                is_deleted = false,
                is_active = true,
                cancel_reason = NULL,
                cancelled_by = NULL,
                cancelled_at = NULL,
                updated_by = {self.escape_value(restored_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='RESTORE',
                    old_status=self.STATUS_CANCELLED,
                    new_status=self.STATUS_INITIAL,
                    changes={},
                    comments='Trade restored to Initial',
                    performed_by=restored_by,
                    async_write=True
                )
                logger.info(f"Trade {trade_id} restored to INITIAL by {restored_by}")

            return success

        except Exception as e:
            logger.error(f"Error restoring trade: {str(e)}")
            raise

    def submit_for_cancellation(self, trade_id: int, submitted_by: str, reason: str = '') -> bool:
        """Submit trade for cancellation approval.
        Sets status=MODIFIED + is_deleted=true immediately so the trade appears
        in the checker's Pending Validation queue. is_deleted=true signals the
        cancellation intent and excludes the trade from chain recalc right away.
        Checker approval finalises to CANCELLED; rejection restores is_deleted=false."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            current_status = current_trade.get('status', '')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_MODIFIED}',
                is_deleted = true,
                is_active = false,
                cancel_reason = {self.escape_value(reason)},
                cancelled_by = {self.escape_value(submitted_by)},
                cancelled_at = '{timestamp}',
                updated_by = {self.escape_value(submitted_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='CANCEL_REQUEST',
                    old_status=current_status,
                    new_status=self.STATUS_MODIFIED,
                    changes={},
                    comments=f'Cancellation requested. Reason: {reason}',
                    performed_by=submitted_by,
                    async_write=True
                )
                logger.info(f"Trade {trade_id} submitted for cancellation (status=MODIFIED, is_deleted=true)")

            return success

        except Exception as e:
            logger.error(f"Error submitting trade for cancellation: {str(e)}")
            raise

    def approve_cancellation(self, trade_id: int, approved_by: str, comments: str = '') -> bool:
        """Checker approves cancellation — finalises status to CANCELLED.
        is_deleted=true was already set by submit_for_cancellation and chain recalc
        already ran at that point, so no position work is needed here."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            if not (current_trade.get('status') == self.STATUS_MODIFIED
                    and current_trade.get('is_deleted') in (True, 'true', 1)):
                raise ValueError(f"Trade {trade_id} is not pending cancellation approval")

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = '{self.STATUS_CANCELLED}',
                updated_by = {self.escape_value(approved_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='CANCEL_APPROVE',
                    old_status=self.STATUS_MODIFIED,
                    new_status=self.STATUS_CANCELLED,
                    changes={},
                    comments=f'Cancellation approved. {comments}' if comments else 'Cancellation approved.',
                    performed_by=approved_by,
                    async_write=True
                )
                logger.info(f"Trade {trade_id} cancellation approved by {approved_by}")

            return success

        except Exception as e:
            logger.error(f"Error approving trade cancellation: {str(e)}")
            raise

    def reject_cancellation(self, trade_id: int, rejected_by: str, comments: str = '') -> str:
        """Checker rejects cancellation — restores is_deleted=false and reverts status
        to the pre-cancel value from trade history. Returns the reverted-to status."""
        try:
            current_trade = self.get_trade_by_id(trade_id)
            if not current_trade:
                raise ValueError(f"Trade {trade_id} not found")

            if not (current_trade.get('status') == self.STATUS_MODIFIED
                    and current_trade.get('is_deleted') in (True, 'true', 1)):
                raise ValueError(f"Trade {trade_id} is not pending cancellation approval")

            # Revert: if cancel_reason was set from a SETTLED trade, go back to SETTLED;
            # otherwise MODIFIED. We check trade history for the pre-cancel status.
            history = self.get_trade_history(trade_id)
            prev_status = self.STATUS_MODIFIED
            for h in history:
                action = str(h.get('action', '')).upper()
                if action == 'CANCEL_REQUEST':
                    prev_status = str(h.get('old_status', self.STATUS_MODIFIED))
                    break

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
            UPDATE {self.DATABASE}.{self.TABLE_NAME}
            SET status = {self.escape_value(prev_status)},
                is_deleted = false,
                is_active = true,
                cancel_reason = NULL,
                cancelled_by = NULL,
                cancelled_at = NULL,
                updated_by = {self.escape_value(rejected_by)},
                updated_at = '{timestamp}'
            WHERE trade_id = {trade_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                self.insert_trade_history(
                    trade_id=trade_id,
                    deal_number=current_trade.get('deal_number', ''),
                    action='CANCEL_REJECT',
                    old_status=self.STATUS_MODIFIED,
                    new_status=prev_status,
                    changes={},
                    comments=f'Cancellation rejected. {comments}' if comments else 'Cancellation rejected.',
                    performed_by=rejected_by,
                    async_write=True
                )
                logger.info(f"Trade {trade_id} cancellation rejected, reverted to {prev_status}")

            return prev_status

        except Exception as e:
            logger.error(f"Error rejecting trade cancellation: {str(e)}")
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
                    performed_by=settled_by,
                    async_write=True  # Async write for fast UI response
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
        """Fetch latest equity price for a security from cis_equity_price only."""
        try:
            query = f"""
            SELECT main_closing_price
            FROM {self.DATABASE}.cis_equity_price
            WHERE security_label = {self.escape_value(security_label)}
              AND is_active = true
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('main_closing_price') is not None:
                return float(results[0]['main_closing_price'])

            return None
        except Exception as e:
            logger.error(f"Error fetching equity price for {security_label}: {str(e)}")
            return None

    def _get_fx_rate(self, portfolio_ccy: str, security_ccy: str, rate_date: Optional[str] = None) -> Optional[float]:
        """
        Fetch FX rate from gmp_cis_sta_dly_fx_rates table.

        Args:
            portfolio_ccy: Portfolio currency (base currency, e.g., 'USD')
            security_ccy: Security currency (foreign currency, e.g., 'SGD')
            rate_date: Optional date in YYYYMMDD format

        Returns:
            FX rate or None if not found

        Note:
            FX pair format is {portfolio_ccy}-{security_ccy} (e.g., USD-SGD)
            If currencies are the same, returns 1.0
        """
        try:
            # Same currency - no conversion needed
            if portfolio_ccy == security_ccy:
                return 1.0

            # Build FX pair: portfolio_ccy-security_ccy
            fx_pair = f"{portfolio_ccy}-{security_ccy}"

            query = f"""
            SELECT spot_rate_d
            FROM {self.DATABASE}.gmp_cis_sta_dly_fx_rates
            WHERE ref_quot_ccy = {self.escape_value(fx_pair)}
            """

            if rate_date:
                query += f" AND `date` = {self.escape_value(rate_date)}"

            query += " ORDER BY `date` DESC LIMIT 1"

            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('spot_rate_d') is not None:
                return float(results[0]['spot_rate_d'])

            # Try reverse pair and invert
            reverse_pair = f"{security_ccy}-{portfolio_ccy}"
            query = f"""
            SELECT spot_rate_d
            FROM {self.DATABASE}.gmp_cis_sta_dly_fx_rates
            WHERE ref_quot_ccy = {self.escape_value(reverse_pair)}
            """

            if rate_date:
                query += f" AND `date` = {self.escape_value(rate_date)}"

            query += " ORDER BY `date` DESC LIMIT 1"

            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('spot_rate_d') is not None:
                rate = float(results[0]['spot_rate_d'])
                return 1.0 / rate if rate != 0 else None

            return None
        except Exception as e:
            logger.error(f"Error fetching FX rate for {portfolio_ccy}-{security_ccy}: {str(e)}")
            return None

    def _get_portfolio_currency(self, portfolio_short_name: str) -> Optional[str]:
        """Get base currency for a portfolio from cis_portfolio table."""
        try:
            query = f"""
            SELECT currency
            FROM {self.DATABASE}.cis_portfolio
            WHERE name = {self.escape_value(portfolio_short_name)}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('currency'):
                return results[0]['currency']
            return None
        except Exception as e:
            logger.error(f"Error getting portfolio currency for {portfolio_short_name}: {str(e)}")
            return None

    def _get_security_details(self, security_label: str) -> Optional[Dict[str, Any]]:
        """Get security details including currency, ISIN, country, asset_class, listing_status."""
        try:
            # Using cis_security table with correct column names
            query = f"""
            SELECT currency_code as security_currency, isin, country,
                   asset_class, listing_status
            FROM {self.DATABASE}.cis_security
            WHERE security_name = {self.escape_value(security_label)}
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return results[0]
            return None
        except Exception as e:
            logger.error(f"Error getting security details for {security_label}: {str(e)}")
            return None

    def update_position_from_trade(self, trade: Dict[str, Any], updated_by: str) -> bool:
        """
        Create a new position version snapshot based on trade.
        Uses INSERT-only pattern - each trade creates a new version row.
        Implements full P&L calculations with multi-currency support:
        - cost_value_local, market_value_local, unrealized_pnl_local (security currency)
        - cost_value_base, market_value_base, unrealized_pnl_base (portfolio currency)
        - FX rate looked up dynamically from gmp_cis_sta_dly_fx_rates
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
            valuation_date = trade_date

            # Get custodian from trade
            custodian = trade.get('custodian', '')
            sub_custodian = trade.get('udf_sub_custodian', '')

            # Get latest position version for this portfolio+security
            current_position = self.get_position(portfolio, security)

            # Fetch current equity price for market value calculation
            equity_price = self._get_equity_price(security)

            # Fetch multi-currency related data
            portfolio_ccy = self._get_portfolio_currency(portfolio)
            security_details = self._get_security_details(security)

            security_ccy = security_details.get('security_currency') if security_details else None
            isin = security_details.get('isin') if security_details else None
            country = security_details.get('country') if security_details else None
            asset_class = security_details.get('asset_class') if security_details else None
            listing_status = security_details.get('listing_status') if security_details else None

            # Get FX rate (portfolio_ccy to security_ccy)
            fx_rate = self._get_fx_rate(portfolio_ccy, security_ccy) if portfolio_ccy and security_ccy else 1.0
            if fx_rate is None:
                fx_rate = 1.0  # Default to 1 if no rate found

            # Generate new version_id (always)
            version_id = self.get_next_id('position_version_id')

            # Helper function to calculate multi-currency values
            def calc_multicurrency_values(qty, avg_cost, current_price):
                # Local values (security currency)
                cost_local = qty * avg_cost
                market_local = qty * current_price
                unrealized_local = market_local - cost_local

                # Base values (portfolio currency) - multiply by FX rate
                # If FX rate is USD-SGD = 1.33, and security is in SGD, portfolio is USD:
                # base_value = local_value / fx_rate (convert SGD to USD)
                if fx_rate and fx_rate != 0:
                    cost_base = cost_local / fx_rate
                    market_base = market_local / fx_rate
                    unrealized_base = unrealized_local / fx_rate
                else:
                    cost_base = cost_local
                    market_base = market_local
                    unrealized_base = unrealized_local

                return {
                    'cost_value_local': cost_local,
                    'market_value_local': market_local,
                    'unrealized_pnl_local': unrealized_local,
                    'cost_value_base': cost_base,
                    'market_value_base': market_base,
                    'unrealized_pnl_base': unrealized_base
                }

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

                    # Calculate multi-currency values
                    mc_vals = calc_multicurrency_values(new_qty, new_avg_cost, current_price)

                    return self._insert_position_version(
                        version_id=version_id, position_id=position_id,
                        position_date=trade_date, portfolio=portfolio, security=security,
                        quantity=new_qty, average_cost=new_avg_cost, total_cost=new_total_cost,
                        realized_pnl=old_realized_pnl, current_price=current_price,
                        market_value=market_value, unrealized_pnl=unrealized_pnl,
                        trade_id=trade_id, trade_type=trade_type,
                        status='OPEN', is_active=True, created_by=updated_by,
                        # Multi-currency fields
                        src_system='CIS',
                        security_currency=security_ccy,
                        portfolio_currency=portfolio_ccy,
                        fx_rate=fx_rate,
                        custodian=custodian,
                        sub_custodian=sub_custodian,
                        isin=isin,
                        country=country,
                        asset_class=asset_class,
                        listing_status=listing_status,
                        # Base currency values calculated in _insert_position_version
                        valuation_date=valuation_date,
                        market_unit_price=current_price
                    )
                else:
                    # New position - generate new position_id
                    position_id = self.get_next_id('position_id')
                    new_total_cost = trade_qty * trade_price

                    current_price = equity_price if equity_price is not None else trade_price
                    market_value = trade_qty * current_price
                    unrealized_pnl = market_value - new_total_cost

                    # Calculate multi-currency values
                    mc_vals = calc_multicurrency_values(trade_qty, trade_price, current_price)

                    return self._insert_position_version(
                        version_id=version_id, position_id=position_id,
                        position_date=trade_date, portfolio=portfolio, security=security,
                        quantity=trade_qty, average_cost=trade_price, total_cost=new_total_cost,
                        realized_pnl=0, current_price=current_price,
                        market_value=market_value, unrealized_pnl=unrealized_pnl,
                        trade_id=trade_id, trade_type=trade_type,
                        status='OPEN', is_active=True, created_by=updated_by,
                        # Multi-currency fields
                        src_system='CIS',
                        security_currency=security_ccy,
                        portfolio_currency=portfolio_ccy,
                        fx_rate=fx_rate,
                        custodian=custodian,
                        sub_custodian=sub_custodian,
                        isin=isin,
                        country=country,
                        asset_class=asset_class,
                        listing_status=listing_status,
                        # Base currency values calculated in _insert_position_version
                        valuation_date=valuation_date,
                        market_unit_price=current_price
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
                            status='CLOSED', is_active=False, created_by=updated_by,
                            # Multi-currency fields - zeroed for closed position
                            src_system='CIS',
                            security_currency=security_ccy,
                            portfolio_currency=portfolio_ccy,
                            fx_rate=fx_rate,
                            custodian=custodian,
                            sub_custodian=sub_custodian,
                            isin=isin,
                            country=country,
                            asset_class=asset_class,
                            listing_status=listing_status,
                            valuation_date=valuation_date,
                            market_unit_price=0
                        )
                    else:
                        # Partial sell - avg_cost unchanged
                        new_total_cost = new_qty * old_avg_cost
                        current_price = equity_price if equity_price is not None else trade_price
                        market_value = new_qty * current_price
                        unrealized_pnl = market_value - new_total_cost

                        # Calculate multi-currency values
                        mc_vals = calc_multicurrency_values(new_qty, old_avg_cost, current_price)

                        return self._insert_position_version(
                            version_id=version_id, position_id=position_id,
                            position_date=trade_date, portfolio=portfolio, security=security,
                            quantity=new_qty, average_cost=old_avg_cost, total_cost=new_total_cost,
                            realized_pnl=cumulative_realized_pnl, current_price=current_price,
                            market_value=market_value, unrealized_pnl=unrealized_pnl,
                            trade_id=trade_id, trade_type=trade_type,
                            status='OPEN', is_active=True, created_by=updated_by,
                            # Multi-currency fields
                            src_system='CIS',
                            security_currency=security_ccy,
                            portfolio_currency=portfolio_ccy,
                            fx_rate=fx_rate,
                            custodian=custodian,
                            sub_custodian=sub_custodian,
                            isin=isin,
                            country=country,
                            asset_class=asset_class,
                            listing_status=listing_status,
                            # Base currency values calculated in _insert_position_version
                            valuation_date=valuation_date,
                            market_unit_price=current_price
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
        created_by: str,
        # Multi-currency and additional fields
        src_system: Optional[str] = 'CIS',
        security_currency: Optional[str] = None,
        portfolio_currency: Optional[str] = None,
        fx_rate: Optional[float] = None,
        pct_ratio: Optional[float] = None,
        isin: Optional[str] = None,
        country: Optional[str] = None,
        asset_class: Optional[str] = None,
        listing_status: Optional[str] = None,
        custodian: Optional[str] = None,
        sub_custodian: Optional[str] = None,
        lots_held: Optional[int] = None,
        # Base currency values (portfolio currency)
        average_cost_base: Optional[float] = None,
        total_cost_base: Optional[float] = None,
        realized_pnl_base: Optional[float] = None,
        unrealized_pnl_base: Optional[float] = None,
        market_value_base: Optional[float] = None,
        # Legacy multi-currency field names
        cost_value_local: Optional[float] = None,
        cost_value_base: Optional[float] = None,
        market_value_local: Optional[float] = None,
        unrealized_pnl_local: Optional[float] = None,
        valuation_date: Optional[str] = None,
        market_unit_price: Optional[float] = None
    ) -> bool:
        """Insert a new position version row into cis_trade_position."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Calculate FX rate if not provided
            if fx_rate is None and security_currency and portfolio_currency:
                fx_rate = self._get_fx_rate(portfolio_currency, security_currency)
            if fx_rate is None:
                fx_rate = 1.0

            # Calculate base currency values if not provided
            if average_cost_base is None and fx_rate and fx_rate != 0:
                average_cost_base = average_cost / fx_rate
            if total_cost_base is None and fx_rate and fx_rate != 0:
                total_cost_base = total_cost / fx_rate
            if realized_pnl_base is None and fx_rate and fx_rate != 0:
                realized_pnl_base = realized_pnl / fx_rate
            if unrealized_pnl_base is None and fx_rate and fx_rate != 0:
                unrealized_pnl_base = unrealized_pnl / fx_rate
            if market_value_base is None and fx_rate and fx_rate != 0:
                market_value_base = market_value / fx_rate

            # Build column list - columns from cis_trade_position table (DDL: 13_avp_tables_kudu.sql)
            # Note: Table has average_cost_base, total_cost_base, realized_pnl_base
            #       but NOT unrealized_pnl_base or market_value_base
            columns = [
                'version_id', 'position_id', 'position_date',
                'portfolio_short_name', 'security_label',
                'quantity', 'average_cost', 'total_cost',
                'realized_pnl', 'current_price', 'market_value', 'unrealized_pnl',
                'trade_id', 'trade_type',
                'lots_held', 'custodian', 'sub_custodian',
                'security_currency', 'portfolio_currency', 'fx_rate',
                'average_cost_base', 'total_cost_base', 'realized_pnl_base',
                'status', 'is_active',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            # DECIMAL(30,8) in CAST avoids "Decimal expression overflow" for large LC values
            def cast_decimal(val):
                if val is None:
                    return 'NULL'
                return f"CAST({val} AS DECIMAL(30,8))"

            # Build values list
            values = [
                str(version_id),
                str(position_id),
                self.escape_value(position_date),
                self.escape_value(portfolio),
                self.escape_value(security),
                cast_decimal(quantity),
                cast_decimal(average_cost),
                cast_decimal(total_cost),
                cast_decimal(realized_pnl),
                cast_decimal(current_price),
                cast_decimal(market_value),
                cast_decimal(unrealized_pnl),
                str(trade_id) if trade_id else 'NULL',
                self.escape_value(trade_type),
                str(lots_held) if lots_held else 'NULL',
                self.escape_value(custodian) if custodian else 'NULL',
                self.escape_value(sub_custodian) if sub_custodian else 'NULL',
                self.escape_value(security_currency) if security_currency else 'NULL',
                self.escape_value(portfolio_currency) if portfolio_currency else 'NULL',
                cast_decimal(fx_rate) if fx_rate else 'NULL',
                cast_decimal(average_cost_base) if average_cost_base is not None else 'NULL',
                cast_decimal(total_cost_base) if total_cost_base is not None else 'NULL',
                cast_decimal(realized_pnl_base) if realized_pnl_base is not None else 'NULL',
                self.escape_value(status),
                str(is_active).lower(),
                self.escape_value(created_by),
                f"'{timestamp}'",
                self.escape_value(created_by),
                f"'{timestamp}'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TRADE_POSITION_TABLE}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
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
            # Use default=str to handle Decimal and other non-JSON-serializable types
            changes_json = json.dumps(changes, default=str).replace('\\', '\\\\').replace("'", "\\'") if changes else '{}'

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

    # Cache key and TTL for trade statistics
    STATS_CACHE_KEY = 'trade_statistics'
    STATS_CACHE_TTL = 30  # seconds - short TTL to keep stats fresh

    def get_trade_statistics(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get trade statistics for dashboard. Single query, cached 30s."""
        import time
        from datetime import date
        perf_start = time.time()

        if use_cache:
            cached = query_cache.get(self.STATS_CACHE_KEY)
            if cached is not None:
                logger.debug(f"[PERF] Trade statistics cache HIT - {(time.time() - perf_start)*1000:.0f}ms")
                return cached

        logger.debug("[PERF] Trade statistics cache MISS - querying DB")

        today = date.today().strftime('%Y-%m-%d')

        try:
            # Main query: non-deleted trades grouped by status + trade_type
            # gross_amount may be NULL on older/GMP trades; fall back to quantity*price
            query = f"""
            SELECT
                status,
                trade_type,
                COUNT(*) AS cnt,
                SUM(CASE WHEN trade_date = '{today}' THEN 1 ELSE 0 END) AS today_cnt,
                SUM(COALESCE(gross_amount, quantity * price, 0)) AS total_notional
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE is_deleted = false OR is_deleted IS NULL
            GROUP BY status, trade_type
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            # Separate count for pending-cancellation trades (MODIFIED + is_deleted=true + cancel_reason set)
            pending_cancel_query = f"""
            SELECT COUNT(*) AS cnt
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE is_deleted = true
              AND status = 'MODIFIED'
              AND cancel_reason IS NOT NULL
            """
            pc_rows = impala_manager.execute_query(pending_cancel_query, database=self.DATABASE)
            pending_cancel_count = int((pc_rows[0].get('cnt') or 0) if pc_rows else 0)

            stats = {
                'total_trades': 0,
                'pending_validation': 0,
                'pending_settlement': 0,
                'settled': 0,
                'cancelled': 0,
                'drafts': 0,
                'today_trades': 0,
                'buy_notional': 0.0,
                'sell_notional': 0.0,
                'status_breakdown': {},
                'type_breakdown': {},
            }

            if results:
                for row in results:
                    status = (row.get('status') or 'Unknown').upper()
                    trade_type = (row.get('trade_type') or 'Unknown').upper()
                    count = int(row.get('cnt') or 0)
                    today_cnt = int(row.get('today_cnt') or 0)
                    notional = float(row.get('total_notional') or 0)

                    stats['total_trades'] += count
                    stats['today_trades'] += today_cnt

                    # Status bucket
                    prev = stats['status_breakdown'].get(status, {'count': 0})
                    prev['count'] += count
                    stats['status_breakdown'][status] = prev

                    # Type bucket (notional per type across all statuses)
                    tb = stats['type_breakdown'].get(trade_type, {'count': 0, 'notional': 0.0})
                    tb['count'] += count
                    tb['notional'] += notional
                    stats['type_breakdown'][trade_type] = tb

                    if status in (self.STATUS_INITIAL, self.STATUS_MODIFIED):
                        stats['pending_validation'] += count
                    if status == self.STATUS_VALIDATED:
                        stats['pending_settlement'] += count
                    elif status == self.STATUS_SETTLED:
                        stats['settled'] += count
                    elif status == self.STATUS_CANCELLED:
                        stats['cancelled'] += count

                    if trade_type == 'BUY':
                        stats['buy_notional'] += notional
                    elif trade_type == 'SELL':
                        stats['sell_notional'] += notional

            # Add pending-cancellation trades (MODIFIED + is_deleted=true) to pending_validation count
            stats['pending_validation'] += pending_cancel_count

            # Convert to sorted lists for template/JSON consumption
            status_order = [
                self.STATUS_INITIAL, self.STATUS_MODIFIED,
                self.STATUS_VALIDATED, self.STATUS_SETTLED, self.STATUS_CANCELLED,
            ]
            stats['status_breakdown'] = [
                {'status': s, 'count': stats['status_breakdown'][s]['count']}
                for s in status_order if s in stats['status_breakdown']
            ] + [
                {'status': s, 'count': v['count']}
                for s, v in stats['status_breakdown'].items() if s not in status_order
            ]
            stats['type_breakdown'] = sorted(
                [{'trade_type': t, 'count': v['count'], 'notional': round(v['notional'], 2)}
                 for t, v in stats['type_breakdown'].items()],
                key=lambda x: x['count'], reverse=True
            )

            query_cache.set(self.STATS_CACHE_KEY, stats, self.STATS_CACHE_TTL)
            logger.debug(f"[PERF] Trade statistics loaded in {(time.time() - perf_start)*1000:.0f}ms")
            return stats

        except Exception as e:
            logger.error(f"Error getting trade statistics: {str(e)}")
            return {
                'total_trades': 0, 'pending_validation': 0, 'pending_settlement': 0,
                'settled': 0, 'cancelled': 0, 'drafts': 0, 'today_trades': 0,
                'buy_notional': 0.0, 'sell_notional': 0.0,
                'status_breakdown': [], 'type_breakdown': [],
            }

    def invalidate_statistics_cache(self) -> None:
        """Invalidate statistics + trade list caches. Call after trade create/update/delete."""
        query_cache.invalidate(self.STATS_CACHE_KEY)
        # Invalidate simple trade list caches so stale data isn't served after mutations
        for _status in ('', 'INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED', 'CANCELLED'):
            for _type in ('', 'BUY', 'SELL'):
                query_cache.invalidate(f"trade_list_v2:{_status}:{_type}:1000")
        logger.debug("Trade statistics + list caches invalidated")

    def get_pending_validation_trades(self, limit: int = 100, cis_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get trades pending checker validation.

        Includes:
        - INITIAL trades (newly booked, not yet validated)
        - MODIFIED trades with is_deleted=false (edited, not yet validated)
        - MODIFIED trades with is_deleted=true + cancel_reason set (pending cancellation approval)

        Args:
            limit: Maximum records to return
            cis_only: If True (default), only show CIS trades (UPPER(src_system) = 'CIS')

        Returns:
            List of trades pending validation
        """
        try:
            cis_clause = "AND UPPER(src_system) = 'CIS'" if cis_only else ""

            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE (
                (
                    (is_deleted = false OR is_deleted IS NULL)
                    AND status IN ('{self.STATUS_INITIAL}', '{self.STATUS_MODIFIED}')
                )
                OR
                (
                    is_deleted = true
                    AND status = '{self.STATUS_MODIFIED}'
                    AND cancel_reason IS NOT NULL
                )
            )
            {cis_clause}
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting pending validation trades: {str(e)}")
            return []

    def get_pending_settlement_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get validated trades pending settlement."""
        return self.get_all_trades(limit=limit, status=self.STATUS_VALIDATED)


# Singleton instance
trade_kudu_repository = TradeKuduRepository()
