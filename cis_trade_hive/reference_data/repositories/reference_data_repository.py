"""
Reference Data Repository - Kudu/Impala Backend

Provides data access layer for reference data using Impala.
Follows Repository pattern for clean architecture.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from django.conf import settings
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger('reference_data')


class ImpalaReferenceRepository:
    """Base repository for Impala/Kudu-based reference data"""

    def __init__(self):
        self.config = settings.IMPALA_CONFIG
        self.database = 'gmp_cis'

    def _execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute query and return results as list of dictionaries

        Args:
            query: SQL query string

        Returns:
            List of dictionaries representing rows
        """
        try:
            results = impala_manager.execute_query(query, database=self.database)
            logger.info(f"Query returned {len(results) if results else 0} rows")
            return results if results else []

        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"Query: {query}")
            raise


class CurrencyRepository(ImpalaReferenceRepository):
    """Repository for Currency data"""

    TABLE_NAME = 'gmp_cis_sta_dly_currency'

    def _remap_columns(self, row: Dict) -> Dict:
        """Remap column names to match expected API"""
        # Note: External Hive table columns: name, full_name, symbol, iso_code, precision, calendar, spot_schedule, rate_precision
        return {
            'code': row.get('iso_code', ''),
            'name': row.get('name', ''),
            'full_name': row.get('full_name', ''),
            'symbol': row.get('symbol', ''),
            'decimal_places': row.get('precision', ''),
            'rate_precision': row.get('rate_precision', ''),
            'calendar': row.get('calendar', ''),
            'spot_schedule': row.get('spot_schedule', ''),
        }

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all currencies from Kudu/Impala

        Args:
            search: Optional search term for code or name

        Returns:
            List of currency dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME}"

        if search:
            query += f" WHERE LOWER(curr_name) LIKE '%{search.lower()}%' OR LOWER(iso_code) LIKE '%{search.lower()}%'"

        query += " ORDER BY iso_code"

        results = self._execute_query(query)
        remapped = [self._remap_columns(row) for row in results]
        return remapped

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific currency by ISO code"""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE iso_code = '{code}' LIMIT 1"

        results = self._execute_query(query)
        return self._remap_columns(results[0]) if results else None

    def get_active_currencies(self) -> List[Dict]:
        """Get list of active currencies"""
        return self.list_all()


class CountryRepository(ImpalaReferenceRepository):
    """Repository for Country data"""

    TABLE_NAME = 'gmp_cis_sta_dly_country'

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all countries from Kudu/Impala

        Args:
            search: Optional search term for code or name

        Returns:
            List of country dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME}"

        if search:
            query += f" WHERE LOWER(label) LIKE '%{search.lower()}%' OR LOWER(full_name) LIKE '%{search.lower()}%'"

        query += " ORDER BY label"

        results = self._execute_query(query)
        # Remap to include 'code' and 'name' keys for consistency
        return [{'code': r.get('label', ''), 'name': r.get('full_name', ''), **r} for r in results]

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code"""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE label = '{code}' LIMIT 1"

        results = self._execute_query(query)
        return results[0] if results else None


class CalendarRepository(ImpalaReferenceRepository):
    """Repository for Calendar/Holiday data"""

    TABLE_NAME = 'gmp_cis_sta_dly_calendar'

    def list_all(
        self,
        calendar_label: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch calendar/holiday data from Kudu/Impala

        Args:
            calendar_label: Filter by specific calendar
            search: Search in calendar description

        Returns:
            List of calendar dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE 1=1"

        if calendar_label:
            query += f" AND calendar_label = '{calendar_label}'"

        if search:
            query += f" AND LOWER(calendar_description) LIKE '%{search.lower()}%'"

        query += " ORDER BY calendar_label, holiday_date"

        return self._execute_query(query)

    def get_distinct_calendars(self) -> List[str]:
        """Get list of distinct calendar labels"""
        query = f"SELECT DISTINCT calendar_label FROM {self.TABLE_NAME}"

        results = self._execute_query(query)
        calendars = [r.get('calendar_label') for r in results if r.get('calendar_label')]
        return sorted(calendars)

    def get_holidays_for_calendar(self, calendar_label: str) -> List[Dict]:
        """Get all holidays for a specific calendar"""
        return self.list_all(calendar_label=calendar_label)


class CounterpartyRepository(ImpalaReferenceRepository):
    """Repository for Counterparty data"""

    TABLE_NAME = 'gmp_cis_sta_dly_counterparty'

    def list_all(self, search: Optional[str] = None, counterparty_type: Optional[str] = None) -> List[Dict]:
        """
        Fetch all counterparties from Kudu/Impala

        Args:
            search: Optional search term for name or description
            counterparty_type: Optional filter by counterparty type

        Returns:
            List of counterparty dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE 1=1"

        if search:
            query += f" AND (LOWER(counterparty_name) LIKE '%{search.lower()}%' OR LOWER(description) LIKE '%{search.lower()}%')"

        if counterparty_type:
            query += f" AND UPPER(counterparty_name) LIKE '%{counterparty_type}%'"

        query += " ORDER BY counterparty_name"

        results = self._execute_query(query)
        # Remap to include standard keys
        return [{
            'code': r.get('counterparty_name', ''),
            'name': r.get('counterparty_name', ''),
            'legal_name': r.get('description', ''),
            'counterparty_type': 'CORPORATE',  # Default since external table doesn't have this
            'email': '',
            'phone': r.get('primary_number', ''),
            'city': r.get('city', ''),
            'country': r.get('country', ''),
            'status': 'ACTIVE',
            'risk_category': 'MEDIUM',
            **r
        } for r in results]

    def get_by_name(self, name: str) -> Optional[Dict]:
        """Get specific counterparty by name"""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE counterparty_name = '{name}' LIMIT 1"

        results = self._execute_query(query)
        return results[0] if results else None


# Singleton instances
currency_repository = CurrencyRepository()
country_repository = CountryRepository()
calendar_repository = CalendarRepository()
counterparty_repository = CounterpartyRepository()
