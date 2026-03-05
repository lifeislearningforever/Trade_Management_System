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
        sub_custodian: str = None
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

            # Get current position
            current = self._get_current_position(portfolio_id, security_id)

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
                    sub_custodian=sub_custodian
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
                    sub_custodian=sub_custodian
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
        sub_custodian: str = None
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
            old_avg_cost = Decimal(str(current.get('average_cost', 0) or 0))
            old_total_cost = old_qty * old_avg_cost
            old_realized_pnl = Decimal(str(current.get('realized_pnl', 0) or 0))
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

        # Build position data
        position_data = {
            'position_id': position_id,
            'portfolio_short_name': portfolio_id,
            'security_label': security_id,
            'quantity': float(new_qty),
            'average_cost': float(new_avg_cost),
            'total_cost': float(new_total_cost),
            'current_price': float(market_price),
            'market_value': float(market_value),
            'unrealized_pnl': float(unrealized_pnl),
            'realized_pnl': float(old_realized_pnl),
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
            'sub_custodian': sub_custodian
        }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # Also write to position_master external table
            self._sync_to_position_master(position_data, updated_by)
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
        sub_custodian: str = None
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
        old_avg_cost = Decimal(str(current.get('average_cost', 0) or 0))
        old_realized_pnl = Decimal(str(current.get('realized_pnl', 0) or 0))
        position_id = current.get('position_id')

        # Validate: no short selling
        if quantity > old_qty:
            return False, f"Insufficient quantity. Available: {old_qty}, Requested: {quantity}", None

        # Calculate realized P&L for this sale
        realized_pnl_this_trade = (price - old_avg_cost) * quantity
        new_realized_pnl = old_realized_pnl + realized_pnl_this_trade

        # Calculate new position
        new_qty = old_qty - quantity

        logger.info(
            f"SELL: Selling {quantity} @ {price} from position {position_id}. "
            f"Old: {old_qty} @ {old_avg_cost}, Realized P&L: {realized_pnl_this_trade}"
        )

        if new_qty <= 0:
            # Position fully closed
            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': 0,
                'average_cost': 0,
                'total_cost': 0,
                'current_price': 0,
                'market_value': 0,
                'unrealized_pnl': 0,
                'realized_pnl': float(new_realized_pnl),
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
                'sub_custodian': sub_custodian
            }
            logger.info(f"Position {position_id} fully closed. Total realized P&L: {new_realized_pnl}")
        else:
            # Partial sell - AVP unchanged
            new_total_cost = new_qty * old_avg_cost
            market_price_raw = self._get_market_price(security_id)
            market_price = Decimal(str(market_price_raw)) if market_price_raw else old_avg_cost
            market_value = new_qty * market_price
            unrealized_pnl = market_value - new_total_cost

            position_data = {
                'position_id': position_id,
                'portfolio_short_name': portfolio_id,
                'security_label': security_id,
                'quantity': float(new_qty),
                'average_cost': float(old_avg_cost),  # Unchanged
                'total_cost': float(new_total_cost),
                'current_price': float(market_price),
                'market_value': float(market_value),
                'unrealized_pnl': float(unrealized_pnl),
                'realized_pnl': float(new_realized_pnl),
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
                'sub_custodian': sub_custodian
            }

        # Save to cis_trade_position
        success = self._save_position(position_data, updated_by)

        if success:
            # Also write to position_master external table
            self._sync_to_position_master(position_data, updated_by)
            return True, "Position updated successfully", position_data
        else:
            return False, "Failed to save position", None

    # =========================================================================
    # POSITION DATA ACCESS
    # =========================================================================

    def _get_current_position(self, portfolio_id: str, security_id: str) -> Optional[Dict[str, Any]]:
        """Get current open position for portfolio-security combination."""
        try:
            query = f"""
            SELECT *
            FROM {self.DATABASE}.{self.POSITION_TABLE}
            WHERE portfolio_short_name = '{self._escape(portfolio_id)}'
              AND security_label = '{self._escape(security_id)}'
              AND status = 'OPEN'
              AND is_active = true
            ORDER BY version_id DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting current position: {str(e)}")
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
        """Get all positions with optional filters."""
        try:
            where_clauses = ["1=1"]  # Base condition

            if portfolio_id:
                where_clauses.append(f"portfolio_short_name = '{self._escape(portfolio_id)}'")

            if status:
                where_clauses.append(f"status = '{self._escape(status)}'")

            where_clause = " AND ".join(where_clauses)

            # Get latest version per position_id
            query = f"""
            SELECT p.*
            FROM {self.DATABASE}.{self.POSITION_TABLE} p
            INNER JOIN (
                SELECT position_id, MAX(version_id) as max_version
                FROM {self.DATABASE}.{self.POSITION_TABLE}
                WHERE {where_clause}
                GROUP BY position_id
            ) latest ON p.position_id = latest.position_id AND p.version_id = latest.max_version
            ORDER BY p.created_at DESC
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
        """Save position to cis_trade_position table (versioned)."""
        try:
            version_id = self._generate_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get FX rate for multi-currency calculations
            security_currency = position_data.get('security_currency', '')
            portfolio_currency = position_data.get('portfolio_currency', '')
            fx_rate_raw = self._get_fx_rate(security_currency, portfolio_currency) if security_currency and portfolio_currency else Decimal('1')
            # Convert to float for calculations (fx_rate returns Decimal)
            fx_rate = float(fx_rate_raw) if fx_rate_raw else 1.0

            # Calculate base currency values (portfolio currency)
            quantity = float(position_data.get('quantity', 0) or 0)
            average_cost = float(position_data.get('average_cost', 0) or 0)
            total_cost = float(position_data.get('total_cost', 0) or 0)
            realized_pnl = float(position_data.get('realized_pnl', 0) or 0)
            unrealized_pnl = float(position_data.get('unrealized_pnl', 0) or 0)
            market_value = float(position_data.get('market_value', 0) or 0)

            # Base currency calculations (divide by fx_rate to convert from local to base)
            if fx_rate and fx_rate != 0:
                average_cost_base = average_cost / fx_rate
                total_cost_base = total_cost / fx_rate
                realized_pnl_base = realized_pnl / fx_rate
                unrealized_pnl_base = unrealized_pnl / fx_rate
                market_value_base = market_value / fx_rate
            else:
                average_cost_base = average_cost
                total_cost_base = total_cost
                realized_pnl_base = realized_pnl
                unrealized_pnl_base = unrealized_pnl
                market_value_base = market_value

            # Match columns to cis_trade_position table structure (from user's environment)
            columns = [
                'version_id', 'position_id', 'position_date',
                'portfolio_short_name', 'security_label',
                'quantity', 'average_cost', 'total_cost',
                'current_price', 'market_value',
                'unrealized_pnl', 'realized_pnl',
                'trade_id', 'trade_type',
                'lots_held', 'custodian', 'sub_custodian',
                'security_currency', 'portfolio_currency', 'fx_rate',
                'average_cost_base', 'total_cost_base', 'realized_pnl_base',
                'unrealized_pnl_base', 'market_value_base',
                'status', 'is_active',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ]

            values = [
                str(version_id),
                str(position_data['position_id']),
                f"'{position_data.get('position_date', timestamp[:10])}'",
                f"'{self._escape(position_data['portfolio_short_name'])}'",
                f"'{self._escape(position_data['security_label'])}'",
                str(quantity),
                str(average_cost),
                str(total_cost),
                str(position_data.get('current_price', 0)),
                str(market_value),
                str(unrealized_pnl),
                str(realized_pnl),
                str(position_data.get('trade_id')) if position_data.get('trade_id') else 'NULL',
                f"'{position_data.get('trade_type', '')}'",
                str(position_data.get('lots_held', 0)) if position_data.get('lots_held') else 'NULL',
                f"'{self._escape(position_data.get('custodian', ''))}'" if position_data.get('custodian') else 'NULL',
                f"'{self._escape(position_data.get('sub_custodian', ''))}'" if position_data.get('sub_custodian') else 'NULL',
                f"'{self._escape(security_currency)}'" if security_currency else 'NULL',
                f"'{self._escape(portfolio_currency)}'" if portfolio_currency else 'NULL',
                str(fx_rate) if fx_rate else 'NULL',
                str(average_cost_base),
                str(total_cost_base),
                str(realized_pnl_base),
                str(unrealized_pnl_base),
                str(market_value_base),
                f"'{position_data.get('status', 'OPEN')}'",
                str(position_data.get('is_active', True)).lower(),
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
                logger.info(f"Saved position version {version_id} for position {position_data['position_id']}")
            return success

        except Exception as e:
            logger.error(f"Error saving position: {str(e)}")
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

    def _get_fx_rate(self, from_ccy: str, to_ccy: str) -> Decimal:
        """Get FX rate between currencies."""
        if from_ccy == to_ccy:
            return Decimal('1')

        try:
            fx_pair = f"{from_ccy}-{to_ccy}"
            query = f"""
            SELECT spot_rate_d
            FROM {self.DATABASE}.gmp_cis_sta_dly_fx_rates
            WHERE ref_quot_ccy = '{fx_pair}'
            ORDER BY `date` DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('spot_rate_d'):
                return Decimal(str(results[0]['spot_rate_d']))

            # Try reverse pair
            reverse_pair = f"{to_ccy}-{from_ccy}"
            query = f"""
            SELECT spot_rate_d
            FROM {self.DATABASE}.gmp_cis_sta_dly_fx_rates
            WHERE ref_quot_ccy = '{reverse_pair}'
            ORDER BY `date` DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('spot_rate_d'):
                rate = Decimal(str(results[0]['spot_rate_d']))
                return Decimal('1') / rate if rate != 0 else Decimal('1')

            return Decimal('1')
        except Exception as e:
            logger.error(f"Error fetching FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            return Decimal('1')

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
