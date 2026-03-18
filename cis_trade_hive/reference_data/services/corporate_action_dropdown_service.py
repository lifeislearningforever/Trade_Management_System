"""
Corporate Action Dropdown Service

Provides dropdown options for corporate action forms:
- Securities (from trade validation repository - same as trade create)
- Corporate Action Types (from UDF)
- Currencies (from reference data table)
"""

import logging
from typing import Dict, List, Any

from django.core.cache import cache

from core.repositories.impala_connection import impala_manager
from udf.repositories.udf_field_repository import udf_field_repository
from trade.repositories.trade_validation_repository import trade_validation_repository

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TIMEOUT = 300  # 5 minutes
CACHE_PREFIX = 'ca_dropdown_'


class CorporateActionDropdownService:
    """Service for fetching dropdown options for corporate action forms"""

    DATABASE = 'gmp_cis'
    OBJECT_TYPE = 'CORPORATE_ACTION'  # UDF Object Type

    def get_all_dropdown_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all dropdown options for corporate action form.

        Returns:
            Dictionary with dropdown options for each field
        """
        return {
            'securities': self.get_securities(),
            'ca_types': self.get_ca_types(),
            'currencies': self.get_currencies(),
        }

    def get_securities(self, search: str = None) -> List[Dict[str, Any]]:
        """
        Get securities for dropdown (same as trade create).

        Args:
            search: Optional search term

        Returns:
            List of security options
        """
        cache_key = f"{CACHE_PREFIX}securities"

        # Try cache first (only for non-search requests)
        if not search:
            try:
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.warning(f"Cache read error for securities: {str(e)}")

        try:
            # Use trade validation repository - same source as trade create
            securities = trade_validation_repository.get_valid_securities(search=search)

            options = [
                {
                    'value': s.get('security_label', ''),
                    'label': f"{s.get('security_label', '')} ({s.get('ticker', s.get('isin', ''))})",
                    'security_type': s.get('security_type', ''),
                    'currency': s.get('currency_code', ''),
                    'isin': s.get('isin', ''),
                }
                for s in securities
            ]

            # Cache non-search results
            if not search and options:
                try:
                    cache.set(cache_key, options, CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Cache write error for securities: {str(e)}")

            return options

        except Exception as e:
            logger.error(f"Error loading securities: {str(e)}")
            return []

    def get_ca_types(self) -> List[Dict[str, Any]]:
        """
        Get corporate action types from UDF.

        Returns:
            List of CA type options
        """
        cache_key = f"{CACHE_PREFIX}ca_types"

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for ca_types: {str(e)}")

        try:
            # Try UDF first
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, 'Corporate Action Type')

            if results:
                options = [
                    {
                        'value': r.get('field_value', ''),
                        'label': r.get('field_value', '').replace('_', ' ').title()
                    }
                    for r in results if r.get('field_value')
                ]

                if options:
                    try:
                        cache.set(cache_key, options, CACHE_TIMEOUT)
                    except Exception as e:
                        logger.warning(f"Cache write error for ca_types: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"UDF not found for Corporate Action Type: {str(e)}")

        # Fallback to default options
        default_options = [
            {'value': 'DIVIDEND', 'label': 'Dividend'},
            {'value': 'STOCK_SPLIT', 'label': 'Stock Split'},
            {'value': 'REVERSE_SPLIT', 'label': 'Reverse Split'},
            {'value': 'BONUS_ISSUE', 'label': 'Bonus Issue'},
            {'value': 'RIGHTS_ISSUE', 'label': 'Rights Issue'},
            {'value': 'MERGER', 'label': 'Merger'},
            {'value': 'ACQUISITION', 'label': 'Acquisition'},
            {'value': 'SPIN_OFF', 'label': 'Spin Off'},
            {'value': 'CAPITAL_DISTRIBUTION', 'label': 'Capital Distribution'},
            {'value': 'CAPITAL_REDUCTION', 'label': 'Capital Reduction'},
            {'value': 'TENDER_OFFER', 'label': 'Tender Offer'},
            {'value': 'SHARE_BUYBACK', 'label': 'Share Buyback'},
            {'value': 'NAME_CHANGE', 'label': 'Name Change'},
            {'value': 'DELISTING', 'label': 'Delisting'},
            {'value': 'CONSOLIDATION', 'label': 'Consolidation'},
            {'value': 'OTHER', 'label': 'Other'},
        ]

        try:
            cache.set(cache_key, default_options, CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Cache write error for ca_types: {str(e)}")

        return default_options

    def get_currencies(self) -> List[Dict[str, Any]]:
        """
        Get currencies from reference data table.

        Returns:
            List of currency options
        """
        cache_key = f"{CACHE_PREFIX}currencies"

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for currencies: {str(e)}")

        try:
            # Query from currency reference table
            # Note: 'symbol' is a reserved word in Impala - use backticks
            query = f"""
            SELECT DISTINCT name, full_name, `symbol`
            FROM {self.DATABASE}.gmp_cis_sta_dly_currency
            WHERE name IS NOT NULL AND name != ''
            ORDER BY name
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                options = [
                    {
                        'value': r.get('name', ''),
                        'label': f"{r.get('name', '')} - {r.get('full_name', r.get('name', ''))}" if r.get('full_name') else r.get('name', ''),
                        'symbol': r.get('symbol', '')
                    }
                    for r in results if r.get('name')
                ]

                if options:
                    try:
                        cache.set(cache_key, options, CACHE_TIMEOUT)
                    except Exception as e:
                        logger.warning(f"Cache write error for currencies: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"Error loading currencies from reference table: {str(e)}")

        # Fallback to securities currency codes
        try:
            query = f"""
            SELECT DISTINCT currency_code
            FROM {self.DATABASE}.cis_security
            WHERE currency_code IS NOT NULL AND currency_code != ''
              AND (is_active = true OR is_active IS NULL)
            ORDER BY currency_code
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                options = [
                    {'value': r.get('currency_code', ''), 'label': r.get('currency_code', '')}
                    for r in results if r.get('currency_code')
                ]

                if options:
                    try:
                        cache.set(cache_key, options, CACHE_TIMEOUT)
                    except Exception as e:
                        logger.warning(f"Cache write error for currencies: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"Error loading currencies from cis_security: {str(e)}")

        # Final fallback
        default_options = [
            {'value': 'USD', 'label': 'USD - US Dollar'},
            {'value': 'SGD', 'label': 'SGD - Singapore Dollar'},
            {'value': 'EUR', 'label': 'EUR - Euro'},
            {'value': 'GBP', 'label': 'GBP - British Pound'},
            {'value': 'JPY', 'label': 'JPY - Japanese Yen'},
            {'value': 'HKD', 'label': 'HKD - Hong Kong Dollar'},
            {'value': 'CNY', 'label': 'CNY - Chinese Yuan'},
            {'value': 'AUD', 'label': 'AUD - Australian Dollar'},
        ]

        return default_options

    def invalidate_cache(self, field_name: str = None) -> None:
        """
        Invalidate dropdown cache.

        Args:
            field_name: Specific field to invalidate, or None for all
        """
        try:
            if field_name:
                cache_key = f"{CACHE_PREFIX}{field_name}"
                cache.delete(cache_key)
                logger.info(f"Invalidated cache for: {field_name}")
            else:
                # Invalidate all
                for key in ['securities', 'ca_types', 'currencies']:
                    cache.delete(f"{CACHE_PREFIX}{key}")
                logger.info("Invalidated all corporate action dropdown caches")

        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")


# Create singleton instance
corporate_action_dropdown_service = CorporateActionDropdownService()
