"""
FX Rate Service
Business logic for FX rate operations following SOLID principles.

SOLID Principles Applied:
- Single Responsibility: Each method has one clear purpose
- Open/Closed: Extensible for new rate sources
- Liskov Substitution: Service layer can be substituted
- Interface Segregation: Clean service interface
- Dependency Inversion: Depends on repository abstraction

Author: CisTrade Team
Last Updated: 2025-12-28
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from django.core.exceptions import ValidationError
from django.core.cache import cache

from market_data.repositories.fx_rate_hive_repository import fx_rate_hive_repository

logger = logging.getLogger(__name__)


class FXRateService:
    """
    Service for FX rate business logic.

    Handles:
    - FX rate retrieval with business rules
    - Currency conversion calculations
    - Rate validation and comparison
    - Caching for performance
    """

    # Cache TTL in seconds (15 minutes for FX rates)
    CACHE_TTL = 900

    @staticmethod
    def get_fx_rates(
        limit: int = 100,
        currency_pair: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        base_currency: Optional[str] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get FX rates with filters and business logic.

        Args:
            limit: Maximum number of records (capped at 1000 for performance)
            currency_pair: Filter by currency pair (e.g., "USD-AED")
            date_from: Start date in YYYYMMDD format
            date_to: End date in YYYYMMDD format
            base_currency: Filter by base currency
            source: Filter by data source

        Returns:
            List of FX rate records with calculated fields

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate and cap limit
        if limit > 1000:
            logger.warning(f"Limit {limit} exceeds maximum, capping at 1000")
            limit = 1000

        # Validate date formats
        if date_from:
            FXRateService._validate_date_format(date_from)
        if date_to:
            FXRateService._validate_date_format(date_to)

        # Validate currency pair format
        if currency_pair:
            FXRateService._validate_currency_pair(currency_pair)

        try:
            rates = fx_rate_hive_repository.get_all_fx_rates(
                limit=limit,
                currency_pair=currency_pair,
                date_from=date_from,
                date_to=date_to,
                base_currency=base_currency,
                source=source
            )

            logger.info(f"Retrieved {len(rates)} FX rates with filters")
            return rates

        except Exception as e:
            logger.error(f"Error in get_fx_rates: {str(e)}")
            raise

    @staticmethod
    def get_latest_rates(limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get the most recent FX rates for each currency pair.

        Uses caching to improve performance for frequently accessed data.

        Args:
            limit: Maximum number of currency pairs

        Returns:
            List of latest FX rates
        """
        cache_key = f"fx_latest_rates_{limit}"

        # Try cache first
        cached_rates = cache.get(cache_key)
        if cached_rates:
            logger.debug(f"Retrieved {len(cached_rates)} latest rates from cache")
            return cached_rates

        try:
            rates = fx_rate_hive_repository.get_latest_rates(limit=limit)

            # Cache the results
            if rates:
                cache.set(cache_key, rates, FXRateService.CACHE_TTL)
                logger.info(f"Cached {len(rates)} latest rates for {FXRateService.CACHE_TTL}s")

            return rates

        except Exception as e:
            logger.error(f"Error getting latest rates: {str(e)}")
            raise

    @staticmethod
    def get_rate_history(
        currency_pair: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get historical FX rates for a currency pair.

        Args:
            currency_pair: Currency pair (e.g., "USD-AED")
            days: Number of days of history (default 30, max 365)

        Returns:
            List of historical rates sorted by date ascending

        Raises:
            ValidationError: If currency_pair is invalid or days is out of range
        """
        # Validate currency pair
        FXRateService._validate_currency_pair(currency_pair)

        # Validate days range
        if days < 1 or days > 365:
            raise ValidationError("Days must be between 1 and 365")

        try:
            rates = fx_rate_hive_repository.get_rate_history(
                currency_pair=currency_pair,
                days=days
            )

            logger.info(f"Retrieved {len(rates)} historical rates for {currency_pair} ({days} days)")
            return rates

        except Exception as e:
            logger.error(f"Error getting rate history for {currency_pair}: {str(e)}")
            raise

    @staticmethod
    def get_rate_for_date(
        currency_pair: str,
        trade_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get FX rate for a specific date and currency pair.

        Args:
            currency_pair: Currency pair (e.g., "USD-AED")
            trade_date: Trade date in YYYYMMDD format

        Returns:
            FX rate record or None if not found

        Raises:
            ValidationError: If inputs are invalid
        """
        FXRateService._validate_currency_pair(currency_pair)
        FXRateService._validate_date_format(trade_date)

        try:
            rate = fx_rate_hive_repository.get_rate_by_date_and_pair(
                trade_date=trade_date,
                currency_pair=currency_pair
            )

            if rate:
                logger.info(f"Found rate for {currency_pair} on {trade_date}")
            else:
                logger.warning(f"No rate found for {currency_pair} on {trade_date}")

            return rate

        except Exception as e:
            logger.error(f"Error getting rate for {currency_pair} on {trade_date}: {str(e)}")
            raise

    @staticmethod
    def convert_currency(
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        trade_date: Optional[str] = None,
        use_mid_rate: bool = True
    ) -> Dict[str, Any]:
        """
        Convert amount from one currency to another using FX rates.

        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            trade_date: Specific date in YYYYMMDD format (uses latest if not provided)
            use_mid_rate: Use mid rate if True, otherwise use bid rate

        Returns:
            Dictionary with conversion details:
            {
                'original_amount': Decimal,
                'converted_amount': Decimal,
                'from_currency': str,
                'to_currency': str,
                'rate_used': Decimal,
                'trade_date': str,
                'rate_type': str  # 'mid' or 'bid'
            }

        Raises:
            ValidationError: If conversion is not possible
        """
        if amount <= 0:
            raise ValidationError("Amount must be positive")

        # Build currency pair
        currency_pair = f"{from_currency}-{to_currency}"

        # Get rate
        if trade_date:
            FXRateService._validate_date_format(trade_date)
            rate_data = fx_rate_hive_repository.get_rate_by_date_and_pair(
                trade_date=trade_date,
                currency_pair=currency_pair
            )
        else:
            # Get latest rate for this pair
            latest_rates = fx_rate_hive_repository.get_latest_rates(limit=1000)
            rate_data = next((r for r in latest_rates if r['currency_pair'] == currency_pair), None)

        if not rate_data:
            raise ValidationError(f"No FX rate found for {currency_pair}")

        # Choose rate type
        if use_mid_rate:
            rate = Decimal(str(rate_data.get('mid_rate', 0)))
            rate_type = 'mid'
        else:
            rate = Decimal(str(rate_data.get('bid_rate', 0)))
            rate_type = 'bid'

        if rate <= 0:
            raise ValidationError(f"Invalid rate: {rate}")

        # Calculate conversion
        converted_amount = amount * rate

        result = {
            'original_amount': float(amount),
            'converted_amount': float(converted_amount),
            'from_currency': from_currency,
            'to_currency': to_currency,
            'rate_used': float(rate),
            'trade_date': rate_data.get('trade_date'),
            'rate_type': rate_type,
            'source': rate_data.get('source', 'Unknown')
        }

        logger.info(f"Converted {amount} {from_currency} to {converted_amount} {to_currency} at rate {rate}")
        return result

    @staticmethod
    def get_currency_pairs() -> List[str]:
        """
        Get list of all available currency pairs.

        Uses caching for performance.

        Returns:
            Sorted list of currency pairs
        """
        cache_key = "fx_currency_pairs"

        # Try cache first
        cached_pairs = cache.get(cache_key)
        if cached_pairs:
            logger.debug(f"Retrieved {len(cached_pairs)} currency pairs from cache")
            return cached_pairs

        try:
            pairs = fx_rate_hive_repository.get_currency_pairs()

            # Cache for longer (1 hour) as this rarely changes
            if pairs:
                cache.set(cache_key, pairs, 3600)
                logger.info(f"Cached {len(pairs)} currency pairs")

            return pairs

        except Exception as e:
            logger.error(f"Error getting currency pairs: {str(e)}")
            raise

    @staticmethod
    def get_base_currencies() -> List[str]:
        """
        Get list of all available base currencies.

        Uses caching for performance.

        Returns:
            Sorted list of base currencies
        """
        cache_key = "fx_base_currencies"

        cached_currencies = cache.get(cache_key)
        if cached_currencies:
            logger.debug(f"Retrieved {len(cached_currencies)} base currencies from cache")
            return cached_currencies

        try:
            currencies = fx_rate_hive_repository.get_base_currencies()

            if currencies:
                cache.set(cache_key, currencies, 3600)
                logger.info(f"Cached {len(currencies)} base currencies")

            return currencies

        except Exception as e:
            logger.error(f"Error getting base currencies: {str(e)}")
            raise

    @staticmethod
    def get_sources() -> List[str]:
        """
        Get list of all available data sources.

        Uses caching for performance.

        Returns:
            List of source identifiers
        """
        cache_key = "fx_sources"

        cached_sources = cache.get(cache_key)
        if cached_sources:
            logger.debug(f"Retrieved {len(cached_sources)} sources from cache")
            return cached_sources

        try:
            sources = fx_rate_hive_repository.get_sources()

            if sources:
                cache.set(cache_key, sources, 3600)
                logger.info(f"Cached {len(sources)} sources")

            return sources

        except Exception as e:
            logger.error(f"Error getting sources: {str(e)}")
            raise

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get FX rate statistics.

        Returns:
            Dictionary with statistics:
            - total_records: Total number of FX rate records
            - unique_pairs: Number of unique currency pairs
            - unique_sources: Number of data sources
            - latest_date: Most recent trade date
            - earliest_date: Oldest trade date
            - source_breakdown: Records per source
        """
        try:
            stats = fx_rate_hive_repository.get_statistics()
            logger.info("Retrieved FX rate statistics")
            return stats

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            raise

    @staticmethod
    def compare_rates_across_sources(
        currency_pair: str,
        trade_date: str
    ) -> List[Dict[str, Any]]:
        """
        Compare FX rates from different sources for the same currency pair and date.

        Useful for identifying rate discrepancies and best rates.

        Args:
            currency_pair: Currency pair (e.g., "USD-AED")
            trade_date: Trade date in YYYYMMDD format

        Returns:
            List of rates from different sources with comparison metrics
        """
        FXRateService._validate_currency_pair(currency_pair)
        FXRateService._validate_date_format(trade_date)

        try:
            # Get all rates for this pair and date
            rates = fx_rate_hive_repository.get_all_fx_rates(
                limit=100,
                currency_pair=currency_pair,
                date_from=trade_date,
                date_to=trade_date
            )

            if not rates:
                logger.warning(f"No rates found for {currency_pair} on {trade_date}")
                return []

            # Calculate average mid rate across sources
            mid_rates = [Decimal(str(r['mid_rate'])) for r in rates if r.get('mid_rate')]
            avg_mid_rate = sum(mid_rates) / len(mid_rates) if mid_rates else Decimal('0')

            # Add comparison metrics
            for rate in rates:
                if rate.get('mid_rate'):
                    rate_mid = Decimal(str(rate['mid_rate']))
                    rate['variance_from_avg'] = float(rate_mid - avg_mid_rate)
                    rate['variance_pct'] = float((rate_mid - avg_mid_rate) / avg_mid_rate * 100) if avg_mid_rate > 0 else 0

            logger.info(f"Compared {len(rates)} rates for {currency_pair} on {trade_date}")
            return rates

        except Exception as e:
            logger.error(f"Error comparing rates: {str(e)}")
            raise

    @staticmethod
    def get_rate_trend(
        currency_pair: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze rate trend over a period.

        Args:
            currency_pair: Currency pair
            days: Number of days to analyze

        Returns:
            Dictionary with trend analysis:
            - trend_direction: 'up', 'down', or 'stable'
            - change_amount: Absolute change
            - change_percent: Percentage change
            - volatility: Standard deviation of rates
            - min_rate: Lowest rate in period
            - max_rate: Highest rate in period
        """
        rates = FXRateService.get_rate_history(currency_pair, days)

        if len(rates) < 2:
            return {
                'trend_direction': 'unknown',
                'change_amount': 0,
                'change_percent': 0,
                'volatility': 0,
                'min_rate': None,
                'max_rate': None,
                'data_points': len(rates)
            }

        # Extract mid rates
        mid_rates = [Decimal(str(r['mid_rate'])) for r in rates if r.get('mid_rate')]

        if not mid_rates:
            return {'error': 'No mid rates available'}

        first_rate = mid_rates[0]
        last_rate = mid_rates[-1]
        change = last_rate - first_rate
        change_pct = (change / first_rate * 100) if first_rate > 0 else 0

        # Determine trend
        if abs(change_pct) < 0.1:
            trend = 'stable'
        elif change > 0:
            trend = 'up'
        else:
            trend = 'down'

        # Calculate volatility (standard deviation)
        mean_rate = sum(mid_rates) / len(mid_rates)
        variance = sum((r - mean_rate) ** 2 for r in mid_rates) / len(mid_rates)
        volatility = float(variance ** Decimal('0.5'))

        result = {
            'currency_pair': currency_pair,
            'period_days': days,
            'data_points': len(mid_rates),
            'trend_direction': trend,
            'change_amount': float(change),
            'change_percent': float(change_pct),
            'volatility': volatility,
            'min_rate': float(min(mid_rates)),
            'max_rate': float(max(mid_rates)),
            'avg_rate': float(mean_rate),
            'first_rate': float(first_rate),
            'last_rate': float(last_rate)
        }

        logger.info(f"Analyzed {days}-day trend for {currency_pair}: {trend} ({change_pct:.2f}%)")
        return result

    # Validation helper methods

    @staticmethod
    def _validate_currency_pair(currency_pair: str) -> None:
        """
        Validate currency pair format.

        Expected format: XXX-YYY (e.g., "USD-AED")

        Raises:
            ValidationError: If format is invalid
        """
        if not currency_pair:
            raise ValidationError("Currency pair is required")

        parts = currency_pair.split('-')
        if len(parts) != 2:
            raise ValidationError("Currency pair must be in format: XXX-YYY (e.g., USD-AED)")

        base, quote = parts
        if len(base) != 3 or len(quote) != 3:
            raise ValidationError("Currency codes must be 3 characters")

        if not base.isalpha() or not quote.isalpha():
            raise ValidationError("Currency codes must be alphabetic")

    @staticmethod
    def _validate_date_format(date_str: str) -> None:
        """
        Validate date format is YYYYMMDD.

        Raises:
            ValidationError: If format is invalid
        """
        if not date_str:
            raise ValidationError("Date is required")

        if len(date_str) != 8:
            raise ValidationError("Date must be in YYYYMMDD format")

        if not date_str.isdigit():
            raise ValidationError("Date must contain only digits")

        # Try parsing to ensure it's a valid date
        try:
            year = int(date_str[0:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            datetime(year, month, day)
        except ValueError:
            raise ValidationError(f"Invalid date: {date_str}")

    @staticmethod
    def clear_cache() -> None:
        """
        Clear all FX rate caches.

        Useful after data updates or for troubleshooting.
        """
        cache_keys = [
            "fx_currency_pairs",
            "fx_base_currencies",
            "fx_sources"
        ]

        # Also clear latest rates cache with different limits
        for limit in [10, 50, 100, 200, 500, 1000]:
            cache_keys.append(f"fx_latest_rates_{limit}")

        for key in cache_keys:
            cache.delete(key)

        logger.info(f"Cleared {len(cache_keys)} FX rate cache keys")


# Singleton instance
fx_rate_service = FXRateService()
