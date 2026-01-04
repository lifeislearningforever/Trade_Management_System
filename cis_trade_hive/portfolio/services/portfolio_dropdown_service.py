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

    @staticmethod
    def get_active_udf_fields(entity_type: str = 'PORTFOLIO') -> List[Dict[str, Any]]:
        """
        Get all active UDF fields for a given entity type.

        Args:
            entity_type: Entity type to filter by (default: PORTFOLIO)

        Returns:
            List of UDF field dictionaries with udf_id, field_name, label
        """
        try:
            query = f"""
            SELECT udf_id, field_name, label, is_required
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.UDF_FIELD_TABLE}
            WHERE entity_type = '{entity_type}'
              AND is_active = true
            ORDER BY field_name
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching UDF fields for {entity_type}: {str(e)}")
            return []

    @staticmethod
    def get_dropdown_options_for_field(udf_id: int) -> List[str]:
        """
        Get dropdown option values for a specific UDF field from legacy table.

        Args:
            udf_id: UDF field ID

        Returns:
            List of option values
        """
        try:
            query = f"""
            SELECT option_value
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.UDF_OPTION_TABLE}
            WHERE udf_id = {udf_id}
              AND is_active = true
            ORDER BY display_order, option_value
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return [r.get('option_value') for r in results if r.get('option_value')] if results else []

        except Exception as e:
            logger.error(f"Error fetching options for UDF ID {udf_id}: {str(e)}")
            return []

    @staticmethod
    def get_dropdown_options_by_field_name(field_name: str, entity_type: str = 'PORTFOLIO') -> List[str]:
        """
        Get dropdown options for a field by its field_name.

        Uses ONLY simplified UDF table: cis_udf_field -> cis_udf_option
        Joins on udf_id to fetch dropdown values for active UDF fields.

        Args:
            field_name: UDF field name (e.g., 'manager', 'account_group')
            entity_type: Entity type (default: PORTFOLIO)

        Returns:
            List of option values, ordered by display_order
        """
        try:
            # Two-table join: cis_udf_field -> cis_udf_option
            query = f""" SELECT f.field_name, f.entity_type, f.label, f.is_active FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.UDF_FIELD_TABLE} f WHERE f.entity_type = '{entity_type}' AND f.is_active = true ORDER BY f.field_name """

            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching options for field {field_name}: {str(e)}")
            return []

    @staticmethod
    def get_currencies() -> List[Dict[str, str]]:
        """
        Get list of currencies from reference data table.

        Returns:
            List of dicts with 'code' and 'name'
        """
        try:
            query = f"""
            SELECT DISTINCT `curr_symbol`, `curr_name`
            FROM {PortfolioDropdownRepository.DATABASE}.{PortfolioDropdownRepository.CURRENCY_TABLE}
            WHERE `curr_symbol` IS NOT NULL AND `curr_symbol` != ''
            ORDER BY `curr_symbol`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownRepository.DATABASE)
            return [
                {
                    'code': r.get('curr_symbol'),
                    'name': r.get('curr_name', r.get('curr_symbol'))
                }
                for r in results if r.get('curr_symbol')
            ] if results else []

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
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
        Log dropdown fetch to audit system.

        Args:
            field_name: Name of field being fetched
            options_count: Number of options returned
            user: Username (default: SYSTEM)
        """
        try:
            self.audit_repo.log_action(
                user_id=user,
                username=user,
                action_type='READ',
                entity_type='UDF_DROPDOWN',
                entity_id=field_name,
                action_detail=f'Fetched {options_count} dropdown options for field: {field_name}',
                status='SUCCESS'
            )
        except Exception as e:
            logger.warning(f"Failed to log dropdown fetch audit: {str(e)}")

    # ========================================================================
    # INDIVIDUAL FIELD DROPDOWN METHODS
    # ========================================================================


    def get_managers(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get portfolio manager field labels from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of manager names (labels)
        """
        try:
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            managers = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'manager' in r.get('label').lower()
            ]
            self._log_dropdown_fetch('manager', len(managers), user)
            return managers
        except Exception as e:
            logger.error(f"Error fetching managers: {str(e)}")
            return []

    def get_account_groups(self, user: str = 'SYSTEM') -> List[str]:
        """
        Get account group options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of account group names
        """
        try:
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            account_groups = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'account group' in r.get('label').lower()
            ]
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
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            portfolio_groups = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'portfolio group' in r.get('label').lower()
            ]
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
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            report_groups = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'report group' in r.get('label').lower()
            ]
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
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            entity_groups = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'entity group' in r.get('label').lower()
            ]
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
            results = self.repository.get_dropdown_options_by_field_name('PORTFOLIO')
            revaluation_status = [
                r.get('field_name')
                for r in results
                if r.get('label') and 'revaluation status' in r.get('label').lower()
            ]
            self._log_dropdown_fetch('revaluation_status', len(revaluation_status), user)
            return revaluation_status
        except Exception as e:
            logger.error(f"Error fetching revaluation_status: {str(e)}")
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
            'currencies': self.get_currencies(user),
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
