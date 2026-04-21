"""
Trade Dropdown Service

Simplified service for trade form dropdowns:
- Uses cis_udf_field for configurable dropdown options
- Uses cis_party for brokers/custodians
- Uses cis_portfolio, cis_security for entity lookups
- No dependency on lookup tables (removed to improve performance)

Performance Optimizations:
- Django cache for UDF options (300s TTL)
- Batch UDF loading to reduce DB queries from 18+ to 1
- Parallel loading with ThreadPoolExecutor for 3-5x speedup
- Graceful fallback to DB on cache miss/error

Required tables: cis_trade, cis_udf_field, cis_party, cis_portfolio, cis_security, cis_equity_price
"""

import logging
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache

from core.repositories.impala_connection import impala_manager
from trade.repositories.trade_validation_repository import trade_validation_repository
from udf.repositories.udf_field_repository import udf_field_repository

logger = logging.getLogger(__name__)

# Cache configuration
UDF_CACHE_TIMEOUT = 300  # 5 minutes
UDF_CACHE_PREFIX = 'udf_trade_'
UDF_BATCH_CACHE_KEY = 'udf_trade_all_fields'
DROPDOWN_ALL_CACHE_KEY = 'trade_dropdown_all'  # Full dropdown cache
DROPDOWN_CACHE_TIMEOUT = 120  # 2 minutes for full dropdown (shorter TTL)


class TradeDropdownService:
    """Service for fetching dropdown options for trade forms with caching"""

    DATABASE = 'gmp_cis'
    OBJECT_TYPE = 'TRADE'  # UDF Object Type for Trade entity

    # List of UDF field names for batch loading
    UDF_FIELD_NAMES = [
        'GL Fund Type', 'GL Cost Centre', 'GL Account Code', 'Selling Rule',
        'Sub Custodian', 'Open/Close Position', 'Extension', 'Fund Type',
        'Income/Exp Type', 'UOBN/UOBN-HK', 'Section 31/26', 'Revision Code',
        'Amortisation Method', 'Delivery Type', 'Income Type', 'Split Type',
        'Reduction Type'
    ]

    # =========================================================================
    # UDF CACHING METHODS
    # =========================================================================

    def _get_cache_key(self, field_name: str) -> str:
        """Generate cache key for a UDF field."""
        return f"{UDF_CACHE_PREFIX}{field_name.replace(' ', '_').replace('/', '_').lower()}"

    def _load_all_udf_fields_batch(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load all UDF fields for TRADE entity in a single batch query.
        Caches individual fields and returns the complete mapping.

        Returns:
            Dictionary mapping field_name to list of options
        """
        try:
            # Try to get from batch cache first
            cached_batch = cache.get(UDF_BATCH_CACHE_KEY)
            if cached_batch is not None:
                logger.debug("UDF batch loaded from cache")
                return cached_batch

            # Single query to load all TRADE UDF fields
            all_fields = udf_field_repository.get_all(object_type=self.OBJECT_TYPE, is_active=True)

            # Group by field_name
            field_map: Dict[str, List[Dict[str, Any]]] = {}
            for field in all_fields:
                field_name = field.get('field_name', '')
                field_value = field.get('field_value', '')
                if field_name and field_value:
                    if field_name not in field_map:
                        field_map[field_name] = []
                    field_map[field_name].append({
                        'value': field_value,
                        'label': field_value.replace('_', ' ').title()
                    })

            # Cache the batch result
            cache.set(UDF_BATCH_CACHE_KEY, field_map, UDF_CACHE_TIMEOUT)

            # Also cache individual fields for single-field lookups
            for field_name, options in field_map.items():
                cache_key = self._get_cache_key(field_name)
                cache.set(cache_key, options, UDF_CACHE_TIMEOUT)

            logger.info(f"UDF batch loaded: {len(field_map)} fields from database")
            return field_map

        except Exception as e:
            logger.error(f"Error loading UDF batch: {str(e)}")
            return {}

    def _get_udf_options(self, field_name: str) -> List[Dict[str, Any]]:
        """
        Get dropdown options from UDF field table with caching.

        Args:
            field_name: The field name in UDF table (e.g., 'Fund Type', 'Selling Rule')

        Returns:
            List of options with 'value' and 'label' keys
        """
        cache_key = self._get_cache_key(field_name)

        # Try cache first
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"UDF cache hit for {field_name}")
                return cached
        except Exception as e:
            logger.warning(f"Cache read error for {field_name}: {str(e)}")

        # Cache miss - try batch load first (more efficient)
        try:
            batch_data = self._load_all_udf_fields_batch()
            if field_name in batch_data:
                return batch_data[field_name]
        except Exception as e:
            logger.warning(f"Batch load failed, falling back to single query: {str(e)}")

        # Fallback to single field query
        try:
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, field_name)
            if results:
                options = [
                    {
                        'value': r.get('field_value', ''),
                        'label': r.get('field_value', '').replace('_', ' ').title()
                    }
                    for r in results if r.get('field_value')
                ]
                # Cache the result
                try:
                    cache.set(cache_key, options, UDF_CACHE_TIMEOUT)
                except Exception as cache_err:
                    logger.warning(f"Cache write error for {field_name}: {str(cache_err)}")

                logger.debug(f"Loaded {len(options)} options from DB for {field_name}")
                return options
        except Exception as e:
            logger.debug(f"UDF not found for {field_name}: {str(e)}")

        return []

    def invalidate_udf_cache(self, field_name: Optional[str] = None) -> None:
        """
        Invalidate UDF cache. Call this when UDF fields are modified.

        Args:
            field_name: Specific field to invalidate, or None to invalidate all
        """
        try:
            if field_name:
                # Invalidate specific field
                cache_key = self._get_cache_key(field_name)
                cache.delete(cache_key)
                logger.info(f"Invalidated UDF cache for: {field_name}")

            # Always invalidate batch cache when any field changes
            cache.delete(UDF_BATCH_CACHE_KEY)
            logger.info("Invalidated UDF batch cache")

        except Exception as e:
            logger.error(f"Error invalidating UDF cache: {str(e)}")

    def warm_udf_cache(self) -> int:
        """
        Pre-load all UDF fields into cache (for app startup).

        Returns:
            Number of fields cached
        """
        try:
            field_map = self._load_all_udf_fields_batch()
            logger.info(f"UDF cache warmed with {len(field_map)} fields")
            return len(field_map)
        except Exception as e:
            logger.error(f"Error warming UDF cache: {str(e)}")
            return 0

    def get_all_dropdown_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all dropdown options for trade form.

        Performance: Uses parallel loading with ThreadPoolExecutor for 3-5x speedup.
        - Full result cache (120s TTL) - instant return when cached
        - Pre-warms UDF cache before loading to reduce DB queries
        - Parallel entity loading (portfolios, securities, etc.)

        Returns:
            Dictionary with dropdown options for each field
        """
        import time
        perf_start = time.time()

        # Check full result cache first (instant return)
        try:
            cached_all = cache.get(DROPDOWN_ALL_CACHE_KEY)
            if cached_all is not None:
                logger.info(f"[PERF] Dropdown cache HIT - {(time.time() - perf_start)*1000:.0f}ms")
                return cached_all
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        logger.info("[PERF] Dropdown cache MISS - loading from DB")

        # Pre-warm UDF cache first (single batch query for all UDF fields)
        self._load_all_udf_fields_batch()

        # Static options (no DB call needed)
        result = {
            'trade_types': self.get_trade_types(),
            'trade_statuses': self.get_trade_statuses(),
        }

        # Define DB-dependent loaders with their result keys
        # Group 1: Entity lookups (heavy DB queries)
        entity_loaders = {
            'portfolios': self.get_portfolios,
            'currencies': self.get_currencies,
            'securities': self.get_securities,
            'counterparties': self.get_counterparties,
            'brokers': self.get_brokers,
            'custodians': self.get_custodians,
        }

        # Group 2: UDF-based options (use pre-warmed cache)
        udf_loaders = {
            'gl_fund_types': self.get_gl_fund_types,
            'gl_cost_centres': self.get_gl_cost_centres,
            'gl_account_codes': self.get_gl_account_codes,
            'selling_rules': self.get_selling_rules,
            'sub_custodians': self.get_sub_custodians,
            'open_close_options': self.get_open_close_options,
            'extensions': self.get_extensions,
            'fund_types': self.get_fund_types,
            'income_exp_types': self.get_income_exp_types,
            'uobn_options': self.get_uobn_options,
            'section_options': self.get_section_options,
            'revision_codes': self.get_revision_codes,
            'amor_methods': self.get_amor_methods,
            'delivery_types': self.get_delivery_types,
            'income_types': self.get_income_types,
            'split_types': self.get_split_types,
            'reduction_types': self.get_reduction_types,
        }

        # Load UDF options synchronously (fast - using pre-warmed cache)
        for key, loader in udf_loaders.items():
            try:
                result[key] = loader()
            except Exception as e:
                logger.warning(f"Error loading {key}: {e}")
                result[key] = []

        # Load entity options in parallel (slow - DB queries)
        try:
            with ThreadPoolExecutor(max_workers=6) as executor:
                future_to_key = {
                    executor.submit(loader): key
                    for key, loader in entity_loaders.items()
                }
                for future in as_completed(future_to_key, timeout=30):
                    key = future_to_key[future]
                    try:
                        result[key] = future.result()
                    except Exception as e:
                        logger.warning(f"Error loading {key} in parallel: {e}")
                        result[key] = []
        except Exception as e:
            logger.error(f"Parallel loading failed, falling back to sequential: {e}")
            # Fallback to sequential loading
            for key, loader in entity_loaders.items():
                if key not in result:
                    try:
                        result[key] = loader()
                    except Exception as ex:
                        logger.warning(f"Error loading {key}: {ex}")
                        result[key] = []

        # Cache the full result for instant returns on subsequent calls
        try:
            cache.set(DROPDOWN_ALL_CACHE_KEY, result, DROPDOWN_CACHE_TIMEOUT)
            logger.info(f"[PERF] Full dropdown loaded and cached in {(time.time() - perf_start)*1000:.0f}ms")
        except Exception as e:
            logger.warning(f"Failed to cache dropdown result: {e}")

        return result

    def invalidate_dropdown_cache(self) -> None:
        """Invalidate the full dropdown cache. Call when entities change."""
        try:
            cache.delete(DROPDOWN_ALL_CACHE_KEY)
            logger.info("Dropdown cache invalidated")
        except Exception as e:
            logger.error(f"Error invalidating dropdown cache: {e}")

    # =========================================================================
    # TRADE TYPES & STATUSES (Static - No DB query)
    # =========================================================================

    def get_trade_types(self) -> List[Dict[str, Any]]:
        """
        Get trade type options.
        Per SA feedback (2026-03-04): Only BUY and SELL
        """
        return [
            {'value': 'BUY', 'label': 'Buy'},
            {'value': 'SELL', 'label': 'Sell'},
        ]

    def get_trade_statuses(self) -> List[Dict[str, Any]]:
        """Get trade status options (static list - workflow statuses)."""
        return [
            {'value': 'INITIAL', 'label': 'Initial'},
            {'value': 'MODIFIED', 'label': 'Modified'},
            {'value': 'PENDING_VALIDATION', 'label': 'Pending Validation'},
            {'value': 'VALIDATED', 'label': 'Validated'},
            {'value': 'SETTLED', 'label': 'Settled'},
            {'value': 'CANCELLED', 'label': 'Cancelled'},
        ]

    # =========================================================================
    # ENTITY LOOKUPS (Portfolio, Security, Counterparty)
    # =========================================================================

    def get_portfolios(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid portfolios for dropdown."""
        portfolios = trade_validation_repository.get_valid_portfolios(search=search)
        return [
            {
                'value': p.get('portfolio_short_name', ''),
                'label': p.get('portfolio_short_name', ''),
                'currency': p.get('currency', ''),
                'manager': p.get('manager', '')
            }
            for p in portfolios
        ]

    def get_securities(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid securities for dropdown."""
        securities = trade_validation_repository.get_valid_securities(search=search)
        return [
            {
                'value': s.get('security_label', ''),
                'label': f"{s.get('security_label', '')} ({s.get('ticker', s.get('isin', ''))})",
                'security_type': s.get('security_type', ''),
                'currency': s.get('currency_code', ''),
                'price': s.get('current_price', 0)
            }
            for s in securities
        ]

    def get_counterparties(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid counterparties (parties) for dropdown."""
        counterparties = trade_validation_repository.get_valid_counterparties(search=search)
        return [
            {
                'value': c.get('party_short_name', ''),
                'label': f"{c.get('party_full_name', '')} ({c.get('party_short_name', '')})",
                'country': c.get('country', ''),
                'is_broker': c.get('is_broker', False)
            }
            for c in counterparties
        ]

    # =========================================================================
    # BROKER & CUSTODIAN (from cis_party table)
    # =========================================================================

    def get_brokers(self) -> List[Dict[str, Any]]:
        """Get broker options from cis_party table where is_broker=true."""
        try:
            query = f"""
            SELECT party_short_name as value,
                   COALESCE(party_full_name, party_short_name) as label,
                   country
            FROM {self.DATABASE}.cis_party
            WHERE is_broker = true
              AND is_active = true
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY party_short_name
            LIMIT 200
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [
                    {
                        'value': r.get('value', ''),
                        'label': f"{r.get('label', '')} ({r.get('value', '')})" if r.get('label') != r.get('value') else r.get('value', ''),
                        'country': r.get('country', '')
                    }
                    for r in results
                ]
        except Exception as e:
            logger.debug(f"Could not load brokers: {str(e)}")

        # Fallback defaults
        return [
            {'value': 'UOB KAY HIAN', 'label': 'UOB Kay Hian'},
            {'value': 'DBS VICKERS', 'label': 'DBS Vickers'},
            {'value': 'OCBC SECURITIES', 'label': 'OCBC Securities'},
        ]

    def get_custodians(self) -> List[Dict[str, Any]]:
        """Get custodian options from cis_party table where is_custodian=true."""
        try:
            query = f"""
            SELECT party_short_name as value,
                   COALESCE(party_full_name, party_short_name) as label,
                   country
            FROM {self.DATABASE}.cis_party
            WHERE is_custodian = true
              AND is_active = true
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY party_short_name
            LIMIT 200
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [
                    {
                        'value': r.get('value', ''),
                        'label': f"{r.get('label', '')} ({r.get('value', '')})" if r.get('label') != r.get('value') else r.get('value', ''),
                        'country': r.get('country', '')
                    }
                    for r in results
                ]
        except Exception as e:
            logger.debug(f"Could not load custodians: {str(e)}")

        # Fallback defaults
        return [
            {'value': 'DBS', 'label': 'DBS Bank'},
            {'value': 'SCB', 'label': 'Standard Chartered'},
            {'value': 'CITI', 'label': 'Citibank'},
            {'value': 'HSBC', 'label': 'HSBC'},
        ]

    # =========================================================================
    # UDF-BASED OPTIONS (Try UDF first, then use defaults)
    # =========================================================================

    def get_gl_fund_types(self) -> List[Dict[str, Any]]:
        """Get GL fund type options."""
        options = self._get_udf_options('GL Fund Type')
        if options:
            return options
        return [
            {'value': 'TRADING', 'label': 'Trading Book'},
            {'value': 'BANKING', 'label': 'Banking Book'},
            {'value': 'INVESTMENT', 'label': 'Investment Book'},
        ]

    def get_gl_cost_centres(self) -> List[Dict[str, Any]]:
        """Get GL cost centre options."""
        options = self._get_udf_options('GL Cost Centre')
        if options:
            return options
        return [
            {'value': 'CC-001', 'label': 'Treasury'},
            {'value': 'CC-002', 'label': 'Investment Management'},
            {'value': 'CC-003', 'label': 'Trading Desk'},
        ]

    def get_gl_account_codes(self) -> List[Dict[str, Any]]:
        """Get GL account code options."""
        options = self._get_udf_options('GL Account Code')
        if options:
            return options
        return [
            {'value': 'ACC-1001', 'label': 'Trading Securities'},
            {'value': 'ACC-1002', 'label': 'Available for Sale'},
            {'value': 'ACC-1003', 'label': 'Held to Maturity'},
        ]

    def get_selling_rules(self) -> List[Dict[str, Any]]:
        """Get selling rule options."""
        options = self._get_udf_options('Selling Rule')
        if options:
            return options
        return [
            {'value': 'FIFO', 'label': 'First In First Out'},
            {'value': 'LIFO', 'label': 'Last In First Out'},
            {'value': 'WAVG', 'label': 'Weighted Average'},
            {'value': 'SPEC', 'label': 'Specific Identification'},
        ]

    def get_sub_custodians(self) -> List[Dict[str, Any]]:
        """Get sub-custodian options."""
        options = self._get_udf_options('Sub Custodian')
        if options:
            return options
        return [
            {'value': 'DBS-SG', 'label': 'DBS Bank Singapore'},
            {'value': 'SCB-SG', 'label': 'Standard Chartered SG'},
            {'value': 'CITI-SG', 'label': 'Citibank Singapore'},
        ]

    def get_open_close_options(self) -> List[Dict[str, Any]]:
        """Get open/close position options."""
        options = self._get_udf_options('Open/Close Position')
        if options:
            return options
        return [
            {'value': 'OPEN', 'label': 'Open'},
            {'value': 'CLOSE', 'label': 'Close'},
        ]

    def get_extensions(self) -> List[Dict[str, Any]]:
        """Get extension options."""
        options = self._get_udf_options('Extension')
        if options:
            return options
        return [
            {'value': 'NONE', 'label': 'None'},
            {'value': 'EXT-1D', 'label': '1 Day Extension'},
            {'value': 'EXT-2D', 'label': '2 Day Extension'},
        ]

    def get_fund_types(self) -> List[Dict[str, Any]]:
        """Get fund type options."""
        options = self._get_udf_options('Fund Type')
        if options:
            return options
        return [
            {'value': 'EQUITY', 'label': 'Equity'},
            {'value': 'FIXED_INCOME', 'label': 'Fixed Income'},
            {'value': 'MONEY_MARKET', 'label': 'Money Market'},
            {'value': 'BALANCED', 'label': 'Balanced'},
        ]

    def get_income_exp_types(self) -> List[Dict[str, Any]]:
        """Get income/expense type options."""
        options = self._get_udf_options('Income/Exp Type')
        if options:
            return options
        return [
            {'value': 'TRADING', 'label': 'Trading'},
            {'value': 'INVESTMENT', 'label': 'Investment'},
            {'value': 'DIVIDEND', 'label': 'Dividend'},
            {'value': 'INTEREST', 'label': 'Interest'},
        ]

    def get_uobn_options(self) -> List[Dict[str, Any]]:
        """Get UOBN/UOBN-HK options."""
        options = self._get_udf_options('UOBN/UOBN-HK')
        if options:
            return options
        return [
            {'value': 'UOBN-SG', 'label': 'UOBN Singapore'},
            {'value': 'UOBN-HK', 'label': 'UOBN Hong Kong'},
            {'value': 'UOBN-MY', 'label': 'UOBN Malaysia'},
        ]

    def get_section_options(self) -> List[Dict[str, Any]]:
        """Get Section 31/26 options."""
        options = self._get_udf_options('Section 31/26')
        if options:
            return options
        return [
            {'value': 'SEC_31', 'label': 'Section 31'},
            {'value': 'SEC_26', 'label': 'Section 26'},
            {'value': 'BOTH', 'label': 'Both'},
            {'value': 'NA', 'label': 'N/A'},
        ]

    def get_revision_codes(self) -> List[Dict[str, Any]]:
        """Get revision code options."""
        options = self._get_udf_options('Revision Code')
        if options:
            return options
        return [
            {'value': 'REV-001', 'label': 'Revision 001'},
            {'value': 'REV-002', 'label': 'Revision 002'},
            {'value': 'NA', 'label': 'N/A'},
        ]

    def get_amor_methods(self) -> List[Dict[str, Any]]:
        """Get amortisation method options."""
        options = self._get_udf_options('Amortisation Method')
        if options:
            return options
        return [
            {'value': 'STD', 'label': 'Standard'},
            {'value': 'EFF_INT', 'label': 'Effective Interest'},
            {'value': 'STRAIGHT', 'label': 'Straight Line'},
            {'value': 'NONE', 'label': 'None'},
        ]

    def get_delivery_types(self) -> List[Dict[str, Any]]:
        """Get delivery type options."""
        options = self._get_udf_options('Delivery Type')
        if options:
            return options
        return [
            {'value': 'TRANSFER', 'label': 'Transfer'},
            {'value': 'CORP_ACTION', 'label': 'Corporate Action'},
            {'value': 'SETTLEMENT', 'label': 'Settlement'},
        ]

    def get_income_types(self) -> List[Dict[str, Any]]:
        """Get income type options."""
        options = self._get_udf_options('Income Type')
        if options:
            return options
        return [
            {'value': 'DIVIDEND', 'label': 'Dividend'},
            {'value': 'INTEREST', 'label': 'Interest'},
            {'value': 'DISTRIBUTION', 'label': 'Distribution'},
        ]

    def get_split_types(self) -> List[Dict[str, Any]]:
        """Get split type options."""
        options = self._get_udf_options('Split Type')
        if options:
            return options
        return [
            {'value': 'STOCK_SPLIT', 'label': 'Stock Split'},
            {'value': 'REVERSE_SPLIT', 'label': 'Reverse Split'},
            {'value': 'BONUS_ISSUE', 'label': 'Bonus Issue'},
        ]

    def get_reduction_types(self) -> List[Dict[str, Any]]:
        """Get reduction type options."""
        options = self._get_udf_options('Reduction Type')
        if options:
            return options
        return [
            {'value': 'RETURN_CAPITAL', 'label': 'Return of Capital'},
            {'value': 'AMORTIZATION', 'label': 'Amortization'},
            {'value': 'WRITEDOWN', 'label': 'Write-down'},
        ]

    # =========================================================================
    # CURRENCY & PRICE METHODS
    # =========================================================================

    def get_currencies(self) -> List[Dict[str, Any]]:
        """Get available currencies from cis_security and cis_equity_price."""
        currencies_set = set()

        # Get currencies from cis_security
        try:
            query = f"""
            SELECT DISTINCT currency_code
            FROM {self.DATABASE}.cis_security
            WHERE (is_active = true OR is_active IS NULL)
              AND currency_code IS NOT NULL
              AND currency_code <> ''
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    if r.get('currency_code'):
                        currencies_set.add(r.get('currency_code'))
        except Exception as e:
            logger.debug(f"Could not load currencies from cis_security: {str(e)}")

        # Get currencies from cis_equity_price
        try:
            query = f"""
            SELECT DISTINCT currency_code
            FROM {self.DATABASE}.cis_equity_price
            WHERE (is_active = true OR is_active IS NULL)
              AND currency_code IS NOT NULL
              AND currency_code <> ''
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    if r.get('currency_code'):
                        currencies_set.add(r.get('currency_code'))
        except Exception as e:
            logger.debug(f"Could not load currencies from cis_equity_price: {str(e)}")

        if currencies_set:
            return [{'value': c, 'label': c} for c in sorted(currencies_set)]

        # Fallback
        return [
            {'value': 'USD', 'label': 'USD'},
            {'value': 'SGD', 'label': 'SGD'},
            {'value': 'EUR', 'label': 'EUR'},
            {'value': 'GBP', 'label': 'GBP'},
        ]

    def get_securities_by_currency(self, currency_code: str) -> List[Dict[str, Any]]:
        """Get securities filtered by currency code."""
        if not currency_code:
            return []

        securities_dict = {}

        # Get from cis_security
        try:
            query = f"""
            SELECT security_name, isin, exchange_code as market
            FROM {self.DATABASE}.cis_security
            WHERE currency_code = '{currency_code}'
              AND (is_active = true OR is_active IS NULL)
            ORDER BY security_name
            LIMIT 500
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    sec_name = r.get('security_name', '')
                    if sec_name:
                        securities_dict[sec_name] = {
                            'value': sec_name,
                            'label': f"{sec_name} ({r.get('isin', '')})",
                            'isin': r.get('isin', ''),
                            'price': 0,
                            'market': r.get('market', ''),
                        }
        except Exception as e:
            logger.debug(f"Error loading from cis_security: {str(e)}")

        # Overlay prices from cis_equity_price
        try:
            query = f"""
            SELECT security_label, isin, main_closing_price as price, price_date
            FROM {self.DATABASE}.cis_equity_price
            WHERE currency_code = '{currency_code}'
              AND (is_active = true OR is_active IS NULL)
            ORDER BY security_label, price_date DESC
            LIMIT 500
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    sec_label = r.get('security_label', '')
                    if sec_label:
                        equity_price = float(r.get('price', 0)) if r.get('price') else 0
                        if sec_label in securities_dict:
                            if equity_price > 0:
                                securities_dict[sec_label]['price'] = equity_price
                        else:
                            securities_dict[sec_label] = {
                                'value': sec_label,
                                'label': f"{sec_label} ({r.get('isin', '')})",
                                'isin': r.get('isin', ''),
                                'price': equity_price,
                                'market': '',
                            }
        except Exception as e:
            logger.debug(f"Error loading from cis_equity_price: {str(e)}")

        return sorted(securities_dict.values(), key=lambda x: x['value'])

    def get_equity_price(self, security_label: str, currency_code: str = None) -> Dict[str, Any]:
        """Get the latest closing price for a security."""
        if not security_label:
            return {'price': 0, 'found': False}

        currency_filter = f"AND currency_code = '{currency_code}'" if currency_code else ""

        try:
            query = f"""
            SELECT security_label, currency_code, main_closing_price as price, price_date, isin
            FROM {self.DATABASE}.cis_equity_price
            WHERE security_label = '{security_label}'
              AND (is_active = true OR is_active IS NULL)
              {currency_filter}
            ORDER BY price_date DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results and len(results) > 0:
                r = results[0]
                price = float(r.get('price', 0)) if r.get('price') else 0
                if price > 0:
                    return {
                        'price': price,
                        'currency_code': r.get('currency_code', ''),
                        'price_date': str(r.get('price_date', '')),
                        'isin': r.get('isin', ''),
                        'found': True
                    }
        except Exception as e:
            logger.debug(f"Error getting price: {str(e)}")

        return {'price': 0, 'found': False}

    # =========================================================================
    # TRADE CHARGE METHODS (from cis_trade_charge_lut)
    # =========================================================================

    def get_broker_charges(self, broker: str, exchange: str = None) -> List[Dict[str, Any]]:
        """Get charges for a broker from cis_trade_charge_lut."""
        if not broker:
            return []

        try:
            escaped_broker = broker.replace("'", "''")
            base_broker = escaped_broker.replace('*', '%').replace('?', '_')
            exchange_filter = f"AND (exchange = '{exchange}' OR exchange IS NULL)" if exchange else ""

            query = f"""
            SELECT fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE (broker = '{escaped_broker}' OR UPPER(broker) = UPPER('{escaped_broker}')
                   OR broker LIKE '{base_broker}' OR UPPER(broker) LIKE UPPER('{base_broker}'))
              {exchange_filter}
            ORDER BY fee_type
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [
                    {
                        'broker': r.get('broker', ''),
                        'fee_type': r.get('fee_type', ''),
                        'exchange': r.get('exchange', '') or '',
                        'country_of_exchange': r.get('country_of_exchange', '') or '',
                        'fee_rule': r.get('fee_rule', ''),
                        'fee_value': float(r.get('fee_value', 0) or 0),
                    }
                    for r in results
                ]
        except Exception as e:
            logger.debug(f"Error getting broker charges: {str(e)}")

        return []

    def calculate_trade_charges(self, broker: str, quantity: float, price: float,
                                trade_type: str = 'BUY', exchange: str = None) -> Dict[str, Any]:
        """Calculate charges for a trade based on broker lookup.

        GST is applied on the sum of all other fees (brokerage + clearing +
        trading + flat fees), NOT on the gross trade value.

        Processing order:
          1. Calculate all non-GST fees against trade_value (or as flat).
          2. Sum those fees → subtotal_fees.
          3. Calculate GST as a % of subtotal_fees.
          4. Total = subtotal_fees + gst.
        """
        trade_value = float(quantity) * float(price)
        charges = self.get_broker_charges(broker, exchange)

        # --- Pass 1: calculate all non-GST fees ---
        non_gst_charges = []
        gst_charges = []
        for charge in charges:
            if 'gst' in charge.get('fee_type', '').lower():
                gst_charges.append(charge)
            else:
                non_gst_charges.append(charge)

        calculated_charges = []
        subtotal_fees = 0.0

        for charge in non_gst_charges:
            fee_rule = charge.get('fee_rule', '')
            fee_value = float(charge.get('fee_value', 0))

            if fee_rule.lower() == 'percent':
                calculated_fee = trade_value * (fee_value / 100)
            elif fee_rule.lower() == 'flat':
                calculated_fee = fee_value
            else:
                calculated_fee = 0.0

            subtotal_fees += calculated_fee
            calculated_charges.append({
                'fee_type': charge.get('fee_type', ''),
                'fee_rule': fee_rule,
                'fee_value': fee_value,
                'exchange': charge.get('exchange', ''),
                'country_of_exchange': charge.get('country_of_exchange', ''),
                'calculated_fee': round(calculated_fee, 6),
            })

        # --- Pass 2: apply GST on subtotal of other fees ---
        for charge in gst_charges:
            fee_rule = charge.get('fee_rule', '')
            fee_value = float(charge.get('fee_value', 0))

            if fee_rule.lower() == 'percent':
                calculated_fee = subtotal_fees * (fee_value / 100)
            elif fee_rule.lower() == 'flat':
                calculated_fee = fee_value
            else:
                calculated_fee = 0.0

            calculated_charges.append({
                'fee_type': charge.get('fee_type', ''),
                'fee_rule': fee_rule,
                'fee_value': fee_value,
                'exchange': charge.get('exchange', ''),
                'country_of_exchange': charge.get('country_of_exchange', ''),
                'calculated_fee': round(calculated_fee, 6),
            })

        total_charges = sum(c['calculated_fee'] for c in calculated_charges)
        grand_total = trade_value + total_charges if trade_type.upper() == 'BUY' else trade_value - total_charges

        return {
            'broker': broker,
            'charges': calculated_charges,
            'total_charges': round(total_charges, 6),
            'trade_value': round(trade_value, 6),
            'grand_total': round(grand_total, 6),
            'trade_type': trade_type.upper(),
        }

    def get_exchanges(self) -> List[Dict[str, Any]]:
        """Get distinct exchanges from charge lookup table."""
        try:
            query = f"""
            SELECT DISTINCT exchange, country_of_exchange
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE exchange IS NOT NULL
            ORDER BY exchange
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [
                    {
                        'value': r.get('exchange', ''),
                        'label': f"{r.get('exchange', '')} ({r.get('country_of_exchange', '')})" if r.get('country_of_exchange') else r.get('exchange', ''),
                        'country': r.get('country_of_exchange', '') or ''
                    }
                    for r in results if r.get('exchange')
                ]
        except Exception as e:
            logger.debug(f"Error getting exchanges: {str(e)}")
        return []

    def get_brokers_from_charge_lut(self) -> List[Dict[str, Any]]:
        """Get distinct brokers from charge lookup table."""
        try:
            query = f"""
            SELECT DISTINCT broker
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE broker IS NOT NULL
            ORDER BY broker
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [{'value': r.get('broker', ''), 'label': r.get('broker', '')}
                        for r in results if r.get('broker')]
        except Exception as e:
            logger.debug(f"Error getting brokers from charge LUT: {str(e)}")
        return []


# Singleton instance
trade_dropdown_service = TradeDropdownService()
