"""
Security Dropdown Service

Provides dropdown data for security forms from:
- UDF system (object_type='SECURITY')
- Reference data tables (counterparty, country, currency)

UDF Table Schema (cis_udf_field):
- udf_id: Primary key
- object_type: Entity type (SECURITY, PORTFOLIO, etc.)
- field_name: Field definition name (e.g., 'price source', 'Security Type')
- field_value: Dropdown option value (the actual values users select)
- is_active: Soft delete flag

All data fetched from Kudu tables via Impala.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from core.repositories.impala_connection import impala_manager
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


class SecurityDropdownRepository:
    """Repository for fetching dropdown options from Kudu tables"""

    DATABASE = 'gmp_cis'
    UDF_FIELD_TABLE = 'cis_udf_field'
    PARTY_TABLE = 'gmp_cis.cis_party'
    COUNTRY_TABLE = 'gmp_cis_sta_dly_country'
    CURRENCY_TABLE = 'gmp_cis_sta_dly_currency'

    @staticmethod
    def get_udf_options_by_field_name(field_name: str, object_type: str = 'SECURITY') -> List[Dict[str, str]]:
        """
        Get UDF dropdown options for a specific field from cis_udf_field table.

        Schema: cis_udf_field table where:
        - object_type is the entity type (e.g., 'SECURITY')
        - field_name is the field definition (e.g., 'price source')
        - field_value contains the actual dropdown values

        Args:
            field_name: UDF field definition name (e.g., 'price source', 'Security Type')
            object_type: Object type (default: SECURITY)

        Returns:
            List of option dictionaries with 'value' key
        """
        try:
            escaped_field = field_name.replace("'", "''")
            # Query from cis_udf_field table - get field_value where field_name matches
            query = f"""
            SELECT DISTINCT field_value
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.UDF_FIELD_TABLE}
            WHERE object_type = '{object_type}'
              AND field_name = '{escaped_field}'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND is_active = true
            ORDER BY field_value
            """

            logger.info(f"Executing UDF dropdown query for field_name={field_name}, object_type={object_type}")
            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                logger.warning(f"UDF field not found: {field_name} for object_type {object_type}")
                return []

            logger.info(f"Found {len(result)} options for {field_name}")
            return [{'value': row.get('field_value', '')} for row in result if row.get('field_value')]

        except Exception as e:
            logger.error(f"Error fetching UDF options for {field_name}: {str(e)}")
            return []

    @staticmethod
    def get_issuers() -> List[Dict[str, str]]:
        """
        Get issuers from cis_party table.

        Returns:
            List of issuer dictionaries with 'name' key (party_short_name)
        """
        try:
            query = f"""
            SELECT party_short_name, party_full_name
            FROM {SecurityDropdownRepository.PARTY_TABLE}
            WHERE is_active = TRUE
              AND (is_deleted IS NULL OR is_deleted = FALSE)
            ORDER BY party_short_name
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'name': row.get('party_short_name', '')} for row in result]

        except Exception as e:
            logger.error(f"Error fetching issuers: {str(e)}")
            return []

    @staticmethod
    def get_countries() -> List[Dict[str, str]]:
        """
        Get countries from country table.
        Filters by max(processing_date) to avoid duplicates.

        Returns:
            List of country dictionaries with 'code' and 'name' keys
        """
        try:
            # Filter by max(processing_date) to avoid duplicates from multiple dates
            query = f"""
            SELECT DISTINCT `label`, `full_name`
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.COUNTRY_TABLE}
            WHERE `label` IS NOT NULL AND `label` != ''
              AND processing_date = (
                  SELECT MAX(processing_date)
                  FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.COUNTRY_TABLE}
              )
            ORDER BY `full_name`
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'code': row.get('label', ''), 'name': row.get('full_name', '')} for row in result if row.get('label')]

        except Exception as e:
            logger.error(f"Error fetching countries: {str(e)}")
            return []

    @staticmethod
    def get_currencies() -> List[Dict[str, str]]:
        """
        Get currencies from gmp_cis_sta_dly_currency table.
        Filters by max(processing_date) to avoid duplicates.

        Schema (from office environment):
        - name: Currency code (e.g., 'SGD', 'USD')
        - full_name: Full currency name (e.g., 'Singapore Dollar')
        - symbol: Currency symbol (reserved word - must be escaped)

        Returns:
            List of currency dictionaries with 'code' and 'name' keys
        """
        try:
            # Note: 'symbol' is a reserved word in Impala, must use backticks
            # Filter by max(processing_date) to avoid duplicates from multiple dates
            query = f"""
            SELECT DISTINCT name, full_name, `symbol`
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.CURRENCY_TABLE}
            WHERE name IS NOT NULL AND name != ''
              AND processing_date = (
                  SELECT MAX(processing_date)
                  FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.CURRENCY_TABLE}
              )
            ORDER BY name
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'code': row.get('name', ''), 'name': row.get('full_name', '')} for row in result if row.get('name')]

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []

    @staticmethod
    def get_all_udf_options(object_type: str = 'SECURITY') -> Dict[str, List[Dict[str, str]]]:
        """
        Fetch ALL UDF dropdown options for object_type in a single query,
        grouped by field_name. Each list starts with a blank entry so users
        can clear/leave a field empty.
        """
        try:
            query = f"""
            SELECT field_name, field_value
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.UDF_FIELD_TABLE}
            WHERE object_type = '{object_type}'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND (is_active = true OR is_active IS NULL)
            ORDER BY field_name, field_value
            """
            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)
            grouped: Dict[str, List[Dict[str, str]]] = {}
            for row in (result or []):
                fname = row.get('field_name', '')
                fval = row.get('field_value', '')
                if fname and fval:
                    grouped.setdefault(fname, []).append({'value': fval})
            # Prepend blank option to every field list
            for fname in grouped:
                grouped[fname] = [{'value': ''}] + grouped[fname]
            logger.info(f"Bulk UDF query returned {len(grouped)} field names: {sorted(grouped.keys())}")
            return grouped
        except Exception as e:
            logger.error(f"Error fetching bulk UDF options: {str(e)}")
            return {}

    @staticmethod
    def get_markets() -> List[Dict[str, str]]:
        """
        Get market dropdown options from UDF table.

        Returns:
            List of market dictionaries with 'value' key
        """
        try:
            query = f"""
            SELECT DISTINCT field_value
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.UDF_FIELD_TABLE}
            WHERE object_type = 'SECURITY'
              AND field_name = 'Market'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND is_active = true
            ORDER BY field_value
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'value': row.get('field_value', '')} for row in result if row.get('field_value')]

        except Exception as e:
            logger.error(f"Error fetching markets: {str(e)}")
            return []


class SecurityDropdownService:
    """Service for providing dropdown data with audit logging"""

    def __init__(self, repository=None, audit_repo=None):
        self.repository = repository or SecurityDropdownRepository()
        self.audit_repo = audit_repo or AuditLogKuduRepository()

    def _log_dropdown_fetch(self, field_name: str, options_count: int, user: str = 'SYSTEM'):
        """Log dropdown fetch to audit trail - Commented out (only log CREATE, UPDATE, DELETE)"""
        # Commented out - no audit logging for dropdown/READ actions
        # try:
        #     self.audit_repo.log_action(
        #         user_id=user,
        #         username=user,
        #         action_type='READ',
        #         entity_type='SECURITY_DROPDOWN',
        #         entity_id=field_name,
        #         action_detail=f'Fetched {options_count} options for {field_name}',
        #         status='SUCCESS'
        #     )
        # except Exception as e:
        #     logger.warning(f"Error logging dropdown fetch: {str(e)}")
        pass

    # ==========================================================================
    # UDF-based dropdowns (object_type='SECURITY')
    # Field names MUST match production cis_udf_field.field_value exactly:
    # Industry, Country of Incorporation, Exchange Code, Security Type,
    # Investment Type, Price Source of Issue, Country of Issue,
    # Country of Primary Exchange, BWCIIF, BWCIIF Others, Issuer Type,
    # Approved S32, BASEL IV - FUND, Business Unit Head, Core/Non Core,
    # Fund / Index Fund, Management Limit Classification, MAS 643 Entity Type,
    # Person In Charge, Substantial >10%, PEWC, S32 Representative,
    # Quoted/Unquoted, Fin/Non-Fin IND, Relative Index
    # ==========================================================================

    def get_industries(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Industry dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Industry', 'SECURITY')
        self._log_dropdown_fetch('industry', len(options), user)
        return options

    def get_country_of_incorporation_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Incorporation dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Country of Incorporation', 'SECURITY')
        self._log_dropdown_fetch('country_of_incorporation', len(options), user)
        return options

    def get_exchange_codes(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Exchange Code dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Exchange Code', 'SECURITY')
        self._log_dropdown_fetch('exchange_code', len(options), user)
        return options

    def get_security_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Security Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Security Type', 'SECURITY')
        self._log_dropdown_fetch('security_type', len(options), user)
        return options

    def get_investment_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Investment Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Investment Type', 'SECURITY')
        self._log_dropdown_fetch('investment_type', len(options), user)
        return options

    def get_price_source_of_issue_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Price Source of Issue dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Price Source of Issue', 'SECURITY')
        self._log_dropdown_fetch('price_source_of_issue', len(options), user)
        return options

    def get_country_of_issue_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Issue dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Country of Issue', 'SECURITY')
        self._log_dropdown_fetch('country_of_issue', len(options), user)
        return options

    def get_country_of_primary_exchange_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Primary Exchange dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Country of Primary Exchange', 'SECURITY')
        self._log_dropdown_fetch('country_of_primary_exchange', len(options), user)
        return options

    def get_bwciif_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BWCIIF dropdown options"""
        options = self.repository.get_udf_options_by_field_name('BWCIIF', 'SECURITY')
        self._log_dropdown_fetch('bwciif', len(options), user)
        return options

    def get_bwciif_others_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BWCIIF Others dropdown options"""
        options = self.repository.get_udf_options_by_field_name('BWCIIF Others', 'SECURITY')
        self._log_dropdown_fetch('bwciif_others', len(options), user)
        return options

    def get_issuer_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Issuer Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Issuer Type', 'SECURITY')
        self._log_dropdown_fetch('issuer_type', len(options), user)
        return options

    def get_approved_s32_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Approved S32 dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Approved S32', 'SECURITY')
        self._log_dropdown_fetch('approved_s32', len(options), user)
        return options

    def get_basel_iv_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BASEL IV - FUND dropdown options"""
        options = self.repository.get_udf_options_by_field_name('BASEL IV - FUND', 'SECURITY')
        self._log_dropdown_fetch('basel_iv_fund', len(options), user)
        return options

    def get_business_unit_head_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Business Unit Head dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Business Unit Head', 'SECURITY')
        self._log_dropdown_fetch('business_unit_head', len(options), user)
        return options

    def get_core_non_core_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Core/Non Core dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Core/Non Core', 'SECURITY')
        self._log_dropdown_fetch('core_non_core', len(options), user)
        return options

    def get_fund_index_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Fund / Index Fund dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Fund / Index Fund', 'SECURITY')
        self._log_dropdown_fetch('fund_index_fund', len(options), user)
        return options

    def get_management_limit_classification_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Management Limit Classification dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Management Limit Classification', 'SECURITY')
        self._log_dropdown_fetch('management_limit_classification', len(options), user)
        return options

    def get_mas_643_entity_type_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get MAS 643 Entity Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('MAS 643 Entity Type', 'SECURITY')
        self._log_dropdown_fetch('mas_643_entity_type', len(options), user)
        return options

    def get_person_in_charge_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Person In Charge dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Person In Charge', 'SECURITY')
        self._log_dropdown_fetch('person_in_charge', len(options), user)
        return options

    def get_substantial_gt_10_percent_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Substantial >10% dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Substantial >10%', 'SECURITY')
        self._log_dropdown_fetch('substantial_gt_10_percent', len(options), user)
        return options

    def get_pewc_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get PEWC dropdown options"""
        options = self.repository.get_udf_options_by_field_name('PEWC', 'SECURITY')
        self._log_dropdown_fetch('pewc', len(options), user)
        return options

    def get_s32_representative_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get S32 Representative dropdown options"""
        options = self.repository.get_udf_options_by_field_name('S32 Representative', 'SECURITY')
        self._log_dropdown_fetch('s32_representative', len(options), user)
        return options

    def get_quoted_unquoted_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Quoted/Unquoted dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Quoted/Unquoted', 'SECURITY')
        self._log_dropdown_fetch('quoted_unquoted', len(options), user)
        return options

    def get_fin_non_fin_ind_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Fin/Non-Fin IND dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Fin/Non-Fin IND', 'SECURITY')
        self._log_dropdown_fetch('fin_non_fin_ind', len(options), user)
        return options

    def get_relative_index_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Relative Index dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Relative Index', 'SECURITY')
        self._log_dropdown_fetch('relative_index', len(options), user)
        return options

    # ==========================================================================
    # Reference data dropdowns
    # ==========================================================================

    def get_issuers(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Issuer dropdown options from party table"""
        issuers = self.repository.get_issuers()
        self._log_dropdown_fetch('issuers', len(issuers), user)
        return issuers

    def get_countries(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country dropdown options from country table"""
        countries = self.repository.get_countries()
        self._log_dropdown_fetch('countries', len(countries), user)
        return countries

    def get_currencies(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Currency dropdown options from currency table"""
        currencies = self.repository.get_currencies()
        self._log_dropdown_fetch('currencies', len(currencies), user)
        return currencies

    def get_markets(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Market dropdown options from UDF table"""
        markets = self.repository.get_markets()
        self._log_dropdown_fetch('markets', len(markets), user)
        return markets

    # ==========================================================================
    # Aggregate method to get all dropdown options at once
    # ==========================================================================

    def get_all_dropdown_options(self, user: str = 'SYSTEM') -> Dict[str, Any]:
        """
        Get all dropdown options for security forms.

        Strategy: 1 bulk UDF query + 4 parallel reference-data queries
        instead of 28 serial Impala round trips.
        """
        logger.info(f"Fetching all security dropdown options for user: {user}")

        # Run bulk UDF query and 4 reference queries in parallel
        ref_results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.repository.get_all_udf_options, 'SECURITY'): 'udf',
                executor.submit(self.repository.get_issuers): 'issuers',
                executor.submit(self.repository.get_countries): 'countries',
                executor.submit(self.repository.get_currencies): 'currencies',
                executor.submit(self.repository.get_markets): 'markets',
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    ref_results[key] = future.result()
                except Exception as e:
                    logger.error(f"Error fetching dropdown '{key}': {e}")
                    ref_results[key] = [] if key != 'udf' else {}

        udf = ref_results.get('udf', {})

        def udf_field(name: str) -> List[Dict[str, str]]:
            return udf.get(name, [{'value': ''}])

        # Quoted/Unquoted not in UDF — hardcoded with blank first
        quoted_unquoted_options = [
            {'value': ''},
            {'value': 'QUOTED'},
            {'value': 'UNQUOTED'},
        ]

        return {
            # UDF-backed dropdowns — field names match cis_udf_field.field_name exactly
            'industries':                               udf_field('Industry'),
            'exchange_codes':                           udf_field('Exchange Code'),
            'security_types':                           udf_field('Security Type'),
            'investment_types':                         udf_field('Investment Type'),
            'issuer_types':                             udf_field('Issuer Type'),
            'security_sub_type_options':                udf_field('Security Sub Type'),
            'security_investment_type_options':         udf_field('Security Investment Type'),
            'fintech_speculative_options':              udf_field('Fintech Speculative'),
            'unlistedeq_speculative_options':           udf_field('Unlisted EQ Speculative'),
            'markets':                                  udf_field('Market Company'),
            'country_of_incorporation_options':         udf_field('Country of Incorporation'),
            'country_of_issue_options':                 udf_field('Country of Issue'),
            'country_of_primary_exchange_options':      udf_field('Country of Primary Exchange'),
            'price_source_of_issue_options':            udf_field('Price Source of Issue'),
            'substantial_gt_10_percent_options':        udf_field('Substantial'),
            'pevc_s32_devest_options':                  udf_field('PEVC'),
            's32_representative_options':               udf_field('S32 Representative'),
            'approved_s32_options':                     udf_field('Approved S32'),
            'mas_643_entity_type_options':              udf_field('MAS 643 Entity Type'),
            'fin_non_fin_ind_options':                  udf_field('Fin/Non-Fin IND'),
            'base_liv_fund_options':                    udf_field('BIS_BASEL fund'),
            'basel_iv_fund_options':                    udf_field('BIS_BASEL fund'),
            'fund_index_fund_options':                  udf_field('Fund / Index Fund'),
            'core_non_core_options':                    udf_field('Core/Non core'),
            'management_limit_classification_options':  udf_field('Management Limit Classification'),
            'relative_index_options':                   udf_field('Relative Index'),
            'business_unit_head_options':               udf_field('Business Unit Head'),
            'person_in_charge_options':                 udf_field('Person in Charge'),
            'pevc_options':                             udf_field('PEVC'),
            'related_company_options':                  udf_field('Related Company'),
            # Hardcoded (not in UDF)
            'quoted_unquoted_options':                  quoted_unquoted_options,
            # Reference data
            'issuers':    ref_results.get('issuers', []),
            'countries':  ref_results.get('countries', []),
            'currencies': ref_results.get('currencies', []),
        }


# Create singleton instance
security_dropdown_service = SecurityDropdownService()
