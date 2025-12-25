"""
Reference Data Services

Fetches reference data from Hive following Repository pattern.
Single Responsibility: Each service handles one type of reference data.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import date
from django.conf import settings
from reference_data.repositories import (
    currency_repository,
    country_repository,
    calendar_repository,
    counterparty_repository,
)

logger = logging.getLogger('reference_data')


class CurrencyService:
    """Service for Currency reference data"""

    def __init__(self):
        self.repository = currency_repository

    def list_all(self, search: Optional[str] = None, is_active: bool = True) -> List[Dict]:
        """
        Fetch all currencies from Hive

        Args:
            search: Optional search term for code or name
            is_active: Filter by active status (not used in Hive implementation)

        Returns:
            List of currency dictionaries
        """
        results = self.repository.list_all(search=search)

        # Transform column names to match expected format
        return [{
            'code': r.get('iso_code'),
            'name': r.get('name'),
            'full_name': r.get('full_name'),
            'symbol': r.get('symbol'),
            'decimal_places': r.get('precision'),
            'rate_precision': r.get('rate_precision'),
            'calendar': r.get('calendar'),
            'spot_schedule': r.get('spot_schedule'),
        } for r in results]

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific currency by ISO code"""
        result = self.repository.get_by_code(code)

        if not result:
            return None

        # Transform column names to match expected format
        return {
            'code': result.get('iso_code'),
            'name': result.get('name'),
            'full_name': result.get('full_name'),
            'symbol': result.get('symbol'),
            'decimal_places': result.get('precision'),
            'rate_precision': result.get('rate_precision'),
            'calendar': result.get('calendar'),
            'spot_schedule': result.get('spot_schedule'),
        }

    def get_active_currencies(self) -> List[Dict]:
        """Get list of active currencies for dropdowns"""
        return self.list_all(is_active=True)


class CountryService:
    """Service for Country reference data"""

    def __init__(self):
        self.repository = country_repository

    def list_all(self, search: Optional[str] = None) -> List[Dict]:
        """
        Fetch all countries from Hive

        Args:
            search: Optional search term for code or name

        Returns:
            List of country dictionaries
        """
        results = self.repository.list_all(search=search)

        # Transform column names to match expected format
        return [{
            'code': r.get('label'),
            'name': r.get('full_name'),
        } for r in results]

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code"""
        result = self.repository.get_by_code(code)

        if not result:
            return None

        # Transform column names to match expected format
        return {
            'code': result.get('label'),
            'name': result.get('full_name'),
        }


class CalendarService:
    """Service for Calendar/Holiday reference data"""

    def __init__(self):
        self.repository = calendar_repository

    def list_all(
        self,
        calendar_label: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch calendar/holiday data from Hive

        Args:
            calendar_label: Filter by specific calendar
            start_date: Filter by date range start (not yet implemented)
            end_date: Filter by date range end (not yet implemented)
            search: Search in calendar description

        Returns:
            List of calendar dictionaries
        """
        # Note: date filtering is done in repository, simplified for now
        return self.repository.list_all(calendar_label=calendar_label, search=search)

    def get_distinct_calendars(self) -> List[str]:
        """Get list of distinct calendar labels"""
        return self.repository.get_distinct_calendars()

    def get_holidays_for_calendar(self, calendar_label: str) -> List[Dict]:
        """Get all holidays for a specific calendar"""
        return self.repository.get_holidays_for_calendar(calendar_label)


class CounterpartyService:
    """Service for Counterparty reference data"""

    def __init__(self):
        self.repository = counterparty_repository

    def list_all(self, search: Optional[str] = None, counterparty_type: Optional[str] = None) -> List[Dict]:
        """
        Fetch all counterparties from Hive

        Args:
            search: Optional search term for name or description
            counterparty_type: Filter by counterparty type (not implemented yet)

        Returns:
            List of counterparty dictionaries
        """
        return self.repository.list_all(search=search)

    def get_by_name(self, name: str) -> Optional[Dict]:
        """Get specific counterparty by name"""
        return self.repository.get_by_name(name)


# Singleton instances
currency_service = CurrencyService()
country_service = CountryService()
calendar_service = CalendarService()
counterparty_service = CounterpartyService()
