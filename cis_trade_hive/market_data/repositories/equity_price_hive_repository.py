"""
Equity Price Repository for Market Data Module

Manages equity/security pricing data in Kudu via Impala.
Follows SOLID principles with clean separation of data access logic.

Author: CisTrade Team
Last Updated: 2026-01-04
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import time

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class EquityPriceHiveRepository:
    """Repository for Equity Price operations with Impala/Kudu."""

    TABLE_NAME = "gmp_cis.cis_equity_price"
    DATABASE = "gmp_cis"

    @staticmethod
    def get_all_equity_prices(
        limit: int = 1000,
        currency_code: Optional[str] = None,
        security_label: Optional[str] = None,
        isin: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        market: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve equity prices from Kudu with filters.

        Args:
            limit: Maximum number of records
            currency_code: Filter by currency
            security_label: Filter by security name
            isin: Filter by ISIN code
            date_from: Filter by start date (YYYY-MM-DD format)
            date_to: Filter by end date (YYYY-MM-DD format)
            market: Filter by market (e.g., NYSE, SGX)

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
                escaped_security = security_label.replace("'", "\\'")
                where_clauses.append(f"security_label = '{escaped_security}'")

            if isin:
                escaped_isin = isin.replace("'", "\\'")
                where_clauses.append(f"isin = '{escaped_isin}'")

            if date_from:
                where_clauses.append(f"price_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"price_date <= '{date_to}'")

            if market:
                escaped_market = market.replace("'", "\\'")
                where_clauses.append(f"market = '{escaped_market}'")

            where_clause = " AND ".join(where_clauses)

            # Build query
            query = f"""
            SELECT
                equity_price_id,
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                market,
                price_timestamp,
                group_name,
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
    def get_equity_price_by_id(equity_price_id: int) -> Optional[Dict[str, Any]]:
        """
        Get equity price by ID.

        Args:
            equity_price_id: Primary key

        Returns:
            Equity price record or None
        """
        try:
            query = f"""
            SELECT
                equity_price_id,
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                market,
                price_timestamp,
                group_name,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            WHERE equity_price_id = {equity_price_id}
              AND is_active = true
            LIMIT 1
            """

            logger.info(f"Retrieving equity price by ID: {equity_price_id}")
            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            if not results:
                logger.warning(f"No equity price found with ID: {equity_price_id}")
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
            logger.error(f"Error getting equity price by ID {equity_price_id}: {str(e)}")
            return None

    @staticmethod
    def insert_equity_price(equity_price_data: Dict[str, Any]) -> bool:
        """
        Insert new equity price record.

        Args:
            equity_price_data: Dictionary with equity price fields

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get next ID
            next_id = EquityPriceHiveRepository._get_next_id()

            # Escape string values
            currency_code = equity_price_data.get('currency_code', '').replace("'", "\\'")
            security_label = equity_price_data.get('security_label', '').replace("'", "\\'")
            isin = equity_price_data.get('isin', '').replace("'", "\\'") if equity_price_data.get('isin') else ''
            price_date = equity_price_data.get('price_date', '')
            main_closing_price = equity_price_data.get('main_closing_price', 0)
            market = equity_price_data.get('market', '').replace("'", "\\'") if equity_price_data.get('market') else ''
            price_timestamp = equity_price_data.get('price_timestamp', int(time.time() * 1000))
            group_name = equity_price_data.get('group_name', '').replace("'", "\\'") if equity_price_data.get('group_name') else ''
            created_by = equity_price_data.get('created_by', 'SYSTEM').replace("'", "\\'")
            created_at = int(time.time() * 1000)

            # Build INSERT query
            insert_query = f"""
            INSERT INTO {EquityPriceHiveRepository.TABLE_NAME} (
                equity_price_id,
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                market,
                price_timestamp,
                group_name,
                is_active,
                created_by,
                created_at
            ) VALUES (
                {next_id},
                '{currency_code}',
                '{security_label}',
                {f"'{isin}'" if isin else 'NULL'},
                '{price_date}',
                {main_closing_price},
                {f"'{market}'" if market else 'NULL'},
                {price_timestamp},
                {f"'{group_name}'" if group_name else 'NULL'},
                true,
                '{created_by}',
                {created_at}
            )
            """

            logger.info(f"Inserting equity price for {security_label} on {price_date}")
            success = impala_manager.execute_write(insert_query, database=EquityPriceHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted equity price ID: {next_id}")
            else:
                logger.error(f"Failed to insert equity price for {security_label}")

            return success

        except Exception as e:
            logger.error(f"Error inserting equity price: {str(e)}")
            return False

    @staticmethod
    def update_equity_price(equity_price_id: int, equity_price_data: Dict[str, Any]) -> bool:
        """
        Update existing equity price record.

        Args:
            equity_price_id: Primary key
            equity_price_data: Dictionary with fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build SET clause
            set_clauses = []

            if 'currency_code' in equity_price_data:
                currency_code = equity_price_data['currency_code'].replace("'", "\\'")
                set_clauses.append(f"currency_code = '{currency_code}'")

            if 'security_label' in equity_price_data:
                security_label = equity_price_data['security_label'].replace("'", "\\'")
                set_clauses.append(f"security_label = '{security_label}'")

            if 'isin' in equity_price_data:
                isin = equity_price_data['isin'].replace("'", "\\'") if equity_price_data['isin'] else ''
                if isin:
                    set_clauses.append(f"isin = '{isin}'")
                else:
                    set_clauses.append("isin = NULL")

            if 'price_date' in equity_price_data:
                set_clauses.append(f"price_date = '{equity_price_data['price_date']}'")

            if 'main_closing_price' in equity_price_data:
                set_clauses.append(f"main_closing_price = {equity_price_data['main_closing_price']}")

            if 'market' in equity_price_data:
                market = equity_price_data['market'].replace("'", "\\'") if equity_price_data['market'] else ''
                if market:
                    set_clauses.append(f"market = '{market}'")
                else:
                    set_clauses.append("market = NULL")

            if 'price_timestamp' in equity_price_data:
                set_clauses.append(f"price_timestamp = {equity_price_data['price_timestamp']}")

            if 'group_name' in equity_price_data:
                group_name = equity_price_data['group_name'].replace("'", "\\'") if equity_price_data['group_name'] else ''
                if group_name:
                    set_clauses.append(f"group_name = '{group_name}'")
                else:
                    set_clauses.append("group_name = NULL")

            # Add audit fields
            updated_by = equity_price_data.get('updated_by', 'SYSTEM').replace("'", "\\'")
            updated_at = int(time.time() * 1000)
            set_clauses.append(f"updated_by = '{updated_by}'")
            set_clauses.append(f"updated_at = {updated_at}")

            if not set_clauses:
                logger.warning("No fields to update")
                return False

            set_clause = ", ".join(set_clauses)

            # Build UPDATE query (using UPSERT for Kudu)
            # First, get existing record
            existing = EquityPriceHiveRepository.get_equity_price_by_id(equity_price_id)
            if not existing:
                logger.error(f"Cannot update: equity price ID {equity_price_id} not found")
                return False

            # Merge existing data with updates
            merged_data = {**existing, **equity_price_data}
            merged_data['updated_by'] = updated_by
            merged_data['updated_at'] = updated_at

            # Use UPSERT to update
            currency_code = merged_data.get('currency_code', '').replace("'", "\\'")
            security_label = merged_data.get('security_label', '').replace("'", "\\'")
            isin = merged_data.get('isin', '').replace("'", "\\'") if merged_data.get('isin') else ''
            price_date = merged_data.get('price_date', '')
            main_closing_price = merged_data.get('main_closing_price', 0)
            market = merged_data.get('market', '').replace("'", "\\'") if merged_data.get('market') else ''
            price_timestamp = merged_data.get('price_timestamp', int(time.time() * 1000))
            group_name = merged_data.get('group_name', '').replace("'", "\\'") if merged_data.get('group_name') else ''
            created_by = merged_data.get('created_by', 'SYSTEM').replace("'", "\\'")
            created_at = merged_data.get('created_at', int(time.time() * 1000))

            upsert_query = f"""
            UPSERT INTO {EquityPriceHiveRepository.TABLE_NAME} (
                equity_price_id,
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                market,
                price_timestamp,
                group_name,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            ) VALUES (
                {equity_price_id},
                '{currency_code}',
                '{security_label}',
                {f"'{isin}'" if isin else 'NULL'},
                '{price_date}',
                {main_closing_price},
                {f"'{market}'" if market else 'NULL'},
                {price_timestamp},
                {f"'{group_name}'" if group_name else 'NULL'},
                true,
                '{created_by}',
                {created_at},
                '{updated_by}',
                {updated_at}
            )
            """

            logger.info(f"Updating equity price ID: {equity_price_id}")
            success = impala_manager.execute_write(upsert_query, database=EquityPriceHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated equity price ID: {equity_price_id}")
            else:
                logger.error(f"Failed to update equity price ID: {equity_price_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating equity price {equity_price_id}: {str(e)}")
            return False

    @staticmethod
    def delete_equity_price(equity_price_id: int, deleted_by: str) -> bool:
        """
        Soft delete equity price (set is_active to false).

        Args:
            equity_price_id: Primary key
            deleted_by: User performing deletion

        Returns:
            True if successful, False otherwise
        """
        try:
            return EquityPriceHiveRepository.update_equity_price(
                equity_price_id,
                {
                    'is_active': False,
                    'updated_by': deleted_by
                }
            )
        except Exception as e:
            logger.error(f"Error deleting equity price {equity_price_id}: {str(e)}")
            return False

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
                equity_price_id,
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                market,
                price_timestamp,
                group_name,
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
                COUNT(DISTINCT market) as unique_markets,
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
                    'unique_markets': 0,
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
                'unique_markets': 0,
                'latest_date': 'N/A',
                'earliest_date': 'N/A'
            }

    @staticmethod
    def _get_next_id() -> int:
        """
        Get next available equity_price_id.

        Returns:
            Next ID
        """
        try:
            query = f"""
            SELECT COALESCE(MAX(equity_price_id), 0) + 1 as next_id
            FROM {EquityPriceHiveRepository.TABLE_NAME}
            """

            results = impala_manager.execute_query(query, database=EquityPriceHiveRepository.DATABASE)

            if results and results[0].get('next_id'):
                return results[0]['next_id']

            return 1

        except Exception as e:
            logger.error(f"Error getting next ID: {str(e)}")
            # Fallback to timestamp-based ID
            return int(time.time() * 1000) % 1000000


# Singleton instance
equity_price_hive_repository = EquityPriceHiveRepository()
