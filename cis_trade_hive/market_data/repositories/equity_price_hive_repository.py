"""
Equity Price Repository for Market Data Module

Manages equity/security pricing data in Kudu via Impala.
Uses composite primary key: (currency_code, security_label)
Follows SOLID principles with clean separation of data access logic.
Includes audit logging for CREATE, UPDATE, DELETE operations.

Author: CisTrade Team
Last Updated: 2026-01-28
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import time

from core.repositories.impala_connection import impala_manager
from core.audit.audit_decorator import log_audit

logger = logging.getLogger(__name__)


class EquityPriceHiveRepository:
    """Repository for Equity Price operations with Impala/Kudu.

    Uses composite primary key: (currency_code, security_label)
    """

    TABLE_NAME = "gmp_cis.cis_equity_price"
    DATABASE = "gmp_cis"

    @staticmethod
    def get_all_equity_prices(
        limit: int = 1000,
        currency_code: Optional[str] = None,
        security_label: Optional[str] = None,
        isin: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve equity prices from Kudu with filters.

        Args:
            limit: Maximum number of records
            currency_code: Filter by currency
            security_label: Filter by security name (supports wildcard search)
            isin: Filter by ISIN code
            date_from: Filter by start date (YYYY-MM-DD format)
            date_to: Filter by end date (YYYY-MM-DD format)

        Returns:
            List of equity price records
        """
        try:
            # Build WHERE clause
            where_clauses = ["is_active = true"]

            if currency_code:
                escaped_currency = currency_code.replace("'", "\\'")
                where_clauses.append(f"currency_code = '{escaped_currency}'")

            if security_label:
                escaped_security = security_label.replace("'", "\\'").lower()
                # Use LIKE with wildcards for partial matching (case-insensitive)
                where_clauses.append(f"LOWER(security_label) LIKE '%{escaped_security}%'")

            if isin:
                escaped_isin = isin.replace("'", "\\'")
                where_clauses.append(f"isin = '{escaped_isin}'")

            if date_from:
                where_clauses.append(f"price_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"price_date <= '{date_to}'")

            where_clause = " AND ".join(where_clauses)

            # Build query - removed market and group_name, using composite key
            query = f"""
            SELECT
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                price_timestamp,
                src_system,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY price_date DESC, security_label
            LIMIT {limit}
            """

            logger.info(f"Executing equity price query with filters: {where_clause}")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            # Add formatted timestamp for display
            for row in results:
                if row.get('price_timestamp'):
                    timestamp_ms = row['price_timestamp']
                    row['price_datetime'] = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

                if row.get('created_at'):
                    created_ms = row['created_at']
                    row['created_at_display'] = datetime.fromtimestamp(created_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

                if row.get('updated_at'):
                    updated_ms = row['updated_at']
                    row['updated_at_display'] = datetime.fromtimestamp(updated_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"Retrieved {len(results)} equity prices")
            return results

        except Exception as e:
            logger.error(f"Error retrieving equity prices: {str(e)}")
            return []

    @staticmethod
    def get_equity_price_by_key(currency_code: str, security_label: str) -> Optional[Dict[str, Any]]:
        """
        Get equity price by composite key (currency_code, security_label).

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)

        Returns:
            Equity price record or None
        """
        try:
            escaped_currency = currency_code.replace("'", "\\'")
            escaped_security = security_label.replace("'", "\\'")

            query = f"""
            SELECT
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                price_timestamp,
                src_system,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE currency_code = '{escaped_currency}'
              AND security_label = '{escaped_security}'
              AND is_active = true
            LIMIT 1
            """

            logger.info(f"Retrieving equity price by key: {currency_code}/{security_label}")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            if not results:
                logger.warning(f"No equity price found with key: {currency_code}/{security_label}")
                return None

            row = results[0]

            # Add formatted timestamps
            if row.get('price_timestamp'):
                timestamp_ms = row['price_timestamp']
                row['price_datetime'] = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

            if row.get('created_at'):
                created_ms = row['created_at']
                row['created_at_display'] = datetime.fromtimestamp(created_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

            if row.get('updated_at'):
                updated_ms = row['updated_at']
                row['updated_at_display'] = datetime.fromtimestamp(updated_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

            return row

        except Exception as e:
            logger.error(f"Error getting equity price by key {currency_code}/{security_label}: {str(e)}")
            return None

    @staticmethod
    def upsert_equity_price(equity_price_data: Dict[str, Any], username: str = 'SYSTEM') -> bool:
        """
        Insert or update equity price using UPSERT (composite key).

        Args:
            equity_price_data: Dictionary with equity price fields
            username: User performing the operation (for audit)

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        success = False
        error_msg = None

        try:
            # Escape string values
            currency_code = equity_price_data.get('currency_code', '').replace("'", "\\'")
            security_label = equity_price_data.get('security_label', '').replace("'", "\\'")
            isin = equity_price_data.get('isin', '').replace("'", "\\'") if equity_price_data.get('isin') else ''
            price_date = equity_price_data.get('price_date', '')
            main_closing_price = equity_price_data.get('main_closing_price', 0)
            price_timestamp = equity_price_data.get('price_timestamp', int(time.time() * 1000))
            src_system = equity_price_data.get('src_system', 'CIS').replace("'", "\\'")
            created_by = equity_price_data.get('created_by', username).replace("'", "\\'")
            created_at = equity_price_data.get('created_at', int(time.time() * 1000))
            updated_by = equity_price_data.get('updated_by', username).replace("'", "\\'") if equity_price_data.get('updated_by') else ''
            updated_at = equity_price_data.get('updated_at', int(time.time() * 1000)) if equity_price_data.get('updated_by') else None

            # Build UPSERT query
            upsert_query = f"""
            UPSERT INTO {EquityPriceHiveRepository.TABLE_NAME} (
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                price_timestamp,
                src_system,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            ) VALUES (
                '{currency_code}',
                '{security_label}',
                {f"'{isin}'" if isin else 'NULL'},
                '{price_date}',
                {main_closing_price},
                {price_timestamp},
                '{src_system}',
                true,
                '{created_by}',
                {created_at},
                {f"'{updated_by}'" if updated_by else 'NULL'},
                {updated_at if updated_at else 'NULL'}
            )
            """

            logger.info(f"Upserting equity price for {currency_code}/{security_label} on {price_date}")
            success = impala_manager.execute_write(upsert_query, database=EquityPriceHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully upserted equity price: {currency_code}/{security_label}")
            else:
                logger.error(f"Failed to upsert equity price for {currency_code}/{security_label}")
                error_msg = "Upsert operation returned False"

            return success

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error upserting equity price: {error_msg}")
            return False

        finally:
            # Audit logging (fire and forget - non-blocking)
            log_audit(
                action_type='UPSERT',
                entity_type='EQUITY_PRICE',
                entity_id=f"{equity_price_data.get('currency_code')}/{equity_price_data.get('security_label')}",
                entity_name=equity_price_data.get('security_label'),
                new_value=equity_price_data,
                success=success,
                error_message=error_msg,
                username=username
            )

    @staticmethod
    def update_equity_price(currency_code: str, security_label: str, equity_price_data: Dict[str, Any], username: str = 'SYSTEM') -> bool:
        """
        Update existing equity price using UPSERT.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            equity_price_data: Dictionary with fields to update
            username: User performing the operation (for audit)

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        success = False
        error_msg = None
        old_value = None

        try:
            # Get existing record for audit comparison
            existing = EquityPriceHiveRepository.get_equity_price_by_key(currency_code, security_label)
            if not existing:
                logger.error(f"Cannot update: equity price {currency_code}/{security_label} not found")
                error_msg = f"Equity price {currency_code}/{security_label} not found"
                return False

            old_value = existing

            # Merge existing data with updates
            merged_data = {**existing, **equity_price_data}
            merged_data['currency_code'] = currency_code
            merged_data['security_label'] = security_label
            merged_data['updated_by'] = username
            merged_data['updated_at'] = int(time.time() * 1000)

            # Use upsert
            success = EquityPriceHiveRepository.upsert_equity_price(merged_data, username)

            if not success:
                error_msg = "Update operation returned False"

            return success

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error updating equity price {currency_code}/{security_label}: {error_msg}")
            return False

        finally:
            # Audit logging (fire and forget - non-blocking)
            log_audit(
                action_type='UPDATE',
                entity_type='EQUITY_PRICE',
                entity_id=f"{currency_code}/{security_label}",
                entity_name=security_label,
                old_value=old_value,
                new_value=equity_price_data,
                success=success,
                error_message=error_msg,
                username=username
            )

    @staticmethod
    def delete_equity_price(currency_code: str, security_label: str, deleted_by: str) -> bool:
        """
        Soft delete equity price (set is_active to false).

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            deleted_by: User performing deletion

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        success = False
        error_msg = None
        old_value = None

        try:
            # Get existing record for audit
            old_value = EquityPriceHiveRepository.get_equity_price_by_key(currency_code, security_label)
            if not old_value:
                error_msg = f"Equity price {currency_code}/{security_label} not found"
                return False

            # Perform soft delete via update
            success = EquityPriceHiveRepository.update_equity_price(
                currency_code,
                security_label,
                {
                    'is_active': False,
                    'updated_by': deleted_by
                },
                username=deleted_by
            )

            if not success:
                error_msg = "Delete operation returned False"

            return success

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting equity price {currency_code}/{security_label}: {error_msg}")
            return False

        finally:
            # Audit logging (fire and forget - non-blocking)
            log_audit(
                action_type='DELETE',
                entity_type='EQUITY_PRICE',
                entity_id=f"{currency_code}/{security_label}",
                entity_name=security_label,
                old_value=old_value,
                success=success,
                error_message=error_msg,
                username=deleted_by
            )

    @staticmethod
    def get_price_history(
        security_label: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get price history for a specific security.

        Args:
            security_label: Security name
            days: Number of days of history

        Returns:
            List of historical prices sorted by date descending
        """
        try:
            escaped_security = security_label.replace("'", "\\'")

            query = f"""
            SELECT
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                price_timestamp,
                src_system,
                created_at,
                updated_at
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE security_label = '{escaped_security}'
              AND is_active = true
            ORDER BY price_date DESC
            LIMIT {days}
            """

            logger.info(f"Retrieving price history for {security_label} ({days} days)")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            # Add formatted timestamps
            for row in results:
                if row.get('price_timestamp'):
                    timestamp_ms = row['price_timestamp']
                    row['price_datetime'] = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"Retrieved {len(results)} historical prices for {security_label}")
            return results

        except Exception as e:
            logger.error(f"Error getting price history for {security_label}: {str(e)}")
            return []

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get equity price statistics.

        Returns:
            Dictionary with statistics
        """
        try:
            stats_query = f"""
            SELECT
                COUNT(*) as total_prices,
                COUNT(DISTINCT security_label) as unique_securities,
                COUNT(DISTINCT currency_code) as unique_currencies,
                MAX(price_date) as latest_date,
                MIN(price_date) as earliest_date
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE is_active = true
            """

            logger.info("Retrieving equity price statistics")
            stats_results = impala_manager.execute_query(stats_query, database=EquityPriceHiveRepository.DATABASE)

            if not stats_results:
                return {
                    'total_prices': 0,
                    'unique_securities': 0,
                    'unique_currencies': 0,
                    'latest_date': 'N/A',
                    'earliest_date': 'N/A'
                }

            return stats_results[0]

        except Exception as e:
            logger.error(f"Error getting equity price statistics: {str(e)}")
            return {
                'total_prices': 0,
                'unique_securities': 0,
                'unique_currencies': 0,
                'latest_date': 'N/A',
                'earliest_date': 'N/A'
            }


# Singleton instance
equity_price_hive_repository = EquityPriceHiveRepository()
