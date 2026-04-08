"""
System Date Service

Core service for managing system date across the CIS application.
Provides unified access to system date with override support.

Priority Order for System Date:
1. User Override (per-user session override)
2. Global Override (admin-set override for all users)
3. GMP File Date (from cis_system_date table)
4. Fallback: Current date (if all above fail)

Features:
- Date validation (business day check, date range limits)
- User override support (session-based)
- Global override support (admin-controlled)
- Caching for performance
- Audit trail for all changes

Author: CIS Trade Hive Team
Created: 2026-04-08
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from enum import Enum

from django.core.cache import cache

from core.repositories.system_date_repository import system_date_repository

logger = logging.getLogger(__name__)


class DateValidationError(Enum):
    """Date validation error types."""
    NONE = 'none'
    INVALID_FORMAT = 'invalid_format'
    TOO_FAR_BACK = 'too_far_back'
    TOO_FAR_FORWARD = 'too_far_forward'
    WEEKEND = 'weekend'
    HOLIDAY = 'holiday'
    EOD_LOCKED = 'eod_locked'


@dataclass
class DateValidationResult:
    """Result of date validation."""
    is_valid: bool
    error: DateValidationError
    message: str
    warnings: list


@dataclass
class SystemDateInfo:
    """Complete system date information."""
    system_date: date                    # Effective system date (T)
    system_date_str: str                 # YYYYMMDD format
    system_date_display: str             # YYYY-MM-DD format
    report_date: Optional[date]          # Report date (T-1)
    report_date_str: Optional[str]
    processing_date: Optional[date]      # Processing date
    processing_date_str: Optional[str]
    source: str                          # 'USER_OVERRIDE', 'GLOBAL_OVERRIDE', 'GMP_FILE', 'FALLBACK'
    is_override: bool                    # True if date is overridden
    override_reason: Optional[str]       # Reason for override
    is_business_day: bool                # Whether system_date is a business day
    gmp_file_date: Optional[str]         # Original GMP file date
    warnings: list                       # Any warnings


# Cache settings
CACHE_KEY_SYSTEM_DATE = 'system_date:gmp_file'
CACHE_KEY_CONFIG_PREFIX = 'system_date:config:'
CACHE_TTL = 300  # 5 minutes


class SystemDateService:
    """
    Core service for system date management.

    This service is the single source of truth for system date across
    the application. All components should use this service to get
    the current system date.
    """

    # Date format constants
    DATE_FORMAT_DB = '%Y%m%d'      # YYYYMMDD
    DATE_FORMAT_DISPLAY = '%Y-%m-%d'  # YYYY-MM-DD
    DATE_FORMAT_ISO = '%Y-%m-%d'

    # =========================================================================
    # MAIN API - Get System Date
    # =========================================================================

    def get_system_date(self, username: str = None) -> date:
        """
        Get the effective system date.

        This is the main method to get system date. It checks overrides
        in priority order and returns the effective date.

        Priority:
        1. User override (if username provided and has active override)
        2. Global override (if active)
        3. GMP file date
        4. Current date (fallback)

        Args:
            username: Optional username to check user-specific override

        Returns:
            Effective system date
        """
        info = self.get_system_date_info(username)
        return info.system_date

    def get_system_date_str(self, username: str = None, format: str = None) -> str:
        """
        Get system date as string.

        Args:
            username: Optional username for user override
            format: Date format (default: YYYYMMDD)

        Returns:
            System date string
        """
        system_date = self.get_system_date(username)
        fmt = format or self.DATE_FORMAT_DB
        return system_date.strftime(fmt)

    def get_system_date_info(self, username: str = None) -> SystemDateInfo:
        """
        Get complete system date information including source and overrides.

        Args:
            username: Optional username for user override

        Returns:
            SystemDateInfo with all date details
        """
        warnings = []

        # Check EOD lock
        if system_date_repository.is_eod_locked():
            warnings.append('System is in EOD lock state')

        # 1. Check user override (highest priority)
        if username:
            user_override = system_date_repository.get_user_date_override(username)
            if user_override:
                try:
                    override_date = self._parse_date(user_override)
                    return self._build_date_info(
                        system_date=override_date,
                        source='USER_OVERRIDE',
                        is_override=True,
                        override_reason=f'User override for {username}',
                        warnings=warnings
                    )
                except ValueError:
                    logger.error(f"Invalid user override date format: {user_override}")

        # 2. Check global override
        global_override = system_date_repository.get_global_date_override()
        if global_override:
            try:
                override_date = self._parse_date(global_override)
                return self._build_date_info(
                    system_date=override_date,
                    source='GLOBAL_OVERRIDE',
                    is_override=True,
                    override_reason='Global admin override',
                    warnings=warnings
                )
            except ValueError:
                logger.error(f"Invalid global override date format: {global_override}")

        # 3. Get from GMP file (with caching)
        gmp_date_info = self._get_gmp_file_date()
        if gmp_date_info:
            system_date_str = gmp_date_info.get('system_date')
            report_date_str = gmp_date_info.get('report_date')
            processing_date_str = gmp_date_info.get('processing_date')

            try:
                system_date = self._parse_date(system_date_str)
                report_date = self._parse_date(report_date_str) if report_date_str else None
                processing_date = self._parse_date(processing_date_str) if processing_date_str else None

                # Check if GMP date is stale (> 5 days old)
                days_old = (date.today() - system_date).days
                if days_old > 5:
                    warnings.append(f'GMP file date is {days_old} days old')

                return self._build_date_info(
                    system_date=system_date,
                    report_date=report_date,
                    processing_date=processing_date,
                    source='GMP_FILE',
                    is_override=False,
                    gmp_file_date=gmp_date_info.get('file_date_raw'),
                    is_business_day=gmp_date_info.get('is_business_day', True),
                    warnings=warnings
                )
            except ValueError as e:
                logger.error(f"Invalid GMP date format: {e}")

        # 4. Fallback to current date
        warnings.append('Using fallback date (GMP file not loaded)')
        logger.warning("No GMP file date available, using current date as fallback")

        return self._build_date_info(
            system_date=date.today(),
            source='FALLBACK',
            is_override=False,
            warnings=warnings
        )

    def get_report_date(self, username: str = None) -> Optional[date]:
        """
        Get the report date (T-1).

        Args:
            username: Optional username

        Returns:
            Report date or None
        """
        info = self.get_system_date_info(username)
        return info.report_date

    def get_processing_date(self, username: str = None) -> Optional[date]:
        """
        Get the processing date.

        Args:
            username: Optional username

        Returns:
            Processing date or None
        """
        info = self.get_system_date_info(username)
        return info.processing_date

    # =========================================================================
    # OVERRIDE MANAGEMENT
    # =========================================================================

    def set_user_override(
        self,
        username: str,
        override_date: str,
        reason: str = '',
        valid_hours: int = 24
    ) -> Tuple[bool, str]:
        """
        Set user-specific date override.

        Args:
            username: User login
            override_date: Override date (YYYYMMDD)
            reason: Reason for override
            valid_hours: Hours until override expires

        Returns:
            Tuple of (success, message)
        """
        # Check if user override is allowed
        if not self._is_user_override_allowed():
            return False, 'User date override is not allowed by system configuration'

        # Check EOD lock
        if system_date_repository.is_eod_locked():
            return False, 'Cannot set override: System is in EOD lock state'

        # Validate date
        validation = self.validate_date(override_date)
        if not validation.is_valid:
            return False, validation.message

        # Set override
        success = system_date_repository.set_user_date_override(
            username=username,
            override_date=override_date,
            reason=reason,
            valid_hours=valid_hours
        )

        if success:
            return True, f'System date override set to {override_date}'
        else:
            return False, 'Failed to set date override'

    def clear_user_override(self, username: str) -> Tuple[bool, str]:
        """
        Clear user-specific date override.

        Args:
            username: User login

        Returns:
            Tuple of (success, message)
        """
        success = system_date_repository.clear_user_date_override(username)

        if success:
            return True, 'Date override cleared'
        else:
            return False, 'Failed to clear date override'

    def set_global_override(
        self,
        override_date: str,
        admin_user: str,
        reason: str = ''
    ) -> Tuple[bool, str]:
        """
        Set global date override (admin only).

        Args:
            override_date: Override date (YYYYMMDD)
            admin_user: Admin username
            reason: Reason for override

        Returns:
            Tuple of (success, message)
        """
        # Validate date
        validation = self.validate_date(override_date, allow_future=True)
        if not validation.is_valid:
            return False, validation.message

        # Set override
        success = system_date_repository.set_global_date_override(
            override_date=override_date,
            updated_by=admin_user,
            reason=reason
        )

        if success:
            # Invalidate cache
            cache.delete(CACHE_KEY_SYSTEM_DATE)
            return True, f'Global system date override set to {override_date}'
        else:
            return False, 'Failed to set global date override'

    def clear_global_override(self, admin_user: str) -> Tuple[bool, str]:
        """
        Clear global date override (admin only).

        Args:
            admin_user: Admin username

        Returns:
            Tuple of (success, message)
        """
        success = system_date_repository.clear_global_date_override(admin_user)

        if success:
            cache.delete(CACHE_KEY_SYSTEM_DATE)
            return True, 'Global date override cleared'
        else:
            return False, 'Failed to clear global date override'

    def is_override_active(self, username: str = None) -> bool:
        """
        Check if any override is active.

        Args:
            username: Optional username to check user override

        Returns:
            True if override is active
        """
        info = self.get_system_date_info(username)
        return info.is_override

    # =========================================================================
    # DATE VALIDATION
    # =========================================================================

    def validate_date(
        self,
        date_str: str,
        allow_past: bool = True,
        allow_future: bool = False
    ) -> DateValidationResult:
        """
        Validate a date string.

        Args:
            date_str: Date string (YYYYMMDD)
            allow_past: Allow past dates
            allow_future: Allow future dates

        Returns:
            DateValidationResult
        """
        warnings = []

        # Check format
        try:
            check_date = self._parse_date(date_str)
        except ValueError:
            return DateValidationResult(
                is_valid=False,
                error=DateValidationError.INVALID_FORMAT,
                message=f'Invalid date format: {date_str}. Expected YYYYMMDD.',
                warnings=[]
            )

        today = date.today()
        days_diff = (check_date - today).days

        # Check past limit
        if not allow_past and days_diff < 0:
            return DateValidationResult(
                is_valid=False,
                error=DateValidationError.TOO_FAR_BACK,
                message='Past dates are not allowed',
                warnings=[]
            )

        # Check max days back
        max_days_back = self._get_config_int('MAX_OVERRIDE_DAYS_BACK', 30)
        if days_diff < -max_days_back:
            return DateValidationResult(
                is_valid=False,
                error=DateValidationError.TOO_FAR_BACK,
                message=f'Date is too far in the past. Maximum {max_days_back} days back allowed.',
                warnings=[]
            )

        # Check future limit
        if not allow_future and days_diff > 0:
            return DateValidationResult(
                is_valid=False,
                error=DateValidationError.TOO_FAR_FORWARD,
                message='Future dates are not allowed',
                warnings=[]
            )

        # Check max days forward
        max_days_forward = self._get_config_int('MAX_OVERRIDE_DAYS_FORWARD', 5)
        if days_diff > max_days_forward:
            return DateValidationResult(
                is_valid=False,
                error=DateValidationError.TOO_FAR_FORWARD,
                message=f'Date is too far in the future. Maximum {max_days_forward} days forward allowed.',
                warnings=[]
            )

        # Check weekend
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            warnings.append(f'{date_str} is a weekend (non-business day)')

        # TODO: Check against holiday calendar
        # if self._is_holiday(check_date):
        #     warnings.append(f'{date_str} is a holiday')

        return DateValidationResult(
            is_valid=True,
            error=DateValidationError.NONE,
            message='Date is valid',
            warnings=warnings
        )

    def is_business_day(self, check_date: date) -> bool:
        """
        Check if date is a business day.

        Args:
            check_date: Date to check

        Returns:
            True if business day
        """
        # Check weekend
        if check_date.weekday() >= 5:
            return False

        # TODO: Check against holiday calendar
        # return not self._is_holiday(check_date)

        return True

    def get_next_business_day(self, from_date: date) -> date:
        """
        Get next business day from given date.

        Args:
            from_date: Starting date

        Returns:
            Next business day
        """
        next_day = from_date + timedelta(days=1)

        while not self.is_business_day(next_day):
            next_day += timedelta(days=1)

        return next_day

    def get_previous_business_day(self, from_date: date) -> date:
        """
        Get previous business day from given date.

        Args:
            from_date: Starting date

        Returns:
            Previous business day
        """
        prev_day = from_date - timedelta(days=1)

        while not self.is_business_day(prev_day):
            prev_day -= timedelta(days=1)

        return prev_day

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_gmp_file_date(self) -> Optional[Dict[str, Any]]:
        """Get GMP file date with caching."""
        # Try cache first
        cached = cache.get(CACHE_KEY_SYSTEM_DATE)
        if cached:
            return cached

        # Fetch from database
        date_info = system_date_repository.get_current_system_date()

        if date_info:
            cache.set(CACHE_KEY_SYSTEM_DATE, date_info, CACHE_TTL)

        return date_info

    def _parse_date(self, date_str: str) -> date:
        """Parse date string (YYYYMMDD) to date object."""
        if not date_str or len(date_str) != 8:
            raise ValueError(f"Invalid date string: {date_str}")

        return datetime.strptime(date_str, self.DATE_FORMAT_DB).date()

    def _format_date(self, d: date, format: str = None) -> str:
        """Format date to string."""
        fmt = format or self.DATE_FORMAT_DB
        return d.strftime(fmt)

    def _build_date_info(
        self,
        system_date: date,
        source: str,
        is_override: bool,
        report_date: date = None,
        processing_date: date = None,
        override_reason: str = None,
        gmp_file_date: str = None,
        is_business_day: bool = None,
        warnings: list = None
    ) -> SystemDateInfo:
        """Build SystemDateInfo object."""
        if is_business_day is None:
            is_business_day = self.is_business_day(system_date)

        # For override, calculate report_date as system_date - 1
        if is_override and report_date is None:
            report_date = system_date - timedelta(days=1)
            processing_date = report_date

        return SystemDateInfo(
            system_date=system_date,
            system_date_str=self._format_date(system_date),
            system_date_display=system_date.strftime(self.DATE_FORMAT_DISPLAY),
            report_date=report_date,
            report_date_str=self._format_date(report_date) if report_date else None,
            processing_date=processing_date,
            processing_date_str=self._format_date(processing_date) if processing_date else None,
            source=source,
            is_override=is_override,
            override_reason=override_reason,
            is_business_day=is_business_day,
            gmp_file_date=gmp_file_date,
            warnings=warnings or []
        )

    def _is_user_override_allowed(self) -> bool:
        """Check if user override is allowed by configuration."""
        config = system_date_repository.get_config('ALLOW_USER_DATE_OVERRIDE')
        if config and config.get('is_active'):
            return config.get('config_value', '').lower() == 'true'
        return True  # Default allow

    def _get_config_int(self, key: str, default: int) -> int:
        """Get integer config value."""
        config = system_date_repository.get_config(key)
        if config and config.get('is_active') and config.get('config_value'):
            try:
                return int(config.get('config_value'))
            except ValueError:
                pass
        return default

    # =========================================================================
    # EOD MANAGEMENT
    # =========================================================================

    def set_eod_lock(self, admin_user: str) -> Tuple[bool, str]:
        """
        Lock system for EOD processing.

        Args:
            admin_user: Admin username

        Returns:
            Tuple of (success, message)
        """
        success = system_date_repository.set_config(
            config_key='EOD_LOCK',
            config_value='true',
            updated_by=admin_user,
            is_active=True
        )

        if success:
            return True, 'EOD lock enabled'
        return False, 'Failed to enable EOD lock'

    def clear_eod_lock(self, admin_user: str) -> Tuple[bool, str]:
        """
        Clear EOD lock.

        Args:
            admin_user: Admin username

        Returns:
            Tuple of (success, message)
        """
        success = system_date_repository.set_config(
            config_key='EOD_LOCK',
            config_value='false',
            updated_by=admin_user,
            is_active=True
        )

        if success:
            return True, 'EOD lock cleared'
        return False, 'Failed to clear EOD lock'

    def is_eod_locked(self) -> bool:
        """Check if system is in EOD lock state."""
        return system_date_repository.is_eod_locked()

    # =========================================================================
    # HISTORY
    # =========================================================================

    def get_history(self, limit: int = 50) -> list:
        """Get system date change history."""
        return system_date_repository.get_history(limit)


# Singleton instance
system_date_service = SystemDateService()
