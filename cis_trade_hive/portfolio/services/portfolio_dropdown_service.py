"""
Portfolio Dropdown Service
Fetches dropdown options for portfolio form fields from Kudu tables.
"""

from typing import List, Dict, Any
import logging
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class PortfolioDropdownService:
    """Service for fetching dropdown options for portfolio forms."""

    DATABASE = 'gmp_cis'
    PORTFOLIO_TABLE = 'cis_portfolio'
    CURRENCY_TABLE = 'gmp_cis_sta_dly_currency'

    @staticmethod
    def get_managers() -> List[str]:
        """
        Get list of unique portfolio managers.

        Returns:
            List of manager names
        """
        try:
            query = f"""
            SELECT DISTINCT `manager`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `manager` IS NOT NULL AND `manager` != ''
            ORDER BY `manager`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('manager') for r in results if r.get('manager')]
        except Exception as e:
            logger.error(f"Error fetching managers: {str(e)}")
            return []

    @staticmethod
    def get_statuses() -> List[str]:
        """
        Get list of unique portfolio statuses.

        Returns:
            List of status values
        """
        try:
            query = f"""
            SELECT DISTINCT `status`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `status` IS NOT NULL AND `status` != ''
            ORDER BY `status`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('status') for r in results if r.get('status')]
        except Exception as e:
            logger.error(f"Error fetching statuses: {str(e)}")
            return ['Active', 'Inactive']  # Default fallback

    @staticmethod
    def get_account_groups() -> List[str]:
        """
        Get list of unique account groups.

        Returns:
            List of account group names
        """
        try:
            query = f"""
            SELECT DISTINCT `account_group`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `account_group` IS NOT NULL AND `account_group` != ''
            ORDER BY `account_group`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('account_group') for r in results if r.get('account_group')]
        except Exception as e:
            logger.error(f"Error fetching account groups: {str(e)}")
            return []

    @staticmethod
    def get_portfolio_groups() -> List[str]:
        """
        Get list of unique portfolio groups.

        Returns:
            List of portfolio group names
        """
        try:
            query = f"""
            SELECT DISTINCT `portfolio_group`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `portfolio_group` IS NOT NULL AND `portfolio_group` != ''
            ORDER BY `portfolio_group`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('portfolio_group') for r in results if r.get('portfolio_group')]
        except Exception as e:
            logger.error(f"Error fetching portfolio groups: {str(e)}")
            return []

    @staticmethod
    def get_report_groups() -> List[str]:
        """
        Get list of unique report groups.

        Returns:
            List of report group names
        """
        try:
            query = f"""
            SELECT DISTINCT `report_group`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `report_group` IS NOT NULL AND `report_group` != ''
            ORDER BY `report_group`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('report_group') for r in results if r.get('report_group')]
        except Exception as e:
            logger.error(f"Error fetching report groups: {str(e)}")
            return []

    @staticmethod
    def get_entity_groups() -> List[str]:
        """
        Get list of unique entity groups.

        Returns:
            List of entity group names
        """
        try:
            query = f"""
            SELECT DISTINCT `entity_group`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `entity_group` IS NOT NULL AND `entity_group` != ''
            ORDER BY `entity_group`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            return [r.get('entity_group') for r in results if r.get('entity_group')]
        except Exception as e:
            logger.error(f"Error fetching entity groups: {str(e)}")
            return []

    @staticmethod
    def get_revaluation_statuses() -> List[str]:
        """
        Get list of unique revaluation statuses.

        Returns:
            List of revaluation status values
        """
        try:
            query = f"""
            SELECT DISTINCT `revaluation_status`
            FROM {PortfolioDropdownService.DATABASE}.{PortfolioDropdownService.PORTFOLIO_TABLE}
            WHERE `revaluation_status` IS NOT NULL AND `revaluation_status` != ''
            ORDER BY `revaluation_status`
            """
            results = impala_manager.execute_query(query, database=PortfolioDropdownService.DATABASE)
            statuses = [r.get('revaluation_status') for r in results if r.get('revaluation_status')]
            # Add default options if none exist
            if not statuses:
                statuses = ['Pending', 'Completed', 'Not Required']
            return statuses
        except Exception as e:
            logger.error(f"Error fetching revaluation statuses: {str(e)}")
            return ['Pending', 'Completed', 'Not Required']

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
