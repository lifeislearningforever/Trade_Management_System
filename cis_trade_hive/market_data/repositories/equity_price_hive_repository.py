"""
Equity Price Repository for Market Data Module

Manages equity/security pricing data in Kudu via Impala.
Uses composite primary key: (currency_code, security_label, price_date)
Supports versioned price history - multiple prices per security (one per date).
Follows SOLID principles with clean separation of data access logic.
Includes audit logging for CREATE, UPDATE, DELETE operations.

Author: CisTrade Team
Last Updated: 2026-01-31
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import time

from core.repositories.impala_connection import impala_manager
from core.audit.audit_decorator import log_audit

logger = logging.getLogger(__name__)


def _ts_to_display(value) -> str:
    """
    Convert a timestamp value to a human-readable 'YYYY-MM-DD HH:MM:SS' string.
    Handles three formats that may exist in the DB during / after migration:
      - STRING already in 'YYYY-MM-DD HH:MM:SS' format  → returned as-is
      - BIGINT / STRING containing Unix milliseconds      → converted via fromtimestamp
      - datetime object (Impala TIMESTAMP type)          → formatted directly
    """
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    try:
        v = int(value)
        # Unix ms if > year-2100 in seconds (i.e. > 4102444800)
        if v > 4_102_444_800:
            return datetime.fromtimestamp(v / 1000).strftime('%Y-%m-%d %H:%M:%S')
        return datetime.fromtimestamp(v).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return str(value)


class EquityPriceHiveRepository:
    """Repository for Equity Price operations with Impala/Kudu.

    Uses composite primary key: (currency_code, security_label, price_date)
    Supports versioned price history - multiple prices per security (one per date).
    """

    TABLE_NAME = "gmp_cis.cis_equity_price"
    DATABASE = "gmp_cis"
    HISTORY_TABLE_NAME = "gmp_cis.cis_equity_price_history"

    @staticmethod
    def refresh_table():
        """
        Issue REFRESH on the equity price table so the next read sees the
        latest Kudu commits.  Called before the optimistic-lock re-read on
        POST to avoid Kudu eventual-consistency false negatives.
        """
        try:
            impala_manager.execute_write(
                f"REFRESH {EquityPriceHiveRepository.TABLE_NAME}",
                database=EquityPriceHiveRepository.DATABASE,
            )
        except Exception as e:
            logger.warning(f"REFRESH equity price table failed (non-fatal): {e}")

    @staticmethod
    def get_all_equity_prices(
        limit: int = 1000,
        currency_code: Optional[str] = None,
        security_label: Optional[str] = None,
        isin: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        src_system: Optional[str] = None
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
            src_system: Filter by source system (CIS or GMP)

        Returns:
            List of equity price records
        """
        try:
            # Build WHERE clause
            where_clauses = ["(ep.is_active = true OR ep.is_active IS NULL)"]

            if currency_code:
                escaped_currency = currency_code.replace("'", "\\'")
                where_clauses.append(f"ep.currency_code = '{escaped_currency}'")

            if security_label:
                escaped_security = security_label.replace("'", "\\'").lower()
                where_clauses.append(
                    f"(LOWER(ep.security_label) LIKE '%{escaped_security}%'"
                    f" OR LOWER(COALESCE(s.security_description, '')) LIKE '%{escaped_security}%')"
                )

            if isin:
                escaped_isin = isin.replace("'", "\\'")
                where_clauses.append(f"ep.isin = '{escaped_isin}'")

            if date_from:
                where_clauses.append(f"ep.price_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"ep.price_date <= '{date_to}'")

            if src_system:
                escaped_src = src_system.replace("'", "\\'")
                where_clauses.append(f"UPPER(ep.src_system) = '{escaped_src.upper()}'")

            where_clause = " AND ".join(where_clauses)

            # Build query - LEFT JOIN cis_security to enrich with security_description
            query = f"""
            SELECT
                ep.currency_code,
                ep.security_label,
                ep.isin,
                ep.price_date,
                ep.main_closing_price,
                ep.price_timestamp,
                ep.src_system,
                ep.is_active,
                ep.created_by,
                ep.created_at,
                ep.updated_by,
                ep.updated_at,
                COALESCE(s.security_description, '') AS security_description
            FROM {EquityPriceHiveRepository.TABLE_NAME} ep
            LEFT JOIN gmp_cis.cis_security s ON ep.security_label = s.security_name
            WHERE {where_clause}
            ORDER BY ep.price_date DESC, ep.security_label
            LIMIT {limit}
            """

            logger.info(f"Executing equity price query with filters: {where_clause}")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            # Add formatted timestamp for display
            for row in results:
                if row.get('price_timestamp'):
                    row['price_datetime'] = _ts_to_display(row['price_timestamp'])

                if row.get('created_at'):
                    row['created_at_display'] = _ts_to_display(row['created_at'])

                if row.get('updated_at'):
                    row['updated_at_display'] = _ts_to_display(row['updated_at'])

            logger.info(f"Retrieved {len(results)} equity prices")
            return results

        except Exception as e:
            logger.error(f"Error retrieving equity prices: {str(e)}")
            return []

    @staticmethod
    def get_equity_price_by_key(currency_code: str, security_label: str, price_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get equity price by composite key (currency_code, security_label, price_date).
        If price_date is not provided, returns the latest price for this security.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            price_date: Price date in YYYY-MM-DD format (optional - if None, returns latest)

        Returns:
            Equity price record or None
        """
        try:
            escaped_currency = currency_code.replace("'", "\\'")
            escaped_security = security_label.replace("'", "\\'")

            date_clause = ""
            if price_date:
                escaped_date = price_date.replace("'", "\\'")
                date_clause = f"AND price_date = '{escaped_date}'"

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
              AND (is_active = true OR is_active IS NULL)
              {date_clause}
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """

            logger.info(f"Retrieving equity price by key: {currency_code}/{security_label}/{price_date or 'latest'}")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            if not results:
                logger.warning(f"No equity price found with key: {currency_code}/{security_label}/{price_date or 'latest'}")
                return None

            row = results[0]

            # Add formatted timestamps
            if row.get('price_timestamp'):
                row['price_datetime'] = _ts_to_display(row['price_timestamp'])

            if row.get('created_at'):
                row['created_at_display'] = _ts_to_display(row['created_at'])

            if row.get('updated_at'):
                row['updated_at_display'] = _ts_to_display(row['updated_at'])

            return row

        except Exception as e:
            logger.error(f"Error getting equity price by key {currency_code}/{security_label}: {str(e)}")
            return None

    @staticmethod
    def get_latest_price(security_label: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest equity price for a security across all currencies.
        Used by trade creation to get the current market price.

        Args:
            security_label: Security label

        Returns:
            Latest equity price record or None
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
                is_active,
                created_by,
                created_at
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE security_label = '{escaped_security}'
              AND (is_active = true OR is_active IS NULL)
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            if not results:
                return None

            return results[0]

        except Exception as e:
            logger.error(f"Error getting latest price for {security_label}: {str(e)}")
            return None

    @staticmethod
    def upsert_equity_price(equity_price_data: Dict[str, Any], username: str = 'SYSTEM', is_update: bool = False, _skip_audit: bool = False) -> bool:
        """
        Insert or update equity price using UPSERT (composite key).

        Args:
            equity_price_data: Dictionary with equity price fields
            username: User performing the operation (for audit)
            is_update: True if record already exists (affects audit action_type)
            _skip_audit: Skip internal audit log (used when caller handles its own audit)

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
            price_timestamp = equity_price_data.get('price_timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            src_system = equity_price_data.get('src_system', 'CIS').replace("'", "\\'")
            created_by = equity_price_data.get('created_by', username).replace("'", "\\'")
            created_at = equity_price_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            updated_by = equity_price_data.get('updated_by', username).replace("'", "\\'") if equity_price_data.get('updated_by') else ''
            updated_at = equity_price_data.get('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')) if equity_price_data.get('updated_by') else None

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
                {f"'{price_timestamp}'" if price_timestamp is not None else 'NULL'},
                '{src_system}',
                true,
                '{created_by}',
                '{created_at}',
                {f"'{updated_by}'" if updated_by else 'NULL'},
                {f"'{updated_at}'" if updated_at else 'NULL'}
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
            if not _skip_audit:
                log_audit(
                    action_type='UPDATE' if is_update else 'CREATE',
                    entity_type='EQUITY_PRICE',
                    entity_id=f"{equity_price_data.get('currency_code')}/{equity_price_data.get('security_label')}",
                    entity_name=equity_price_data.get('security_label'),
                    new_value=equity_price_data,
                    success=success,
                    error_message=error_msg,
                    username=username
                )

    @staticmethod
    def update_equity_price(currency_code: str, security_label: str, equity_price_data: Dict[str, Any], username: str = 'SYSTEM', price_date: Optional[str] = None) -> bool:
        """
        Update existing equity price using UPSERT.

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            equity_price_data: Dictionary with fields to update
            username: User performing the operation (for audit)
            price_date: Price date (part of composite key). If None, updates the latest price.

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        success = False
        error_msg = None
        old_value = None

        try:
            # Get existing record for audit comparison
            existing = EquityPriceHiveRepository.get_equity_price_by_key(currency_code, security_label, price_date)
            if not existing:
                logger.error(f"Cannot update: equity price {currency_code}/{security_label}/{price_date or 'latest'} not found")
                error_msg = f"Equity price {currency_code}/{security_label}/{price_date or 'latest'} not found"
                return False

            old_value = existing

            # Merge existing data with updates
            merged_data = {**existing, **equity_price_data}
            merged_data['currency_code'] = currency_code
            merged_data['security_label'] = security_label
            merged_data['updated_by'] = username
            _now = datetime.now()
            merged_data['updated_at'] = _now.strftime('%Y-%m-%d %H:%M:%S')
            # Store as Unix milliseconds (string) so every save produces a
            # strictly unique token. Two saves in the same millisecond are
            # impossible from separate HTTP requests; _ts_to_display() already
            # handles this numeric-string format for display.
            import time as _time
            merged_data['price_timestamp'] = str(int(_time.time() * 1000))

            # Use upsert; skip its own audit — update_equity_price's finally block handles it
            success = EquityPriceHiveRepository.upsert_equity_price(merged_data, username, is_update=True, _skip_audit=True)

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
                entity_id=f"{currency_code}/{security_label}/{price_date or 'latest'}",
                entity_name=security_label,
                old_value=old_value,
                new_value=equity_price_data,
                success=success,
                error_message=error_msg,
                username=username
            )

    @staticmethod
    def delete_equity_price(currency_code: str, security_label: str, deleted_by: str, price_date: Optional[str] = None) -> bool:
        """
        Soft delete equity price (set is_active to false).

        Args:
            currency_code: Currency code (part of composite key)
            security_label: Security label (part of composite key)
            deleted_by: User performing deletion
            price_date: Price date (part of composite key). If None, deletes the latest price.

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        success = False
        error_msg = None
        old_value = None

        try:
            # Get existing record for audit
            old_value = EquityPriceHiveRepository.get_equity_price_by_key(currency_code, security_label, price_date)
            if not old_value:
                error_msg = f"Equity price {currency_code}/{security_label}/{price_date or 'latest'} not found"
                return False

            # Use the actual price_date from the record found
            actual_price_date = old_value.get('price_date', price_date)

            # Perform soft delete via update
            success = EquityPriceHiveRepository.update_equity_price(
                currency_code,
                security_label,
                {
                    'is_active': False,
                    'updated_by': deleted_by
                },
                username=deleted_by,
                price_date=actual_price_date
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
                entity_id=f"{currency_code}/{security_label}/{price_date or 'latest'}",
                entity_name=security_label,
                old_value=old_value,
                success=success,
                error_message=error_msg,
                username=deleted_by
            )

    @staticmethod
    def get_price_history(
        security_label: str,
        days: int = 30,
        reference_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get price history for a specific security.

        Args:
            security_label: Security name
            days: Number of days of history
            reference_date: Anchor date for the window (YYYY-MM-DD).
                            Defaults to today so current callers are unaffected.
                            On the detail page we pass the record's own price_date
                            so older records always show their surrounding history.

        Returns:
            List of historical prices sorted by date descending
        """
        try:
            escaped_security = security_label.replace("'", "\\'")
            anchor = datetime.strptime(reference_date, '%Y-%m-%d') if reference_date else datetime.now()
            from_date = (anchor - timedelta(days=days)).strftime('%Y-%m-%d')

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
              AND (is_active = true OR is_active IS NULL)
              AND price_date >= '{from_date}'
            ORDER BY price_date ASC
            LIMIT 365
            """

            logger.info(f"Retrieving price history for {security_label} ({days} days from {from_date})")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            # Add formatted timestamps
            for row in results:
                if row.get('price_timestamp'):
                    row['price_datetime'] = _ts_to_display(row['price_timestamp'])

            logger.info(f"Retrieved {len(results)} historical prices for {security_label}")
            return results

        except Exception as e:
            logger.error(f"Error getting price history for {security_label}: {str(e)}")
            return []

    @staticmethod
    def save_to_history(existing_record: Dict[str, Any], changed_by: str, change_type: str = 'UPDATE') -> bool:
        """
        Save a snapshot of the existing record to the history table before it gets overwritten.
        Called BEFORE update or delete operations.

        Args:
            existing_record: The current record dict (before the change)
            changed_by: Username making the change
            change_type: 'UPDATE' or 'DELETE'

        Returns:
            True if history record saved successfully
        """
        try:
            history_id = int(time.time() * 1000)  # PK — keep as BIGINT ms
            changed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            currency_code = str(existing_record.get('currency_code', '')).replace("'", "\\'")
            security_label = str(existing_record.get('security_label', '')).replace("'", "\\'")
            price_date = str(existing_record.get('price_date', '')).replace("'", "\\'")
            isin = str(existing_record.get('isin', '')).replace("'", "\\'") if existing_record.get('isin') else None
            main_closing_price = existing_record.get('main_closing_price', 0)
            price_timestamp = existing_record.get('price_timestamp')
            src_system = str(existing_record.get('src_system', '')).replace("'", "\\'") if existing_record.get('src_system') else None
            escaped_changed_by = changed_by.replace("'", "\\'")
            escaped_change_type = change_type.replace("'", "\\'")

            query = f"""
            UPSERT INTO {EquityPriceHiveRepository.HISTORY_TABLE_NAME} (
                history_id, currency_code, security_label, price_date,
                isin, main_closing_price, price_timestamp, src_system,
                changed_by, changed_at, change_type
            ) VALUES (
                {history_id},
                '{currency_code}',
                '{security_label}',
                '{price_date}',
                {f"'{isin}'" if isin else 'NULL'},
                {main_closing_price if main_closing_price is not None else 'NULL'},
                {f"'{price_timestamp}'" if price_timestamp else 'NULL'},
                {f"'{src_system}'" if src_system else 'NULL'},
                '{escaped_changed_by}',
                '{changed_at}',
                '{escaped_change_type}'
            )
            """

            success = impala_manager.execute_write(query, database=EquityPriceHiveRepository.DATABASE)

            if success:
                logger.info(f"Saved history for {currency_code}/{security_label}/{price_date} ({change_type} by {changed_by})")
            else:
                logger.error(f"Failed to save history for {currency_code}/{security_label}/{price_date}")

            return success

        except Exception as e:
            logger.error(f"Error saving to history: {str(e)}")
            return False

    @staticmethod
    def get_version_history(
        currency_code: str,
        security_label: str,
        price_date: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get edit history for a specific equity price record.

        Args:
            currency_code: Currency code
            security_label: Security label
            price_date: Price date
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            escaped_currency = currency_code.replace("'", "\\'")
            escaped_security = security_label.replace("'", "\\'")
            escaped_date = price_date.replace("'", "\\'")

            query = f"""
            SELECT
                history_id, currency_code, security_label, price_date,
                isin, main_closing_price, price_timestamp, src_system,
                changed_by, changed_at, change_type
            FROM {EquityPriceHiveRepository.HISTORY_TABLE_NAME}
            WHERE currency_code = '{escaped_currency}'
              AND security_label = '{escaped_security}'
              AND price_date = '{escaped_date}'
            ORDER BY changed_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            for row in results:
                if row.get('changed_at'):
                    row['changed_at_display'] = _ts_to_display(row['changed_at'])

            logger.info(f"Retrieved {len(results)} history records for {currency_code}/{security_label}/{price_date}")
            return results

        except Exception as e:
            logger.error(f"Error getting version history: {str(e)}")
            return []

    @staticmethod
    def get_all_history_for_security(
        currency_code: str,
        security_label: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all edit history for a security across all dates.

        Args:
            currency_code: Currency code
            security_label: Security label
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            escaped_currency = currency_code.replace("'", "\\'")
            escaped_security = security_label.replace("'", "\\'")

            query = f"""
            SELECT
                history_id, currency_code, security_label, price_date,
                isin, main_closing_price, price_timestamp, src_system,
                changed_by, changed_at, change_type
            FROM {EquityPriceHiveRepository.HISTORY_TABLE_NAME}
            WHERE currency_code = '{escaped_currency}'
              AND security_label = '{escaped_security}'
            ORDER BY changed_at DESC
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            for row in results:
                if row.get('changed_at'):
                    row['changed_at_display'] = _ts_to_display(row['changed_at'])

            logger.info(f"Retrieved {len(results)} history records for {currency_code}/{security_label}")
            return results

        except Exception as e:
            logger.error(f"Error getting history for security: {str(e)}")
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
            WHERE (is_active = true OR is_active IS NULL)
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
