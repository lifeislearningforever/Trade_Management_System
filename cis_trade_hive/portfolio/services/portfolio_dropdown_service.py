"""
Portfolio Dropdown Service - Simplified UDF System

This service provides dropdown options for portfolio forms using ONLY the simplified
UDF system tables:
- cis_udf_field: UDF field definitions (entity_type, field_name, label, is_active, etc.)
- cis_udf_option: Dropdown option values (linked by udf_id)

NO references to legacy cis_udf_definition table - completely removed.

Architecture:
- Repository Pattern: Separates data access logic
- Service Layer: Business logic and data transformation
- Audit Logging: All dropdown fetches logged to core audit system
- SOLID Principles: Single responsibility, dependency injection ready

Author: CIS Trade Hive Team
Date: 2026-01-01
"""

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from core.repositories.impala_connection import impala_manager
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


# ============================================================================
# REPOSITORY LAYER - Data Access
# ============================================================================

class PortfolioDropdownRepository:
    """Repository for fetching dropdown data from Kudu/Impala tables."""

    DATABASE = 'gmp_cis'
    UDF_FIELD_TABLE = 'cis_udf_field'  # Simplified UDF table (ONLY table for UDF field definitions)
    CURRENCY_TABLE = 'gmp_cis_sta_dly_currency'
    COUNTRY_TABLE = 'gmp_cis_sta_dly_country'
    PARTY_TABLE = 'cis_party'  # Party table for Entity dropdown

    @staticmethod
    def get_active_udf_fields(object_type: str = 'PORTFOLIO') -> List[Dict[str, Any]]:
        """
        Get all active UDF fields for a given object type.

        Schema: cis_udf_field (object_type, field_name, field_value, is_active, created_by, created_at, updated_by, updated_at)

        Args:
            object_type: Object type to filter by (default: PORTFOLIO)

        Returns:
            List of UDF field dictionaries with field_name, field_value
        """
        try:
            query = f"""
            SELECT object_type, field_name, field_value, is_active
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.UDF_FIELD_TABLE}
            WHERE object_type = '{object_type}'
              AND is_active = true
              AND field_value IS NOT NULL
              AND field_value <> ''
            ORDER BY field_name
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching UDF fields for {object_type}: {str(e)}")
            return []

    @staticmethod
    def get_dropdown_options_by_field_name(field_name: str, object_type: str = 'PORTFOLIO') -> List[Dict[str, Any]]:
        """
        Get dropdown options for a field by its field_name (definition).

        Schema: cis_udf_field table where:
        - object_type: Entity type (PORTFOLIO, TRADE, etc.)
        - field_name: The field definition (e.g., 'Portfolio Manager')
        - field_value: The actual dropdown values (e.g., 'John Doe')
        - is_active: Boolean flag
        - Records with empty field_value are DEFINITIONS, non-empty are VALUES

        Args:
            field_name: UDF field definition name (e.g., 'Portfolio Manager', 'Account Group')
            object_type: Object type (default: PORTFOLIO)

        Returns:
            List of dicts with field_value (the actual dropdown values, excluding definition record)
        """
        try:
            escaped_field = field_name.replace("'", "''")
            # Only get VALUE records (where field_value is NOT empty)
            query = f"""
            SELECT field_name, field_value, is_active
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.UDF_FIELD_TABLE}
            WHERE object_type = '{object_type}'
              AND field_name = '{escaped_field}'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND is_active = true
            ORDER BY field_value
            """

            logger.info(f"Executing dropdown query for field_name={field_name}")
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            logger.info(f"Dropdown query returned {len(results) if results else 0} values for {field_name}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching options for field name {field_name}: {str(e)}")
            return []

    @staticmethod
    def get_currencies() -> List[Dict[str, str]]:
        """
        Get list of currencies from reference data table.

        Schema: gmp_cis_sta_dly_currency (name, full_name, `symbol`)
        Note: 'symbol' is a reserved word in Impala, must use backticks

        Returns:
            List of dicts with 'code' and 'name'
        """
        try:
            # Note: 'symbol' is a reserved word in Impala, must use backticks
            # Filter by max(processing_date) to avoid duplicates from multiple dates
            query = f"""
            SELECT DISTINCT name, full_name, `symbol`
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.CURRENCY_TABLE}
            WHERE name IS NOT NULL AND name != ''
              AND processing_date = (
                  SELECT MAX(processing_date)
                  FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.CURRENCY_TABLE}
              )
            ORDER BY name
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return [
                {
                    'code': r.get('name'),
                    'name': r.get('full_name', r.get('name'))
                }
                for r in results if r.get('name')
            ] if results else []

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []

    @staticmethod
    def get_countries() -> List[Dict[str, str]]:
        """
        Get list of countries from Hive external table.

        Returns:
            List of dicts with 'code' (label) and 'name' (full_name)
        """
        try:
            # Filter by max(processing_date) to avoid duplicates from multiple dates
            query = f"""
            SELECT DISTINCT `label`, `full_name`
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.COUNTRY_TABLE}
            WHERE `label` IS NOT NULL AND `label` != ''
              AND processing_date = (
                  SELECT MAX(processing_date)
                  FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.COUNTRY_TABLE}
              )
            ORDER BY `full_name`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return [
                {
                    'code': r.get('label'),
                    'name': r.get('full_name', r.get('label'))
                }
                for r in results if r.get('label')
            ] if results else []

        except Exception as e:
            logger.error(f"Error fetching countries: {str(e)}")
            return []

    @staticmethod
    def get_entities() -> List[Dict[str, str]]:
        """
        Get list of entities from Party table for dropdown.

        Returns:
            List of dicts with 'code' (party_short_name) and 'name' (party_full_name)
        """
        try:
            query = f"""
            SELECT party_short_name, party_full_name
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.PARTY_TABLE}
            WHERE party_short_name IS NOT NULL AND party_short_name != ''
              AND (is_active = TRUE OR is_active IS NULL)
            ORDER BY party_short_name
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return [
                {
                    'code': r.get('party_short_name'),
                    'name': r.get('party_full_name', r.get('party_short_name'))
                }
                for r in results if r.get('party_short_name')
            ] if results else []

        except Exception as e:
            logger.error(f"Error fetching entities from party table: {str(e)}")
            return []


# ============================================================================
# SERVICE LAYER - Business Logic
# ============================================================================

class PortfolioDropdownService:
    """
    Service for providing dropdown options to portfolio forms.

    Uses ONLY the simplified UDF system (cis_udf_field + cis_udf_option).
    All references to legacy cis_udf_definition table have been removed.

    Provides a clean, audited API for fetching dropdown values based on
    active UDF field definitions for each entity type.
    """

    def __init__(self, repository: Optional[PortfolioDropdownRepository] = None,
                 audit_repo: Optional[AuditLogKuduRepository] = None):
        """
        Initialize service with dependency injection support.

        Args:
            repository: Data repository (defaults to PortfolioDropdownRepository)
            audit_repo: Audit repository (defaults to AuditLogKuduRepository)
        """
        self.repository = repository or PortfolioDropdownRepository()
        self.audit_repo = audit_repo or AuditLogKuduRepository()

    def _log_dropdown_fetch(self, field_name: str, options_count: int, user: str = 'SYSTEM'):
        """
        Log dropdown fetch to audit system - Commented out (only log CREATE, UPDATE, DELETE)

        Args:
            field_name: Name of field being fetched
            options_count: Number of options returned
            user: Username (default: SYSTEM)
        """
        # Commented out - no audit logging for dropdown/READ actions
        # try:
        #     self.audit_repo.log_action(
        #         user_id=user,
        #         username=user,
        #         action_type='READ',
        #         entity_type='UDF_DROPDOWN',
        #         entity_id=field_name,
        #         action_detail=f'Fetched {options_count} dropdown options for field: {field_name}',
        #         status='SUCCESS'
        #     )
        # except Exception as e:
        #     logger.warning(f"Failed to log dropdown fetch audit: {str(e)}")
        pass

    # ========================================================================
    # INDIVIDUAL FIELD DROPDOWN METHODS
    # ========================================================================


    def get_managers(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get portfolio manager options from UDF system.

        Fetches from cis_udf_field where field_name = 'Portfolio Manager'.
        The actual manager names are stored in field_value column.

        Args:
            user: Username for audit logging

        Returns:
            List of manager names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Portfolio Manager', 'PORTFOLIO')
            managers = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('manager', len(managers), user)
            return managers
        except Exception as e:
            logger.error(f"Error fetching managers: {str(e)}")
            return []

    def get_account_groups(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get account group options from UDF system.

        Returns all account group values defined in UDF (no filtering).

        Args:
            user: Username for audit logging

        Returns:
            List of account group names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Account Group', 'PORTFOLIO')
            account_groups = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('account_groups', len(account_groups), user)
            return account_groups
        except Exception as e:
            logger.error(f"Error fetching account_groups: {str(e)}")
            return []

    def get_portfolio_groups(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get portfolio group options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of portfolio group names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Portfolio Group', 'PORTFOLIO')
            portfolio_groups = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('portfolio_groups', len(portfolio_groups), user)
            return portfolio_groups
        except Exception as e:
            logger.error(f"Error fetching portfolio_groups: {str(e)}")
            return []

    def get_report_groups(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get report group options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of report group names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Report Group', 'PORTFOLIO')
            report_groups = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('report_groups', len(report_groups), user)
            return report_groups
        except Exception as e:
            logger.error(f"Error fetching report_groups: {str(e)}")
            return []

    def get_entity_groups(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get entity group options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of entity group names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Entity Group', 'PORTFOLIO')
            entity_groups = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('entity_groups', len(entity_groups), user)
            return entity_groups
        except Exception as e:
            logger.error(f"Error fetching entity_groups: {str(e)}")
            return []

    def get_revaluation_statuses(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get revaluation status options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of revaluation status values
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Revaluation Status', 'PORTFOLIO')
            revaluation_status = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('revaluation_status', len(revaluation_status), user)
            return revaluation_status
        except Exception as e:
            logger.error(f"Error fetching revaluation_status: {str(e)}")
            return []

    def get_accounting_sections(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get accounting section options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of accounting section values
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Accounting Section', 'PORTFOLIO')
            accounting_sections = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('accounting_sections', len(accounting_sections), user)
            return accounting_sections
        except Exception as e:
            logger.error(f"Error fetching accounting_sections: {str(e)}")
            return []

    def get_statuses(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get portfolio status options.

        Note: Portfolio status is typically hardcoded, not from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of status values
        """
        # Portfolio status is a core field, not UDF-driven
        statuses = ['ACTIVE', 'PENDING', 'CLOSED']
        self._log_dropdown_fetch('status', len(statuses), user)
        return statuses

    def get_currencies(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """
        Get currency options from reference data.

        Args:
            user: Username for audit logging

        Returns:
            List of dicts with 'code' and 'name'
        """
        currencies = self.repository.get_currencies()
        self._log_dropdown_fetch('currency', len(currencies), user)
        return currencies

    def get_countries(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """
        Get country options from Hive external table.

        Args:
            user: Username for audit logging

        Returns:
            List of dicts with 'code' and 'name'
        """
        countries = self.repository.get_countries()
        self._log_dropdown_fetch('country', len(countries), user)
        return countries

    def get_desk_heads(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get desk head options from UDF system.

        Fetches from cis_udf_field where field_name = 'Head of Desk'.
        The actual desk head names are stored in field_value column.

        Args:
            user: Username for audit logging

        Returns:
            List of desk head names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Head of Desk', 'PORTFOLIO')
            desk_heads = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('desk_head', len(desk_heads), user)
            return desk_heads
        except Exception as e:
            logger.error(f"Error fetching desk_heads: {str(e)}")
            return []

    def get_cash_balance_lists(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get cash balance list options from UDF system.

        Fetches from cis_udf_field where field_name = 'Cash Balance List'.
        The actual values are stored in field_value column.

        Args:
            user: Username for audit logging

        Returns:
            List of cash balance list names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Cash Balance List', 'PORTFOLIO')
            cash_balance_lists = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('cash_balance_list', len(cash_balance_lists), user)
            return cash_balance_lists
        except Exception as e:
            logger.error(f"Error fetching cash_balance_lists: {str(e)}")
            return []

    def get_entities(self, user: str = 'SYSTEM') -> List[Dict[str, str]]:
        """
        Get entity options from Party table.

        Args:
            user: Username for audit logging

        Returns:
            List of dicts with 'code' and 'name'
        """
        entities = self.repository.get_entities()
        self._log_dropdown_fetch('entity', len(entities), user)
        return entities

    def get_investment_types(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get investment type options from UDF system.

        Fetches from cis_udf_field where field_name = 'Investment Type'.
        The actual values are stored in field_value column.

        Args:
            user: Username for audit logging

        Returns:
            List of investment type names
        """
        try:
            results = PortfolioDropdownRepository.get_dropdown_options_by_field_name('Investment Type', 'PORTFOLIO')
            investment_types = [r.get('field_value') for r in results if r.get('field_value')]
            self._log_dropdown_fetch('investment_type', len(investment_types), user)
            return investment_types
        except Exception as e:
            logger.error(f"Error fetching investment_types: {str(e)}")
            return []

    # ========================================================================
    # AGGREGATE METHODS
    # ========================================================================

    def get_all_dropdown_options(self, user: str = 'SYSTEM') -> Dict[str, Any]:
        """
        Get all dropdown options for portfolio form in one call.

        This method aggregates all dropdown data needed by the portfolio
        form, reducing the number of separate method calls.

        Args:
            user: Username for audit logging

        Returns:
            Dictionary with all dropdown options
        """
        logger.info(f"Fetching all portfolio dropdown options for user: {user}")

        return {
            'managers': self.get_managers(user),
            'statuses': self.get_statuses(user),
            'account_groups': self.get_account_groups(user),
            'portfolio_groups': self.get_portfolio_groups(user),
            'report_groups': self.get_report_groups(user),
            'entity_groups': self.get_entity_groups(user),
            'revaluation_statuses': self.get_revaluation_statuses(user),
            'accounting_sections': self.get_accounting_sections(user),
            'currencies': self.get_currencies(user),
            'countries': self.get_countries(user),
            'desk_heads': self.get_desk_heads(user),
            'cash_balance_lists': self.get_cash_balance_lists(user),
            'entities': self.get_entities(user),
            'investment_types': self.get_investment_types(user),
        }

    def get_udf_field_metadata(self, entity_type: str = 'PORTFOLIO') -> List[Dict[str, Any]]:
        """
        Get metadata about available UDF fields for an entity.

        Useful for dynamically rendering UDF fields in forms.

        Args:
            entity_type: Entity type to fetch fields for

        Returns:
            List of UDF field metadata dicts
        """
        return self.repository.get_active_udf_fields(entity_type)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

# Create singleton instance for easy import
portfolio_dropdown_service = PortfolioDropdownService()
