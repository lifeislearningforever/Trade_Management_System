"""
Market Data Hive Repositories (ORC + ACID)

Data access layer for market data in Hive managed tables:
- Equity Price
- FX Rate
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


# =============================================================================
# EQUITY PRICE REPOSITORY
# =============================================================================

class EquityPriceHiveRepository(HiveBaseRepository):
    """Repository for equity price operations with Hive managed tables."""

    @property
    def table_name(self) -> str:
        return 'cis_equity_price'

    @property
    def primary_key(self) -> str:
        return 'price_id'

    @property
    def columns(self) -> List[str]:
        return [
            'price_id', 'security_id', 'security_code', 'price_date',
            'open_price', 'high_price', 'low_price', 'close_price',
            'volume', 'currency', 'source', 'created_at', 'created_by',
            'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_latest_price(self, security_id: str) -> Optional[Dict[str, Any]]:
        """Get latest price for a security."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE security_id = '{security_id}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by price_date descending in Python
            if results:
                results.sort(key=lambda x: x.get('price_date', ''), reverse=True)
                return results[0]
            return None

        except Exception as e:
            logger.error(f"Error fetching latest price: {str(e)}")
            return None

    def get_price_history(
        self,
        security_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 365
    ) -> List[Dict[str, Any]]:
        """Get price history for a security."""
        try:
            where_clauses = [
                f"security_id = '{security_id}'",
                "deleted_at IS NULL"
            ]

            if date_from:
                where_clauses.append(f"price_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"price_date <= '{date_to}'")

            where_clause = " AND ".join(where_clauses)

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by price_date descending
            if results:
                results.sort(key=lambda x: x.get('price_date', ''), reverse=True)

            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching price history: {str(e)}")
            return []

    def get_prices_for_date(self, price_date: str) -> List[Dict[str, Any]]:
        """Get all prices for a specific date."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE price_date = '{price_date}'
                  AND deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching prices for date: {str(e)}")
            return []

    def create_price(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new price record."""
        try:
            price_id = self._generate_id('PRC')
            now = datetime.now()

            record = {
                'price_id': price_id,
                'security_id': data.get('security_id'),
                'security_code': data.get('security_code'),
                'price_date': data.get('price_date'),
                'open_price': data.get('open_price'),
                'high_price': data.get('high_price'),
                'low_price': data.get('low_price'),
                'close_price': data.get('close_price'),
                'volume': data.get('volume'),
                'currency': data.get('currency'),
                'source': data.get('source', 'MANUAL'),
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created price {price_id} for security {data.get('security_id')}")
                return price_id
            return None

        except Exception as e:
            logger.error(f"Error creating price: {str(e)}")
            return None

    def bulk_create_prices(self, prices: List[Dict[str, Any]], created_by: str) -> int:
        """Bulk create price records."""
        try:
            now = datetime.now()
            records = []

            for price_data in prices:
                price_id = self._generate_id('PRC')
                records.append({
                    'price_id': price_id,
                    'security_id': price_data.get('security_id'),
                    'security_code': price_data.get('security_code'),
                    'price_date': price_data.get('price_date'),
                    'open_price': price_data.get('open_price'),
                    'high_price': price_data.get('high_price'),
                    'low_price': price_data.get('low_price'),
                    'close_price': price_data.get('close_price'),
                    'volume': price_data.get('volume'),
                    'currency': price_data.get('currency'),
                    'source': price_data.get('source', 'BULK'),
                    'created_at': now,
                    'created_by': created_by,
                    'updated_at': now,
                    'updated_by': created_by,
                    'deleted_at': None
                })

            if self.bulk_create(records):
                logger.info(f"Bulk created {len(records)} price records")
                return len(records)
            return 0

        except Exception as e:
            logger.error(f"Error bulk creating prices: {str(e)}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        """Get equity price statistics."""
        try:
            query = f"""
                SELECT security_id, currency, source
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            security_count = len(set(r.get('security_id') for r in results)) if results else 0
            source_counts = {}
            currency_counts = {}

            if results:
                for row in results:
                    source = row.get('source', 'Unknown')
                    source_counts[source] = source_counts.get(source, 0) + 1

                    currency = row.get('currency', 'Unknown')
                    currency_counts[currency] = currency_counts.get(currency, 0) + 1

            return {
                'total_prices': total,
                'securities_with_prices': security_count,
                'by_source': [
                    {'source': k, 'count': v}
                    for k, v in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
                ],
                'by_currency': [
                    {'currency': k, 'count': v}
                    for k, v in sorted(currency_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ]
            }

        except Exception as e:
            logger.error(f"Error getting price statistics: {str(e)}")
            return {'total_prices': 0, 'securities_with_prices': 0, 'by_source': [], 'by_currency': []}

    # =========================================================================
    # HISTORY METHODS
    # =========================================================================

    def save_to_history(self, existing_record: Dict[str, Any], changed_by: str, change_type: str = 'UPDATE') -> bool:
        """
        Save a snapshot of the existing record to the history table before update/delete.

        Args:
            existing_record: The current record dict (before the change)
            changed_by: Username making the change
            change_type: 'UPDATE' or 'DELETE'

        Returns:
            True if history record saved successfully
        """
        try:
            history_id = self._generate_id('PRCH')
            now = datetime.now()

            # Build column list for history table
            history_columns = [
                'history_id', 'price_id', 'security_id', 'security_code', 'price_date',
                'open_price', 'high_price', 'low_price', 'close_price',
                'volume', 'currency', 'source', 'change_type', 'changed_by',
                'changed_at', 'created_at'
            ]

            # Prepare values
            values = []
            values.append(f"'{history_id}'")
            values.append(f"'{existing_record.get('price_id', '')}'")
            values.append(f"'{existing_record.get('security_id', '')}'")
            values.append(f"'{existing_record.get('security_code', '')}'" if existing_record.get('security_code') else 'NULL')

            # Handle price_date (DATE type)
            price_date = existing_record.get('price_date')
            if price_date:
                if hasattr(price_date, 'strftime'):
                    values.append(f"'{price_date.strftime('%Y-%m-%d')}'")
                else:
                    values.append(f"'{price_date}'")
            else:
                values.append('NULL')

            # Numeric fields
            values.append(str(existing_record.get('open_price')) if existing_record.get('open_price') is not None else 'NULL')
            values.append(str(existing_record.get('high_price')) if existing_record.get('high_price') is not None else 'NULL')
            values.append(str(existing_record.get('low_price')) if existing_record.get('low_price') is not None else 'NULL')
            values.append(str(existing_record.get('close_price')) if existing_record.get('close_price') is not None else 'NULL')
            values.append(str(existing_record.get('volume')) if existing_record.get('volume') is not None else 'NULL')

            # String fields
            values.append(f"'{existing_record.get('currency', '')}'" if existing_record.get('currency') else 'NULL')
            values.append(f"'{existing_record.get('source', '')}'" if existing_record.get('source') else 'NULL')
            values.append(f"'{change_type}'")
            values.append(f"'{changed_by}'")

            # Timestamps
            values.append(f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'")
            values.append(f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'")

            query = f"""
                INSERT INTO {self.database}.cis_equity_price_history
                ({', '.join(history_columns)})
                VALUES ({', '.join(values)})
            """

            success = self.conn_manager.execute_write(query, database=self.database)

            if success:
                logger.info(f"Saved history for price {existing_record.get('price_id')} ({change_type} by {changed_by})")
            else:
                logger.error(f"Failed to save history for price {existing_record.get('price_id')}")

            return success

        except Exception as e:
            logger.error(f"Error saving to history: {str(e)}")
            return False

    def get_version_history(
        self,
        price_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get edit history for a specific equity price record.

        Args:
            price_id: Price ID
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            query = f"""
                SELECT
                    history_id, price_id, security_id, security_code, price_date,
                    open_price, high_price, low_price, close_price,
                    volume, currency, source, change_type, changed_by,
                    changed_at, created_at
                FROM {self.database}.cis_equity_price_history
                WHERE price_id = '{price_id}'
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by changed_at descending
            if results:
                results.sort(key=lambda x: x.get('changed_at', ''), reverse=True)

            logger.info(f"Retrieved {len(results) if results else 0} history records for price {price_id}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting version history: {str(e)}")
            return []

    def get_all_history_for_security(
        self,
        security_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all edit history for a security across all price records.

        Args:
            security_id: Security ID
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            query = f"""
                SELECT
                    history_id, price_id, security_id, security_code, price_date,
                    open_price, high_price, low_price, close_price,
                    volume, currency, source, change_type, changed_by,
                    changed_at, created_at
                FROM {self.database}.cis_equity_price_history
                WHERE security_id = '{security_id}'
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by changed_at descending
            if results:
                results.sort(key=lambda x: x.get('changed_at', ''), reverse=True)

            logger.info(f"Retrieved {len(results) if results else 0} history records for security {security_id}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting history for security: {str(e)}")
            return []

    def update_price_with_history(
        self,
        price_id: str,
        data: Dict[str, Any],
        updated_by: str
    ) -> bool:
        """
        Update a price record and save the old version to history.

        Args:
            price_id: Price ID to update
            data: Fields to update
            updated_by: Username performing the update

        Returns:
            True if successful
        """
        try:
            # Get existing record first
            existing = self.find_by_id(price_id)
            if not existing:
                logger.error(f"Cannot update: price {price_id} not found")
                return False

            # Save to history before update
            self.save_to_history(existing, updated_by, 'UPDATE')

            # Perform update
            data['updated_by'] = updated_by
            data['updated_at'] = datetime.now()

            success = self.update(price_id, data)

            if success:
                logger.info(f"Updated price {price_id} with history saved")
            return success

        except Exception as e:
            logger.error(f"Error updating price with history: {str(e)}")
            return False

    def delete_price_with_history(
        self,
        price_id: str,
        deleted_by: str
    ) -> bool:
        """
        Soft delete a price record and save to history.

        Args:
            price_id: Price ID to delete
            deleted_by: Username performing the deletion

        Returns:
            True if successful
        """
        try:
            # Get existing record first
            existing = self.find_by_id(price_id)
            if not existing:
                logger.error(f"Cannot delete: price {price_id} not found")
                return False

            # Save to history before delete
            self.save_to_history(existing, deleted_by, 'DELETE')

            # Perform soft delete
            success = self.soft_delete(price_id, deleted_by)

            if success:
                logger.info(f"Deleted price {price_id} with history saved")
            return success

        except Exception as e:
            logger.error(f"Error deleting price with history: {str(e)}")
            return False


# =============================================================================
# FX RATE REPOSITORY
# =============================================================================

class FXRateHiveRepository(HiveBaseRepository):
    """Repository for FX rate operations with Hive managed tables."""

    @property
    def table_name(self) -> str:
        return 'cis_fx_rate'

    @property
    def primary_key(self) -> str:
        return 'rate_id'

    @property
    def columns(self) -> List[str]:
        return [
            'rate_id', 'from_currency', 'to_currency', 'rate_date',
            'rate', 'bid_rate', 'ask_rate', 'source',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_latest_rate(self, from_currency: str, to_currency: str) -> Optional[Dict[str, Any]]:
        """Get latest FX rate for a currency pair."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE from_currency = '{from_currency}'
                  AND to_currency = '{to_currency}'
                  AND deleted_at IS NULL
                LIMIT 100
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by rate_date descending
            if results:
                results.sort(key=lambda x: x.get('rate_date', ''), reverse=True)
                return results[0]
            return None

        except Exception as e:
            logger.error(f"Error fetching latest FX rate: {str(e)}")
            return None

    def get_rate_for_date(
        self,
        from_currency: str,
        to_currency: str,
        rate_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get FX rate for a specific date."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE from_currency = '{from_currency}'
                  AND to_currency = '{to_currency}'
                  AND rate_date = '{rate_date}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error fetching FX rate for date: {str(e)}")
            return None

    def get_rate_history(
        self,
        from_currency: str,
        to_currency: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 365
    ) -> List[Dict[str, Any]]:
        """Get FX rate history for a currency pair."""
        try:
            where_clauses = [
                f"from_currency = '{from_currency}'",
                f"to_currency = '{to_currency}'",
                "deleted_at IS NULL"
            ]

            if date_from:
                where_clauses.append(f"rate_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"rate_date <= '{date_to}'")

            where_clause = " AND ".join(where_clauses)

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by rate_date descending
            if results:
                results.sort(key=lambda x: x.get('rate_date', ''), reverse=True)

            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching FX rate history: {str(e)}")
            return []

    def get_rates_for_date(self, rate_date: str) -> List[Dict[str, Any]]:
        """Get all FX rates for a specific date."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE rate_date = '{rate_date}'
                  AND deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching FX rates for date: {str(e)}")
            return []

    def get_all_currency_pairs(self) -> List[Dict[str, str]]:
        """Get all unique currency pairs."""
        try:
            query = f"""
                SELECT DISTINCT from_currency, to_currency
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching currency pairs: {str(e)}")
            return []

    def create_rate(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new FX rate record."""
        try:
            rate_id = self._generate_id('FX')
            now = datetime.now()

            record = {
                'rate_id': rate_id,
                'from_currency': data.get('from_currency'),
                'to_currency': data.get('to_currency'),
                'rate_date': data.get('rate_date'),
                'rate': data.get('rate'),
                'bid_rate': data.get('bid_rate'),
                'ask_rate': data.get('ask_rate'),
                'source': data.get('source', 'MANUAL'),
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created FX rate {rate_id} for {data.get('from_currency')}/{data.get('to_currency')}")
                return rate_id
            return None

        except Exception as e:
            logger.error(f"Error creating FX rate: {str(e)}")
            return None

    def bulk_create_rates(self, rates: List[Dict[str, Any]], created_by: str) -> int:
        """Bulk create FX rate records."""
        try:
            now = datetime.now()
            records = []

            for rate_data in rates:
                rate_id = self._generate_id('FX')
                records.append({
                    'rate_id': rate_id,
                    'from_currency': rate_data.get('from_currency'),
                    'to_currency': rate_data.get('to_currency'),
                    'rate_date': rate_data.get('rate_date'),
                    'rate': rate_data.get('rate'),
                    'bid_rate': rate_data.get('bid_rate'),
                    'ask_rate': rate_data.get('ask_rate'),
                    'source': rate_data.get('source', 'BULK'),
                    'created_at': now,
                    'created_by': created_by,
                    'updated_at': now,
                    'updated_by': created_by,
                    'deleted_at': None
                })

            if self.bulk_create(records):
                logger.info(f"Bulk created {len(records)} FX rate records")
                return len(records)
            return 0

        except Exception as e:
            logger.error(f"Error bulk creating FX rates: {str(e)}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        """Get FX rate statistics."""
        try:
            query = f"""
                SELECT from_currency, to_currency, source
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            pairs = set()
            source_counts = {}

            if results:
                for row in results:
                    pair = f"{row.get('from_currency')}/{row.get('to_currency')}"
                    pairs.add(pair)

                    source = row.get('source', 'Unknown')
                    source_counts[source] = source_counts.get(source, 0) + 1

            return {
                'total_rates': total,
                'currency_pairs': len(pairs),
                'by_source': [
                    {'source': k, 'count': v}
                    for k, v in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
                ]
            }

        except Exception as e:
            logger.error(f"Error getting FX rate statistics: {str(e)}")
            return {'total_rates': 0, 'currency_pairs': 0, 'by_source': []}

    # =========================================================================
    # HISTORY METHODS
    # =========================================================================

    def save_to_history(self, existing_record: Dict[str, Any], changed_by: str, change_type: str = 'UPDATE') -> bool:
        """
        Save a snapshot of the existing FX rate record to history table.

        Args:
            existing_record: The current record dict (before the change)
            changed_by: Username making the change
            change_type: 'UPDATE' or 'DELETE'

        Returns:
            True if history record saved successfully
        """
        try:
            history_id = self._generate_id('FXH')
            now = datetime.now()

            history_columns = [
                'history_id', 'rate_id', 'from_currency', 'to_currency', 'rate_date',
                'rate', 'bid_rate', 'ask_rate', 'source', 'change_type',
                'changed_by', 'changed_at', 'created_at'
            ]

            values = []
            values.append(f"'{history_id}'")
            values.append(f"'{existing_record.get('rate_id', '')}'")
            values.append(f"'{existing_record.get('from_currency', '')}'")
            values.append(f"'{existing_record.get('to_currency', '')}'")

            # Handle rate_date
            rate_date = existing_record.get('rate_date')
            if rate_date:
                if hasattr(rate_date, 'strftime'):
                    values.append(f"'{rate_date.strftime('%Y-%m-%d')}'")
                else:
                    values.append(f"'{rate_date}'")
            else:
                values.append('NULL')

            # Numeric fields
            values.append(str(existing_record.get('rate')) if existing_record.get('rate') is not None else 'NULL')
            values.append(str(existing_record.get('bid_rate')) if existing_record.get('bid_rate') is not None else 'NULL')
            values.append(str(existing_record.get('ask_rate')) if existing_record.get('ask_rate') is not None else 'NULL')

            # String fields
            values.append(f"'{existing_record.get('source', '')}'" if existing_record.get('source') else 'NULL')
            values.append(f"'{change_type}'")
            values.append(f"'{changed_by}'")

            # Timestamps
            values.append(f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'")
            values.append(f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'")

            query = f"""
                INSERT INTO {self.database}.cis_fx_rate_history
                ({', '.join(history_columns)})
                VALUES ({', '.join(values)})
            """

            success = self.conn_manager.execute_write(query, database=self.database)

            if success:
                logger.info(f"Saved FX rate history for {existing_record.get('rate_id')} ({change_type} by {changed_by})")
            else:
                logger.error(f"Failed to save FX rate history for {existing_record.get('rate_id')}")

            return success

        except Exception as e:
            logger.error(f"Error saving FX rate to history: {str(e)}")
            return False

    def get_version_history(self, rate_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get edit history for a specific FX rate record.

        Args:
            rate_id: Rate ID
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            query = f"""
                SELECT
                    history_id, rate_id, from_currency, to_currency, rate_date,
                    rate, bid_rate, ask_rate, source, change_type,
                    changed_by, changed_at, created_at
                FROM {self.database}.cis_fx_rate_history
                WHERE rate_id = '{rate_id}'
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            if results:
                results.sort(key=lambda x: x.get('changed_at', ''), reverse=True)

            logger.info(f"Retrieved {len(results) if results else 0} history records for rate {rate_id}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting FX rate version history: {str(e)}")
            return []

    def get_history_for_currency_pair(
        self,
        from_currency: str,
        to_currency: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all edit history for a currency pair.

        Args:
            from_currency: From currency code
            to_currency: To currency code
            limit: Maximum records to return

        Returns:
            List of historical versions sorted by changed_at DESC
        """
        try:
            query = f"""
                SELECT
                    history_id, rate_id, from_currency, to_currency, rate_date,
                    rate, bid_rate, ask_rate, source, change_type,
                    changed_by, changed_at, created_at
                FROM {self.database}.cis_fx_rate_history
                WHERE from_currency = '{from_currency}'
                  AND to_currency = '{to_currency}'
                LIMIT {limit}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            if results:
                results.sort(key=lambda x: x.get('changed_at', ''), reverse=True)

            logger.info(f"Retrieved {len(results) if results else 0} history records for {from_currency}/{to_currency}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error getting FX rate history for pair: {str(e)}")
            return []

    def update_rate_with_history(self, rate_id: str, data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update an FX rate record and save the old version to history.

        Args:
            rate_id: Rate ID to update
            data: Fields to update
            updated_by: Username performing the update

        Returns:
            True if successful
        """
        try:
            existing = self.find_by_id(rate_id)
            if not existing:
                logger.error(f"Cannot update: FX rate {rate_id} not found")
                return False

            self.save_to_history(existing, updated_by, 'UPDATE')

            data['updated_by'] = updated_by
            data['updated_at'] = datetime.now()

            success = self.update(rate_id, data)

            if success:
                logger.info(f"Updated FX rate {rate_id} with history saved")
            return success

        except Exception as e:
            logger.error(f"Error updating FX rate with history: {str(e)}")
            return False

    def delete_rate_with_history(self, rate_id: str, deleted_by: str) -> bool:
        """
        Soft delete an FX rate record and save to history.

        Args:
            rate_id: Rate ID to delete
            deleted_by: Username performing the deletion

        Returns:
            True if successful
        """
        try:
            existing = self.find_by_id(rate_id)
            if not existing:
                logger.error(f"Cannot delete: FX rate {rate_id} not found")
                return False

            self.save_to_history(existing, deleted_by, 'DELETE')

            success = self.soft_delete(rate_id, deleted_by)

            if success:
                logger.info(f"Deleted FX rate {rate_id} with history saved")
            return success

        except Exception as e:
            logger.error(f"Error deleting FX rate with history: {str(e)}")
            return False


# Singleton instances
equity_price_hive_repository = EquityPriceHiveRepository()
fx_rate_hive_repository = FXRateHiveRepository()
