"""
Trade Validation Repository

Validates trade references against master data:
- Portfolio: Must exist in cis_portfolio with SETTLED status
- Security: Must exist in cis_security with ACTIVE/APPROVED status
- Counterparty: Must exist in cis_party with is_active=true

All queries use Kudu via Impala.

Performance Features:
- Dropdown data cached for 5 minutes to reduce database load
- Individual entity validation uses fresh data (no cache)
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from core.repositories.impala_connection import impala_manager, query_cache

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check"""
    is_valid: bool
    entity_type: str
    entity_name: str
    message: str
    details: Optional[Dict[str, Any]] = None


class TradeValidationRepository:
    """Repository for validating trade references against master data"""

    DATABASE = 'gmp_cis'

    # Portfolio table
    PORTFOLIO_TABLE = 'cis_portfolio'
    # Only SETTLED portfolios can be used for trading (completed maker-checker workflow)
    PORTFOLIO_VALID_STATUSES = ['SETTLED', 'settled']

    # Security table
    SECURITY_TABLE = 'cis_security'
    # Note: NULL status is also allowed for legacy data that hasn't been migrated
    # Case-insensitive matching for status
    SECURITY_VALID_STATUSES = ['ACTIVE', 'APPROVED', 'SETTLED', 'active', 'approved', 'settled', None, '']

    # Counterparty table (using cis_party instead of deprecated cis_counterparty_kudu)
    COUNTERPARTY_TABLE = 'cis_party'

    @staticmethod
    def escape_value(val: Any) -> str:
        """Escape value for SQL query."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
        if isinstance(val, bool):
            return str(val).lower()
        return str(val)

    # =========================================================================
    # PORTFOLIO VALIDATION
    # =========================================================================

    def validate_portfolio(self, portfolio_name: str) -> ValidationResult:
        """
        Validate that portfolio exists and is in SETTLED status.

        Args:
            portfolio_name: Portfolio short name to validate

        Returns:
            ValidationResult with is_valid, message, and portfolio details
        """
        try:
            if not portfolio_name or not portfolio_name.strip():
                return ValidationResult(
                    is_valid=False,
                    entity_type='PORTFOLIO',
                    entity_name=portfolio_name or '',
                    message='Portfolio name is required'
                )

            portfolio_name_escaped = portfolio_name.replace("'", "''")
            status_list = ", ".join([f"'{s}'" for s in self.PORTFOLIO_VALID_STATUSES])

            query = f"""
            SELECT name, currency, manager, cash_balance, status, is_active
            FROM {self.DATABASE}.{self.PORTFOLIO_TABLE}
            WHERE name = '{portfolio_name_escaped}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            if not results:
                return ValidationResult(
                    is_valid=False,
                    entity_type='PORTFOLIO',
                    entity_name=portfolio_name,
                    message=f"Portfolio '{portfolio_name}' not found"
                )

            portfolio = results[0]
            status = portfolio.get('status', '') or ''
            is_active = portfolio.get('is_active', False)

            # Case-insensitive status check
            status_upper = status.upper() if status else ''
            valid_statuses_upper = [s.upper() for s in self.PORTFOLIO_VALID_STATUSES if s]

            logger.debug(f"Portfolio '{portfolio_name}' - status: '{status}', is_active: {is_active}")

            if status_upper not in valid_statuses_upper:
                return ValidationResult(
                    is_valid=False,
                    entity_type='PORTFOLIO',
                    entity_name=portfolio_name,
                    message=f"Portfolio '{portfolio_name}' has status '{status}'. Only SETTLED portfolios can be used for trading.",
                    details=portfolio
                )

            # Also check is_active flag
            if not is_active:
                return ValidationResult(
                    is_valid=False,
                    entity_type='PORTFOLIO',
                    entity_name=portfolio_name,
                    message=f"Portfolio '{portfolio_name}' is not active (is_active=false).",
                    details=portfolio
                )

            return ValidationResult(
                is_valid=True,
                entity_type='PORTFOLIO',
                entity_name=portfolio_name,
                message=f"Portfolio '{portfolio_name}' is valid for trading (status: {status})",
                details=portfolio
            )

        except Exception as e:
            logger.error(f"Error validating portfolio '{portfolio_name}': {str(e)}")
            return ValidationResult(
                is_valid=False,
                entity_type='PORTFOLIO',
                entity_name=portfolio_name,
                message=f"Error validating portfolio: {str(e)}"
            )

    # Cache TTL for dropdown data (5 minutes)
    CACHE_TTL = 300

    def get_valid_portfolios(self, search: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get list of valid portfolios for trade entry dropdown.
        Results are cached for 5 minutes to improve performance.

        Args:
            search: Optional search term
            limit: Maximum results

        Returns:
            List of portfolio dictionaries
        """
        try:
            # Check cache first (only for non-search queries)
            cache_key = f"portfolios:{search or 'all'}:{limit}"
            if not search:  # Cache only full list queries
                cached = query_cache.get(cache_key)
                if cached:
                    return cached

            # Use UPPER() for case-insensitive status matching
            query = f"""
            SELECT name AS portfolio_short_name,
                   name AS portfolio_full_name,
                   currency,
                   manager,
                   cash_balance,
                   status
            FROM {self.DATABASE}.{self.PORTFOLIO_TABLE}
            WHERE UPPER(status) = 'SETTLED'
              AND is_active = true
            """

            if search:
                search_escaped = search.replace("'", "''")
                query += f" AND (LOWER(name) LIKE '%{search_escaped.lower()}%')"

            query += f" ORDER BY name LIMIT {limit}"

            logger.debug(f"get_valid_portfolios query: {query}")
            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.debug(f"get_valid_portfolios returned {len(results) if results else 0} portfolios")

            # Cache the results
            if not search and results:
                query_cache.set(cache_key, results, self.CACHE_TTL)

            return results if results else []

        except Exception as e:
            logger.error(f"Error getting valid portfolios: {str(e)}")
            return []

    # =========================================================================
    # SECURITY VALIDATION
    # =========================================================================

    def validate_security(self, security_name: str) -> ValidationResult:
        """
        Validate that security exists and is in ACTIVE/APPROVED status.

        Args:
            security_name: Security name/label to validate

        Returns:
            ValidationResult with is_valid, message, and security details
        """
        try:
            if not security_name or not security_name.strip():
                return ValidationResult(
                    is_valid=False,
                    entity_type='SECURITY',
                    entity_name=security_name or '',
                    message='Security name is required'
                )

            security_name_escaped = security_name.replace("'", "''")
            status_list = ", ".join([f"'{s}'" for s in self.SECURITY_VALID_STATUSES])

            query = f"""
            SELECT security_name, security_type, isin, ticker,
                   currency_code, price, issuer, status, is_active
            FROM {self.DATABASE}.{self.SECURITY_TABLE}
            WHERE security_name = '{security_name_escaped}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            if not results:
                return ValidationResult(
                    is_valid=False,
                    entity_type='SECURITY',
                    entity_name=security_name,
                    message=f"Security '{security_name}' not found"
                )

            security = results[0]
            status = security.get('status', '') or ''
            is_active = security.get('is_active')

            # Handle various representations of is_active (boolean, string, None)
            if isinstance(is_active, str):
                is_active = is_active.lower() in ('true', '1', 'yes')
            elif is_active is None:
                is_active = True  # Default to True for legacy data without is_active field

            logger.debug(f"Security '{security_name}' - status: '{status}', is_active: {is_active}")

            # Case-insensitive status check (including NULL/empty for legacy data)
            status_upper = status.upper() if status else ''
            valid_statuses_upper = ['ACTIVE', 'APPROVED', 'SETTLED']

            # Status is valid if it's in valid list, or empty/None (legacy data)
            status_valid = (status_upper in valid_statuses_upper or
                          status is None or
                          status == '' or
                          status == 'None' or
                          status_upper == 'NONE')

            if not status_valid:
                return ValidationResult(
                    is_valid=False,
                    entity_type='SECURITY',
                    entity_name=security_name,
                    message=f"Security '{security_name}' has status '{status}'. Only ACTIVE or APPROVED securities can be traded.",
                    details=security
                )

            if not is_active:
                return ValidationResult(
                    is_valid=False,
                    entity_type='SECURITY',
                    entity_name=security_name,
                    message=f"Security '{security_name}' is not active (is_active=false).",
                    details=security
                )

            return ValidationResult(
                is_valid=True,
                entity_type='SECURITY',
                entity_name=security_name,
                message=f"Security '{security_name}' is valid for trading (status: {status or 'N/A'})",
                details=security
            )

        except Exception as e:
            logger.error(f"Error validating security '{security_name}': {str(e)}")
            return ValidationResult(
                is_valid=False,
                entity_type='SECURITY',
                entity_name=security_name,
                message=f"Error validating security: {str(e)}"
            )

    def get_valid_securities(self, search: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get list of valid securities for trade entry dropdown.
        Results are cached for 5 minutes to improve performance.

        Args:
            search: Optional search term
            limit: Maximum results

        Returns:
            List of security dictionaries
        """
        try:
            # Check cache first (only for non-search queries)
            cache_key = f"securities:{search or 'all'}:{limit}"
            if not search:  # Cache only full list queries
                cached = query_cache.get(cache_key)
                if cached:
                    return cached

            # Use UPPER() for case-insensitive status matching
            # Include NULL/empty status for legacy data
            query = f"""
            SELECT security_name AS security_label,
                   security_name AS security_full_name,
                   security_type,
                   isin,
                   ticker,
                   currency_code,
                   price AS current_price,
                   issuer,
                   status
            FROM {self.DATABASE}.{self.SECURITY_TABLE}
            WHERE (UPPER(status) IN ('ACTIVE', 'APPROVED', 'SETTLED')
                   OR status IS NULL
                   OR status = ''
                   OR UPPER(status) = 'NONE')
              AND (is_active = true OR is_active IS NULL)
            """

            if search:
                search_escaped = search.replace("'", "''")
                query += f"""
                AND (LOWER(security_name) LIKE '%{search_escaped.lower()}%'
                     OR LOWER(isin) LIKE '%{search_escaped.lower()}%'
                     OR LOWER(ticker) LIKE '%{search_escaped.lower()}%')
                """

            query += f" ORDER BY security_name LIMIT {limit}"

            logger.debug(f"get_valid_securities query: {query}")
            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.debug(f"get_valid_securities returned {len(results) if results else 0} securities")

            # Cache the results
            if not search and results:
                query_cache.set(cache_key, results, self.CACHE_TTL)

            return results if results else []

        except Exception as e:
            logger.error(f"Error getting valid securities: {str(e)}")
            return []

    # =========================================================================
    # COUNTERPARTY VALIDATION
    # =========================================================================

    def validate_counterparty(self, counterparty_name: str) -> ValidationResult:
        """
        Validate that counterparty (party) exists and is active.

        Args:
            counterparty_name: Party short name to validate

        Returns:
            ValidationResult with is_valid, message, and counterparty details
        """
        try:
            # Counterparty is optional for some trade types
            if not counterparty_name or not counterparty_name.strip():
                return ValidationResult(
                    is_valid=True,
                    entity_type='COUNTERPARTY',
                    entity_name='',
                    message='Counterparty is optional'
                )

            counterparty_escaped = counterparty_name.replace("'", "''")

            query = f"""
            SELECT party_short_name, party_full_name,
                   country, is_broker, is_custodian, is_active, is_deleted
            FROM {self.DATABASE}.{self.COUNTERPARTY_TABLE}
            WHERE party_short_name = '{counterparty_escaped}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            if not results:
                return ValidationResult(
                    is_valid=False,
                    entity_type='COUNTERPARTY',
                    entity_name=counterparty_name,
                    message=f"Counterparty '{counterparty_name}' not found"
                )

            counterparty = results[0]
            is_active = counterparty.get('is_active', False)
            is_deleted = counterparty.get('is_deleted', False)

            if is_deleted:
                return ValidationResult(
                    is_valid=False,
                    entity_type='COUNTERPARTY',
                    entity_name=counterparty_name,
                    message=f"Counterparty '{counterparty_name}' has been deleted.",
                    details=counterparty
                )

            if not is_active:
                return ValidationResult(
                    is_valid=False,
                    entity_type='COUNTERPARTY',
                    entity_name=counterparty_name,
                    message=f"Counterparty '{counterparty_name}' is not active.",
                    details=counterparty
                )

            return ValidationResult(
                is_valid=True,
                entity_type='COUNTERPARTY',
                entity_name=counterparty_name,
                message=f"Counterparty '{counterparty_name}' is valid",
                details=counterparty
            )

        except Exception as e:
            logger.error(f"Error validating counterparty '{counterparty_name}': {str(e)}")
            return ValidationResult(
                is_valid=False,
                entity_type='COUNTERPARTY',
                entity_name=counterparty_name,
                message=f"Error validating counterparty: {str(e)}"
            )

    def get_valid_counterparties(self, search: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get list of valid counterparties (parties) for trade entry dropdown.
        Results are cached for 5 minutes to improve performance.

        Args:
            search: Optional search term
            limit: Maximum results

        Returns:
            List of counterparty dictionaries with party_short_name and party_full_name
        """
        try:
            # Check cache first (only for non-search queries)
            cache_key = f"counterparties:{search or 'all'}:{limit}"
            if not search:  # Cache only full list queries
                cached = query_cache.get(cache_key)
                if cached:
                    return cached

            query = f"""
            SELECT party_short_name,
                   party_full_name,
                   country,
                   is_broker,
                   is_custodian
            FROM {self.DATABASE}.{self.COUNTERPARTY_TABLE}
            WHERE is_active = true
              AND (is_deleted = false OR is_deleted IS NULL)
            """

            if search:
                search_escaped = search.replace("'", "''")
                query += f"""
                AND (LOWER(party_short_name) LIKE '%{search_escaped.lower()}%'
                     OR LOWER(party_full_name) LIKE '%{search_escaped.lower()}%')
                """

            query += f" ORDER BY party_short_name LIMIT {limit}"

            results = impala_manager.execute_query(query, database=self.DATABASE)

            # Cache the results
            if not search and results:
                query_cache.set(cache_key, results, self.CACHE_TTL)

            return results if results else []

        except Exception as e:
            logger.error(f"Error getting valid counterparties: {str(e)}")
            return []

    # =========================================================================
    # COMBINED VALIDATION
    # =========================================================================

    def validate_trade_references(
        self,
        portfolio_name: str,
        security_name: str,
        counterparty_name: Optional[str] = None
    ) -> Tuple[bool, List[ValidationResult]]:
        """
        Validate all trade references at once.

        Args:
            portfolio_name: Portfolio short name
            security_name: Security name/label
            counterparty_name: Optional counterparty short name

        Returns:
            Tuple of (all_valid: bool, results: List[ValidationResult])
        """
        results = []

        # Validate Portfolio (required)
        portfolio_result = self.validate_portfolio(portfolio_name)
        results.append(portfolio_result)

        # Validate Security (required)
        security_result = self.validate_security(security_name)
        results.append(security_result)

        # Validate Counterparty (optional)
        if counterparty_name:
            counterparty_result = self.validate_counterparty(counterparty_name)
            results.append(counterparty_result)

        all_valid = all(r.is_valid for r in results)

        return all_valid, results

    def get_validation_errors(self, results: List[ValidationResult]) -> List[str]:
        """
        Extract error messages from validation results.

        Args:
            results: List of ValidationResult objects

        Returns:
            List of error messages
        """
        return [r.message for r in results if not r.is_valid]

    # =========================================================================
    # AUTO-POPULATE HELPERS
    # =========================================================================

    def get_portfolio_details(self, portfolio_name: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio details for auto-populating trade form.

        Args:
            portfolio_name: Portfolio short name

        Returns:
            Portfolio dictionary or None
        """
        result = self.validate_portfolio(portfolio_name)
        return result.details if result.is_valid else None

    def get_security_details(self, security_name: str) -> Optional[Dict[str, Any]]:
        """
        Get security details for auto-populating trade form.

        Args:
            security_name: Security name

        Returns:
            Security dictionary or None
        """
        result = self.validate_security(security_name)
        return result.details if result.is_valid else None

    def get_counterparty_details(self, counterparty_name: str) -> Optional[Dict[str, Any]]:
        """
        Get counterparty details for auto-populating trade form.

        Args:
            counterparty_name: Counterparty short name

        Returns:
            Counterparty dictionary or None
        """
        result = self.validate_counterparty(counterparty_name)
        return result.details if result.is_valid else None


# Singleton instance
trade_validation_repository = TradeValidationRepository()
