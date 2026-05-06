"""
System Date Repository

Data access layer for system date operations.
Reads system date from GMP file date table (cis_system_date).

Tables:
- cis_system_date: GMP file date (MRC_PC_DATE.txt)

Author: CIS Trade Hive Team
Created: 2026-04-08
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class SystemDateRepository:
    """Repository for system date database operations."""

    DATABASE = 'gmp_cis'
    SYSTEM_DATE_TABLE = 'cis_system_date'

    @staticmethod
    def get_current_system_date() -> Optional[Dict[str, Any]]:
        """
        Get current active system date from GMP file.

        Returns:
            Dict with system_date, report_date, processing_date, etc.
            None if no active date found.
        """
        try:
            query = f"""
            SELECT date_id, system_date, report_date, processing_date,
                   source_file, file_date_raw, is_active, is_business_day,
                   loaded_by, loaded_at, created_at, updated_at
            FROM {SystemDateRepository.DATABASE}.{SystemDateRepository.SYSTEM_DATE_TABLE}
            WHERE is_active = true
            ORDER BY loaded_at DESC
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=SystemDateRepository.DATABASE)

            if results and len(results) > 0:
                return results[0]

            logger.warning("No active system date found in cis_system_date table")
            return None

        except Exception as e:
            logger.error(f"Error getting current system date: {str(e)}")
            return None

    @staticmethod
    def update_system_date(
        system_date: str,
        report_date: str,
        processing_date: str,
        source_file: str,
        file_date_raw: str,
        loaded_by: str,
        is_business_day: bool = True
    ) -> bool:
        """
        Update system date (called by ETL after loading MRC_PC_DATE.txt).

        First deactivates all existing records, then inserts new active record.

        Args:
            system_date: Business date T (YYYYMMDD)
            report_date: Report date T-1 (YYYYMMDD)
            processing_date: Processing date (YYYYMMDD)
            source_file: Source file name
            file_date_raw: Raw date from file
            loaded_by: ETL job or user
            is_business_day: Whether system_date is a business day

        Returns:
            True if successful
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Deactivate all existing records
            deactivate_sql = f"""
            UPDATE {SystemDateRepository.DATABASE}.{SystemDateRepository.SYSTEM_DATE_TABLE}
            SET is_active = false, updated_at = '{timestamp_str}'
            WHERE is_active = true
            """
            impala_manager.execute_write(deactivate_sql, database=SystemDateRepository.DATABASE)

            # Generate new date_id (BIGINT ms PK — intentional)
            date_id = timestamp_ms

            # Insert new active record
            insert_sql = f"""
            UPSERT INTO {SystemDateRepository.DATABASE}.{SystemDateRepository.SYSTEM_DATE_TABLE} (
                date_id, system_date, report_date, processing_date,
                source_file, file_date_raw, is_active, is_business_day,
                loaded_by, loaded_at, created_at, updated_at
            ) VALUES (
                {date_id}, '{system_date}', '{report_date}', '{processing_date}',
                '{source_file}', '{file_date_raw}', true, {str(is_business_day).lower()},
                '{loaded_by}', '{timestamp_str}', '{timestamp_str}', '{timestamp_str}'
            )
            """

            success = impala_manager.execute_write(insert_sql, database=SystemDateRepository.DATABASE)

            if success:
                logger.info(f"System date updated: system_date={system_date}, report_date={report_date}")

            return success

        except Exception as e:
            logger.error(f"Error updating system date: {str(e)}")
            return False


# Singleton instance
system_date_repository = SystemDateRepository()
