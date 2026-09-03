"""
Multi-Currency Service - FX Rate Lookup and Currency Conversion

Phase 4: Multi-currency support with:
- FX rate lookup from gmp_cis_sta_dly_fx_rates
- Local (security) and Base (portfolio) currency calculations
- Combined P&L calculation
- Latest rate lookup (floating rate)

Based on SA Team Questionnaire Feedback (2026-03-04).
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date, timedelta
from functools import lru_cache

from core.repositories.impala_connection import impala_manager
from django.conf import settings

logger = logging.getLogger(__name__)


class MultiCurrencyService:
    """
    Service for multi-currency position calculations.

    Features:
    - FX rate lookup from daily FX rates table
    - Convert between security currency (local) and portfolio currency (base)
    - Calculate cost/market values in both currencies
    - Combined P&L (not separate FX P&L)
    """

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    FX_RATE_TABLE = 'gmp_cis_sta_dly_fx_rates'
    PORTFOLIO_TABLE = 'cis_portfolio'
    SECURITY_TABLE = 'cis_security'

    # Precision for FX calculations
    FX_PRECISION = Decimal('0.00000001')  # 8 decimals

    def __init__(self):
        """Initialize multi-currency service."""
        self._fx_cache = {}
        self._cache_ttl = 300  # 5 minutes cache

    # =========================================================================
    # FX RATE LOOKUP
    # =========================================================================

    def get_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: str = None,
        strict: bool = False
    ) -> Tuple[Decimal, str]:
        """
        Get FX rate between two currencies.

        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'SGD')
            rate_date: Optional date for historical rate (YYYY-MM-DD)
            strict: If True, raise error when rate not found instead of defaulting to 1.0

        Returns:
            Tuple of (rate, rate_date_used)

        Raises:
            ValueError: If strict=True and no rate is found
        """
        # Same currency - no conversion
        if from_currency == to_currency:
            return Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d')

        if not from_currency or not to_currency:
            if strict:
                raise ValueError(f"Currency codes are required. Got from='{from_currency}', to='{to_currency}'")
            return Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d')

        try:
            # Check cache first
            cache_key = f"{from_currency}-{to_currency}-{rate_date or 'latest'}"
            cached = self._get_cached_rate(cache_key)
            if cached:
                return cached

            # Try direct pair: FROM-TO
            rate, date_used = self._lookup_rate(from_currency, to_currency, rate_date)
            if rate:
                self._cache_rate(cache_key, (rate, date_used))
                return rate, date_used

            # Try reverse pair: TO-FROM and invert
            rate, date_used = self._lookup_rate(to_currency, from_currency, rate_date)
            if rate and rate != Decimal('0'):
                inverted = (Decimal('1') / rate).quantize(self.FX_PRECISION, rounding=ROUND_HALF_UP)
                self._cache_rate(cache_key, (inverted, date_used))
                return inverted, date_used

            # Try triangulation through USD
            if from_currency != 'USD' and to_currency != 'USD':
                rate_from_usd, _ = self._lookup_rate(from_currency, 'USD', rate_date)
                rate_to_usd, _ = self._lookup_rate('USD', to_currency, rate_date)

                if rate_from_usd and rate_to_usd:
                    triangulated = (rate_from_usd * rate_to_usd).quantize(
                        self.FX_PRECISION, rounding=ROUND_HALF_UP
                    )
                    self._cache_rate(cache_key, (triangulated, rate_date or datetime.now().strftime('%Y-%m-%d')))
                    return triangulated, rate_date or datetime.now().strftime('%Y-%m-%d')

            # Rate not found
            if strict:
                raise ValueError(
                    f"FX rate not found for {from_currency}->{to_currency}. "
                    f"Please ensure rate exists in FX rates table."
                )

            # Default to 1 if no rate found (legacy behavior for non-strict mode)
            logger.warning(f"No FX rate found for {from_currency}-{to_currency}, using 1.0")
            return Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d')

        except ValueError:
            # Re-raise ValueError (from strict mode)
            raise
        except Exception as e:
            logger.error(f"Error getting FX rate: {str(e)}")
            if strict:
                raise ValueError(f"Error fetching FX rate for {from_currency}->{to_currency}: {str(e)}")
            return Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d')

    def _lookup_rate(
        self,
        from_ccy: str,
        to_ccy: str,
        rate_date: str = None
    ) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Look up FX rate from database.

        The FX rate table uses ref_quot_ccy column with format FC-LC (e.g., USD-SGD).
        Uses spot_rate_d as the rate value, with `date` for date filtering.
        """
        try:
            fx_pair = f"{from_ccy}-{to_ccy}"

            if rate_date:
                # Convert rate_date from YYYY-MM-DD to YYYYMMDD if needed
                formatted_date = rate_date.replace('-', '') if '-' in rate_date else rate_date

                # Specific date - try exact match first
                query = f"""
                SELECT spot_rate_d, `date`
                FROM {self.DATABASE}.{self.FX_RATE_TABLE}
                WHERE ref_quot_ccy = '{fx_pair}'
                  AND `date` = '{formatted_date}'
                LIMIT 1
                """
                results = impala_manager.execute_query(query, database=self.DATABASE)

                # If no exact match, get closest earlier date
                if not results:
                    query = f"""
                    SELECT spot_rate_d, `date`
                    FROM {self.DATABASE}.{self.FX_RATE_TABLE}
                    WHERE ref_quot_ccy = '{fx_pair}'
                      AND `date` <= '{formatted_date}'
                    ORDER BY `date` DESC
                    LIMIT 1
                    """
                    results = impala_manager.execute_query(query, database=self.DATABASE)
            else:
                # Latest rate
                query = f"""
                SELECT spot_rate_d, `date`
                FROM {self.DATABASE}.{self.FX_RATE_TABLE}
                WHERE ref_quot_ccy = '{fx_pair}'
                ORDER BY `date` DESC
                LIMIT 1
                """
                results = impala_manager.execute_query(query, database=self.DATABASE)

            if results and results[0].get('spot_rate_d') is not None:
                rate = Decimal(str(results[0]['spot_rate_d']))
                date_used = results[0].get('date', rate_date)
                logger.info(f"[FX_LOOKUP] Found rate for {fx_pair}: {rate} on {date_used}")
                return rate, date_used

            logger.debug(f"[FX_LOOKUP] No rate found for {fx_pair}")
            return None, None

        except Exception as e:
            logger.error(f"Error looking up FX rate for {from_ccy}-{to_ccy}: {str(e)}")
            return None, None

    def get_latest_rates_for_currency(self, base_currency: str) -> List[Dict[str, Any]]:
        """Get all latest FX rates for a base currency."""
        try:
            # Use correct column names: ref_quot_ccy, spot_rate_d, date
            query = f"""
            SELECT ref_quot_ccy, spot_rate_d, `date`
            FROM {self.DATABASE}.{self.FX_RATE_TABLE}
            WHERE ref_quot_ccy LIKE '{base_currency}-%'
            ORDER BY `date` DESC
            LIMIT 100
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            # Deduplicate to get latest for each pair
            latest = {}
            for row in results or []:
                pair = row.get('ref_quot_ccy')
                if pair not in latest:
                    latest[pair] = {
                        'pair': pair,
                        'rate': float(row.get('spot_rate_d', 1)),
                        'date': row.get('date')
                    }

            return list(latest.values())

        except Exception as e:
            logger.error(f"Error getting rates for currency: {str(e)}")
            return []

    def get_fx_rates_batch(
        self,
        currency_pairs: List[Tuple[str, str]],
        rate_date: str = None
    ) -> Dict[str, Tuple[Decimal, str]]:
        """
        Batch fetch FX rates for multiple currency pairs in a single query.

        Performance optimization for trade list view.

        Args:
            currency_pairs: List of (from_currency, to_currency) tuples
            rate_date: Optional date for historical rates

        Returns:
            Dict mapping 'FROM-TO' to (rate, date_used)
        """
        if not currency_pairs:
            return {}

        results = {}
        pairs_to_fetch = []

        # Check cache first, collect pairs that need fetching
        for from_ccy, to_ccy in currency_pairs:
            if from_ccy == to_ccy:
                results[f"{from_ccy}-{to_ccy}"] = (Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d'))
                continue

            if not from_ccy or not to_ccy:
                results[f"{from_ccy}-{to_ccy}"] = (Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d'))
                continue

            cache_key = f"{from_ccy}-{to_ccy}-{rate_date or 'latest'}"
            cached = self._get_cached_rate(cache_key)
            if cached:
                results[f"{from_ccy}-{to_ccy}"] = cached
            else:
                pairs_to_fetch.append((from_ccy, to_ccy))

        if not pairs_to_fetch:
            return results

        try:
            # Build single query for all pairs (both directions)
            direct_pairs = [f"'{fc}-{tc}'" for fc, tc in pairs_to_fetch]
            reverse_pairs = [f"'{tc}-{fc}'" for fc, tc in pairs_to_fetch]
            all_pairs = direct_pairs + reverse_pairs

            if rate_date:
                formatted_date = rate_date.replace('-', '') if '-' in rate_date else rate_date
                query = f"""
                SELECT ref_quot_ccy, spot_rate_d, `date`
                FROM {self.DATABASE}.{self.FX_RATE_TABLE}
                WHERE ref_quot_ccy IN ({','.join(all_pairs)})
                  AND `date` <= '{formatted_date}'
                ORDER BY `date` DESC
                """
            else:
                query = f"""
                SELECT ref_quot_ccy, spot_rate_d, `date`
                FROM {self.DATABASE}.{self.FX_RATE_TABLE}
                WHERE ref_quot_ccy IN ({','.join(all_pairs)})
                ORDER BY `date` DESC
                """

            rows = impala_manager.execute_query(query, database=self.DATABASE)

            # Build lookup dict (latest rate per pair)
            rate_lookup = {}
            for row in rows or []:
                pair = row.get('ref_quot_ccy')
                if pair and pair not in rate_lookup:
                    rate_lookup[pair] = {
                        'rate': Decimal(str(row.get('spot_rate_d', 1))),
                        'date': row.get('date', rate_date)
                    }

            # Process each pair
            for from_ccy, to_ccy in pairs_to_fetch:
                direct_key = f"{from_ccy}-{to_ccy}"
                reverse_key = f"{to_ccy}-{from_ccy}"

                if direct_key in rate_lookup:
                    rate = rate_lookup[direct_key]['rate']
                    date_used = rate_lookup[direct_key]['date']
                    results[direct_key] = (rate, date_used)
                    cache_key = f"{from_ccy}-{to_ccy}-{rate_date or 'latest'}"
                    self._cache_rate(cache_key, (rate, date_used))
                elif reverse_key in rate_lookup:
                    reverse_rate = rate_lookup[reverse_key]['rate']
                    if reverse_rate and reverse_rate != Decimal('0'):
                        rate = (Decimal('1') / reverse_rate).quantize(self.FX_PRECISION, rounding=ROUND_HALF_UP)
                        date_used = rate_lookup[reverse_key]['date']
                        results[direct_key] = (rate, date_used)
                        cache_key = f"{from_ccy}-{to_ccy}-{rate_date or 'latest'}"
                        self._cache_rate(cache_key, (rate, date_used))
                    else:
                        results[direct_key] = (Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d'))
                else:
                    # No rate found - default to 1.0
                    results[direct_key] = (Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d'))
                    logger.warning(f"[FX_BATCH] No rate found for {direct_key}, using 1.0")

            logger.info(f"[FX_BATCH] Fetched {len(pairs_to_fetch)} pairs in single query, {len(results)} total results")

        except Exception as e:
            logger.error(f"Error in batch FX rate lookup: {str(e)}")
            # Fallback to 1.0 for any unfetched pairs
            for from_ccy, to_ccy in pairs_to_fetch:
                key = f"{from_ccy}-{to_ccy}"
                if key not in results:
                    results[key] = (Decimal('1'), rate_date or datetime.now().strftime('%Y-%m-%d'))

        return results

    # =========================================================================
    # CURRENCY CONVERSION
    # =========================================================================

    def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate_date: str = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Convert amount from one currency to another.

        Args:
            amount: Amount in source currency
            from_currency: Source currency
            to_currency: Target currency
            rate_date: Optional date for historical rate

        Returns:
            Tuple of (converted_amount, fx_rate_used)
        """
        if from_currency == to_currency:
            return amount, Decimal('1')

        fx_rate, _ = self.get_fx_rate(from_currency, to_currency, rate_date)
        converted = (amount * fx_rate).quantize(self.FX_PRECISION, rounding=ROUND_HALF_UP)

        return converted, fx_rate

    # =========================================================================
    # POSITION MULTI-CURRENCY CALCULATIONS
    # =========================================================================

    def calculate_position_values(
        self,
        quantity: Decimal,
        avg_cost_local: Decimal,
        current_price: Decimal,
        security_currency: str,
        portfolio_currency: str,
        rate_date: str = None
    ) -> Dict[str, Any]:
        """
        Calculate all position values in both local and base currency.

        Args:
            quantity: Position quantity
            avg_cost_local: Average cost in security currency
            current_price: Current market price in security currency
            security_currency: Security currency code
            portfolio_currency: Portfolio base currency code
            rate_date: Optional date for FX rate

        Returns:
            Dict with all calculated values
        """
        # Local currency calculations (security currency)
        cost_value_local = quantity * avg_cost_local
        market_value_local = quantity * current_price
        unrealized_pnl_local = market_value_local - cost_value_local

        # Get FX rate
        fx_rate, fx_date = self.get_fx_rate(security_currency, portfolio_currency, rate_date)

        # Base currency calculations (portfolio currency)
        cost_value_base = (cost_value_local * fx_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        market_value_base = (market_value_local * fx_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        unrealized_pnl_base = (unrealized_pnl_local * fx_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        # Average costs in base currency
        avg_cost_base = (avg_cost_local * fx_rate).quantize(
            self.FX_PRECISION, rounding=ROUND_HALF_UP
        )

        return {
            # Local currency (security)
            'cost_value_local': float(cost_value_local),
            'market_value_local': float(market_value_local),
            'unrealized_pnl_local': float(unrealized_pnl_local),
            'avg_cost_local': float(avg_cost_local),
            'security_currency': security_currency,

            # Base currency (portfolio)
            'cost_value_base': float(cost_value_base),
            'market_value_base': float(market_value_base),
            'unrealized_pnl_base': float(unrealized_pnl_base),
            'avg_cost_base': float(avg_cost_base),
            'portfolio_currency': portfolio_currency,

            # FX info
            'fx_rate': float(fx_rate),
            'fx_rate_date': fx_date
        }

    def calculate_realized_pnl_multicurrency(
        self,
        sell_quantity: Decimal,
        sell_price: Decimal,
        avg_cost: Decimal,
        security_currency: str,
        portfolio_currency: str,
        rate_date: str = None
    ) -> Dict[str, Any]:
        """
        Calculate realized P&L in both currencies.

        Combined P&L (per SA feedback) - not separate FX P&L.
        """
        # Local P&L
        realized_pnl_local = (sell_price - avg_cost) * sell_quantity

        # Get FX rate
        fx_rate, fx_date = self.get_fx_rate(security_currency, portfolio_currency, rate_date)

        # Base P&L (combined - includes FX impact)
        realized_pnl_base = (realized_pnl_local * fx_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        return {
            'realized_pnl_local': float(realized_pnl_local),
            'realized_pnl_base': float(realized_pnl_base),
            'security_currency': security_currency,
            'portfolio_currency': portfolio_currency,
            'fx_rate': float(fx_rate),
            'fx_rate_date': fx_date
        }

    # =========================================================================
    # CURRENCY METADATA
    # =========================================================================

    def get_portfolio_currency(self, portfolio_short_name: str) -> Optional[str]:
        """Get base currency for a portfolio."""
        try:
            query = f"""
            SELECT currency
            FROM {self.DATABASE}.{self.PORTFOLIO_TABLE}
            WHERE name = '{self._escape(portfolio_short_name)}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('currency'):
                return results[0]['currency']
            return None

        except Exception as e:
            logger.error(f"Error getting portfolio currency: {str(e)}")
            return None

    def get_security_currency(self, security_label: str) -> Optional[str]:
        """Get currency for a security."""
        try:
            query = f"""
            SELECT security_currency
            FROM {self.DATABASE}.{self.SECURITY_TABLE}
            WHERE security_label = '{self._escape(security_label)}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and results[0].get('security_currency'):
                return results[0]['security_currency']
            return None

        except Exception as e:
            logger.error(f"Error getting security currency: {str(e)}")
            return None

    def get_position_currencies(
        self,
        portfolio_short_name: str,
        security_label: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get both security and portfolio currencies."""
        security_ccy = self.get_security_currency(security_label)
        portfolio_ccy = self.get_portfolio_currency(portfolio_short_name)
        return security_ccy, portfolio_ccy

    # =========================================================================
    # MARKET VALUE REFRESH WITH FX
    # =========================================================================

    def refresh_position_values(
        self,
        position: Dict[str, Any],
        current_price: Decimal = None
    ) -> Dict[str, Any]:
        """
        Refresh position market values with latest FX rate.

        Args:
            position: Current position data
            current_price: Optional new market price (uses stored if not provided)

        Returns:
            Dict with updated values
        """
        quantity = Decimal(str(position.get('quantity', 0)))
        avg_cost = Decimal(str(position.get('average_cost', 0)))

        if current_price is None:
            current_price = Decimal(str(position.get('current_price', avg_cost)))

        security_ccy = position.get('security_currency', 'USD')
        portfolio_ccy = position.get('portfolio_currency', 'USD')

        return self.calculate_position_values(
            quantity=quantity,
            avg_cost_local=avg_cost,
            current_price=current_price,
            security_currency=security_ccy,
            portfolio_currency=portfolio_ccy
        )

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    def _get_cached_rate(self, cache_key: str) -> Optional[Tuple[Decimal, str]]:
        """Get rate from cache if still valid."""
        if cache_key in self._fx_cache:
            cached_at, rate_data = self._fx_cache[cache_key]
            if (datetime.now() - cached_at).total_seconds() < self._cache_ttl:
                return rate_data
            else:
                del self._fx_cache[cache_key]
        return None

    def _cache_rate(self, cache_key: str, rate_data: Tuple[Decimal, str]):
        """Cache FX rate."""
        self._fx_cache[cache_key] = (datetime.now(), rate_data)

    def clear_cache(self):
        """Clear FX rate cache."""
        self._fx_cache.clear()
        logger.info("FX rate cache cleared")

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _escape(self, value: str) -> str:
        """Escape string for SQL. Impala uses C-style \\' escaping, not doubled quotes."""
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")


# Singleton instance
multicurrency_service = MultiCurrencyService()
