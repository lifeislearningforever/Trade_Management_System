"""
Equity Price Service
Business logic for equity price operations following SOLID principles.

Uses composite primary key: (currency_code, security_label, price_date)
Supports versioned price history - multiple prices per security (one per date).

SOLID Principles Applied:
- Single Responsibility: Each method has one clear purpose
- Open/Closed: Extensible for new price sources
- Liskov Substitution: Service layer can be substituted
- Interface Segregation: Clean service interface
- Dependency Inversion: Depends on repository abstraction

Author: CisTrade Team
Last Updated: 2026-01-31
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import time
from django.core.exceptions import ValidationError
from django.core.cache import cache

from market_data.repositories.equity_price_hive_repository import equity_price_hive_repository

logger = logging.getLogger(__name__)


class EquityPriceService:
    """
    Service for equity price business logic.

    Uses composite key: (currency_code, security_label, price_date)
    Supports versioned price history - multiple prices per security (one per date).

    Handles:
    - Equity price CRUD operations with business rules
    - Price validation and comparison
    - Historical price analysis
    - Caching for performance
    """

    # Cache TTL in seconds (15 minutes for equity prices)
    CACHE_TTL = 900

    @staticmethod
    def get_equity_prices(
        limit: int = 100,
        currency_code: Optional[str] = None,
        security_label: Optional[str] = None,
        isin: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get equity prices with filters and business logic.

        Args:
            limit: Maximum number of records (capped at 1000 for performance)
            currency_code: Filter by currency
            security_label: Filter by security name (supports wildcard search)
            isin: Filter by ISIN
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format

        Returns:
            List of equity price records

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate and cap limit
        if limit > 1000:
            logger.warning(f"Limit {limit} exceeds maximum, capping at 1000")
            limit = 1000

        # Validate date formats
        if date_from:
            EquityPriceService._validate_date_format(date_from)
        if date_to:
            EquityPriceService._validate_date_format(date_to)

        try:
            prices = equity_price_hive_repository.get_all_equity_prices(
                limit=limit,
                currency_code=currency_code,
                security_label=security_label,
                isin=isin,
                date_from=date_from,
                date_to=date_to
            )

            logger.info(f"Retrieved {len(prices)} equity prices with filters")
            return prices

        except Exception as e:
            logger.error(f"Error in get_equity_prices: {str(e)}")
            raise

    @staticmethod
    def get_equity_price_by_key(currency_code: str, security_label: str, price_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get equity price by composite key.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            price_date: Price date in YYYY-MM-DD format (optional - if None, returns latest)

        Returns:
            Equity price record or None

        Raises:
            ValidationError: If keys are invalid
        """
        if not currency_code or not security_label:
            raise ValidationError("Both currency_code and security_label are required")

        try:
            price = equity_price_hive_repository.get_equity_price_by_key(currency_code, security_label, price_date)

            if price:
                logger.info(f"Found equity price: {currency_code}/{security_label}/{price_date or 'latest'}")
            else:
                logger.warning(f"No equity price found: {currency_code}/{security_label}/{price_date or 'latest'}")

            return price

        except Exception as e:
            logger.error(f"Error getting equity price {currency_code}/{security_label}: {str(e)}")
            raise

    @staticmethod
    def create_equity_price(
        equity_price_data: Dict[str, Any],
        user: str = 'SYSTEM'
    ) -> bool:
        """
        Create new equity price with validation.

        Args:
            equity_price_data: Dictionary with price data
            user: Username creating the price

        Returns:
            True if successful

        Raises:
            ValidationError: If validation fails
        """
        # Validate required fields
        required_fields = ['currency_code', 'security_label', 'price_date', 'main_closing_price']
        for field in required_fields:
            if not equity_price_data.get(field):
                raise ValidationError(f"{field} is required")

        # Validate date format
        EquityPriceService._validate_date_format(equity_price_data['price_date'])

        # Validate price is positive
        price = equity_price_data.get('main_closing_price')
        try:
            price_decimal = Decimal(str(price))
            if price_decimal <= 0:
                raise ValidationError("Main closing price must be positive")
        except (ValueError, TypeError):
            raise ValidationError("Invalid price value")

        # Add created_by
        equity_price_data['created_by'] = user

        # Generate timestamp if not provided
        if not equity_price_data.get('price_timestamp'):
            equity_price_data['price_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            success = equity_price_hive_repository.upsert_equity_price(equity_price_data, username=user)

            if success:
                logger.info(f"Successfully created equity price for {equity_price_data.get('currency_code')}/"
                           f"{equity_price_data.get('security_label')} on {equity_price_data.get('price_date')}")
                # Clear cache
                EquityPriceService.clear_cache()
            else:
                logger.error(f"Failed to create equity price")

            return success

        except Exception as e:
            logger.error(f"Error creating equity price: {str(e)}")
            raise

    @staticmethod
    def update_equity_price(
        currency_code: str,
        security_label: str,
        equity_price_data: Dict[str, Any],
        user: str = 'SYSTEM',
        price_date: Optional[str] = None
    ) -> bool:
        """
        Update existing equity price with validation.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            equity_price_data: Dictionary with fields to update
            user: Username updating the price
            price_date: Price date (part of composite key). If None, updates the latest price.

        Returns:
            True if successful

        Raises:
            ValidationError: If validation fails
        """
        if not currency_code or not security_label:
            raise ValidationError("Both currency_code and security_label are required")

        # Validate date format if provided
        if 'price_date' in equity_price_data:
            EquityPriceService._validate_date_format(equity_price_data['price_date'])

        # Validate price if provided
        if 'main_closing_price' in equity_price_data:
            price = equity_price_data['main_closing_price']
            try:
                price_decimal = Decimal(str(price))
                if price_decimal <= 0:
                    raise ValidationError("Main closing price must be positive")
            except (ValueError, TypeError):
                raise ValidationError("Invalid price value")

        # Save old values to history before updating
        try:
            existing = equity_price_hive_repository.get_equity_price_by_key(
                currency_code, security_label, price_date
            )
            if existing:
                equity_price_hive_repository.save_to_history(existing, user, 'UPDATE')
        except Exception as e:
            logger.warning(f"Could not save history before update: {str(e)}")

        # Add updated_by
        equity_price_data['updated_by'] = user

        try:
            success = equity_price_hive_repository.update_equity_price(
                currency_code,
                security_label,
                equity_price_data,
                username=user,
                price_date=price_date
            )

            if success:
                logger.info(f"Successfully updated equity price: {currency_code}/{security_label}/{price_date or 'latest'}")
                # Clear cache
                EquityPriceService.clear_cache()
            else:
                logger.error(f"Failed to update equity price: {currency_code}/{security_label}/{price_date or 'latest'}")

            return success

        except Exception as e:
            logger.error(f"Error updating equity price {currency_code}/{security_label}: {str(e)}")
            raise

    @staticmethod
    def delete_equity_price(
        currency_code: str,
        security_label: str,
        user: str = 'SYSTEM',
        price_date: Optional[str] = None
    ) -> bool:
        """
        Soft delete equity price.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            user: Username deleting the price
            price_date: Price date (part of composite key). If None, deletes the latest price.

        Returns:
            True if successful

        Raises:
            ValidationError: If keys are invalid
        """
        if not currency_code or not security_label:
            raise ValidationError("Both currency_code and security_label are required")

        # Save old values to history before deleting
        try:
            existing = equity_price_hive_repository.get_equity_price_by_key(
                currency_code, security_label, price_date
            )
            if existing:
                equity_price_hive_repository.save_to_history(existing, user, 'DELETE')
        except Exception as e:
            logger.warning(f"Could not save history before delete: {str(e)}")

        try:
            success = equity_price_hive_repository.delete_equity_price(
                currency_code,
                security_label,
                deleted_by=user,
                price_date=price_date
            )

            if success:
                logger.info(f"Successfully deleted equity price: {currency_code}/{security_label}/{price_date or 'latest'}")
                # Clear cache
                EquityPriceService.clear_cache()
            else:
                logger.error(f"Failed to delete equity price: {currency_code}/{security_label}/{price_date or 'latest'}")

            return success

        except Exception as e:
            logger.error(f"Error deleting equity price {currency_code}/{security_label}: {str(e)}")
            raise

    @staticmethod
    def get_price_history(
        security_label: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get historical prices for a security.

        Args:
            security_label: Security name
            days: Number of days of history (default 30, max 365)

        Returns:
            List of historical prices sorted by date descending

        Raises:
            ValidationError: If security_label is invalid or days is out of range
        """
        if not security_label:
            raise ValidationError("Security label is required")

        if days < 1 or days > 365:
            raise ValidationError("Days must be between 1 and 365")

        try:
            prices = equity_price_hive_repository.get_price_history(
                security_label=security_label,
                days=days
            )

            logger.info(f"Retrieved {len(prices)} historical prices for {security_label} ({days} days)")
            return prices

        except Exception as e:
            logger.error(f"Error getting price history for {security_label}: {str(e)}")
            raise

    @staticmethod
    def get_version_history(
        currency_code: str,
        security_label: str,
        price_date: str
    ) -> List[Dict[str, Any]]:
        """
        Get edit history for a specific equity price record.

        Args:
            currency_code: Currency code
            security_label: Security label
            price_date: Price date

        Returns:
            List of historical versions (old values before edits)
        """
        if not currency_code or not security_label or not price_date:
            return []

        try:
            return equity_price_hive_repository.get_version_history(
                currency_code, security_label, price_date
            )
        except Exception as e:
            logger.error(f"Error getting version history: {str(e)}")
            return []

    @staticmethod
    def get_all_history_for_security(
        currency_code: str,
        security_label: str
    ) -> List[Dict[str, Any]]:
        """
        Get all edit history for a security across all dates.

        Args:
            currency_code: Currency code
            security_label: Security label

        Returns:
            List of historical versions
        """
        if not currency_code or not security_label:
            return []

        try:
            return equity_price_hive_repository.get_all_history_for_security(
                currency_code, security_label
            )
        except Exception as e:
            logger.error(f"Error getting security history: {str(e)}")
            return []

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get equity price statistics.

        Returns:
            Dictionary with statistics:
            - total_prices: Total number of equity price records
            - unique_securities: Number of unique securities
            - unique_currencies: Number of currencies
            - latest_date: Most recent price date
            - earliest_date: Oldest price date
        """
        try:
            stats = equity_price_hive_repository.get_statistics()
            logger.info("Retrieved equity price statistics")
            return stats

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            raise

    @staticmethod
    def get_price_trend(
        security_label: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze price trend over a period.

        Args:
            security_label: Security name
            days: Number of days to analyze

        Returns:
            Dictionary with trend analysis:
            - trend_direction: 'up', 'down', or 'stable'
            - change_amount: Absolute change
            - change_percent: Percentage change
            - volatility: Standard deviation of prices
            - min_price: Lowest price in period
            - max_price: Highest price in period
        """
        prices = EquityPriceService.get_price_history(security_label, days)

        if len(prices) < 2:
            return {
                'trend_direction': 'unknown',
                'change_amount': 0,
                'change_percent': 0,
                'volatility': 0,
                'min_price': None,
                'max_price': None,
                'data_points': len(prices)
            }

        # Extract prices
        price_values = [Decimal(str(p['main_closing_price'])) for p in prices if p.get('main_closing_price')]

        if not price_values:
            return {'error': 'No price data available'}

        first_price = price_values[-1]  # Oldest (prices sorted DESC)
        last_price = price_values[0]    # Newest
        change = last_price - first_price
        change_pct = (change / first_price * 100) if first_price > 0 else 0

        # Determine trend
        if abs(change_pct) < 0.5:
            trend = 'stable'
        elif change > 0:
            trend = 'up'
        else:
            trend = 'down'

        # Calculate volatility (standard deviation)
        mean_price = sum(price_values) / len(price_values)
        variance = sum((p - mean_price) ** 2 for p in price_values) / len(price_values)
        volatility = float(variance ** Decimal('0.5'))

        result = {
            'security_label': security_label,
            'period_days': days,
            'data_points': len(price_values),
            'trend_direction': trend,
            'change_amount': float(change),
            'change_percent': float(change_pct),
            'volatility': volatility,
            'min_price': float(min(price_values)),
            'max_price': float(max(price_values)),
            'avg_price': float(mean_price),
            'first_price': float(first_price),
            'last_price': float(last_price)
        }

        logger.info(f"Analyzed {days}-day trend for {security_label}: {trend} ({change_pct:.2f}%)")
        return result

    # Validation helper methods

    @staticmethod
    def _validate_date_format(date_str: str) -> None:
        """
        Validate date format is YYYY-MM-DD.

        Raises:
            ValidationError: If format is invalid
        """
        if not date_str:
            raise ValidationError("Date is required")

        if len(date_str) != 10:
            raise ValidationError("Date must be in YYYY-MM-DD format")

        if date_str[4] != '-' or date_str[7] != '-':
            raise ValidationError("Date must be in YYYY-MM-DD format")

        # Try parsing to ensure it's a valid date
        try:
            year = int(date_str[0:4])
            month = int(date_str[5:7])
            day = int(date_str[8:10])
            datetime(year, month, day)
        except ValueError:
            raise ValidationError(f"Invalid date: {date_str}")

    @staticmethod
    def clear_cache() -> None:
        """
        Clear all equity price caches.

        Useful after data updates or for troubleshooting.
        """
        cache_keys = [
            "equity_price_statistics"
        ]

        for key in cache_keys:
            cache.delete(key)

        logger.info(f"Cleared {len(cache_keys)} equity price cache keys")


# Singleton instance
equity_price_service = EquityPriceService()
