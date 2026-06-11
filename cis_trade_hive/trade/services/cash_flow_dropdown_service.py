"""
Cash Flow Dropdown Service

Provides dropdown options for cash flow forms:
- Portfolios (validated for trading)
- Securities (from trade validation repository)
- Cash Flow Types (from UDF)
- Send/Receive (from UDF)
- Cash Flow Status (from UDF)
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
CACHE_PREFIX = 'cf_dropdown_'


class CashFlowDropdownService:
    """Service for fetching dropdown options for cash flow forms"""

    DATABASE = 'gmp_cis'
    OBJECT_TYPE = 'CASH_FLOW'  # UDF Object Type

    def get_all_dropdown_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all dropdown options for cash flow form.

        Returns:
            Dictionary with dropdown options for each field
        """
        return {
            'portfolios': self.get_portfolios(),
            'securities': self.get_securities(),
            'cash_flow_types': self.get_cash_flow_types(),
            'send_receive_options': self.get_send_receive_options(),
            'cash_flow_statuses': self.get_cash_flow_statuses(),
            'currencies': self.get_currencies(),
        }

    def get_portfolios(self, search: str = None) -> List[Dict[str, Any]]:
        """
        Get portfolios for dropdown (validated for trading).

        Args:
            search: Optional search term

        Returns:
            List of portfolio options
        """
        cache_key = f"{CACHE_PREFIX}portfolios"

        # Try cache first (only for non-search requests)
        if not search:
            try:
                cached = cache.get(cache_key)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.warning(f"Cache read error for portfolios: {str(e)}")

        try:
            # Use trade validation repository - same source as trade create
            portfolios = trade_validation_repository.get_valid_portfolios(search=search)

            options = [
                {
                    'value': p.get('portfolio_short_name', ''),
                    'label': p.get('portfolio_short_name', ''),
                    'currency': p.get('currency', ''),
                    'status': p.get('status', ''),
                }
                for p in portfolios
            ]

            # Cache non-search results
            if not search and options:
                try:
                    cache.set(cache_key, options, CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Cache write error for portfolios: {str(e)}")

            return options

        except Exception as e:
            logger.error(f"Error loading portfolios: {str(e)}")
            return []

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

    def get_cash_flow_types(self) -> List[Dict[str, Any]]:
        """
        Get cash flow types from UDF.

        Returns:
            List of cash flow type options
        """
        cache_key = f"{CACHE_PREFIX}cash_flow_types"

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for cash_flow_types: {str(e)}")

        try:
            # Try UDF first
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, 'Cash Flow Type')

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
                        logger.warning(f"Cache write error for cash_flow_types: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"UDF not found for Cash Flow Type: {str(e)}")

        # Fallback to default options
        default_options = [
            {'value': 'CAPITAL_DISTRIBUTION', 'label': 'Capital Distribution'},
            {'value': 'CASH_DIVIDEND',        'label': 'Cash Dividend'},
            {'value': 'INCOME_DISTRIBUTION',  'label': 'Income Distribution'},
            {'value': 'PIPELINE',             'label': 'Pipeline'},
            {'value': 'PROVISION',            'label': 'Provision'},
            {'value': 'RETURN_OF_CAPITAL',    'label': 'Return of Capital'},
            {'value': 'UNCALL_COMMITMENT',    'label': 'Uncall Commitment'},
            {'value': 'YTD_REALISE',          'label': 'YTD Realise'},
        ]

        try:
            cache.set(cache_key, default_options, CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Cache write error for cash_flow_types: {str(e)}")

        return default_options

    def get_send_receive_options(self) -> List[Dict[str, Any]]:
        """
        Get Send/Receive options from UDF.

        Returns:
            List of send/receive options
        """
        cache_key = f"{CACHE_PREFIX}send_receive"

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for send_receive: {str(e)}")

        try:
            # Try UDF first
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, 'Send Receive')

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
                        logger.warning(f"Cache write error for send_receive: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"UDF not found for Send Receive: {str(e)}")

        # Fallback to default options
        default_options = [
            {'value': 'SEND', 'label': 'Send'},
            {'value': 'RECEIVE', 'label': 'Receive'},
        ]

        try:
            cache.set(cache_key, default_options, CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Cache write error for send_receive: {str(e)}")

        return default_options

    def get_cash_flow_statuses(self) -> List[Dict[str, Any]]:
        """
        Get Cash Flow Status options from UDF.

        Returns:
            List of cash flow status options
        """
        cache_key = f"{CACHE_PREFIX}cash_flow_status"

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for cash_flow_status: {str(e)}")

        try:
            # Try UDF first
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, 'Cash Flow Status')

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
                        logger.warning(f"Cache write error for cash_flow_status: {str(e)}")

                    return options

        except Exception as e:
            logger.debug(f"UDF not found for Cash Flow Status: {str(e)}")

        # Fallback to default options
        default_options = [
            {'value': 'PENDING', 'label': 'Pending'},
            {'value': 'CONFIRMED', 'label': 'Confirmed'},
            {'value': 'SETTLED', 'label': 'Settled'},
            {'value': 'CANCELLED', 'label': 'Cancelled'},
            {'value': 'PROJECTED', 'label': 'Projected'},
            {'value': 'ACTUAL', 'label': 'Actual'},
        ]

        try:
            cache.set(cache_key, default_options, CACHE_TIMEOUT)
        except Exception as e:
            logger.warning(f"Cache write error for cash_flow_status: {str(e)}")

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
                for key in ['portfolios', 'securities', 'cash_flow_types', 'send_receive', 'cash_flow_status', 'currencies']:
                    cache.delete(f"{CACHE_PREFIX}{key}")
                logger.info("Invalidated all cash flow dropdown caches")

        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")


# Create singleton instance
cash_flow_dropdown_service = CashFlowDropdownService()
