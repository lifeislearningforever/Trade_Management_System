"""
Equity Price Dropdown Service

Provides dropdown data with cascading logic for equity price forms.
Implements cascading: Currency → Security → ISIN

Author: CisTrade Team
Last Updated: 2026-01-04
"""

from typing import List, Dict, Any, Optional
import logging

from core.repositories.impala_connection import impala_manager
from udf.repositories.udf_hive_repository import udf_option_repository
from core.audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)


class EquityPriceDropdownService:
    """
    Service for providing dropdown options with cascading logic.

    Cascading Flow:
    1. User selects Currency → Filter Securities by currency_code
    2. User selects Security → Auto-populate ISIN from security
    3. Market dropdown from UDF
    """

    @staticmethod
    def get_currencies(user: str = 'SYSTEM') -> List[Dict[str, Any]]:
        """
        Get all available currencies from gmp_cis_sta_dly_currency.

        Args:
            user: Username for audit logging

        Returns:
            List of currency dictionaries with iso_code and curr_name
        """
        try:
            query = """
            SELECT DISTINCT
                iso_code,
                curr_name
            FROM gmp_cis.gmp_cis_sta_dly_currency
            WHERE iso_code IS NOT NULL
              AND curr_name IS NOT NULL
            ORDER BY curr_name
            """

            logger.info(f"Fetching currencies for user: {user}")
            results = impala_manager.execute_query(query, database='gmp_cis')

            # Log to audit
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=user,
                user_email='',
                action_type='DROPDOWN_FETCH',
                entity_type='EQUITY_PRICE',
                entity_name='Currency Dropdown',
                action_description=f'Fetched {len(results)} currencies for equity price dropdown',
                status='SUCCESS'
            )

            logger.info(f"Retrieved {len(results)} currencies")
            return results

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=user,
                user_email='',
                action_type='DROPDOWN_FETCH',
                entity_type='EQUITY_PRICE',
                entity_name='Currency Dropdown',
                action_description=f'Failed to fetch currencies: {str(e)}',
                status='FAILURE'
            )
            return []

    @staticmethod
    def get_securities_by_currency(
        currency_code: Optional[str] = None,
        user: str = 'SYSTEM'
    ) -> List[Dict[str, Any]]:
        """
        Get securities filtered by currency code (for cascading dropdown).

        Args:
            currency_code: Filter by currency (if None, returns all)
            user: Username for audit logging

        Returns:
            List of security dictionaries with security_id, security_name, isin, currency_code
        """
        try:
            # Build WHERE clause
            where_clauses = ["is_active = true"]

            if currency_code:
                escaped_currency = currency_code.replace("'", "\\'")
                where_clauses.append(f"currency_code = '{escaped_currency}'")

            where_clause = " AND ".join(where_clauses)

            query = f"""
            SELECT DISTINCT
                security_id,
                security_name,
                isin,
                currency_code
            FROM gmp_cis.cis_security
            WHERE {where_clause}
              AND security_name IS NOT NULL
            ORDER BY security_name
            LIMIT 1000
            """

            logger.info(f"Fetching securities for currency: {currency_code or 'ALL'} (user: {user})")
            results = impala_manager.execute_query(query, database='gmp_cis')

            # Log to audit
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=user,
                user_email='',
                action_type='DROPDOWN_FETCH',
                entity_type='EQUITY_PRICE',
                entity_name='Security Dropdown',
                action_description=f'Fetched {len(results)} securities for currency: {currency_code or "ALL"}',
                status='SUCCESS'
            )

            logger.info(f"Retrieved {len(results)} securities")
            return results

        except Exception as e:
            logger.error(f"Error fetching securities: {str(e)}")
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=user,
                user_email='',
                action_type='DROPDOWN_FETCH',
                entity_type='EQUITY_PRICE',
                entity_name='Security Dropdown',
                action_description=f'Failed to fetch securities: {str(e)}',
                status='FAILURE'
            )
            return []

    @staticmethod
    def get_security_details(
        security_id: Optional[int] = None,
        security_name: Optional[str] = None,
        user: str = 'SYSTEM'
    ) -> Optional[Dict[str, Any]]:
        """
        Get security details including ISIN (for auto-populating ISIN field).

        Args:
            security_id: Security ID
            security_name: Security name (alternative lookup)
            user: Username for audit logging

        Returns:
            Security details dictionary or None
        """
        try:
            where_clauses = ["is_active = true"]

            if security_id:
                where_clauses.append(f"security_id = {security_id}")
            elif security_name:
                escaped_name = security_name.replace("'", "\\'")
                where_clauses.append(f"security_name = '{escaped_name}'")
            else:
                logger.warning("No security_id or security_name provided")
                return None

            where_clause = " AND ".join(where_clauses)

            query = f"""
            SELECT
                security_id,
                security_name,
                isin,
                currency_code,
                ticker,
                security_type,
                investment_type
            FROM gmp_cis.cis_security
            WHERE {where_clause}
            LIMIT 1
            """

            logger.info(f"Fetching security details for: {security_id or security_name}")
            results = impala_manager.execute_query(query, database='gmp_cis')

            if results:
                logger.info(f"Retrieved security details: {results[0].get('security_name')}")
                return results[0]
            else:
                logger.warning(f"No security found for: {security_id or security_name}")
                return None

        except Exception as e:
            logger.error(f"Error fetching security details: {str(e)}")
            return None

    @staticmethod
    def get_markets(user: str = 'SYSTEM') -> List[str]:
        """
        Get market options from UDF system.

        Args:
            user: Username for audit logging

        Returns:
            List of market names
        """
        try:
            # Get markets from UDF with entity_type='EQUITY_PRICE' and label='market'
            udf_options = udf_option_repository.get_udf_options_by_entity_and_label(
                entity_type='EQUITY_PRICE',
                label='market'
            )

            if udf_options:
                markets = [opt.get('field_name') for opt in udf_options if opt.get('field_name')]
                logger.info(f"Retrieved {len(markets)} markets from UDF")

                # Log to audit
                audit_log_kudu_repository.log_action(
                    user_id='0',
                    username=user,
                    user_email='',
                    action_type='DROPDOWN_FETCH',
                    entity_type='EQUITY_PRICE',
                    entity_name='Market Dropdown',
                    action_description=f'Fetched {len(markets)} markets from UDF',
                    status='SUCCESS'
                )

                return markets
            else:
                logger.warning("No UDF markets found for EQUITY_PRICE.market - using defaults")
                # Fallback to common markets if UDF not configured
                default_markets = [
                    'NYSE', 'NASDAQ', 'SGX', 'LSE', 'HKEX',
                    'TSE', 'SSE', 'SZSE', 'ASX', 'BSE'
                ]

                audit_log_kudu_repository.log_action(
                    user_id='0',
                    username=user,
                    user_email='',
                    action_type='DROPDOWN_FETCH',
                    entity_type='EQUITY_PRICE',
                    entity_name='Market Dropdown',
                    action_description=f'Using default markets (UDF not configured): {len(default_markets)} markets',
                    status='SUCCESS'
                )

                return default_markets

        except Exception as e:
            logger.error(f"Error fetching markets: {str(e)}")
            audit_log_kudu_repository.log_action(
                user_id='0',
                username=user,
                user_email='',
                action_type='DROPDOWN_FETCH',
                entity_type='EQUITY_PRICE',
                entity_name='Market Dropdown',
                action_description=f'Failed to fetch markets: {str(e)}',
                status='FAILURE'
            )
            # Return default markets on error
            return ['NYSE', 'NASDAQ', 'SGX', 'LSE', 'HKEX', 'TSE', 'SSE', 'SZSE', 'ASX', 'BSE']

    @staticmethod
    def get_all_dropdown_options(user: str = 'SYSTEM') -> Dict[str, Any]:
        """
        Get all dropdown options in one call (for form initialization).

        Args:
            user: Username for audit logging

        Returns:
            Dictionary with all dropdown data:
            {
                'currencies': [...],
                'markets': [...],
                'securities': [...]  # All securities (unfiltered)
            }
        """
        try:
            logger.info(f"Fetching all dropdown options for user: {user}")

            currencies = EquityPriceDropdownService.get_currencies(user)
            markets = EquityPriceDropdownService.get_markets(user)
            securities = EquityPriceDropdownService.get_securities_by_currency(None, user)  # All securities

            result = {
                'currencies': currencies,
                'markets': markets,
                'securities': securities
            }

            logger.info(f"Fetched all dropdowns: {len(currencies)} currencies, "
                       f"{len(markets)} markets, {len(securities)} securities")

            return result

        except Exception as e:
            logger.error(f"Error fetching all dropdown options: {str(e)}")
            return {
                'currencies': [],
                'markets': [],
                'securities': []
            }


# Singleton instance
equity_price_dropdown_service = EquityPriceDropdownService()
