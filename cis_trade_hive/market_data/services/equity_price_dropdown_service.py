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
                iso_code as curr_name
            FROM gmp_cis.gmp_cis_sta_dly_currency
            WHERE iso_code IS NOT NULL
            ORDER BY iso_code
            """

            logger.info(f"Fetching currencies for user: {user}")
            results = impala_manager.execute_query(query, database='gmp_cis')

            logger.info(f"Retrieved {len(results)} currencies")
            return results

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []

    @staticmethod
    def get_securities_by_currency(
        currency_code: Optional[str] = None,
        user: str = 'SYSTEM'
    ) -> List[Dict[str, Any]]:
        """
        Get securities filtered by currency code (for cascading dropdown).

        Uses cis_security table (same as Trade module) for consistency.

        Args:
            currency_code: Filter by currency (if None, returns all)
            user: Username for audit logging

        Returns:
            List of security dictionaries with security_id, security_name, isin, currency_code
        """
        try:
            # Build WHERE clause - no status filter, matches how trade module queries cis_security
            where_clauses = []

            if currency_code:
                escaped_currency = currency_code.replace("'", "''")
                where_clauses.append(f"currency_code = '{escaped_currency}'")

            base_conditions = "security_name IS NOT NULL AND currency_code IS NOT NULL AND currency_code != ''"
            if where_clauses:
                where_clause = " AND ".join(where_clauses) + " AND " + base_conditions
            else:
                where_clause = base_conditions

            # Use cis_security table (same as Trade module)
            query = f"""
            SELECT DISTINCT
                security_id,
                security_name,
                isin,
                currency_code
            FROM gmp_cis.cis_security
            WHERE {where_clause}
            ORDER BY security_name
            LIMIT 1000
            """

            logger.info(f"Fetching securities for currency: {currency_code or 'ALL'} (user: {user})")
            results = impala_manager.execute_query(query, database='gmp_cis')

            logger.info(f"Retrieved {len(results)} securities")
            return results

        except Exception as e:
            logger.error(f"Error fetching securities: {str(e)}")
            return []

    @staticmethod
    def get_security_details(
        security_id: Optional[int] = None,
        security_name: Optional[str] = None,
        user: str = 'SYSTEM'
    ) -> Optional[Dict[str, Any]]:
        """
        Get security details including ISIN (for auto-populating ISIN field).

        Uses cis_security table (same as Trade module) for consistency.

        Args:
            security_id: Security ID
            security_name: Security name (alternative lookup)
            user: Username for audit logging

        Returns:
            Security details dictionary or None
        """
        try:
            where_clauses = []

            if security_id:
                where_clauses.append(f"security_id = {security_id}")
            elif security_name:
                escaped_name = security_name.replace("'", "''")
                where_clauses.append(f"security_name = '{escaped_name}'")
            else:
                logger.warning("No security_id or security_name provided")
                return None

            where_clause = " AND ".join(where_clauses)

            # Use cis_security table (same as Trade module)
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
        Get market options (using default markets).

        Args:
            user: Username for audit logging

        Returns:
            List of market names
        """
        # Return default markets directly (UDF integration can be added later)
        default_markets = [
            'NYSE', 'NASDAQ', 'SGX', 'LSE', 'HKEX',
            'TSE', 'SSE', 'SZSE', 'ASX', 'BSE'
        ]
        logger.info(f"Returning {len(default_markets)} default markets")
        return default_markets

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
