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
from django.conf import settings

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TIMEOUT = 300  # 5 minutes
CACHE_PREFIX = 'ca_dropdown_'


class CorporateActionDropdownService:
    """Service for fetching dropdown options for corporate action forms"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    OBJECT_TYPE = 'CORPORATE_ACTIONS'  # UDF Object Type (stored with S in Kudu)

    # Maps UDF display labels (field_value) → internal processing codes used by ca_cash_flow_service
    UDF_LABEL_TO_CODE = {
        'cash dividend':        'CASH_DIVIDEND',
        'dividend':             'CASH_DIVIDEND',
        'special dividend':     'SPECIAL_DIVIDEND',
        'capital distribution': 'CAPITAL_DISTRIBUTION',
        'income distribution':  'INCOME_DISTRIBUTION',
        'return of capital':    'ROC',
        'roc':                  'ROC',
        'rights':               'RIGHTS_ISSUE',
        'rights issue':         'RIGHTS_ISSUE',
        'rights entitlement':   'RIGHTS_ENTITLEMENT',
        'warrants':             'WARRANT_ENTITLEMENT',
        'warrant entitlement':  'WARRANT_ENTITLEMENT',
        'split':                'STOCK_SPLIT',
        'stock split':          'STOCK_SPLIT',
        'reverse split':        'REVERSE_SPLIT',
        'bonus':                'BONUS_ISSUE',
        'bonus issue':          'BONUS_ISSUE',
        'consolidation':        'CONSOLIDATION',
        'interest':             'INTEREST',
        'coupon':               'COUPON',
    }

    # Normalises any dirty/legacy ca_type value (from GMP migration or inconsistent
    # manual entry) to the canonical internal code used by the dropdown and service.
    # Keys are lowercased stripped values; values are canonical dropdown option values.
    CA_TYPE_NORMALISE_MAP = {
        # Dividend variants -- also normalises the legacy stored code 'DIVIDEND'
        # itself (pre-rename CAs synced before sync_gmp_corporate_actions.py
        # switched to CASH_DIVIDEND) since normalise_ca_type() lowercases its
        # input before lookup, so old and new records converge on one value.
        'dividend':             'CASH_DIVIDEND',
        'cash dividend':        'CASH_DIVIDEND',
        'cash_dividend':        'CASH_DIVIDEND',
        'cashdividend':         'CASH_DIVIDEND',
        # Special dividend
        'special dividend':     'SPECIAL_DIVIDEND',
        'special_dividend':     'SPECIAL_DIVIDEND',
        # Split variants
        'split':                'STOCK_SPLIT',
        'stock split':          'STOCK_SPLIT',
        'stock_split':          'STOCK_SPLIT',
        'reverse split':        'REVERSE_SPLIT',
        'reverse_split':        'REVERSE_SPLIT',
        # Bonus
        'bonus issue':          'BONUS_ISSUE',
        'bonus_issue':          'BONUS_ISSUE',
        'bonus':                'BONUS_ISSUE',
        # Rights
        'rights issue':         'RIGHTS_ISSUE',
        'rights_issue':         'RIGHTS_ISSUE',
        'rights':               'RIGHTS_ISSUE',
        'rights entitlement':   'RIGHTS_ENTITLEMENT',
        'rights_entitlement':   'RIGHTS_ENTITLEMENT',
        # Warrants
        'warrants':             'WARRANT_ENTITLEMENT',
        'warrant entitlement':  'WARRANT_ENTITLEMENT',
        'warrant_entitlement':  'WARRANT_ENTITLEMENT',
        # Capital
        'capital distribution': 'CAPITAL_DISTRIBUTION',
        'capital_distribution': 'CAPITAL_DISTRIBUTION',
        'capital reduction':    'CAPITAL_REDUCTION',
        'capital_reduction':    'CAPITAL_REDUCTION',
        # Income
        'income distribution':  'INCOME_DISTRIBUTION',
        'income_distribution':  'INCOME_DISTRIBUTION',
        # Others
        'interest':             'INTEREST',
        'coupon':               'COUPON',
        'roc':                  'ROC',
        'consolidation':        'CONSOLIDATION',
        'merger':               'MERGER',
        'acquisition':          'ACQUISITION',
        'spin off':             'SPIN_OFF',
        'spin_off':             'SPIN_OFF',
        'tender offer':         'TENDER_OFFER',
        'tender_offer':         'TENDER_OFFER',
        'share buyback':        'SHARE_BUYBACK',
        'share_buyback':        'SHARE_BUYBACK',
        'name change':          'NAME_CHANGE',
        'name_change':          'NAME_CHANGE',
        'delisting':            'DELISTING',
        'other':                'OTHER',
    }

    def normalise_ca_type(self, raw_value: str) -> str:
        """Map any legacy/inconsistent ca_type string to the canonical dropdown value.

        Handles GMP migration variants (e.g. 'DIVIDEND'), mixed-case CIS entries
        (e.g. 'Cash Dividend', 'CASH DIVIDEND') and underscore variants.
        Returns the original value unchanged if no mapping is found (already canonical
        or truly unknown).
        """
        if not raw_value:
            return raw_value
        key = raw_value.strip().lower()
        return self.CA_TYPE_NORMALISE_MAP.get(key, raw_value.strip().upper())

    def get_ca_type_label(self, raw_ca_type: str) -> str:
        """
        Return the display label for a stored ca_type value, e.g. 'DIVIDEND'
        or 'CASH_DIVIDEND' -> 'Cash Dividend'. Normalises first so legacy
        codes converge on the current label. Falls back to the raw value if
        no matching option is found.
        """
        if not raw_ca_type:
            return raw_ca_type
        canonical = self.normalise_ca_type(raw_ca_type)
        for option in self.get_ca_types():
            if option.get('value') == canonical:
                return option.get('label', raw_ca_type)
        return raw_ca_type

    def get_all_dropdown_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all dropdown options for corporate action form.

        Returns:
            Dictionary with dropdown options for each field
        """
        return {
            'securities': self.get_securities(),
            'portfolios': self.get_portfolios(),
            'ca_types': self.get_ca_types(),
            'currencies': self.get_currencies(),
        }

    def get_portfolios(self, search: str = None) -> List[Dict[str, Any]]:
        """
        Get portfolios for dropdown (same as trade create).

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
            # Query portfolios from cis_portfolio table
            # Note: Portfolio table uses 'name' as the primary identifier (no short_name column)
            query = f"""
            SELECT DISTINCT name, currency
            FROM {self.DATABASE}.cis_portfolio
            WHERE name IS NOT NULL AND name != ''
              AND (is_active = true OR is_active IS NULL)
              AND status IN ('VALIDATED', 'SETTLED', 'INITIAL')
            ORDER BY name
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            options = []
            if results:
                options = [
                    {
                        'value': r.get('name', ''),
                        'label': r.get('name', ''),
                        'currency': r.get('currency', ''),
                    }
                    for r in results if r.get('name')
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
            # Try UDF first (object_type='CORPORATE_ACTIONS', field_name='Corporate Action Type')
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, 'Corporate Action Type')

            if results:
                options = []
                for r in results:
                    raw_label = r.get('field_value', '')
                    if not raw_label:
                        continue
                    # Map UDF display label → internal processing code
                    internal_code = self.UDF_LABEL_TO_CODE.get(raw_label.lower().strip())
                    if not internal_code:
                        # Unknown label: log a warning so it's visible, skip it
                        logger.warning(
                            f"CA type '{raw_label}' from UDF has no internal code mapping — "
                            f"add it to UDF_LABEL_TO_CODE in corporate_action_dropdown_service.py"
                        )
                        continue
                    options.append({
                        'value': internal_code,
                        'label': raw_label.title(),
                    })

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
            {'value': 'CASH_DIVIDEND', 'label': 'Cash Dividend'},
            {'value': 'SPLIT', 'label': 'Split'},
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
