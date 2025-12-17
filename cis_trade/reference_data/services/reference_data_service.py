"""
Reference Data Services

Fetches reference data from Kudu/Impala following Repository pattern.
Single Responsibility: Each service handles one type of reference data.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date
from django.conf import settings
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger('reference_data')


class BaseReferenceService:
    """Base class for reference data services (DRY principle)"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = None  # Override in subclasses

    def _execute_query(self, query: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Execute query and return results"""
        try:
            results = impala_manager.execute_query(query, params, self.DATABASE)
            logger.info(f"Fetched {len(results)} rows from {self.TABLE_NAME}")
            return results
        except Exception as e:
            logger.error(f"Error fetching from {self.TABLE_NAME}: {str(e)}")
            return []


class CurrencyService(BaseReferenceService):
    """Service for Currency reference data"""

    TABLE_NAME = 'gmp_cis_sta_dly_currency'

    def list_all(self, search: Optional[str] = None, is_active: bool = True) -> List[Dict]:
        """
        Fetch all currencies from Kudu.

        Args:
            search: Optional search term for code or name
            is_active: Filter by active status

        Returns:
            List of currency dictionaries
        """
        query = f"""
            SELECT
                name,
                full_name,
                symbol,
                iso_code AS code,
                precision AS decimal_places,
                rate_precision,
                calendar,
                spot_schedule
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE 1=1
        """

        params = []

        if search:
            query += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(iso_code) LIKE LOWER(%s))"
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        query += " ORDER BY iso_code"

        return self._execute_query(query, params if params else None)

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific currency by ISO code"""
        query = f"""
            SELECT
                name,
                full_name,
                symbol,
                iso_code AS code,
                precision AS decimal_places,
                rate_precision,
                calendar,
                spot_schedule
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE iso_code = %s
            LIMIT 1
        """

        results = self._execute_query(query, [code])
        return results[0] if results else None

    def get_active_currencies(self) -> List[Dict]:
        """Get list of active currencies for dropdowns"""
        return self.list_all(is_active=True)


class CountryService(BaseReferenceService):
    """Service for Country reference data"""

    TABLE_NAME = 'gmp_cis_sta_dly_country'

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all countries from Kudu.

        Args:
            search: Optional search term for code or name

        Returns:
            List of country dictionaries
        """
        query = f"""
            SELECT
                label AS code,
                full_name AS name
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE 1=1
        """

        params = []

        if search:
            query += " AND (LOWER(label) LIKE LOWER(%s) OR LOWER(full_name) LIKE LOWER(%s))"
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        query += " ORDER BY label"

        return self._execute_query(query, params if params else None)

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code"""
        query = f"""
            SELECT
                label AS code,
                full_name AS name
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE label = %s
            LIMIT 1
        """

        results = self._execute_query(query, [code])
        return results[0] if results else None


class CalendarService(BaseReferenceService):
    """Service for Calendar/Holiday reference data"""

    TABLE_NAME = 'gmp_cis_sta_dly_calendar'

    def list_all(
        self,
        calendar_label: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch calendar/holiday data from Kudu.

        Args:
            calendar_label: Filter by specific calendar
            start_date: Filter by date range start
            end_date: Filter by date range end
            search: Search in calendar description

        Returns:
            List of calendar dictionaries
        """
        query = f"""
            SELECT
                calendar_label,
                calendar_description,
                CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(
                    NULLIF(TRIM(holiday_date), ''), 'yyyyMMdd')) AS DATE) AS holiday_date
            FROM {self.DATABASE}.{self.TABLE_NAME}
            WHERE 1=1
        """

        params = []

        if calendar_label:
            query += " AND calendar_label = %s"
            params.append(calendar_label)

        if start_date:
            query += " AND CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(NULLIF(TRIM(holiday_date), ''), 'yyyyMMdd')) AS DATE) >= %s"
            params.append(start_date)

        if end_date:
            query += " AND CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(NULLIF(TRIM(holiday_date), ''), 'yyyyMMdd')) AS DATE) <= %s"
            params.append(end_date)

        if search:
            query += " AND LOWER(calendar_description) LIKE LOWER(%s)"
            params.append(f"%{search}%")

        query += " ORDER BY holiday_date DESC"

        return self._execute_query(query, params if params else None)

    def get_distinct_calendars(self) -> List[str]:
        """Get list of distinct calendar labels"""
        query = f"""
            SELECT DISTINCT calendar_label
            FROM {self.DATABASE}.{self.TABLE_NAME}
            ORDER BY calendar_label
        """

        results = self._execute_query(query)
        return [r.get('calendar_label') for r in results if r.get('calendar_label')]

    def get_holidays_for_year(self, calendar_label: str, year: int) -> List[Dict]:
        """Get all holidays for a specific calendar and year"""
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        return self.list_all(calendar_label=calendar_label, start_date=start_date, end_date=end_date)


class CounterpartyService(BaseReferenceService):
    """Service for Counterparty reference data"""

    # For now, use Django ORM since counterparty might not be in Kudu yet
    # This demonstrates flexibility of the architecture

    def list_all(self, search: Optional[str] = None, counterparty_type: Optional[str] = None) -> List[Dict]:
        """
        Fetch all counterparties.

        In production, this would query Kudu.
        For now, returns empty list or uses Django ORM.
        """
        from reference_data.models import Counterparty

        queryset = Counterparty.objects.filter(is_active=True)

        if search:
            queryset = queryset.filter(
                models.Q(code__icontains=search) |
                models.Q(name__icontains=search)
            )

        if counterparty_type:
            queryset = queryset.filter(counterparty_type=counterparty_type)

        # Convert to list of dicts
        return list(queryset.values(
            'id', 'code', 'name', 'legal_name', 'counterparty_type',
            'email', 'phone', 'city', 'country', 'status', 'risk_category'
        ))

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific counterparty by code"""
        from reference_data.models import Counterparty

        try:
            obj = Counterparty.objects.get(code=code, is_active=True)
            return {
                'id': obj.id,
                'code': obj.code,
                'name': obj.name,
                'legal_name': obj.legal_name,
                'counterparty_type': obj.counterparty_type,
                'email': obj.email,
                'phone': obj.phone,
                'city': obj.city,
                'country': obj.country,
                'status': obj.status,
                'risk_category': obj.risk_category,
            }
        except Counterparty.DoesNotExist:
            return None


# Singleton instances
currency_service = CurrencyService()
country_service = CountryService()
calendar_service = CalendarService()
counterparty_service = CounterpartyService()
