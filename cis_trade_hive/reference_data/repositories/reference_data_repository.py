"""
Reference Data Repository - Hive Backend

Provides data access layer for reference data using PyHive.
Follows Repository pattern for clean architecture.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from django.conf import settings
from pyhive import hive

logger = logging.getLogger('reference_data')


class HiveReferenceRepository:
    """Base repository for Hive-based reference data"""

    def __init__(self):
        self.config = settings.HIVE_CONFIG

    def _get_connection(self):
        """Get Hive connection"""
        # Don't specify database in connection - use fully qualified table names instead
        return hive.Connection(
            host=self.config['HOST'],
            port=self.config['PORT'],
            auth=self.config.get('AUTH', 'NONE')
        )

    def _execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute query and return results as list of dictionaries

        Args:
            query: SQL query string
            params: Optional tuple of query parameters

        Returns:
            List of dictionaries representing rows
        """
        connection = None
        cursor = None
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Get column names
            columns = [desc[0] for desc in cursor.description]

            # Fetch all rows and convert to dict
            rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in rows]

            logger.info(f"Query returned {len(results)} rows")
            return results

        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"Query: {query}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


class CurrencyRepository(HiveReferenceRepository):
    """Repository for Currency data"""

    TABLE_NAME = 'cis.gmp_cis_sta_dly_currency'

    def _remap_columns(self, row: Dict) -> Dict:
        """Remap column names to match expected API"""
        # Handle both qualified (table.column) and unqualified (column) names
        prefix = 'gmp_cis_sta_dly_currency.'
        return {
            'name': row.get(f'{prefix}name') or row.get('name'),
            'full_name': row.get(f'{prefix}full_name') or row.get('full_name'),
            'symbol': row.get(f'{prefix}symbol') or row.get('symbol'),
            'iso_code': row.get(f'{prefix}iso_code') or row.get('iso_code'),
            'precision': row.get(f'{prefix}precision') or row.get('precision'),
            'rate_precision': row.get(f'{prefix}rate_precision') or row.get('rate_precision'),
            'calendar': row.get(f'{prefix}calendar') or row.get('calendar'),
            'spot_schedule': row.get(f'{prefix}spot_schedule') or row.get('spot_schedule'),
        }

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all currencies from Hive

        Args:
            search: Optional search term for code or name

        Returns:
            List of currency dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME}"

        if search:
            query += f" WHERE LOWER(name) LIKE '%{search.lower()}%' OR LOWER(iso_code) LIKE '%{search.lower()}%'"

        # NOTE: ORDER BY causes issues with PyHive - sort in Python instead
        results = self._execute_query(query)
        remapped = [self._remap_columns(row) for row in results]
        return sorted(remapped, key=lambda x: x.get('iso_code') or '')

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific currency by ISO code"""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE iso_code = '{code}' LIMIT 1"

        results = self._execute_query(query)
        return self._remap_columns(results[0]) if results else None

    def get_active_currencies(self) -> List[Dict]:
        """Get list of active currencies"""
        return self.list_all()


class CountryRepository(HiveReferenceRepository):
    """Repository for Country data"""

    TABLE_NAME = 'cis.gmp_cis_sta_dly_country'

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all countries from Hive

        Args:
            search: Optional search term for code or name

        Returns:
            List of country dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME}"

        if search:
            query += f" WHERE LOWER(label) LIKE '%{search.lower()}%' OR LOWER(full_name) LIKE '%{search.lower()}%'"

        # NOTE: ORDER BY causes issues with PyHive - sort in Python instead
        results = self._execute_query(query)
        return sorted(results, key=lambda x: x.get('label') or '')

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code"""
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE label = '{code}' LIMIT 1"

        results = self._execute_query(query)
        return results[0] if results else None


class CalendarRepository(HiveReferenceRepository):
    """Repository for Calendar/Holiday data"""

    TABLE_NAME = 'cis.gmp_cis_sta_dly_calendar'

    def list_all(
        self,
        calendar_label: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch calendar/holiday data from Hive

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

        # NOTE: ORDER BY causes issues with PyHive - skip sorting for large dataset (100k records)
        # Django pagination will handle sorting display
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


class CounterpartyRepository(HiveReferenceRepository):
    """Repository for Counterparty data"""

    TABLE_NAME = 'cis.gmp_cis_sta_dly_counterparty'

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all counterparties from Hive

        Args:
            search: Optional search term for name or description

        Returns:
            List of counterparty dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME}"

        if search:
            query += f" WHERE LOWER(counterparty_name) LIKE '%{search.lower()}%' OR LOWER(description) LIKE '%{search.lower()}%'"

        # NOTE: ORDER BY causes issues with PyHive - sort in Python instead
        results = self._execute_query(query)
        return sorted(results, key=lambda x: x.get('counterparty_name') or '')

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
