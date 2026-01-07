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
    """Service for Counterparty reference data - Now with full CRUD operations"""

    def __init__(self):
        self.repository = counterparty_repository

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
            country: Filter by country
            is_active: Filter by active status

        Returns:
            List of counterparty dictionaries
        """
        return self.repository.list_all(search=search, country=country, is_active=is_active)

    def get_by_short_name(self, short_name: str) -> Optional[Dict]:
        """Get specific counterparty by short name (primary key)"""
        return self.repository.get_by_short_name(short_name)

    def get_distinct_countries(self) -> List[str]:
        """Get list of distinct countries for dropdown filter"""
        return self.repository.get_distinct_countries()

    def validate_counterparty(
        self,
        counterparty_data: Dict[str, Any],
        is_update: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Validate counterparty data

        Args:
            counterparty_data: Dictionary with counterparty fields
            is_update: True if this is an update operation

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required field validation
        short_name = counterparty_data.get('counterparty_short_name', '').strip()
        if not short_name:
            return False, "Counterparty short name is required"

        # Check for duplicate on create
        if not is_update:
            existing = self.repository.get_by_short_name(short_name)
            if existing:
                return False, f"Counterparty with short name '{short_name}' already exists"

        # Validate short name length
        if len(short_name) > 100:
            return False, "Counterparty short name must be 100 characters or less"

        # Full name validation
        full_name = counterparty_data.get('counterparty_full_name', '').strip()
        if full_name and len(full_name) > 255:
            return False, "Counterparty full name must be 255 characters or less"

        return True, None

    def create_counterparty(
        self,
        counterparty_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Create new counterparty with validation and audit logging

        Args:
            counterparty_data: Dictionary with all counterparty fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Validate
        is_valid, error_msg = self.validate_counterparty(counterparty_data, is_update=False)
        if not is_valid:
            return False, error_msg

        # Set audit fields
        username = user_info.get('username', 'system')
        counterparty_data['created_by'] = username
        counterparty_data['updated_by'] = username
        counterparty_data['is_active'] = True
        counterparty_data['is_deleted'] = False

        # Create in repository
        success = self.repository.create(counterparty_data)

        if success:
            return True, None
        else:
            return False, "Failed to create counterparty in database"

    def update_counterparty(
        self,
        short_name: str,
        counterparty_data: Dict[str, Any],
        user_info: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Update existing counterparty with validation and audit logging

        Args:
            short_name: Counterparty short name (primary key)
            counterparty_data: Dictionary with updated fields
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Counterparty '{short_name}' not found"

        # Validate (skip duplicate check for updates)
        counterparty_data['counterparty_short_name'] = short_name
        is_valid, error_msg = self.validate_counterparty(counterparty_data, is_update=True)
        if not is_valid:
            return False, error_msg

        # Set audit fields
        username = user_info.get('username', 'system')
        counterparty_data['updated_by'] = username

        # Update in repository
        success = self.repository.update(short_name, counterparty_data)

        if success:
            return True, None
        else:
            return False, "Failed to update counterparty in database"

    def delete_counterparty(
        self,
        short_name: str,
        user_info: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Soft delete counterparty

        Args:
            short_name: Counterparty short name
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Counterparty '{short_name}' not found"

        # Check if already deleted
        if existing.get('is_deleted'):
            return False, f"Counterparty '{short_name}' is already deleted"

        # Soft delete
        username = user_info.get('username', 'system')
        success = self.repository.soft_delete(short_name, username)

        if success:
            return True, None
        else:
            return False, "Failed to delete counterparty in database"

    def restore_counterparty(
        self,
        short_name: str,
        user_info: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        Restore soft-deleted counterparty

        Args:
            short_name: Counterparty short name
            user_info: User information for audit logging

        Returns:
            Tuple of (success, error_message)
        """
        # Check if exists
        existing = self.repository.get_by_short_name(short_name)
        if not existing:
            return False, f"Counterparty '{short_name}' not found"

        # Check if not deleted
        if not existing.get('is_deleted'):
            return False, f"Counterparty '{short_name}' is not deleted"

        # Restore
        username = user_info.get('username', 'system')
        success = self.repository.restore(short_name, username)

        if success:
            return True, None
        else:
            return False, "Failed to restore counterparty in database"


# Singleton instances
currency_service = CurrencyService()
country_service = CountryService()
calendar_service = CalendarService()
counterparty_service = CounterpartyService()
