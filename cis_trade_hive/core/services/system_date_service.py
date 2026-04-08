"""
System Date Service

Core service for managing system date across the CIS application.
Provides unified access to system date from GMP file (MRC_PC_DATE.txt).

Date Logic:
- report_date: Date from GMP file (T-1)
- processing_date: Same as report_date
- system_date: report_date + 1 (business date T)

Author: CIS Trade Hive Team
Created: 2026-04-08
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta
from dataclasses import dataclass

from django.core.cache import cache

from core.repositories.system_date_repository import system_date_repository

logger = logging.getLogger(__name__)


@dataclass
class SystemDateInfo:
    """System date information from GMP file."""
    system_date: date                    # Business date (T)
    system_date_str: str                 # YYYYMMDD format
    system_date_display: str             # YYYY-MM-DD format
    report_date: Optional[date]          # Report date (T-1)
    report_date_str: Optional[str]
    report_date_display: Optional[str]
    processing_date: Optional[date]      # Processing date
    processing_date_str: Optional[str]
    source: str                          # 'GMP_FILE' or 'FALLBACK'
    is_business_day: bool
    source_file: Optional[str]           # Source file name
    loaded_at: Optional[datetime]        # When data was loaded


# Cache settings
CACHE_KEY_SYSTEM_DATE = 'system_date:current'
CACHE_TTL = 300  # 5 minutes


class SystemDateService:
    """
    Core service for system date management.

    This service provides the system date from GMP file (MRC_PC_DATE.txt).
    All components should use this service to get the current system date.
    """

    # Date format constants
    DATE_FORMAT_DB = '%Y%m%d'      # YYYYMMDD
    DATE_FORMAT_DISPLAY = '%Y-%m-%d'  # YYYY-MM-DD

    def get_system_date(self) -> date:
        """
        Get the current system date.

        Returns:
            System date (T) from GMP file, or today as fallback
        """
        info = self.get_system_date_info()
        return info.system_date

    def get_system_date_str(self, format: str = None) -> str:
        """
        Get system date as string.

        Args:
            format: Date format (default: YYYYMMDD)

        Returns:
            System date string
        """
        system_date = self.get_system_date()
        fmt = format or self.DATE_FORMAT_DB
        return system_date.strftime(fmt)

    def get_report_date(self) -> Optional[date]:
        """
        Get the report date (T-1).

        Returns:
            Report date from GMP file
        """
        info = self.get_system_date_info()
        return info.report_date

    def get_processing_date(self) -> Optional[date]:
        """
        Get the processing date.

        Returns:
            Processing date from GMP file
        """
        info = self.get_system_date_info()
        return info.processing_date

    def get_system_date_info(self) -> SystemDateInfo:
        """
        Get complete system date information.

        Returns:
            SystemDateInfo with all date details
        """
        # Try cache first
        cached = cache.get(CACHE_KEY_SYSTEM_DATE)
        if cached:
            return cached

        # Fetch from database
        gmp_date_info = system_date_repository.get_current_system_date()

        if gmp_date_info:
            system_date_str = gmp_date_info.get('system_date')
            report_date_str = gmp_date_info.get('report_date')
            processing_date_str = gmp_date_info.get('processing_date')

            try:
                system_date = self._parse_date(system_date_str)
                report_date = self._parse_date(report_date_str) if report_date_str else None
                processing_date = self._parse_date(processing_date_str) if processing_date_str else None

                # Convert loaded_at from epoch ms to datetime
                loaded_at_ms = gmp_date_info.get('loaded_at')
                loaded_at = datetime.fromtimestamp(loaded_at_ms / 1000) if loaded_at_ms else None

                info = SystemDateInfo(
                    system_date=system_date,
                    system_date_str=system_date_str,
                    system_date_display=system_date.strftime(self.DATE_FORMAT_DISPLAY),
                    report_date=report_date,
                    report_date_str=report_date_str,
                    report_date_display=report_date.strftime(self.DATE_FORMAT_DISPLAY) if report_date else None,
                    processing_date=processing_date,
                    processing_date_str=processing_date_str,
                    source='GMP_FILE',
                    is_business_day=gmp_date_info.get('is_business_day', True),
                    source_file=gmp_date_info.get('source_file'),
                    loaded_at=loaded_at
                )

                # Cache the result
                cache.set(CACHE_KEY_SYSTEM_DATE, info, CACHE_TTL)
                return info

            except ValueError as e:
                logger.error(f"Invalid GMP date format: {e}")

        # Fallback to current date
        logger.warning("No GMP file date available, using current date as fallback")
        today = date.today()
        yesterday = today - timedelta(days=1)

        return SystemDateInfo(
            system_date=today,
            system_date_str=today.strftime(self.DATE_FORMAT_DB),
            system_date_display=today.strftime(self.DATE_FORMAT_DISPLAY),
            report_date=yesterday,
            report_date_str=yesterday.strftime(self.DATE_FORMAT_DB),
            report_date_display=yesterday.strftime(self.DATE_FORMAT_DISPLAY),
            processing_date=yesterday,
            processing_date_str=yesterday.strftime(self.DATE_FORMAT_DB),
            source='FALLBACK',
            is_business_day=today.weekday() < 5,
            source_file=None,
            loaded_at=None
        )

    def is_business_day(self, check_date: date = None) -> bool:
        """
        Check if date is a business day.

        Args:
            check_date: Date to check (default: system date)

        Returns:
            True if business day (not weekend)
        """
        if check_date is None:
            info = self.get_system_date_info()
            return info.is_business_day

        # Simple weekend check
        return check_date.weekday() < 5

    def clear_cache(self):
        """Clear the cached system date."""
        cache.delete(CACHE_KEY_SYSTEM_DATE)
        logger.info("System date cache cleared")

    def _parse_date(self, date_str: str) -> date:
        """Parse date string (YYYYMMDD) to date object."""
        if not date_str or len(date_str) != 8:
            raise ValueError(f"Invalid date string: {date_str}")
        return datetime.strptime(date_str, self.DATE_FORMAT_DB).date()


# Singleton instance
system_date_service = SystemDateService()
