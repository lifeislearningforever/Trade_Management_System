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
    # Field names match the Excel spreadsheet provided
    # ==========================================================================

    def get_exchange_codes(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Exchange Code dropdown options (field_name='Exchange Code')"""
        options = self.repository.get_udf_options_by_field_name('Exchange Code', 'SECURITY')
        self._log_dropdown_fetch('exchange_code', len(options), user)
        return options

    def get_country_of_issue_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Issue dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Country of Issue', 'SECURITY')
        self._log_dropdown_fetch('country_of_issue', len(options), user)
        return options

    def get_security_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Security Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Security Type', 'SECURITY')
        self._log_dropdown_fetch('security_type', len(options), user)
        return options

    def get_investment_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Investment Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('investment type', 'SECURITY')
        self._log_dropdown_fetch('investment_type', len(options), user)
        return options

    def get_issuer_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Issuer Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Issuer Type', 'SECURITY')
        self._log_dropdown_fetch('issuer_type', len(options), user)
        return options

    def get_basel_iv_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BASEL IV - FUND dropdown options"""
        options = self.repository.get_udf_options_by_field_name('BASEL IV - FUND', 'SECURITY')
        self._log_dropdown_fetch('basel_iv_fund', len(options), user)
        return options

    def get_business_unit_head_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Business Unit Head (BSU) dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Business Unit Head (BSU)', 'SECURITY')
        self._log_dropdown_fetch('business_unit_head', len(options), user)
        return options

    def get_core_non_core_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Core/Non-core dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Core/ Non-core', 'SECURITY')
        self._log_dropdown_fetch('core_non_core', len(options), user)
        return options

    def get_fund_index_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Fund / Index Fund dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Fund / Index Fund', 'SECURITY')
        self._log_dropdown_fetch('fund_index_fund', len(options), user)
        return options

    def get_investment_type_mas610_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Investment type (MAS610) dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Investment type', 'SECURITY')
        self._log_dropdown_fetch('investment_type_mas610', len(options), user)
        return options

    def get_management_limit_classification_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Management Limit classification dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Management Limit classification', 'SECURITY')
        self._log_dropdown_fetch('management_limit_classification', len(options), user)
        return options

    def get_mas_643_entity_type_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get MAS 643 Entity Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('MAS 643 Entity Type', 'SECURITY')
        self._log_dropdown_fetch('mas_643_entity_type', len(options), user)
        return options

    def get_person_in_charge_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Person In charge (PIC) dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Person In charge (PIC)', 'SECURITY')
        self._log_dropdown_fetch('person_in_charge', len(options), user)
        return options

    def get_pevc_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get PEVC dropdown options"""
        options = self.repository.get_udf_options_by_field_name('PEVC', 'SECURITY')
        self._log_dropdown_fetch('pevc', len(options), user)
        return options

    def get_s32_representative_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get S32 Representative dropdown options"""
        options = self.repository.get_udf_options_by_field_name('S32 Representative', 'SECURITY')
        self._log_dropdown_fetch('s32_representative', len(options), user)
        return options

    def get_substantial_gt_10_percent_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Substantial >10% dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Substantial >10%', 'SECURITY')
        self._log_dropdown_fetch('substantial_gt_10_percent', len(options), user)
        return options

    def get_relative_index_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get relative index dropdown options"""
        options = self.repository.get_udf_options_by_field_name('relative index', 'SECURITY')
        self._log_dropdown_fetch('relative_index', len(options), user)
        return options

    def get_fin_non_fin_ind_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get fin/non-fin IND dropdown options"""
        options = self.repository.get_udf_options_by_field_name('fin/non-fin IND', 'SECURITY')
        self._log_dropdown_fetch('fin_non_fin_ind', len(options), user)
        return options

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

    def get_quoted_unquoted_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Quoted/Unquoted dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Quoted/Unquoted', 'SECURITY')
        self._log_dropdown_fetch('quoted_unquoted', len(options), user)
        return options

    def get_record_type_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Record Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('Record Type', 'SECURITY')
        self._log_dropdown_fetch('record_type', len(options), user)
        return options

    def get_pevc_s32_devest_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get PEVC/S32/Devest dropdown options"""
        options = self.repository.get_udf_options_by_field_name('PEVC_S32_DEVEST', 'SECURITY')
        self._log_dropdown_fetch('pevc_s32_devest', len(options), user)
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

        Returns:
            Dictionary containing all dropdown lists
        """
        logger.info(f"Fetching all security dropdown options for user: {user}")

        return {
            # UDF-based dropdowns (from Excel field names)
            'exchange_codes': self.get_exchange_codes(user),
            'country_of_issue_options': self.get_country_of_issue_options(user),
            'security_types': self.get_security_types(user),
            'investment_types': self.get_investment_types(user),
            'issuer_types': self.get_issuer_types(user),
            'basel_iv_fund_options': self.get_basel_iv_fund_options(user),
            'business_unit_head_options': self.get_business_unit_head_options(user),
            'core_non_core_options': self.get_core_non_core_options(user),
            'fund_index_fund_options': self.get_fund_index_fund_options(user),
            'investment_type_mas610_options': self.get_investment_type_mas610_options(user),
            'management_limit_classification_options': self.get_management_limit_classification_options(user),
            'mas_643_entity_type_options': self.get_mas_643_entity_type_options(user),
            'person_in_charge_options': self.get_person_in_charge_options(user),
            'pevc_options': self.get_pevc_options(user),
            's32_representative_options': self.get_s32_representative_options(user),
            'substantial_gt_10_percent_options': self.get_substantial_gt_10_percent_options(user),
            'relative_index_options': self.get_relative_index_options(user),
            'fin_non_fin_ind_options': self.get_fin_non_fin_ind_options(user),
            'industries': self.get_industries(user),
            'country_of_incorporation_options': self.get_country_of_incorporation_options(user),
            'quoted_unquoted_options': self.get_quoted_unquoted_options(user),
            'record_type_options': self.get_record_type_options(user),
            'pevc_s32_devest_options': self.get_pevc_s32_devest_options(user),

            # Reference data dropdowns
            'issuers': self.get_issuers(user),
            'countries': self.get_countries(user),
            'currencies': self.get_currencies(user),
            'markets': self.get_markets(user),
        }


# Create singleton instance
security_dropdown_service = SecurityDropdownService()
