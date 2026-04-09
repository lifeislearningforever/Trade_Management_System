"""
Position Service - AVP (Average Price Position) Calculator

Phase 1: Basic AVP with weighted average calculation.

Key Features:
- Weighted average price calculation for BUY/SELL trades
- 8 decimal precision for AVP calculations
- Output to position_master Hive external table with src_system='CIS'
- Position history tracking in cis_trade_position
- Multi-currency support (local/base)

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import uuid

from core.repositories.impala_connection import impala_manager
from trade.services.multicurrency_service import multicurrency_service

logger = logging.getLogger(__name__)


class PositionService:
    """
    Service for calculating positions using weighted average method.

    AVP Formula:
    - BUY:  new_avg_cost = (old_total_cost + trade_cost + charges) / new_quantity
    - SELL: avg_cost unchanged, realized P&L = (sell_price - avg_cost) * quantity
    """

    DATABASE = 'gmp_cis'
    POSITION_TABLE = 'cis_trade_position'  # Internal CIS position tracking
    POSITION_MASTER_TABLE = 'position_master'  # External Hive table (shared)
    AVP_PRECISION = Decimal('0.00000001')  # 8 decimal places

    # Trade types that affect position
    POSITION_AFFECTING_TYPES = ['BUY', 'SELL']

    def __init__(self):
        """Initialize the position service."""
        pass

    # =========================================================================
    # AVP CALCULATION
    # =========================================================================

    def calculate_position(
        self,
        portfolio_id: str,
        security_id: str,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        is_chain_recalc: bool = False,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADE_DATE'
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Calculate position using weighted average method.

        Args:
            portfolio_id: Portfolio short name
            security_id: Security label
            trade_type: BUY or SELL
            quantity: Trade quantity (positive)
            price: Trade price per unit
            charges: Total charges (commission + sec_fee + other_charges)
            position_date: Position date (YYYY-MM-DD)
            trade_id: Reference trade ID
            updated_by: User performing the update
            security_currency: Security currency code
            portfolio_currency: Portfolio base currency code
            isin: ISIN code
            security_name: Security full name

        Returns:
            Tuple of (success, message, position_data)
        """
        try:
            # Validate trade type
            if trade_type not in self.POSITION_AFFECTING_TYPES:
                return True, f"Trade type {trade_type} does not affect position", None

            # Convert to Decimal for precision
            qty = Decimal(str(quantity))
            prc = Decimal(str(price))
            chrg = Decimal(str(charges)) if charges else Decimal('0')

            # Validate inputs
            if qty <= 0:
                return False, "Quantity must be positive", None
            if prc <= 0:
                return False, "Price must be positive", None

            # Get the appropriate base position for calculation
            # For chain recalculation (backdated trades), we need position BEFORE this date
            # to avoid picking up the old position for the same date
            # For normal trades, we include same date positions
            if is_chain_recalc:
                # Chain recalc: get position strictly BEFORE this date, scoped to same basis
                current = self._get_position_as_of_date(
                    portfolio_id, security_id, position_date,
                    include_same_date=False, position_basis=position_basis
                )
                logger.info(
                    f"Chain recalc mode: Getting position BEFORE {position_date} for "
                    f"{portfolio_id}/{security_id} basis={position_basis}. Found: {current is not None}"
                )
            else:
                # Normal mode: include same date positions, scoped to same basis
                current = self._get_position_as_of_date(
                    portfolio_id, security_id, position_date, position_basis=position_basis
                )

            # If no position before this date, this is the first trade for this date range
            # (which is correct for backdated trades creating a new earliest position)

            if trade_type == 'BUY':
                return self._process_buy(
                    current=current,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    quantity=qty,
                    price=prc,
                    charges=chrg,
                    position_date=position_date,
                    trade_id=trade_id,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name,
                    custodian=custodian,
                    sub_custodian=sub_custodian,
                    uncall_fc=uncall_fc,
                    uncall_lc=uncall_lc,
                    pipeline_fc=pipeline_fc,
                    pipeline_lc=pipeline_lc,
                    position_type=position_type,
                    position_basis=position_basis
                )
            elif trade_type == 'SELL':
                return self._process_sell(
                    current=current,
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    quantity=qty,
                    price=prc,
                    position_date=position_date,
                    trade_id=trade_id,
                    updated_by=updated_by,
                    security_currency=security_currency,
                    portfolio_currency=portfolio_currency,
                    isin=isin,
                    security_name=security_name,
                    custodian=custodian,
                    sub_custodian=sub_custodian,
                    uncall_fc=uncall_fc,
                    uncall_lc=uncall_lc,
                    pipeline_fc=pipeline_fc,
                    pipeline_lc=pipeline_lc,
                    position_type=position_type,
                    position_basis=position_basis
                )

        except Exception as e:
            logger.error(f"Error calculating position: {str(e)}")
            return False, f"Position calculation error: {str(e)}", None

    def _process_buy(
        self,
        current: Optional[Dict[str, Any]],
        portfolio_id: str,
        security_id: str,
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADE_DATE'
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Process BUY trade - increase position, recalculate AVP.

        Formula:
            new_total_cost = old_total_cost + (buy_qty * buy_price) + charges
            new_quantity = old_quantity + buy_qty
            new_avg_cost = new_total_cost / new_quantity
        """
        if current:
            # Existing position - add to it
            old_qty = Decimal(str(current.get('quantity', 0) or 0))
            # Use new column name average_cost_fc (fallback to average_cost for backward compat)
            old_avg_cost = Decimal(str(current.get('average_cost_fc') or current.get('average_cost', 0) or 0))
            old_total_cost = old_qty * old_avg_cost
            # Use new column name realized_pnl_fc (fallback to realized_pnl for backward compat)
            old_realized_pnl = Decimal(str(current.get('realized_pnl_fc') or current.get('realized_pnl', 0) or 0))
            position_id = current.get('position_id')

            # Calculate new values
            trade_cost = (quantity * price) + charges
            new_qty = old_qty + quantity
            new_total_cost = old_total_cost + trade_cost
            new_avg_cost = (new_total_cost / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )

            logger.info(
                f"BUY: Adding {quantity} @ {price} to position {position_id}. "
                f"Old: {old_qty} @ {old_avg_cost}, New: {new_qty} @ {new_avg_cost}"
            )
        else:
            # New position
            position_id = self._generate_id()
            old_qty = Decimal('0')
            old_realized_pnl = Decimal('0')

            trade_cost = (quantity * price) + charges
            new_qty = quantity
            new_total_cost = trade_cost
            new_avg_cost = (new_total_cost / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )

            logger.info(
                f"BUY: Creating new position {position_id}. "
                f"Qty: {new_qty}, AVP: {new_avg_cost}"
            )

        # Fetch market price for unrealized P&L (convert to Decimal for consistency)
        market_price_raw = self._get_market_price(security_id)
        market_price = Decimal(str(market_price_raw)) if market_price_raw else price
        market_value = new_qty * market_price
        unrealized_pnl = market_value - new_total_cost

        # Calculate LC values for NON-REVALUED portfolios (historical cost basis)
        # Get current FX rate at trade time - this becomes the "historical" rate
        fx_rate = Decimal('1')
        if security_currency and portfolio_currency and security_currency != portfolio_currency:
            fx_rate = self._get_fx_rate(security_currency, portfolio_currency)

        # For NON-REVALUED: maintain weighted average LC cost
        # new_total_cost_lc = old_total_cost_lc + (trade_cost * fx_rate_at_trade_time)
        # new_avg_cost_lc = new_total_cost_lc / new_qty
        if current:
            old_total_cost_lc = Decimal(str(current.get('total_cost_lc', 0) or 0))
            if old_total_cost_lc == 0:
                # Fallback if no LC value stored - use FC * current FX
                old_total_cost_lc = Decimal(str(current.get('total_cost_fc') or current.get('total_cost', 0) or 0)) * fx_rate
            trade_cost_lc = trade_cost * fx_rate
            new_total_cost_lc = old_total_cost_lc + trade_cost_lc
            new_avg_cost_lc = (new_total_cost_lc / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )
            old_realized_pnl_lc = Decimal(str(current.get('realized_pnl_lc', 0) or 0))
        else:
            trade_cost_lc = trade_cost * fx_rate
            new_total_cost_lc = trade_cost_lc
            new_avg_cost_lc = (new_total_cost_lc / new_qty).quantize(
                self.AVP_PRECISION, rounding=ROUND_HALF_UP
            )
            old_realized_pnl_lc = Decimal('0')

        # Calculate market_value_lc using FX rate
        market_value_lc = market_value * fx_rate

        # Build position data
        # FC = Foreign Currency (Security Currency)
        # LC = Local Currency (Portfolio Currency)
        position_data = {
            'position_id': position_id,
            'portfolio_short_name': portfolio_id,
            'security_label': security_id,
            'quantity': float(new_qty),
            # Cost in FC (Foreign Currency = Security Currency)
            'average_cost_fc': float(new_avg_cost),
            'total_cost_fc': float(new_total_cost),
            # Cost in LC (Local Currency = Portfolio Currency)
            'average_cost_lc': float(new_avg_cost_lc),
            'total_cost_lc': float(new_total_cost_lc),
            # Market value
            'market_price': float(market_price),
            'market_value_fc': float(market_value),
            'market_value_lc': float(market_value_lc),
            # P&L
            'unrealized_pnl_fc': float(unrealized_pnl),
            'realized_pnl_fc': float(old_realized_pnl),
            'realized_pnl_lc': float(old_realized_pnl_lc),
            # Dividend tracking (initialized to 0 or carry forward)
            'dividend_fc': float(current.get('dividend_fc', 0) or 0) if current else 0,
            'dividend_lc': float(current.get('dividend_lc', 0) or 0) if current else 0,
            # Trade reference
            'trade_id': trade_id,
            'trade_type': 'BUY',
            'position_date': position_date,
            'status': 'OPEN',
            'is_active': True,
            'src_system': 'CIS',
            'security_currency': security_currency,
            'portfolio_currency': portfolio_currency,
            'isin': isin,
            'security_name': security_name,
            'custodian': custodian,
            'sub_custodian': sub_custodian,
            'uncall_fc': float(uncall_fc) if uncall_fc is not None else 0,
            'uncall_lc': float(uncall_lc) if uncall_lc is not None else 0,
            'pipeline_fc': float(pipeline_fc) if pipeline_fc is not None else 0,
            'pipeline_lc': float(pipeline_lc) if pipeline_lc is not None else 0,
            'position_type': position_type or 'LONG',
            'position_basis': position_basis
        }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # TODO: Enable position_master sync after table is created
            # Disabled: position_master table may not exist in all environments
            # self._sync_to_position_master(position_data, updated_by)
            return True, "Position updated successfully", position_data
        else:
            return False, "Failed to save position", None

    def _process_sell(
        self,
        current: Optional[Dict[str, Any]],
        portfolio_id: str,
        security_id: str,
        quantity: Decimal,
        price: Decimal,
        position_date: str,
        trade_id: int,
        updated_by: str,
        security_currency: str = None,
        portfolio_currency: str = None,
        isin: str = None,
        security_name: str = None,
        custodian: str = None,
        sub_custodian: str = None,
        uncall_fc: Decimal = None,
        uncall_lc: Decimal = None,
        pipeline_fc: Decimal = None,
        pipeline_lc: Decimal = None,
        position_type: str = None,
        position_basis: str = 'TRADE_DATE'
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Process SELL trade - decrease position, AVP unchanged.

        Formula:
            realized_pnl = (sell_price - avg_cost) * sell_qty
            new_quantity = old_quantity - sell_qty
            new_avg_cost = old_avg_cost (unchanged)
        """
        # Validate: cannot sell without position
        if not current:
            return False, f"No position found for {security_id} in portfolio {portfolio_id}", None

        old_qty = Decimal(str(current.get('quantity', 0) or 0))
        # Use new column name average_cost_fc (fallback to average_cost for backward compat)
        old_avg_cost = Decimal(str(current.get('average_cost_fc') or current.get('average_cost', 0) or 0))
        # Use new column name realized_pnl_fc (fallback to realized_pnl for backward compat)
        old_realized_pnl = Decimal(str(current.get('realized_pnl_fc') or current.get('realized_pnl', 0) or 0))
        position_id = current.get('position_id')

        # Validate: no short selling
        if quantity > old_qty:
            return False, f"Insufficient quantity. Available: {old_qty}, Requested: {quantity}", None

        # Calculate realized P&L for this sale
        realized_pnl_this_trade = (price - old_avg_cost) * quantity
        new_realized_pnl = old_realized_pnl + realized_pnl_this_trade

        # Calculate new position
        new_qty = old_qty - quantity

        # Get FX rate for LC calculations
        fx_rate = Decimal('1')
        if security_currency and portfolio_currency and security_currency != portfolio_currency:
            fx_rate = self._get_fx_rate(security_currency, portfolio_currency)

        # Get existing LC values from current position
        old_avg_cost_lc = Decimal(str(current.get('average_cost_lc', 0) or 0))
        old_total_cost_lc = Decimal(str(current.get('total_cost_lc', 0) or 0))
        old_realized_pnl_lc = Decimal(str(current.get('realized_pnl_lc', 0) or 0))

        # Fallback if no LC values stored
        if old_avg_cost_lc == 0 and old_avg_cost > 0:
            old_avg_cost_lc = old_avg_cost * fx_rate
            old_total_cost_lc = old_qty * old_avg_cost_lc

        # Calculate realized P&L in LC
        # For NON-REVALUED: use historical avg_cost_lc, current sell_price * fx_rate
        realized_pnl_this_trade_lc = (price * fx_rate - old_avg_cost_lc) * quantity
        new_realized_pnl_lc = old_realized_pnl_lc + realized_pnl_this_trade_lc

        logger.info(
            f"SELL: Selling {quantity} @ {price} from position {position_id}. "
            f"Old: {old_qty} @ {old_avg_cost}, Realized P&L: {realized_pnl_this_trade}, "
            f"Realized P&L LC: {realized_pnl_this_trade_lc}"
        )

        if new_qty <= 0:
            # Position fully closed
            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': 0,
                # Cost in FC
                'average_cost_fc': 0,
                'total_cost_fc': 0,
                # Cost in LC
                'average_cost_lc': 0,
                'total_cost_lc': 0,
                # Market value
                'market_price': 0,
                'market_value_fc': 0,
                'market_value_lc': 0,
                # P&L
                'unrealized_pnl_fc': 0,
                'realized_pnl_fc': float(new_realized_pnl),
                'realized_pnl_lc': float(new_realized_pnl_lc),
                # Dividend tracking - carry forward from current position
                'dividend_fc': float(current.get('dividend_fc', 0) or 0),
                'dividend_lc': float(current.get('dividend_lc', 0) or 0),
                # Trade reference
                'trade_id': trade_id,
                'trade_type': 'SELL',
                'position_date': position_date,
                'status': 'CLOSED',
                'is_active': False,
                'src_system': 'CIS',
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'custodian': custodian,
                'sub_custodian': sub_custodian,
                'uncall_fc': 0,
                'uncall_lc': 0,
                'pipeline_fc': 0,
                'pipeline_lc': 0,
                'position_type': position_type or 'LONG',
                'position_basis': position_basis
            }
            logger.info(f"Position {position_id} fully closed. Total realized P&L: {new_realized_pnl}, LC: {new_realized_pnl_lc}")
        else:
            # Partial sell - AVP unchanged
            new_total_cost = new_qty * old_avg_cost
            new_total_cost_lc = new_qty * old_avg_cost_lc  # LC cost unchanged per unit

            market_price_raw = self._get_market_price(security_id)
            market_price = Decimal(str(market_price_raw)) if market_price_raw else old_avg_cost
            market_value = new_qty * market_price
            market_value_lc = market_value * fx_rate  # Calculate market_value_lc
            unrealized_pnl = market_value - new_total_cost

            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': float(new_qty),
                # Cost in FC - unchanged for SELL
                'average_cost_fc': float(old_avg_cost),
                'total_cost_fc': float(new_total_cost),
                # Cost in LC - unchanged for SELL
                'average_cost_lc': float(old_avg_cost_lc),
                'total_cost_lc': float(new_total_cost_lc),
                # Market value
                'market_price': float(market_price),
                'market_value_fc': float(market_value),
                'market_value_lc': float(market_value_lc),
                # P&L
                'unrealized_pnl_fc': float(unrealized_pnl),
                'realized_pnl_fc': float(new_realized_pnl),
                'realized_pnl_lc': float(new_realized_pnl_lc),
                # Dividend tracking - carry forward from current position
                'dividend_fc': float(current.get('dividend_fc', 0) or 0),
                'dividend_lc': float(current.get('dividend_lc', 0) or 0),
                # Trade reference
                'trade_id': trade_id,
                'trade_type': 'SELL',
                'position_date': position_date,
                'status': 'OPEN',
                'is_active': True,
                'src_system': 'CIS',
                'security_currency': security_currency,
                'portfolio_currency': portfolio_currency,
                'isin': isin,
                'security_name': security_name,
                'custodian': custodian,
                'sub_custodian': sub_custodian,
                'uncall_fc': float(uncall_fc) if uncall_fc is not None else float(current.get('uncall_fc', 0) or 0),
                'uncall_lc': float(uncall_lc) if uncall_lc is not None else float(current.get('uncall_lc', 0) or 0),
                'pipeline_fc': float(pipeline_fc) if pipeline_fc is not None else float(current.get('pipeline_fc', 0) or 0),
                'pipeline_lc': float(pipeline_lc) if pipeline_lc is not None else float(current.get('pipeline_lc', 0) or 0),
                'position_type': position_type or current.get('position_type') or 'LONG',
                'position_basis': position_basis
            }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # TODO: Enable position_master sync after table is created
            # Disabled: position_master table may not exist in all environments
            # self._sync_to_position_master(position_data, updated_by)
            return True, "Position updated successfully", position_data
        else:
            return False, "Failed to save position", None

    # =========================================================================
    # POSITION DATA ACCESS
    # =========================================================================

    def _get_current_position(self, portfolio_id: str, security_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current open position for portfolio-security combination.

        Returns the latest version (is_latest=true) of the most recent position_date.
        """
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND status = 'OPEN'
              AND is_active = true
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting current position: {str(e)}")
            return None

    def _get_position_as_of_date(
        self,
        portfolio_id: str,
        security_id: str,
        as_of_date: str,
        include_same_date: bool = True,
        position_basis: str = 'TRADE_DATE'
    ) -> Optional[Dict[str, Any]]:
        """
        Get position as of a specific date, scoped to a specific position_basis.

        Critical for dual-position logic: TRADE_DATE and SETTLE_DATE positions are
        stored separately. Each basis chain must only look at its own prior positions
        to avoid cross-contamination of AVP calculations.

        Args:
            portfolio_id: Portfolio short name
            security_id: Security label
            as_of_date: Date to check (YYYY-MM-DD)
            include_same_date: If True, includes positions with position_date <= as_of_date
                              If False, only positions with position_date < as_of_date (for backdated)
            position_basis: 'TRADE_DATE' or 'SETTLE_DATE' — scope lookup to this basis only

        Returns the latest version (is_latest=true) with position_date <= or < as_of_date.
        """
        try:
            date_operator = '<=' if include_same_date else '<'

            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND position_date {date_operator} '{as_of_date}'
              AND position_basis = '{position_basis}'
              AND (is_latest = true OR is_latest IS NULL)
            ORDER BY position_date DESC, version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting position as of {as_of_date}: {str(e)}")
            return None

    def get_position(self, portfolio_id: str, security_id: str) -> Optional[Dict[str, Any]]:
        """Public method to get current position."""
        return self._get_current_position(portfolio_id, security_id)

    def get_all_positions(
        self,
        portfolio_id: str = None,
        status: str = 'OPEN',
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get all positions with optional filters.

        Only returns latest versions (is_latest=true) for each portfolio+security combination.
        """
        try:
            where_clauses = ["(is_latest = true OR is_latest IS NULL)"]

            if portfolio_id:
                where_clauses.append(f"portfolio_short_name = '{self._escape(portfolio_id)}'")

            if status:
                where_clauses.append(f"status = '{self._escape(status)}'")

            where_clause = " AND ".join(where_clauses)

            # Get latest version (is_latest=true) per portfolio+security, most recent date
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE {where_clause}
            ORDER BY position_date DESC, created_at DESC
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return []

    # =========================================================================
    # POSITION PERSISTENCE
    # =========================================================================

    def _save_position(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Save position to cis_trade_position table (versioned, immutable).

        Version-based approach:
        1. Mark any existing versions for same portfolio+security+position_date as is_latest=false
        2. Insert new version with is_latest=true
        3. Never delete - maintains full audit trail
        """
        try:
            version_id = self._generate_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            position_date = position_data.get('position_date', timestamp[:10])
            portfolio_id = position_data['portfolio_short_name']
            security_id = position_data['security_label']

            # Step 1: Mark existing versions for this date as is_latest=false
            # This is done via UPSERT with the same version_id but is_latest=false
            position_basis = position_data.get('position_basis', 'TRADE_DATE')
            self._mark_old_versions_not_latest(portfolio_id, security_id, position_date, position_basis)

            # Get FX rate for multi-currency calculations
            # Use strict=True for cross-currency positions to ensure accurate AVP
            security_currency = position_data.get('security_currency', '')
            portfolio_currency = position_data.get('portfolio_currency', '')
            is_cross_currency = security_currency and portfolio_currency and security_currency != portfolio_currency
            try:
                fx_rate_raw = self._get_fx_rate(
                    security_currency, portfolio_currency, strict=is_cross_currency
                ) if security_currency and portfolio_currency else Decimal('1')
            except ValueError as e:
                # Log error and use 1.0 as fallback, but mark position as needing FX review
                logger.error(f"FX rate lookup failed for position {portfolio_id}/{security_id}: {e}")
                fx_rate_raw = Decimal('1')
                # TODO: Could add a flag to position record indicating FX rate issue
            # Convert to float for calculations (fx_rate returns Decimal)
            fx_rate = float(fx_rate_raw) if fx_rate_raw else 1.0

            # Calculate LC (portfolio currency) values from FC (security currency) values
            # FC = Foreign Currency = Security Currency (where trade happens)
            # LC = Local Currency = Portfolio Currency (reporting currency)
            quantity = float(position_data.get('quantity', 0) or 0)
            # Use _fc suffixed fields (set by _process_buy/_process_sell), fallback to non-suffixed for backward compat
            average_cost = float(position_data.get('average_cost_fc') or position_data.get('average_cost', 0) or 0)
            total_cost = float(position_data.get('total_cost_fc') or position_data.get('total_cost', 0) or 0)
            realized_pnl = float(position_data.get('realized_pnl_fc') or position_data.get('realized_pnl', 0) or 0)
            unrealized_pnl = float(position_data.get('unrealized_pnl_fc') or position_data.get('unrealized_pnl', 0) or 0)
            market_value = float(position_data.get('market_value_fc') or position_data.get('market_value', 0) or 0)

            # Get portfolio revaluation status
            revaluation_status = self._get_portfolio_revaluation_status(portfolio_id)
            logger.debug(f"Portfolio {portfolio_id} revaluation_status: {revaluation_status}")

            # LC calculations based on revaluation_status
            # fx_rate = security_currency -> portfolio_currency (e.g., USD/SGD = 1.35)
            if revaluation_status == 'NON-REVALUED':
                # NON-REVALUED: Cost values use historical LC from trade (stored in position_data)
                # Market value uses current FX rate
                # If historical LC not available, fall back to current FX conversion
                average_cost_lc = float(position_data.get('average_cost_lc', 0) or 0)
                if average_cost_lc == 0 and average_cost > 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    average_cost_lc = average_cost * fx_rate
                    logger.warning(f"No historical average_cost_lc for {portfolio_id}/{security_id}, using current FX")

                total_cost_lc = float(position_data.get('total_cost_lc', 0) or 0)
                if total_cost_lc == 0 and total_cost > 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    total_cost_lc = total_cost * fx_rate
                    logger.warning(f"No historical total_cost_lc for {portfolio_id}/{security_id}, using current FX")

                realized_pnl_lc = float(position_data.get('realized_pnl_lc', 0) or 0)
                if realized_pnl_lc == 0 and realized_pnl != 0 and fx_rate:
                    # Fallback: use current FX if historical not available
                    realized_pnl_lc = realized_pnl * fx_rate
                    logger.warning(f"No historical realized_pnl_lc for {portfolio_id}/{security_id}, using current FX")

                # Market value LC always uses current FX rate (mark-to-market)
                market_value_lc = market_value * fx_rate if fx_rate else market_value

                # Unrealized P&L LC = market_value_lc - total_cost_lc
                unrealized_pnl_lc = market_value_lc - total_cost_lc

                logger.info(
                    f"NON-REVALUED position {portfolio_id}/{security_id}: "
                    f"cost_lc={total_cost_lc:.2f} (historical), "
                    f"market_lc={market_value_lc:.2f} (current FX), "
                    f"unrealized_lc={unrealized_pnl_lc:.2f}"
                )
            else:
                # REVALUED (default): All values use current FX rate (mark-to-market)
                if fx_rate and fx_rate != 0:
                    average_cost_lc = average_cost * fx_rate
                    total_cost_lc = total_cost * fx_rate
                    realized_pnl_lc = realized_pnl * fx_rate
                    market_value_lc = market_value * fx_rate
                    unrealized_pnl_lc = market_value_lc - total_cost_lc
                else:
                    average_cost_lc = average_cost
                    total_cost_lc = total_cost
                    realized_pnl_lc = realized_pnl
                    market_value_lc = market_value
                    unrealized_pnl_lc = unrealized_pnl

                logger.debug(
                    f"REVALUED position {portfolio_id}/{security_id}: "
                    f"all LC values use current FX rate {fx_rate}"
                )

            # Match columns to cis_trade_position table structure (DDL: 13_avp_tables_kudu.sql)
            # FC = Foreign Currency (Security Currency)
            # LC = Local Currency (Portfolio Currency)
            # Updated column names: average_cost_fc, total_cost_fc, average_cost_lc, total_cost_lc
            # Added: market_price, market_value_fc, dividend_fc, dividend_lc
            # Added: last_cash_flow_amount_fc, last_cash_flow_amount_lc
            columns = [
                'version_id', 'position_id', 'position_date',
                'portfolio_short_name', 'security_label',
                'quantity',
                # Cost in FC (Foreign Currency = Security Currency)
                'average_cost_fc', 'total_cost_fc',
                # Cost in LC (Local Currency = Portfolio Currency)
                'average_cost_lc', 'total_cost_lc',
                # P&L in FC
                'realized_pnl_fc', 'unrealized_pnl_fc',
                # P&L in LC
                'realized_pnl_lc', 'unrealized_pnl_lc',
                # Market value
                'market_price', 'market_value_fc', 'market_value_lc',
                # Dividend tracking
                'dividend_fc', 'dividend_lc',
                # Trade reference
                'trade_id', 'trade_type',
                'lots_held', 'custodian', 'sub_custodian',
                'security_currency', 'portfolio_currency', 'fx_rate',
                'status', 'is_active', 'is_latest',
                # Uncalled capital (PE/VC)
                'uncall_fc', 'uncall_lc',
                # Pipeline (pending trades/commitments)
                'pipeline_fc', 'pipeline_lc',
                # Position classification
                'position_type',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            # Helper to cast decimal values to DECIMAL(20,8) to avoid precision errors
            def cast_decimal(val):
                if val is None:
                    return 'NULL'
                return f"CAST({val} AS DECIMAL(20,8))"

            # Get values from position_data (already set with _fc and _lc suffixes)
            # Fall back to calculated local values for LC values if not in position_data
            average_cost_fc_val = float(position_data.get('average_cost_fc', 0) or 0)
            total_cost_fc_val = float(position_data.get('total_cost_fc', 0) or 0)
            realized_pnl_fc_val = float(position_data.get('realized_pnl_fc', 0) or 0)
            unrealized_pnl_fc_val = float(position_data.get('unrealized_pnl_fc', 0) or 0)
            market_price_val = float(position_data.get('market_price', 0) or 0)
            market_value_fc_val = float(position_data.get('market_value_fc', 0) or 0)
            dividend_fc_val = float(position_data.get('dividend_fc', 0) or 0)
            dividend_lc_val = float(position_data.get('dividend_lc', 0) or 0)

            # Use LC values from position_data if available, otherwise use calculated values
            average_cost_lc_val = float(position_data.get('average_cost_lc', 0) or 0) or average_cost_lc
            total_cost_lc_val = float(position_data.get('total_cost_lc', 0) or 0) or total_cost_lc

            values = [
                str(version_id),
                str(position_data['position_id']),
                f"'{position_date}'",
                f"'{self._escape(portfolio_id)}'",
                f"'{self._escape(security_id)}'",
                cast_decimal(quantity),
                # Cost in FC
                cast_decimal(average_cost_fc_val),
                cast_decimal(total_cost_fc_val),
                # Cost in LC
                cast_decimal(average_cost_lc_val),
                cast_decimal(total_cost_lc_val),
                # P&L in FC
                cast_decimal(realized_pnl_fc_val),
                cast_decimal(unrealized_pnl_fc_val),
                # P&L in LC
                cast_decimal(realized_pnl_lc),
                cast_decimal(unrealized_pnl_lc),
                # Market value
                cast_decimal(market_price_val),
                cast_decimal(market_value_fc_val),
                cast_decimal(market_value_lc),
                # Dividend tracking
                cast_decimal(dividend_fc_val),
                cast_decimal(dividend_lc_val),
                # Trade reference
                str(position_data.get('trade_id')) if position_data.get('trade_id') else 'NULL',
                f"'{position_data.get('trade_type', '')}'",
                str(position_data.get('lots_held', 0)) if position_data.get('lots_held') else 'NULL',
                f"'{self._escape(position_data.get('custodian', ''))}'" if position_data.get('custodian') else 'NULL',
                f"'{self._escape(position_data.get('sub_custodian', ''))}'" if position_data.get('sub_custodian') else 'NULL',
                f"'{self._escape(security_currency)}'" if security_currency else 'NULL',
                f"'{self._escape(portfolio_currency)}'" if portfolio_currency else 'NULL',
                cast_decimal(fx_rate) if fx_rate else 'NULL',
                f"'{position_data.get('status', 'OPEN')}'",
                str(position_data.get('is_active', True)).lower(),
                'true',  # is_latest = true for new version
                # Uncalled capital (PE/VC)
                cast_decimal(position_data.get('uncall_fc', 0) or 0),
                cast_decimal(position_data.get('uncall_lc', 0) or 0),
                # Pipeline (pending trades/commitments)
                cast_decimal(position_data.get('pipeline_fc', 0) or 0),
                cast_decimal(position_data.get('pipeline_lc', 0) or 0),
                # Position classification
                f"'{position_data.get('position_type', 'LONG')}'" if position_data.get('position_type') else "'LONG'",
                f"'{self._escape(updated_by)}'",
                f"'{timestamp}'",
                f"'{self._escape(updated_by)}'",
                f"'{timestamp}'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(
                    f"Saved position version {version_id} for position {position_data['position_id']} "
                    f"(date={position_date}, is_latest=true)"
                )

                # Sync to cis_position gold table
                # TODO: DUAL POSITION LOGIC — position_basis hardcoded 'TRADE_DATE' here is WRONG.
                # Once dual position logic is implemented, position_basis must come from
                # position_data (set by caller via calculate_position's position_basis param).
                # See trade_kudu_repository.py TODO for full implementation plan.
                sync_data = {
                    'position_id': position_data['position_id'],
                    'version_id': version_id,
                    'portfolio': portfolio_id,
                    'security_label': security_id,
                    'position_basis': position_data.get('position_basis', 'TRADE_DATE'),  # TODO: pass from caller
                    'position_date': position_date,
                    'src_system': 'CIS',
                    'processing_date': timestamp[:10].replace('-', ''),  # YYYYMMDD
                    'quantity': quantity,
                    'average_cost_fc': average_cost,
                    'cost_fc': total_cost,
                    'market_value_fc': market_value,
                    'net_book_value_fc': total_cost,  # cost - provision (no provision for now)
                    'unrealized_pnl_fc': unrealized_pnl,
                    'average_cost_lc': average_cost_lc,
                    'cost_lc': total_cost_lc,
                    'market_value_lc': market_value_lc,
                    'net_book_value_lc': total_cost_lc,
                    'unrealized_pnl_lc': unrealized_pnl_lc,
                    'provision_fc': 0,
                    'provision_lc': 0,
                    'dividend_fc': dividend_fc_val,
                    'dividend_lc': dividend_lc_val,
                    'realized_pnl_fc': realized_pnl,
                    'realized_pnl_lc': realized_pnl_lc,
                    'isin': position_data.get('isin', ''),
                }
                self._sync_to_cis_position(sync_data, updated_by)

            return success

        except Exception as e:
            logger.error(f"Error saving position: {str(e)}")
            return False

    def _sync_to_cis_position(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Sync CIS position to cis_position gold/master table.

        This is called whenever a position is saved to cis_trade_position with is_latest=true.
        The cis_position table is the consolidated view from all source systems.

        Schema from production (cis_position):
            position_id, version_id, portfolio, security_label, position_basis,
            position_date, src_system, processing_date, quantity, average_cost_fc,
            cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc,
            cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc,
            provision_fc, provision_lc, dividend_fc, dividend_lc,
            realized_pnl_fc, realized_pnl_lc, isin, average_cost_lc,
            placeholder_3, placeholder_4

        Args:
            position_data: Position data to sync
            updated_by: User performing the update

        Returns:
            True if sync successful, False otherwise
        """
        try:
            # cis_position table columns (matching actual production schema)
            # Note: average_cost renamed to average_cost_fc, placeholder_2 renamed to average_cost_lc
            columns = [
                'position_id', 'version_id', 'portfolio', 'security_label',
                'position_basis', 'position_date', 'src_system', 'processing_date',
                'quantity',
                'average_cost_fc',      # Avg cost in Security Currency (renamed from average_cost)
                'cost_fc',              # Total cost in Security Currency
                'market_value_fc',
                'net_book_value_fc',
                'unrealized_pnl_fc',
                'cost_lc',              # Total cost in Portfolio Currency
                'market_value_lc',
                'net_book_value_lc',
                'unrealized_pnl_lc',
                'provision_fc', 'provision_lc',
                'dividend_fc', 'dividend_lc',
                'realized_pnl_fc', 'realized_pnl_lc',
                'isin',
                'average_cost_lc',      # Avg cost in Portfolio Currency (renamed from placeholder_2)
                'placeholder_3', 'placeholder_4',
                'uncall_fc', 'uncall_lc',
                'pipeline_fc', 'pipeline_lc',
                'position_type'
            ]

            # Helper for decimal formatting — cis_position uses DECIMAL(18,4)
            def cast_decimal(val, precision=4):
                if val is None:
                    return 'CAST(0 AS DECIMAL(18,4))'
                try:
                    return f"CAST({float(val)} AS DECIMAL(18,{precision}))"
                except (ValueError, TypeError):
                    return 'CAST(0 AS DECIMAL(18,4))'

            values = [
                str(position_data.get('position_id', 0)),
                str(position_data.get('version_id', 0)),
                f"'{self._escape(position_data.get('portfolio', ''))}'",
                f"'{self._escape(position_data.get('security_label', ''))}'",
                f"'{position_data.get('position_basis', 'TRADE_DATE')}'",
                f"'{position_data.get('position_date', '')}'",
                "'CIS'",  # src_system - always CIS for CIS-generated positions
                f"'{position_data.get('processing_date', '')}'",
                cast_decimal(position_data.get('quantity', 0)),
                cast_decimal(position_data.get('average_cost_fc', 0)),
                cast_decimal(position_data.get('cost_fc', 0)),
                cast_decimal(position_data.get('market_value_fc', 0)),
                cast_decimal(position_data.get('net_book_value_fc', 0)),
                cast_decimal(position_data.get('unrealized_pnl_fc', 0)),
                cast_decimal(position_data.get('cost_lc', 0)),
                cast_decimal(position_data.get('market_value_lc', 0)),
                cast_decimal(position_data.get('net_book_value_lc', 0)),
                cast_decimal(position_data.get('unrealized_pnl_lc', 0)),
                cast_decimal(position_data.get('provision_fc', 0)),
                cast_decimal(position_data.get('provision_lc', 0)),
                cast_decimal(position_data.get('dividend_fc', 0)),
                cast_decimal(position_data.get('dividend_lc', 0)),
                cast_decimal(position_data.get('realized_pnl_fc', 0)),
                cast_decimal(position_data.get('realized_pnl_lc', 0)),
                f"'{self._escape(position_data.get('isin', ''))}'",
                cast_decimal(position_data.get('average_cost_lc', 0)),
                "''",  # placeholder_3
                "''",  # placeholder_4
                cast_decimal(position_data.get('uncall_fc', 0)),
                cast_decimal(position_data.get('uncall_lc', 0)),
                cast_decimal(position_data.get('pipeline_fc', 0)),
                cast_decimal(position_data.get('pipeline_lc', 0)),
                f"'{position_data.get('position_type', 'LONG')}'" if position_data.get('position_type') else "'LONG'"
            ]

            query = f"""
            UPSERT INTO {self.DATABASE}.cis_position
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(
                    f"Synced to cis_position: {position_data.get('portfolio')}/{position_data.get('security_label')}"
                )
            else:
                logger.warning(
                    f"Failed to sync to cis_position: {position_data.get('portfolio')}/{position_data.get('security_label')}"
                )

            return success

        except Exception as e:
            logger.error(f"Error syncing to cis_position: {str(e)}")
            # Don't fail the main operation if gold table sync fails
            return False

    def _mark_old_versions_not_latest(
        self,
        portfolio_id: str,
        security_id: str,
        position_date: str,
        position_basis: str = 'TRADE_DATE'
    ) -> bool:
        """
        Mark existing versions for a position_date+basis as is_latest=false.

        Scoped to position_basis so TRADE_DATE and SETTLE_DATE chains are
        independently versioned — recalculating one basis never stomps on the other.

        Note: Kudu doesn't support UPDATE with complex WHERE, so we need to:
        1. Query existing versions for this date+basis
        2. Re-insert each with is_latest=false
        """
        try:
            query = f"""
            SELECT version_id, position_id, position_date,
                   portfolio_short_name, security_label,
                   quantity, average_cost_fc, total_cost_fc,
                   average_cost_lc, total_cost_lc,
                   realized_pnl_fc, unrealized_pnl_fc,
                   realized_pnl_lc, unrealized_pnl_lc,
                   market_price, market_value_fc, market_value_lc,
                   dividend_fc, dividend_lc,
                   trade_id, trade_type,
                   lots_held, custodian, sub_custodian,
                   security_currency, portfolio_currency, fx_rate,
                   status, is_active,
                   created_by, created_at, updated_by, updated_at
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND position_date = '{position_date}'
              AND position_basis = '{position_basis}'
              AND is_latest = true
            """

            existing = impala_manager.execute_query(query, database=self.DATABASE)

            if not existing:
                # No existing versions to update
                return True

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for row in existing:
                # Re-insert with is_latest=false (UPSERT by version_id)
                # Using new column names
                update_query = f"""
                UPSERT INTO {self.DATABASE}.{self.POSITION_TABLE}
                (version_id, position_id, position_date, position_basis,
                 portfolio_short_name, security_label,
                 quantity, average_cost_fc, total_cost_fc,
                 average_cost_lc, total_cost_lc,
                 realized_pnl_fc, unrealized_pnl_fc,
                 realized_pnl_lc, unrealized_pnl_lc,
                 market_price, market_value_fc, market_value_lc,
                 dividend_fc, dividend_lc,
                 trade_id, trade_type,
                 lots_held, custodian, sub_custodian,
                 security_currency, portfolio_currency, fx_rate,
                 status, is_active, is_latest,
                 created_by, created_at, updated_by, updated_at)
                VALUES (
                    {row['version_id']}, {row['position_id']}, '{row['position_date']}',
                    '{position_basis}',
                    '{self._escape(row['portfolio_short_name'])}', '{self._escape(row['security_label'])}',
                    CAST({row.get('quantity') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('average_cost_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('total_cost_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('average_cost_lc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('total_cost_lc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('realized_pnl_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('unrealized_pnl_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('realized_pnl_lc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('unrealized_pnl_lc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('market_price') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('market_value_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('market_value_lc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('dividend_fc') or 0} AS DECIMAL(20,8)),
                    CAST({row.get('dividend_lc') or 0} AS DECIMAL(20,8)),
                    {row.get('trade_id') or 'NULL'},
                    '{row.get('trade_type', '')}',
                    {row.get('lots_held') or 'NULL'},
                    {f"'{self._escape(row.get('custodian', ''))}'" if row.get('custodian') else 'NULL'},
                    {f"'{self._escape(row.get('sub_custodian', ''))}'" if row.get('sub_custodian') else 'NULL'},
                    {f"'{self._escape(row.get('security_currency', ''))}'" if row.get('security_currency') else 'NULL'},
                    {f"'{self._escape(row.get('portfolio_currency', ''))}'" if row.get('portfolio_currency') else 'NULL'},
                    {f"CAST({row.get('fx_rate')} AS DECIMAL(20,8))" if row.get('fx_rate') else 'NULL'},
                    '{row.get('status', 'OPEN')}',
                    {str(row.get('is_active', True)).lower()},
                    false,
                    '{self._escape(row.get('created_by', ''))}',
                    '{row.get('created_at', timestamp)}',
                    'SYSTEM',
                    '{timestamp}'
                )
                """
                impala_manager.execute_write(update_query, database=self.DATABASE)
                logger.debug(f"Marked version {row['version_id']} as is_latest=false")

            logger.info(
                f"Marked {len(existing)} old version(s) as is_latest=false "
                f"for {portfolio_id}/{security_id} on {position_date}"
            )
            return True

        except Exception as e:
            logger.error(f"Error marking old versions: {str(e)}")
            return False

    def _sync_to_position_master(self, position_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Sync CIS position to position_master Hive external table.

        This writes the position to the shared position_master table with src_system='CIS'.
        The table is partitioned by (src_id, processing_date).
        """
        try:
            timestamp = datetime.now()
            processing_date = timestamp.strftime('%d%m%Y')  # DDMMYYYY format
            etl_batch_id = f"CIS-AVP-{timestamp.strftime('%Y%m%d%H%M%S')}"

            # Map CIS position fields to position_master schema
            columns = [
                'portfolio', 'security_full_name', 'security_short_name', 'isin',
                'quantity', 'market_price', 'average_cost',
                'cost_lc', 'market_value_lc', 'unrealized_pnl_lc',
                'product_type', 'security_type', 'security_currency',
                'reporting_date', 'position_basis',
                'src_system', 'source_table',
                'etl_insert_ts', 'etl_batch_id',
                'src_id', 'processing_date'
            ]

            # Build values
            portfolio = self._escape(position_data.get('portfolio_short_name', ''))
            security_label = self._escape(position_data.get('security_label', ''))
            security_name = self._escape(position_data.get('security_name', security_label))
            isin = self._escape(position_data.get('isin', ''))
            quantity = position_data.get('quantity', 0)
            market_price = position_data.get('current_price', 0)
            avg_cost = position_data.get('average_cost', 0)
            total_cost = position_data.get('total_cost', 0)
            market_value = position_data.get('market_value', 0)
            unrealized_pnl = position_data.get('unrealized_pnl', 0)
            security_currency = self._escape(position_data.get('security_currency', ''))
            position_date = position_data.get('position_date', timestamp.strftime('%Y-%m-%d'))

            values = [
                f"'{portfolio}'",
                f"'{security_name}'",
                f"'{security_label}'",
                f"'{isin}'" if isin else 'NULL',
                str(quantity),
                str(market_price),
                str(avg_cost),
                str(total_cost),  # cost_lc
                str(market_value),  # market_value_lc
                str(unrealized_pnl),  # unrealized_pnl_lc
                "'EQUITY'",  # product_type default
                "'COMMON STOCK'",  # security_type default
                f"'{security_currency}'" if security_currency else 'NULL',
                f"'{position_date}'",  # reporting_date
                "'trade_date'",  # position_basis
                "'CIS'",  # src_system
                "'cis_trade_position'",  # source_table
                f"'{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'",  # etl_insert_ts
                f"'{etl_batch_id}'",  # etl_batch_id
                "'CIS'",  # src_id (partition)
                f"'{processing_date}'"  # processing_date (partition)
            ]

            query = f"""
            INSERT INTO {self.DATABASE}.{self.POSITION_MASTER_TABLE}
            PARTITION (src_id='CIS', processing_date='{processing_date}')
            ({', '.join(columns[:-2])})
            VALUES ({', '.join(values[:-2])})
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)
            if success:
                logger.info(f"Synced position to position_master: {portfolio}/{security_label}")
            else:
                logger.warning(f"Failed to sync position to position_master: {portfolio}/{security_label}")

            return success

        except Exception as e:
            logger.error(f"Error syncing to position_master: {str(e)}")
            return False

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    def _get_market_price(self, security_label: str) -> Optional[float]:
        """Fetch latest market price for a security."""
        try:
            query = f"""
            SELECT main_closing_price
            FROM {self.DATABASE}.cis_equity_price
            WHERE security_label = '{self._escape(security_label)}'
              AND is_active = true
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('main_closing_price') is not None:
                return float(results[0]['main_closing_price'])
            return None
        except Exception as e:
            logger.error(f"Error fetching market price for {security_label}: {str(e)}")
            return None

    def _get_fx_rate(self, from_ccy: str, to_ccy: str, strict: bool = False) -> Decimal:
        """
        Get FX rate between currencies using multicurrency service.

        Args:
            from_ccy: Source currency code
            to_ccy: Target currency code
            strict: If True, raise error when rate not found (for AVP calculations)

        Returns:
            FX rate as Decimal

        Raises:
            ValueError: If strict=True and no rate is found
        """
        if from_ccy == to_ccy:
            return Decimal('1')

        if not from_ccy or not to_ccy:
            if strict:
                raise ValueError(f"Currency codes are required for FX rate lookup. "
                                f"Got from='{from_ccy}', to='{to_ccy}'")
            return Decimal('1')

        try:
            # Use multicurrency service with strict mode
            rate, _ = multicurrency_service.get_fx_rate(from_ccy, to_ccy, strict=strict)
            return rate
        except ValueError:
            # Re-raise ValueError from strict mode
            raise
        except Exception as e:
            logger.error(f"Error fetching FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            if strict:
                raise ValueError(f"Error fetching FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            return Decimal('1')

    def _get_portfolio_revaluation_status(self, portfolio_id: str) -> str:
        """
        Get portfolio revaluation status from cis_portfolio table.

        Args:
            portfolio_id: Portfolio short name

        Returns:
            'REVALUED' or 'NON-REVALUED' (defaults to 'REVALUED' if not found)
        """
        try:
            query = f"""
            SELECT revaluation_status
            FROM {self.DATABASE}.cis_portfolio
            WHERE name = '{self._escape(portfolio_id)}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('revaluation_status'):
                status = results[0]['revaluation_status'].upper()
                if status in ('REVALUED', 'NON-REVALUED'):
                    return status
            # Default to REVALUED if not found or invalid
            return 'REVALUED'
        except Exception as e:
            logger.error(f"Error fetching revaluation status for {portfolio_id}: {str(e)}")
            return 'REVALUED'  # Default to REVALUED on error

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate_trade_for_position(
        self,
        trade_type: str,
        quantity: Decimal,
        price: Decimal,
        portfolio_id: str,
        security_id: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate trade data before position calculation.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Rule 1: Only BUY/SELL affect position
        if trade_type not in self.POSITION_AFFECTING_TYPES:
            return True, []  # Skip validation, trade doesn't affect position

        # Rule 2: Quantity must be positive
        if quantity <= 0:
            errors.append("Trade quantity must be positive")

        # Rule 3: Price must be positive
        if price <= 0:
            errors.append("Trade price must be positive")

        # Rule 4: No short selling (SELL qty <= position qty)
        if trade_type == 'SELL':
            current_position = self._get_current_position(portfolio_id, security_id)
            available_qty = Decimal(str(current_position.get('quantity', 0) or 0)) if current_position else Decimal('0')
            if quantity > available_qty:
                errors.append(
                    f"Insufficient quantity for sale. Available: {available_qty}, Requested: {quantity}"
                )

        return len(errors) == 0, errors

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _generate_id(self) -> int:
        """Generate unique ID for position/version."""
        return int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def _escape(self, value: str) -> str:
        """Escape string value for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "''")


# Singleton instance
position_service = PositionService()
