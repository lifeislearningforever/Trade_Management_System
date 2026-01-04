"""
Security Dropdown Service

Provides dropdown data for security forms from:
- UDF system (entity_type='SECURITY')
- Reference data tables (counterparty, country, currency)

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
    COUNTERPARTY_TABLE = 'gmp_cis_sta_dly_counterparty'
    COUNTRY_TABLE = 'gmp_cis_sta_dly_country'
    CURRENCY_TABLE = 'gmp_cis_sta_dly_currency'

    @staticmethod
    def get_udf_options_by_field_name(field_name: str, entity_type: str = 'SECURITY') -> List[Dict[str, str]]:
        """
        Get UDF dropdown options for a specific field from simplified single table.

        Args:
            field_name: UDF field code/name (stored in 'label' column)
            entity_type: Entity type (default: SECURITY)

        Returns:
            List of option dictionaries with 'value' key
        """
        try:
            # Query from single cis_udf_field table
            # Note: 'label' column contains field_code, 'field_name' column contains option_value
            query = f"""
            SELECT DISTINCT field_name as option_value
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.UDF_FIELD_TABLE}
            WHERE label = '{field_name}'
              AND entity_type = '{entity_type}'
              AND is_active = true
            ORDER BY field_name
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                logger.warning(f"UDF field not found: {field_name} for entity {entity_type}")
                return []

            return [{'value': row.get('option_value', '')} for row in result]

        except Exception as e:
            logger.error(f"Error fetching UDF options for {field_name}: {str(e)}")
            return []

    @staticmethod
    def get_issuers() -> List[Dict[str, str]]:
        """
        Get issuers from counterparty table where is_counterparty_issuer='Y'.

        Returns:
            List of issuer dictionaries with 'name' key
        """
        try:
            query = f"""
            SELECT counterparty_name
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.COUNTERPARTY_TABLE}
            WHERE is_counterparty_issuer = 'Y'
            ORDER BY counterparty_name
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'name': row.get('counterparty_name', '')} for row in result]

        except Exception as e:
            logger.error(f"Error fetching issuers: {str(e)}")
            return []

    @staticmethod
    def get_countries() -> List[Dict[str, str]]:
        """
        Get countries from country table.

        Returns:
            List of country dictionaries with 'code' and 'name' keys
        """
        try:
            query = f"""
            SELECT label, full_name
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.COUNTRY_TABLE}
            ORDER BY full_name
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'code': row.get('label', ''), 'name': row.get('full_name', '')} for row in result]

        except Exception as e:
            logger.error(f"Error fetching countries: {str(e)}")
            return []

    @staticmethod
    def get_currencies() -> List[Dict[str, str]]:
        """
        Get currencies from currency table.

        Returns:
            List of currency dictionaries with 'code' and 'name' keys
        """
        try:
            query = f"""
            SELECT iso_code, curr_name
            FROM {SecurityDropdownRepository.DATABASE}.{SecurityDropdownRepository.CURRENCY_TABLE}
            ORDER BY iso_code
            """

            result = impala_manager.execute_query(query, database=SecurityDropdownRepository.DATABASE)

            if not result:
                return []

            return [{'code': row.get('iso_code', ''), 'name': row.get('curr_name', '')} for row in result]

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []


class SecurityDropdownService:
    """Service for providing dropdown data with audit logging"""

    def __init__(self, repository=None, audit_repo=None):
        self.repository = repository or SecurityDropdownRepository()
        self.audit_repo = audit_repo or AuditLogKuduRepository()

    def _log_dropdown_fetch(self, field_name: str, options_count: int, user: str = 'SYSTEM'):
        """Log dropdown fetch to audit trail"""
        try:
            self.audit_repo.log_action(
                user_id=user,
                username=user,
                action_type='VIEW',
                entity_type='SECURITY_DROPDOWN',
                entity_name=field_name,
                action_description=f'Fetched {options_count} options for {field_name}',
                status='SUCCESS'
            )
        except Exception as e:
            logger.error(f"Error logging dropdown fetch: {str(e)}")

    # UDF-based dropdowns (entity_type='SECURITY')

    def get_industries(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Industry dropdown options"""
        options = self.repository.get_udf_options_by_field_name('industry', 'SECURITY')
        self._log_dropdown_fetch('industry', len(options), user)
        return options

    def get_country_of_incorporation_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Incorporation dropdown options"""
        options = self.repository.get_udf_options_by_field_name('country_of_incorporation', 'SECURITY')
        self._log_dropdown_fetch('country_of_incorporation', len(options), user)
        return options

    def get_quoted_unquoted_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Quoted/Unquoted dropdown options"""
        options = self.repository.get_udf_options_by_field_name('quoted_unquoted', 'SECURITY')
        self._log_dropdown_fetch('quoted_unquoted', len(options), user)
        return options

    def get_security_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Security Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('security_type', 'SECURITY')
        self._log_dropdown_fetch('security_type', len(options), user)
        return options

    def get_investment_types(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Investment Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('investment_type', 'SECURITY')
        self._log_dropdown_fetch('investment_type', len(options), user)
        return options

    def get_price_sources(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Price Source dropdown options"""
        options = self.repository.get_udf_options_by_field_name('price_source', 'SECURITY')
        self._log_dropdown_fetch('price_source', len(options), user)
        return options

    def get_country_of_issue_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Issue dropdown options"""
        options = self.repository.get_udf_options_by_field_name('country_of_issue', 'SECURITY')
        self._log_dropdown_fetch('country_of_issue', len(options), user)
        return options

    def get_country_of_primary_exchange_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Country of Primary Exchange dropdown options"""
        options = self.repository.get_udf_options_by_field_name('country_of_primary_exchange', 'SECURITY')
        self._log_dropdown_fetch('country_of_primary_exchange', len(options), user)
        return options

    def get_bwciif_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BWCIIF dropdown options"""
        options = self.repository.get_udf_options_by_field_name('bwciif', 'SECURITY')
        self._log_dropdown_fetch('bwciif', len(options), user)
        return options

    def get_bwciif_others_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get BWCIIF Others dropdown options"""
        options = self.repository.get_udf_options_by_field_name('bwciif_others', 'SECURITY')
        self._log_dropdown_fetch('bwciif_others', len(options), user)
        return options

    def get_issuer_type_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Issuer Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('issuer_type', 'SECURITY')
        self._log_dropdown_fetch('issuer_type', len(options), user)
        return options

    def get_approved_s32_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Approved S32 dropdown options"""
        options = self.repository.get_udf_options_by_field_name('approved_s32', 'SECURITY')
        self._log_dropdown_fetch('approved_s32', len(options), user)
        return options

    def get_basel_iv_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Basel IV Fund dropdown options"""
        options = self.repository.get_udf_options_by_field_name('basel_iv_fund', 'SECURITY')
        self._log_dropdown_fetch('basel_iv_fund', len(options), user)
        return options

    def get_business_unit_head_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Business Unit Head dropdown options"""
        options = self.repository.get_udf_options_by_field_name('business_unit_head', 'SECURITY')
        self._log_dropdown_fetch('business_unit_head', len(options), user)
        return options

    def get_core_noncore_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Core/Non-core dropdown options"""
        options = self.repository.get_udf_options_by_field_name('core_noncore', 'SECURITY')
        self._log_dropdown_fetch('core_noncore', len(options), user)
        return options

    def get_fund_index_fund_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Fund/Index Fund dropdown options"""
        options = self.repository.get_udf_options_by_field_name('fund_index_fund', 'SECURITY')
        self._log_dropdown_fetch('fund_index_fund', len(options), user)
        return options

    def get_management_limit_classification_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Management Limit Classification dropdown options"""
        options = self.repository.get_udf_options_by_field_name('management_limit_classification', 'SECURITY')
        self._log_dropdown_fetch('management_limit_classification', len(options), user)
        return options

    def get_mas_643_entity_type_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get MAS 643 Entity Type dropdown options"""
        options = self.repository.get_udf_options_by_field_name('mas_643_entity_type', 'SECURITY')
        self._log_dropdown_fetch('mas_643_entity_type', len(options), user)
        return options

    def get_person_in_charge_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Person In Charge dropdown options"""
        options = self.repository.get_udf_options_by_field_name('person_in_charge', 'SECURITY')
        self._log_dropdown_fetch('person_in_charge', len(options), user)
        return options

    def get_substantial_10_pct_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Substantial >10% dropdown options"""
        options = self.repository.get_udf_options_by_field_name('substantial_10_pct', 'SECURITY')
        self._log_dropdown_fetch('substantial_10_pct', len(options), user)
        return options

    def get_relative_index_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Relative Index dropdown options"""
        options = self.repository.get_udf_options_by_field_name('relative_index', 'SECURITY')
        self._log_dropdown_fetch('relative_index', len(options), user)
        return options

    def get_fin_nonfin_ind_options(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Fin/Non-fin IND dropdown options"""
        options = self.repository.get_udf_options_by_field_name('fin_nonfin_ind', 'SECURITY')
        self._log_dropdown_fetch('fin_nonfin_ind', len(options), user)
        return options

    # Reference data dropdowns

    def get_issuers(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """Get Issuer dropdown options from counterparty table"""
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

    # Aggregate method to get all dropdown options at once

    def get_all_dropdown_options(self, user: str = 'SYSTEM') -> Dict[str, Any]:
        """
        Get all dropdown options for security forms.

        Returns:
            Dictionary containing all dropdown lists
        """
        return {
            # UDF-based dropdowns
            'industries': self.get_industries(user),
            'country_of_incorporation_options': self.get_country_of_incorporation_options(user),
            'quoted_unquoted_options': self.get_quoted_unquoted_options(user),
            'security_types': self.get_security_types(user),
            'investment_types': self.get_investment_types(user),
            'price_sources': self.get_price_sources(user),
            'country_of_issue_options': self.get_country_of_issue_options(user),
            'country_of_primary_exchange_options': self.get_country_of_primary_exchange_options(user),
            'bwciif_options': self.get_bwciif_options(user),
            'bwciif_others_options': self.get_bwciif_others_options(user),
            'issuer_type_options': self.get_issuer_type_options(user),
            'approved_s32_options': self.get_approved_s32_options(user),
            'basel_iv_fund_options': self.get_basel_iv_fund_options(user),
            'business_unit_head_options': self.get_business_unit_head_options(user),
            'core_noncore_options': self.get_core_noncore_options(user),
            'fund_index_fund_options': self.get_fund_index_fund_options(user),
            'management_limit_classification_options': self.get_management_limit_classification_options(user),
            'mas_643_entity_type_options': self.get_mas_643_entity_type_options(user),
            'person_in_charge_options': self.get_person_in_charge_options(user),
            'substantial_10_pct_options': self.get_substantial_10_pct_options(user),
            'relative_index_options': self.get_relative_index_options(user),
            'fin_nonfin_ind_options': self.get_fin_nonfin_ind_options(user),

            # Reference data dropdowns
            'issuers': self.get_issuers(user),
            'countries': self.get_countries(user),
            'currencies': self.get_currencies(user),
        }


# Create singleton instance
security_dropdown_service = SecurityDropdownService()
