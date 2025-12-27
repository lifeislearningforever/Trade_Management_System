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
        # Repository already returns properly mapped columns
        return results

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
        # Repository already returns properly mapped columns
        return results

    def get_by_code(self, code: str) -> Optional[Dict]:
        """Get specific country by code"""
        result = self.repository.get_by_code(code)

        if not result:
            return None

        # Transform column names to match expected format
        # Handle both qualified (table.column) and unqualified (column) names
        prefix = 'gmp_cis_sta_dly_country.'
        return {
            'code': result.get(f'{prefix}label') or result.get('label'),
            'name': result.get(f'{prefix}full_name') or result.get('full_name'),
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
        results = self.repository.list_all(calendar_label=calendar_label, search=search)

        # Transform column names to match expected format
        # Handle both qualified (table.column) and unqualified (column) names
        prefix = 'gmp_cis_sta_dly_calendar.'
        return [{
            'calendar_label': r.get(f'{prefix}calendar_label') or r.get('calendar_label'),
            'calendar_description': r.get(f'{prefix}calendar_description') or r.get('calendar_description'),
            'holiday_date': r.get(f'{prefix}holiday_date') or r.get('holiday_date'),
        } for r in results]

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
            counterparty_type: Filter by counterparty type

        Returns:
            List of counterparty dictionaries
        """
        results = self.repository.list_all(search=search, counterparty_type=counterparty_type)
        # Repository already returns properly mapped columns
        return results

    def get_by_name(self, name: str) -> Optional[Dict]:
        """Get specific counterparty by name"""
        result = self.repository.get_by_name(name)

        if not result:
            return None

        # Transform column names to match expected format
        prefix = 'gmp_cis_sta_dly_counterparty.'
        return {
            'counterparty_name': result.get(f'{prefix}counterparty_name') or result.get('counterparty_name'),
            'description': result.get(f'{prefix}description') or result.get('description'),
            'salutation': result.get(f'{prefix}salutation') or result.get('salutation'),
            'address': result.get(f'{prefix}address') or result.get('address'),
            'city': result.get(f'{prefix}city') or result.get('city'),
            'country': result.get(f'{prefix}country') or result.get('country'),
            'postal_code': result.get(f'{prefix}postal_code') or result.get('postal_code'),
            'fax': result.get(f'{prefix}fax') or result.get('fax'),
            'telex': result.get(f'{prefix}telex') or result.get('telex'),
            'industry': result.get(f'{prefix}industry') or result.get('industry'),
            'is_counterparty_broker': result.get(f'{prefix}is_counterparty_broker') or result.get('is_counterparty_broker'),
            'is_counterparty_custodian': result.get(f'{prefix}is_counterparty_custodian') or result.get('is_counterparty_custodian'),
            'is_counterparty_issuer': result.get(f'{prefix}is_counterparty_issuer') or result.get('is_counterparty_issuer'),
            'primary_contact': result.get(f'{prefix}primary_contact') or result.get('primary_contact'),
            'primary_number': result.get(f'{prefix}primary_number') or result.get('primary_number'),
            'other_contact': result.get(f'{prefix}other_contact') or result.get('other_contact'),
            'other_number': result.get(f'{prefix}other_number') or result.get('other_number'),
            'custodian_group': result.get(f'{prefix}custodian_group') or result.get('custodian_group'),
            'broker_group': result.get(f'{prefix}broker_group') or result.get('broker_group'),
            'resident_y_n': result.get(f'{prefix}resident_y_n') or result.get('resident_y_n'),
        }


# Singleton instances
currency_service = CurrencyService()
country_service = CountryService()
calendar_service = CalendarService()
counterparty_service = CounterpartyService()
