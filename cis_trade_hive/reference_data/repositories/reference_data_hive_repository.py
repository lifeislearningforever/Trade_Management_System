"""
Reference Data Hive Repositories (ORC + ACID)

Data access layer for reference data in Hive managed tables:
- Counterparty
- Currency
- Country
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


# =============================================================================
# COUNTERPARTY REPOSITORY
# =============================================================================

class CounterpartyHiveRepository(HiveBaseRepository):
    """Repository for counterparty operations with Hive managed tables."""

    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'

    @property
    def table_name(self) -> str:
        return 'cis_counterparty'

    @property
    def primary_key(self) -> str:
        return 'counterparty_id'

    @property
    def columns(self) -> List[str]:
        return [
            'counterparty_id', 'counterparty_code', 'counterparty_name',
            'counterparty_type', 'country', 'address', 'contact_name',
            'contact_email', 'contact_phone', 'status', 'is_active',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_all_counterparties(
        self,
        limit: int = 1000,
        status: Optional[str] = None,
        counterparty_type: Optional[str] = None,
        country: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Fetch all counterparties with optional filters."""
        try:
            where_clauses = []

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            if status:
                where_clauses.append(f"status = '{status}'")

            if counterparty_type:
                where_clauses.append(f"counterparty_type = '{counterparty_type}'")

            if country:
                where_clauses.append(f"country = '{country}'")

            if search:
                search_term = search.replace("'", "''").lower()
                where_clauses.append(
                    f"(LOWER(counterparty_name) LIKE '%{search_term}%' OR "
                    f"LOWER(counterparty_code) LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching counterparties: {str(e)}")
            return []

    def get_counterparty_by_id(self, counterparty_id: str) -> Optional[Dict[str, Any]]:
        """Get counterparty by ID."""
        return self.find_by_id(counterparty_id)

    def get_counterparty_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get counterparty by code."""
        try:
            code_escaped = code.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE counterparty_code = '{code_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error fetching counterparty by code: {str(e)}")
            return None

    def create_counterparty(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new counterparty."""
        try:
            counterparty_id = self._generate_id('CP')
            now = datetime.now()

            record = {
                'counterparty_id': counterparty_id,
                'counterparty_code': data.get('counterparty_code'),
                'counterparty_name': data.get('counterparty_name'),
                'counterparty_type': data.get('counterparty_type'),
                'country': data.get('country'),
                'address': data.get('address'),
                'contact_name': data.get('contact_name'),
                'contact_email': data.get('contact_email'),
                'contact_phone': data.get('contact_phone'),
                'status': self.STATUS_ACTIVE,
                'is_active': True,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created counterparty {counterparty_id}")
                return counterparty_id
            return None

        except Exception as e:
            logger.error(f"Error creating counterparty: {str(e)}")
            return None

    def update_counterparty(self, counterparty_id: str, data: Dict[str, Any],
                           updated_by: str) -> bool:
        """Update counterparty data."""
        try:
            update_data = {}
            updatable_fields = [
                'counterparty_code', 'counterparty_name', 'counterparty_type',
                'country', 'address', 'contact_name', 'contact_email', 'contact_phone'
            ]

            for field in updatable_fields:
                if field in data:
                    update_data[field] = data[field]

            update_data['updated_by'] = updated_by

            return self.update(counterparty_id, update_data)

        except Exception as e:
            logger.error(f"Error updating counterparty: {str(e)}")
            return False

    def delete_counterparty(self, counterparty_id: str, deleted_by: str) -> bool:
        """Soft delete a counterparty."""
        return self.soft_delete(counterparty_id, deleted_by)

    def get_statistics(self) -> Dict[str, Any]:
        """Get counterparty statistics."""
        try:
            query = f"""
                SELECT counterparty_type, country, status
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            type_counts = {}
            country_counts = {}
            active_count = 0

            if results:
                for row in results:
                    cp_type = row.get('counterparty_type', 'Unknown')
                    type_counts[cp_type] = type_counts.get(cp_type, 0) + 1

                    country = row.get('country', 'Unknown')
                    country_counts[country] = country_counts.get(country, 0) + 1

                    if row.get('status') == self.STATUS_ACTIVE:
                        active_count += 1

            return {
                'total_counterparties': total,
                'active_counterparties': active_count,
                'by_type': [
                    {'type': k, 'count': v}
                    for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
                ],
                'by_country': [
                    {'country': k, 'count': v}
                    for k, v in sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ]
            }

        except Exception as e:
            logger.error(f"Error getting counterparty statistics: {str(e)}")
            return {'total_counterparties': 0, 'active_counterparties': 0, 'by_type': [], 'by_country': []}


# =============================================================================
# CURRENCY REPOSITORY
# =============================================================================

class CurrencyHiveRepository(HiveBaseRepository):
    """Repository for currency operations with Hive managed tables."""

    @property
    def table_name(self) -> str:
        return 'cis_currency'

    @property
    def primary_key(self) -> str:
        return 'currency_id'

    @property
    def columns(self) -> List[str]:
        return [
            'currency_id', 'currency_code', 'currency_name', 'symbol',
            'decimal_places', 'is_active', 'created_at', 'created_by',
            'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_all_currencies(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all currencies."""
        try:
            where_clause = "deleted_at IS NULL"
            if not include_inactive:
                where_clause += " AND is_active = TRUE"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching currencies: {str(e)}")
            return []

    def get_currency_by_code(self, currency_code: str) -> Optional[Dict[str, Any]]:
        """Get currency by code."""
        try:
            code_escaped = currency_code.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE currency_code = '{code_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error fetching currency by code: {str(e)}")
            return None

    def create_currency(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new currency."""
        try:
            currency_id = self._generate_id('CUR')
            now = datetime.now()

            record = {
                'currency_id': currency_id,
                'currency_code': data.get('currency_code'),
                'currency_name': data.get('currency_name'),
                'symbol': data.get('symbol'),
                'decimal_places': data.get('decimal_places', 2),
                'is_active': True,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created currency {currency_id}")
                return currency_id
            return None

        except Exception as e:
            logger.error(f"Error creating currency: {str(e)}")
            return None

    # =========================================================================
    # Backward Compatibility Aliases (for service layer)
    # =========================================================================

    def list_all(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias for get_all_currencies (backward compatibility with service layer)."""
        currencies = self.get_all_currencies(include_inactive=False)

        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            currencies = [
                c for c in currencies
                if search_lower in c.get('currency_code', '').lower()
                or search_lower in c.get('currency_name', '').lower()
            ]

        # Map to expected format for views
        return [
            {
                'code': c.get('currency_code'),
                'name': c.get('currency_code'),  # Short name
                'full_name': c.get('currency_name'),
                'symbol': c.get('symbol'),
                'decimal_places': c.get('decimal_places'),
                'rate_precision': c.get('decimal_places'),  # Use decimal_places as fallback
                'calendar': '',
                'spot_schedule': '',
            }
            for c in currencies
        ]

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Alias for get_currency_by_code (backward compatibility)."""
        result = self.get_currency_by_code(code)
        if result:
            return {
                'code': result.get('currency_code'),
                'name': result.get('currency_code'),
                'full_name': result.get('currency_name'),
                'symbol': result.get('symbol'),
                'decimal_places': result.get('decimal_places'),
                'rate_precision': result.get('decimal_places'),
                'calendar': '',
                'spot_schedule': '',
            }
        return None


# =============================================================================
# COUNTRY REPOSITORY
# =============================================================================

class CountryHiveRepository(HiveBaseRepository):
    """Repository for country operations with Hive managed tables."""

    @property
    def table_name(self) -> str:
        return 'cis_country'

    @property
    def primary_key(self) -> str:
        return 'country_id'

    @property
    def columns(self) -> List[str]:
        return [
            'country_id', 'country_code', 'country_name', 'region',
            'currency_code', 'is_active', 'created_at', 'created_by',
            'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_all_countries(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all countries."""
        try:
            where_clause = "deleted_at IS NULL"
            if not include_inactive:
                where_clause += " AND is_active = TRUE"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching countries: {str(e)}")
            return []

    def get_country_by_code(self, country_code: str) -> Optional[Dict[str, Any]]:
        """Get country by code."""
        try:
            code_escaped = country_code.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE country_code = '{code_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error fetching country by code: {str(e)}")
            return None

    def get_countries_by_region(self, region: str) -> List[Dict[str, Any]]:
        """Get countries by region."""
        try:
            region_escaped = region.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE region = '{region_escaped}'
                  AND deleted_at IS NULL
                  AND is_active = TRUE
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching countries by region: {str(e)}")
            return []

    def create_country(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new country."""
        try:
            country_id = self._generate_id('CTY')
            now = datetime.now()

            record = {
                'country_id': country_id,
                'country_code': data.get('country_code'),
                'country_name': data.get('country_name'),
                'region': data.get('region'),
                'currency_code': data.get('currency_code'),
                'is_active': True,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created country {country_id}")
                return country_id
            return None

        except Exception as e:
            logger.error(f"Error creating country: {str(e)}")
            return None

    # =========================================================================
    # Backward Compatibility Aliases (for service layer)
    # =========================================================================

    def list_all(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias for get_all_countries (backward compatibility with service layer)."""
        countries = self.get_all_countries(include_inactive=False)

        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            countries = [
                c for c in countries
                if search_lower in c.get('country_code', '').lower()
                or search_lower in c.get('country_name', '').lower()
            ]

        # Map to expected format for views
        return [
            {
                'code': c.get('country_code'),
                'name': c.get('country_name'),
                'region': c.get('region'),
                'currency_code': c.get('currency_code'),
            }
            for c in countries
        ]

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Alias for get_country_by_code (backward compatibility)."""
        result = self.get_country_by_code(code)
        if result:
            return {
                'code': result.get('country_code'),
                'name': result.get('country_name'),
                'region': result.get('region'),
                'currency_code': result.get('currency_code'),
            }
        return None


# Singleton instances
counterparty_hive_repository = CounterpartyHiveRepository()
currency_hive_repository = CurrencyHiveRepository()
country_hive_repository = CountryHiveRepository()
