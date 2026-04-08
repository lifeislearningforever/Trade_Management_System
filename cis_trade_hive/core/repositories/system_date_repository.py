"""
System Date Repository

Data access layer for system date operations.
Handles reading from GMP file date table and configuration overrides.

Tables:
- cis_system_date: GMP file date (MRC_PC_DATE.txt)
- cis_system_config: Configuration overrides
- cis_user_date_override: Per-user date overrides
- cis_system_date_history: Audit trail

Author: CIS Trade Hive Team
Created: 2026-04-08
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class SystemDateRepository:
    """Repository for system date database operations."""

    DATABASE = 'gmp_cis'
    SYSTEM_DATE_TABLE = 'cis_system_date'
    CONFIG_TABLE = 'cis_system_config'
    USER_OVERRIDE_TABLE = 'cis_user_date_override'
    HISTORY_TABLE = 'cis_system_date_history'

    # =========================================================================
    # SYSTEM DATE (from GMP file)
    # =========================================================================

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

            # Deactivate all existing records
            deactivate_sql = f"""
            UPDATE {SystemDateRepository.DATABASE}.{SystemDateRepository.SYSTEM_DATE_TABLE}
            SET is_active = false, updated_at = {timestamp_ms}
            WHERE is_active = true
            """
            impala_manager.execute_write(deactivate_sql, database=SystemDateRepository.DATABASE)

            # Generate new date_id (timestamp-based)
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
                '{loaded_by}', {timestamp_ms}, {timestamp_ms}, {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=SystemDateRepository.DATABASE)

            if success:
                # Log to history
                SystemDateRepository._log_history(
                    date_id=date_id,
                    action='LOAD',
                    system_date=system_date,
                    report_date=report_date,
                    processing_date=processing_date,
                    performed_by=loaded_by,
                    notes=f'Loaded from {source_file}'
                )
                logger.info(f"System date updated: system_date={system_date}, report_date={report_date}")

            return success

        except Exception as e:
            logger.error(f"Error updating system date: {str(e)}")
            return False

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    @staticmethod
    def get_config(config_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a configuration value.

        Args:
            config_key: Configuration key

        Returns:
            Configuration dict or None
        """
        try:
            query = f"""
            SELECT config_key, config_value, config_type, description, category,
                   is_active, valid_from, valid_to,
                   created_by, created_at, updated_by, updated_at
            FROM {SystemDateRepository.DATABASE}.{SystemDateRepository.CONFIG_TABLE}
            WHERE config_key = '{config_key}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=SystemDateRepository.DATABASE)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error getting config {config_key}: {str(e)}")
            return None

    @staticmethod
    def get_configs_by_category(category: str) -> List[Dict[str, Any]]:
        """
        Get all configurations for a category.

        Args:
            category: Category name (e.g., 'SYSTEM_DATE')

        Returns:
            List of configuration dicts
        """
        try:
            query = f"""
            SELECT config_key, config_value, config_type, description, category,
                   is_active, valid_from, valid_to,
                   created_by, created_at, updated_by, updated_at
            FROM {SystemDateRepository.DATABASE}.{SystemDateRepository.CONFIG_TABLE}
            WHERE category = '{category}'
            ORDER BY config_key
            """

            results = impala_manager.execute_query(query, database=SystemDateRepository.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting configs for category {category}: {str(e)}")
            return []

    @staticmethod
    def set_config(
        config_key: str,
        config_value: str,
        updated_by: str,
        is_active: bool = True
    ) -> bool:
        """
        Set a configuration value.

        Args:
            config_key: Configuration key
            config_value: New value
            updated_by: User making the change
            is_active: Whether config is active

        Returns:
            True if successful
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

            # Escape value for SQL
            escaped_value = config_value.replace("'", "''") if config_value else ''

            sql = f"""
            UPSERT INTO {SystemDateRepository.DATABASE}.{SystemDateRepository.CONFIG_TABLE} (
                config_key, config_value, is_active, updated_by, updated_at
            ) VALUES (
                '{config_key}', '{escaped_value}', {str(is_active).lower()},
                '{updated_by}', {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(sql, database=SystemDateRepository.DATABASE)

            if success:
                logger.info(f"Config updated: {config_key}={config_value} by {updated_by}")

            return success

        except Exception as e:
            logger.error(f"Error setting config {config_key}: {str(e)}")
            return False

    @staticmethod
    def get_global_date_override() -> Optional[str]:
        """
        Get global system date override if active.

        Returns:
            Override date string (YYYYMMDD) or None if no active override
        """
        try:
            config = SystemDateRepository.get_config('SYSTEM_DATE_OVERRIDE')

            if config and config.get('is_active') and config.get('config_value'):
                return config.get('config_value')

            return None

        except Exception as e:
            logger.error(f"Error getting global date override: {str(e)}")
            return None

    @staticmethod
    def set_global_date_override(
        override_date: str,
        updated_by: str,
        reason: str = ''
    ) -> bool:
        """
        Set global system date override.

        Args:
            override_date: Override date (YYYYMMDD)
            updated_by: Admin user
            reason: Reason for override

        Returns:
            True if successful
        """
        try:
            success = SystemDateRepository.set_config(
                config_key='SYSTEM_DATE_OVERRIDE',
                config_value=override_date,
                updated_by=updated_by,
                is_active=True
            )

            if success:
                # Log to history
                SystemDateRepository._log_history(
                    date_id=0,
                    action='OVERRIDE',
                    system_date=override_date,
                    override_date=override_date,
                    override_reason=reason,
                    performed_by=updated_by,
                    notes=f'Global override set: {reason}'
                )

            return success

        except Exception as e:
            logger.error(f"Error setting global date override: {str(e)}")
            return False

    @staticmethod
    def clear_global_date_override(updated_by: str) -> bool:
        """
        Clear global system date override.

        Args:
            updated_by: Admin user

        Returns:
            True if successful
        """
        try:
            success = SystemDateRepository.set_config(
                config_key='SYSTEM_DATE_OVERRIDE',
                config_value='',
                updated_by=updated_by,
                is_active=False
            )

            if success:
                SystemDateRepository._log_history(
                    date_id=0,
                    action='CLEAR_OVERRIDE',
                    performed_by=updated_by,
                    notes='Global override cleared'
                )

            return success

        except Exception as e:
            logger.error(f"Error clearing global date override: {str(e)}")
            return False

    @staticmethod
    def is_eod_locked() -> bool:
        """
        Check if system is in EOD lock state.

        Returns:
            True if EOD locked
        """
        try:
            config = SystemDateRepository.get_config('EOD_LOCK')
            if config and config.get('is_active'):
                return config.get('config_value', '').lower() == 'true'
            return False

        except Exception as e:
            logger.error(f"Error checking EOD lock: {str(e)}")
            return False

    # =========================================================================
    # USER OVERRIDE
    # =========================================================================

    @staticmethod
    def get_user_date_override(username: str) -> Optional[str]:
        """
        Get user-specific date override.

        Args:
            username: User login

        Returns:
            Override date string (YYYYMMDD) or None
        """
        try:
            query = f"""
            SELECT override_id, username, override_date, override_reason,
                   is_active, valid_until, created_at
            FROM {SystemDateRepository.DATABASE}.{SystemDateRepository.USER_OVERRIDE_TABLE}
            WHERE username = '{username}'
              AND is_active = true
              AND (valid_until IS NULL OR valid_until > {int(datetime.now().timestamp() * 1000)})
            ORDER BY created_at DESC
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=SystemDateRepository.DATABASE)

            if results and len(results) > 0:
                return results[0].get('override_date')

            return None

        except Exception as e:
            logger.error(f"Error getting user date override for {username}: {str(e)}")
            return None

    @staticmethod
    def set_user_date_override(
        username: str,
        override_date: str,
        reason: str = '',
        valid_hours: int = 24
    ) -> bool:
        """
        Set user-specific date override.

        Args:
            username: User login
            override_date: Override date (YYYYMMDD)
            reason: Reason for override
            valid_hours: Hours until override expires (default 24)

        Returns:
            True if successful
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            valid_until = timestamp_ms + (valid_hours * 60 * 60 * 1000)
            override_id = timestamp_ms

            # Deactivate existing overrides for user
            deactivate_sql = f"""
            UPDATE {SystemDateRepository.DATABASE}.{SystemDateRepository.USER_OVERRIDE_TABLE}
            SET is_active = false, updated_at = {timestamp_ms}
            WHERE username = '{username}' AND is_active = true
            """
            impala_manager.execute_write(deactivate_sql, database=SystemDateRepository.DATABASE)

            # Insert new override
            insert_sql = f"""
            UPSERT INTO {SystemDateRepository.DATABASE}.{SystemDateRepository.USER_OVERRIDE_TABLE} (
                override_id, username, override_date, override_reason,
                is_active, valid_until, created_by, created_at, updated_at
            ) VALUES (
                {override_id}, '{username}', '{override_date}', '{reason.replace("'", "''")}',
                true, {valid_until}, '{username}', {timestamp_ms}, {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=SystemDateRepository.DATABASE)

            if success:
                logger.info(f"User date override set: {username} -> {override_date}")
                SystemDateRepository._log_history(
                    date_id=0,
                    action='USER_OVERRIDE',
                    system_date=override_date,
                    override_date=override_date,
                    override_reason=reason,
                    performed_by=username,
                    notes=f'User override for {valid_hours} hours'
                )

            return success

        except Exception as e:
            logger.error(f"Error setting user date override for {username}: {str(e)}")
            return False

    @staticmethod
    def clear_user_date_override(username: str) -> bool:
        """
        Clear user-specific date override.

        Args:
            username: User login

        Returns:
            True if successful
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)

            sql = f"""
            UPDATE {SystemDateRepository.DATABASE}.{SystemDateRepository.USER_OVERRIDE_TABLE}
            SET is_active = false, updated_at = {timestamp_ms}
            WHERE username = '{username}' AND is_active = true
            """

            success = impala_manager.execute_write(sql, database=SystemDateRepository.DATABASE)

            if success:
                logger.info(f"User date override cleared for {username}")
                SystemDateRepository._log_history(
                    date_id=0,
                    action='CLEAR_USER_OVERRIDE',
                    performed_by=username,
                    notes='User override cleared'
                )

            return success

        except Exception as e:
            logger.error(f"Error clearing user date override for {username}: {str(e)}")
            return False

    # =========================================================================
    # HISTORY
    # =========================================================================

    @staticmethod
    def _log_history(
        date_id: int,
        action: str,
        performed_by: str,
        system_date: str = None,
        report_date: str = None,
        processing_date: str = None,
        override_date: str = None,
        override_reason: str = None,
        ip_address: str = None,
        user_agent: str = None,
        notes: str = None
    ) -> bool:
        """Log action to history table."""
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            history_id = timestamp_ms

            # Build values, handling NULLs
            def sql_val(val):
                if val is None:
                    return 'NULL'
                return f"'{val.replace(chr(39), chr(39)+chr(39))}'"

            sql = f"""
            UPSERT INTO {SystemDateRepository.DATABASE}.{SystemDateRepository.HISTORY_TABLE} (
                history_id, date_id, action,
                system_date, report_date, processing_date,
                override_date, override_reason,
                performed_by, performed_at,
                ip_address, user_agent, notes
            ) VALUES (
                {history_id}, {date_id}, '{action}',
                {sql_val(system_date)}, {sql_val(report_date)}, {sql_val(processing_date)},
                {sql_val(override_date)}, {sql_val(override_reason)},
                '{performed_by}', {timestamp_ms},
                {sql_val(ip_address)}, {sql_val(user_agent)}, {sql_val(notes)}
            )
            """

            return impala_manager.execute_write(sql, database=SystemDateRepository.DATABASE)

        except Exception as e:
            logger.error(f"Error logging system date history: {str(e)}")
            return False

    @staticmethod
    def get_history(limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get system date history.

        Args:
            limit: Maximum records to return

        Returns:
            List of history records
        """
        try:
            query = f"""
            SELECT history_id, date_id, action,
                   system_date, report_date, processing_date,
                   override_date, override_reason,
                   performed_by, performed_at, notes
            FROM {SystemDateRepository.DATABASE}.{SystemDateRepository.HISTORY_TABLE}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=SystemDateRepository.DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting system date history: {str(e)}")
            return []


# Singleton instance
system_date_repository = SystemDateRepository()
