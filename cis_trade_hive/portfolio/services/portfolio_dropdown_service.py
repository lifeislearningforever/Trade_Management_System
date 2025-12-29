"""
Portfolio Dropdown Service
Fetches dropdown options for portfolio form fields from UDF Options table in Kudu.

This service retrieves dropdown values from cis_udf_option table,
which acts as a centralized lookup table for all dropdown fields.
"""

from typing import List, Dict, Any
import logging
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class PortfolioDropdownService:
    """Service for fetching dropdown options for portfolio forms from UDF tables."""

    DATABASE = 'gmp_cis'
    UDF_OPTION_TABLE = 'cis_udf_option'
    UDF_DEFINITION_TABLE = 'cis_udf_definition'
    CURRENCY_TABLE = 'gmp_cis_sta_dly_currency'

    @staticmethod
    def _get_udf_options(field_name: str) -> List[str]:
        """
        Get dropdown options for a UDF field from cis_udf_option table.

        Args:
            field_name: The UDF field name (e.g., 'manager', 'account_group')

        Returns:
            List of active option values
        """
        try:
            # First get the UDF definition to find the udf_id
            def_query = f"""
            SELECT udf_id
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.UDF_DEFINITION_TABLE}
            WHERE field_name = '{field_name}'
              AND entity_type = 'PORTFOLIO'
              AND is_active = true
            LIMIT 1
            """
            def_results = impala_manager.execute_query(def_query, database=PortfolioDropdownService.DATABASE)

            if not def_results:
                logger.warning(f"No UDF definition found for field: {field_name}")
                return []

            udf_id = def_results[0].get('udf_id')

            # Get active options for this UDF
            opt_query = f"""
            SELECT option_value
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.UDF_OPTION_TABLE}
            WHERE udf_id = {udf_id}
              AND is_active = true
            ORDER BY display_order, option_value
            """
            results = impala_manager.execute_query(opt_query, database=PortfolioDropdownService.DATABASE)
            return [r.get('option_value') for r in results if r.get('option_value')]

        except Exception as e:
            logger.error(f"Error fetching UDF options for {field_name}: {str(e)}")
            return []

    @staticmethod
    def get_managers() -> List[str]:
        """
        Get list of portfolio managers from UDF options.

        Returns:
            List of manager names
        """
        return PortfolioDropdownService._get_udf_options('manager')

    @staticmethod
    def get_statuses() -> List[str]:
        """
        Get list of portfolio statuses from UDF options.

        Returns:
            List of status values
        """
        statuses = PortfolioDropdownService._get_udf_options('status')
        # Add default statuses if none exist
        if not statuses:
            statuses = ['ACTIVE', 'PENDING', 'CLOSED']
        return statuses

    @staticmethod
    def get_account_groups() -> List[str]:
        """
        Get list of account groups from UDF options.

        Returns:
            List of account group names
        """
        return PortfolioDropdownService._get_udf_options('account_group')

    @staticmethod
    def get_portfolio_groups() -> List[str]:
        """
        Get list of portfolio groups from UDF options.

        Returns:
            List of portfolio group names
        """
        return PortfolioDropdownService._get_udf_options('portfolio_group')

    @staticmethod
    def get_report_groups() -> List[str]:
        """
        Get list of report groups from UDF options.

        Returns:
            List of report group names
        """
        return PortfolioDropdownService._get_udf_options('report_group')

    @staticmethod
    def get_entity_groups() -> List[str]:
        """
        Get list of entity groups from UDF options.

        Returns:
            List of entity group names
        """
        return PortfolioDropdownService._get_udf_options('entity_group')

    @staticmethod
    def get_revaluation_statuses() -> List[str]:
        """
        Get list of revaluation statuses from UDF options.

        Returns:
            List of revaluation status values
        """
        statuses = PortfolioDropdownService._get_udf_options('revaluation_status')
        # Add default options if none exist
        if not statuses:
            statuses = ['Pending', 'Completed', 'Not Required']
        return statuses

    @staticmethod
    def get_currencies() -> List[Dict[str, str]]:
        """
        Get list of currencies from currency reference table.

        Returns:
            List of dictionaries with curr_symbol and curr_name
        """
        try:
            query = f"""
            SELECT DISTINCT `curr_symbol`, `curr_name`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.CURRENCY_TABLE}
            WHERE `curr_symbol` IS NOT NULL AND `curr_symbol` != ''
            ORDER BY `curr_symbol`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [
                {
                    'code': r.get('curr_symbol'),
                    'name': r.get('curr_name', r.get('curr_symbol'))
                }
                for r in results if r.get('curr_symbol')
            ]
        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []

    @staticmethod
    def get_all_dropdown_options() -> Dict[str, Any]:
        """
        Get all dropdown options for portfolio form.

        Returns:
            Dictionary with all dropdown options
        """
        return {
            'managers': PortfolioDropdownService.get_managers(),
            'statuses': PortfolioDropdownService.get_statuses(),
            'account_groups': PortfolioDropdownService.get_account_groups(),
            'portfolio_groups': PortfolioDropdownService.get_portfolio_groups(),
            'report_groups': PortfolioDropdownService.get_report_groups(),
            'entity_groups': PortfolioDropdownService.get_entity_groups(),
            'revaluation_statuses': PortfolioDropdownService.get_revaluation_statuses(),
            'currencies': PortfolioDropdownService.get_currencies(),
        }


# Singleton instance
portfolio_dropdown_service = PortfolioDropdownService()
