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
        self.database = self.config['DATABASE']

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

    def _execute_write(self, query: str) -> bool:
        """
        Execute write query (INSERT/UPDATE/DELETE)

        Args:
            query: SQL query string

        Returns:
            True if successful
        """
        try:
            impala_manager.execute_write(query, database=self.database)
            logger.info("Write query executed successfully")
            return True

        except Exception as e:
            logger.error(f"Error executing write query: {str(e)}")
            logger.error(f"Query: {query}")
            raise

    def _escape_sql(self, value: str) -> str:
        """Escape single quotes in SQL values. Impala uses C-style \\' escaping, not doubled quotes."""
        if value is None:
            return ''
        return str(value).replace('\\', '\\\\').replace("'", "\\'")


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
            'processing_date': row.get('processing_date', ''),
        }

    def _get_max_processing_date_subquery(self) -> str:
        """Get subquery for max processing_date filter"""
        return f"(SELECT MAX(processing_date) FROM {self.TABLE_NAME})"

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all currencies from Kudu/Impala for the latest processing_date.

        Args:
            search: Optional search term for code or name

        Returns:
            List of currency dictionaries
        """
        # Filter by max(processing_date) to get only latest data
        query = f"""
        SELECT * FROM {self.TABLE_NAME}
        WHERE processing_date = {self._get_max_processing_date_subquery()}
        """

        if search:
            search_escaped = search.replace('\\', '\\\\').replace("'", "\\'").lower()
            query += f""" AND (
                LOWER(iso_code) LIKE '%{search_escaped}%'
                OR LOWER(name) LIKE '%{search_escaped}%'
                OR LOWER(full_name) LIKE '%{search_escaped}%'
                OR LOWER(`symbol`) LIKE '%{search_escaped}%'
            )"""

        query += " ORDER BY iso_code"

        results = self._execute_query(query)
        remapped = [self._remap_columns(row) for row in results]
        return remapped

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific currency by ISO code for the latest processing_date"""
        code_escaped = code.replace('\\', '\\\\').replace("'", "\\'")
        query = f"""
        SELECT * FROM {self.TABLE_NAME}
        WHERE iso_code = '{code_escaped}'
          AND processing_date = {self._get_max_processing_date_subquery()}
        LIMIT 1
        """

        results = self._execute_query(query)
        return self._remap_columns(results[0]) if results else None

    def get_active_currencies(self) -> List[Dict]:
        """Get list of active currencies"""
        return self.list_all()


class CountryRepository(ImpalaReferenceRepository):
    """Repository for Country data"""

    TABLE_NAME = 'gmp_cis_sta_dly_country'

    def _get_max_processing_date_subquery(self) -> str:
        """Get subquery for max processing_date filter to avoid duplicates"""
        return f"(SELECT MAX(processing_date) FROM {self.TABLE_NAME})"

    def _has_processing_date_column(self) -> bool:
        """Check if the table has processing_date column (production vs docker)"""
        try:
            check_query = f"SELECT processing_date FROM {self.TABLE_NAME} LIMIT 1"
            self._execute_query(check_query)
            return True
        except Exception:
            return False

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all countries from Kudu/Impala.

        Uses max(processing_date) filter to avoid duplicates in production.
        Handles both table schemas:
        - Docker/Simple: label, full_name only (no processing_date)
        - Production/Hive: label, full_name, processing_date

        Args:
            search: Optional search term for code or name

        Returns:
            List of country dictionaries with 'code' and 'name' keys
        """
        # Use DISTINCT and filter by max processing_date to avoid duplicates
        query = f"SELECT DISTINCT label, full_name FROM {self.TABLE_NAME}"

        conditions = []

        # Try to filter by max processing_date (production schema)
        # This avoids duplicates when multiple processing dates exist
        try:
            max_date_query = f"SELECT MAX(processing_date) as max_date FROM {self.TABLE_NAME}"
            max_date_result = self._execute_query(max_date_query)
            if max_date_result and max_date_result[0].get('max_date'):
                conditions.append(f"processing_date = {self._get_max_processing_date_subquery()}")
        except Exception:
            # Docker schema doesn't have processing_date column - skip this filter
            pass

        if search:
            search_escaped = search.replace('\\', '\\\\').replace("'", "\\'").lower()
            conditions.append(f"(LOWER(label) LIKE '%{search_escaped}%' OR LOWER(full_name) LIKE '%{search_escaped}%')")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY label"

        results = self._execute_query(query)
        # Remap to include 'code' and 'name' keys for consistency
        return [{'code': r.get('label', ''), 'name': r.get('full_name', ''), **r} for r in results]

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code (using max processing_date to avoid duplicates)"""
        code_escaped = code.replace('\\', '\\\\').replace("'", "\\'")

        # Try with max processing_date filter first (production)
        try:
            query = f"""
            SELECT label, full_name FROM {self.TABLE_NAME}
            WHERE label = '{code_escaped}'
              AND processing_date = {self._get_max_processing_date_subquery()}
            LIMIT 1
            """
            results = self._execute_query(query)
            if results:
                r = results[0]
                return {'code': r.get('label', ''), 'name': r.get('full_name', ''), **r}
        except Exception:
            pass

        # Fallback for Docker schema (no processing_date)
        query = f"""
        SELECT label, full_name FROM {self.TABLE_NAME}
        WHERE label = '{code_escaped}'
        LIMIT 1
        """

        results = self._execute_query(query)
        if results:
            r = results[0]
            return {'code': r.get('label', ''), 'name': r.get('full_name', ''), **r}
        return None


class CalendarRepository(ImpalaReferenceRepository):
    """Repository for Calendar/Holiday data"""

    TABLE_NAME = 'gmp_cis_sta_dly_calendar'

    def _get_max_processing_date_subquery(self) -> str:
        """Get subquery for max processing_date filter"""
        return f"(SELECT MAX(processing_date) FROM {self.TABLE_NAME})"

    def list_all(
        self,
        calendar_label: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch calendar/holiday data from Kudu/Impala for the latest processing_date.

        Args:
            calendar_label: Filter by specific calendar
            search: Search in calendar description

        Returns:
            List of calendar dictionaries
        """
        # Filter by max(processing_date) to get only latest data
        query = f"""
        SELECT * FROM {self.TABLE_NAME}
        WHERE processing_date = {self._get_max_processing_date_subquery()}
        """

        if calendar_label:
            calendar_label_escaped = calendar_label.replace('\\', '\\\\').replace("'", "\\'")
            query += f" AND calendar_label = '{calendar_label_escaped}'"

        if search:
            search_escaped = search.replace('\\', '\\\\').replace("'", "\\'").lower()
            query += f""" AND (
                LOWER(calendar_label) LIKE '%{search_escaped}%'
                OR LOWER(calendar_description) LIKE '%{search_escaped}%'
                OR CAST(holiday_date AS STRING) LIKE '%{search_escaped}%'
            )"""

        query += " ORDER BY calendar_label, holiday_date"

        return self._execute_query(query)

    def get_distinct_calendars(self) -> List[str]:
        """Get list of distinct calendar labels for the latest processing_date"""
        query = f"""
        SELECT DISTINCT calendar_label FROM {self.TABLE_NAME}
        WHERE processing_date = {self._get_max_processing_date_subquery()}
        """

        results = self._execute_query(query)
        calendars = [r.get('calendar_label') for r in results if r.get('calendar_label')]
        return sorted(calendars)

    def get_holidays_for_calendar(self, calendar_label: str) -> List[Dict]:
        """Get all holidays for a specific calendar"""
        return self.list_all(calendar_label=calendar_label)


class MascodeRepository(ImpalaReferenceRepository):
    """Repository for MAS Code / Industry Group data"""

    TABLE_NAME = 'gmp_cis_sta_dly_mascode'

    def _get_max_processing_date_subquery(self) -> str:
        """Get subquery for max processing_date filter"""
        return f"(SELECT MAX(processing_date) FROM {self.TABLE_NAME})"

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all MAS codes from Kudu/Impala for the latest processing_date.

        Args:
            search: Optional search term for mas_code or industry_group

        Returns:
            List of mascode dictionaries
        """
        # Filter by max(processing_date) to get only latest data
        query = f"""
        SELECT * FROM {self.TABLE_NAME}
        WHERE processing_date = {self._get_max_processing_date_subquery()}
        """

        if search:
            search_escaped = search.replace('\\', '\\\\').replace("'", "\\'").lower()
            query += f""" AND (
                LOWER(mas_code) LIKE '%{search_escaped}%'
                OR LOWER(industry_group) LIKE '%{search_escaped}%'
            )"""

        query += " ORDER BY mas_code"

        return self._execute_query(query)

    def get_distinct_industry_groups(self) -> List[str]:
        """Get list of distinct industry groups for the latest processing_date"""
        query = f"""
        SELECT DISTINCT industry_group FROM {self.TABLE_NAME}
        WHERE processing_date = {self._get_max_processing_date_subquery()}
          AND industry_group IS NOT NULL AND industry_group != ''
        """

        results = self._execute_query(query)
        groups = [r.get('industry_group') for r in results if r.get('industry_group')]
        return sorted(groups)


class CounterpartyRepository(ImpalaReferenceRepository):
    """Repository for Counterparty data - Now using Kudu table with stable primary key"""

    TABLE_NAME = 'cis_counterparty_kudu'

    def list_all(
        self,
        search: Optional[str] = None,
        country: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict]:
        """
        Fetch all counterparties from Kudu table

        Args:
            search: Optional search term for name or description
            country: Optional filter by country
            is_active: Optional filter by active status

        Returns:
            List of counterparty dictionaries
        """
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE 1=1"

        if search:
            search_escaped = search.replace('\\', '\\\\').replace("'", "\\'")
            query += f" AND (LOWER(counterparty_short_name) LIKE '%{search_escaped.lower()}%' OR LOWER(counterparty_full_name) LIKE '%{search_escaped.lower()}%')"

        if country:
            country_escaped = country.replace('\\', '\\\\').replace("'", "\\'")
            query += f" AND country = '{country_escaped}'"

        if is_active is not None:
            query += f" AND is_active = {str(is_active).upper()}"

        # Order by src_system='CIS' first, then by counterparty_short_name
        query += " ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, counterparty_short_name"

        results = self._execute_query(query)
        return results

    def get_by_short_name(self, short_name: str) -> Optional[Dict]:
        """Get specific counterparty by short name (primary key)"""
        short_name_escaped = short_name.replace('\\', '\\\\').replace("'", "\\'")
        query = f"SELECT * FROM {self.TABLE_NAME} WHERE counterparty_short_name = '{short_name_escaped}' LIMIT 1"

        results = self._execute_query(query)
        return results[0] if results else None

    def get_distinct_countries(self) -> List[str]:
        """Get list of distinct countries for dropdown filter"""
        query = f"SELECT DISTINCT country FROM {self.TABLE_NAME} WHERE country IS NOT NULL AND country != '' ORDER BY country"
        results = self._execute_query(query)
        return [r['country'] for r in results if r.get('country')]

    def create(self, counterparty_data: Dict[str, Any]) -> bool:
        """
        Create new counterparty using UPSERT

        Args:
            counterparty_data: Dictionary with all counterparty fields

        Returns:
            True if successful, False otherwise
        """
        # Build column list and values list
        columns = []
        values = []

        # Required fields
        columns.append('counterparty_short_name')
        values.append(f"'{self._escape_sql(counterparty_data.get('counterparty_short_name', ''))}'")

        # Optional string fields
        string_fields = [
            'm_label', 'counterparty_full_name', 'record_type',
            'address_line_0', 'address_line_1', 'address_line_2', 'address_line_3',
            'city', 'country', 'postal_code',
            'fax_number', 'telex_number', 'primary_contact', 'primary_number',
            'other_contact', 'other_number',
            'industry', 'industry_group',
            'subsidiary_level', 'counterparty_grandparent', 'counterparty_parent',
            'resident_y_n', 'mas_industry_code', 'country_of_incorporation', 'cels_code',
            'src_system', 'sub_system', 'data_cat', 'data_frq', 'src_id',
            'processing_date', 'created_by', 'updated_by'
        ]

        for field in string_fields:
            if field in counterparty_data:
                columns.append(field)
                value = counterparty_data[field]
                if value is None or value == '':
                    values.append('NULL')
                else:
                    values.append(f"'{self._escape_sql(str(value))}'")

        # Boolean fields
        boolean_fields = [
            'is_broker', 'is_custodian', 'is_issuer', 'is_bank',
            'is_subsidiary', 'is_corporate', 'is_active', 'is_deleted'
        ]

        for field in boolean_fields:
            if field in counterparty_data:
                columns.append(field)
                value = counterparty_data[field]
                if isinstance(value, bool):
                    values.append(str(value).upper())
                elif isinstance(value, str) and value.upper() in ['TRUE', 'FALSE']:
                    values.append(value.upper())
                else:
                    values.append('FALSE')

        # Build UPSERT query
        columns_str = ', '.join(columns)
        values_str = ', '.join(values)

        query = f"""
        UPSERT INTO {self.TABLE_NAME} ({columns_str})
        VALUES ({values_str})
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            print(f"Error creating counterparty: {e}")
            return False

    def update(self, short_name: str, counterparty_data: Dict[str, Any]) -> bool:
        """
        Update existing counterparty using UPSERT

        Args:
            short_name: Counterparty short name (primary key)
            counterparty_data: Dictionary with updated fields

        Returns:
            True if successful, False otherwise
        """
        # UPSERT works for both insert and update in Kudu
        counterparty_data['counterparty_short_name'] = short_name
        return self.create(counterparty_data)

    def soft_delete(self, short_name: str, updated_by: str) -> bool:
        """
        Soft delete counterparty (set is_active = false, is_deleted = true)

        Args:
            short_name: Counterparty short name
            updated_by: User performing the delete

        Returns:
            True if successful, False otherwise
        """
        short_name_escaped = short_name.replace('\\', '\\\\').replace("'", "\\'")
        updated_by_escaped = updated_by.replace('\\', '\\\\').replace("'", "\\'")

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            counterparty_short_name, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            counterparty_short_name,
            FALSE as is_active,
            TRUE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE counterparty_short_name = '{short_name_escaped}'
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            print(f"Error soft deleting counterparty: {e}")
            return False

    def restore(self, short_name: str, updated_by: str) -> bool:
        """
        Restore soft-deleted counterparty (set is_active = true, is_deleted = false)

        Args:
            short_name: Counterparty short name
            updated_by: User performing the restore

        Returns:
            True if successful, False otherwise
        """
        short_name_escaped = short_name.replace('\\', '\\\\').replace("'", "\\'")
        updated_by_escaped = updated_by.replace('\\', '\\\\').replace("'", "\\'")

        query = f"""
        UPSERT INTO {self.TABLE_NAME} (
            counterparty_short_name, is_active, is_deleted, updated_by, updated_at
        )
        SELECT
            counterparty_short_name,
            TRUE as is_active,
            FALSE as is_deleted,
            '{updated_by_escaped}' as updated_by,
            now() as updated_at
        FROM {self.TABLE_NAME}
        WHERE counterparty_short_name = '{short_name_escaped}'
        """

        try:
            self._execute_write(query)
            return True
        except Exception as e:
            print(f"Error restoring counterparty: {e}")
            return False


# Singleton instances
currency_repository = CurrencyRepository()
country_repository = CountryRepository()
calendar_repository = CalendarRepository()
mascode_repository = MascodeRepository()
counterparty_repository = CounterpartyRepository()
