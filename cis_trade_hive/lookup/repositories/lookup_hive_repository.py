"""
Lookup Table Hive Repository

Dynamically discovers and manages any tables containing 'lookup' in their name.
Hive Managed Tables implementation - no Django ORM.

Note: Due to Hive ACID limitations, some operations (ORDER BY, COUNT) are handled
in Python rather than SQL. See docs/HIVE_ACID_LIMITATIONS.md for details.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from core.repositories.hive_connection import hive_manager

logger = logging.getLogger(__name__)


class LookupHiveRepository:
    """Repository for dynamic lookup table management in Hive"""

    def __init__(self, database: str = 'gmp_cis'):
        self.database = database

    # =========================================================================
    # TABLE DISCOVERY
    # =========================================================================

    def discover_lookup_tables(self) -> List[Dict[str, Any]]:
        """
        Discover all tables containing 'lookup' in their name.

        Returns:
            List of table metadata with name, columns, row count
        """
        try:
            # Get all tables with 'lookup' in name
            query = f"SHOW TABLES IN {self.database} LIKE '*lookup*'"
            results = hive_manager.execute_query(query, database=self.database)

            tables = []
            if results:
                for row in results:
                    # Hive returns 'tab_name' column
                    table_name = row.get('tab_name', row.get('name', row.get('NAME', '')))
                    if table_name:
                        table_info = self.get_table_info(table_name)
                        if table_info:
                            tables.append(table_info)

            # Sort in Python (Hive ACID doesn't support ORDER BY well)
            tables.sort(key=lambda x: x.get('table_name', ''))
            logger.info(f"Discovered {len(tables)} lookup tables")
            return tables

        except Exception as e:
            logger.error(f"Error discovering lookup tables: {str(e)}")
            return []

    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific lookup table.

        Args:
            table_name: Name of the table

        Returns:
            Table metadata including columns and row count
        """
        try:
            # Get column info
            columns = self.get_table_columns(table_name)

            # Get row count (simple query without aggregation in WHERE)
            # Due to Hive ACID limitations, we fetch all and count in Python
            count_query = f"SELECT * FROM {self.database}.{table_name}"
            count_result = hive_manager.execute_query(count_query, database=self.database)
            row_count = len(count_result) if count_result else 0

            # Derive display name from table name
            display_name = self._format_table_name(table_name)

            # Identify primary key column
            pk_column = self._identify_pk_column(columns)

            return {
                'table_name': table_name,
                'display_name': display_name,
                'columns': columns,
                'row_count': row_count,
                'pk_column': pk_column,
                'database': self.database
            }

        except Exception as e:
            logger.error(f"Error getting table info for {table_name}: {str(e)}")
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get column metadata for a table.

        Args:
            table_name: Name of the table

        Returns:
            List of column metadata
        """
        try:
            query = f"DESCRIBE {self.database}.{table_name}"
            results = hive_manager.execute_query(query, database=self.database)

            columns = []
            if results:
                for row in results:
                    # Hive DESCRIBE returns 'col_name', 'data_type', 'comment'
                    col_name = row.get('col_name', row.get('name', row.get('NAME', '')))
                    col_type = row.get('data_type', row.get('type', row.get('TYPE', 'STRING')))

                    # Skip empty rows and partition info
                    if col_name and not col_name.startswith('#') and col_name.strip():
                        # Skip partition and table info rows
                        if col_name.lower() in ('', '# partition information', '# col_name'):
                            continue
                        columns.append({
                            'name': col_name.strip(),
                            'type': col_type.upper() if col_type else 'STRING',
                            'display_name': self._format_column_name(col_name.strip()),
                            'is_nullable': True
                        })

            return columns

        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {str(e)}")
            return []

    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================

    def get_all_rows(
        self,
        table_name: str,
        search: str = None,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all rows from a lookup table with optional filtering.

        Note: Due to Hive ACID limitations, ORDER BY is done in Python.

        Args:
            table_name: Name of the lookup table
            search: Search string to filter across all text columns
            filters: Column-specific filters
            order_by: Column to order by (handled in Python)
            limit: Max rows to return
            offset: Offset for pagination

        Returns:
            Tuple of (rows, total_count)
        """
        try:
            columns = self.get_table_columns(table_name)
            col_names = [c['name'] for c in columns]

            # Build WHERE clause
            where_clauses = []

            # Search across text columns
            if search:
                search_conditions = []
                for col in columns:
                    if col['type'] in ('STRING', 'VARCHAR', 'CHAR'):
                        search_conditions.append(
                            f"LOWER({col['name']}) LIKE LOWER('%{self._escape_sql(search)}%')"
                        )
                if search_conditions:
                    where_clauses.append(f"({' OR '.join(search_conditions)})")

            # Apply specific filters
            if filters:
                for col_name, value in filters.items():
                    if value is not None and col_name in col_names:
                        if isinstance(value, bool):
                            where_clauses.append(f"{col_name} = {str(value).lower()}")
                        elif isinstance(value, (int, float)):
                            where_clauses.append(f"{col_name} = {value}")
                        else:
                            where_clauses.append(f"{col_name} = '{self._escape_sql(str(value))}'")

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Get all rows (we'll sort and paginate in Python due to Hive ACID limitations)
            data_query = f"""
                SELECT {', '.join(col_names)}
                FROM {self.database}.{table_name}
                {where_sql}
            """
            all_rows = hive_manager.execute_query(data_query, database=self.database) or []

            total_count = len(all_rows)

            # Sort in Python (Hive ACID doesn't support ORDER BY well)
            if order_by and order_by in col_names:
                all_rows.sort(key=lambda x: str(x.get(order_by, '') or ''))
            elif not order_by:
                # Default: order by display_order if exists, then pk
                if 'display_order' in col_names:
                    all_rows.sort(key=lambda x: x.get('display_order', 0) or 0)
                elif col_names:
                    all_rows.sort(key=lambda x: str(x.get(col_names[0], '') or ''))

            # Apply pagination in Python
            paginated_rows = all_rows[offset:offset + limit]

            return paginated_rows, total_count

        except Exception as e:
            logger.error(f"Error getting rows from {table_name}: {str(e)}")
            return [], 0

    def get_row_by_pk(self, table_name: str, pk_column: str, pk_value: Any) -> Optional[Dict[str, Any]]:
        """
        Get a single row by primary key.

        Args:
            table_name: Name of the lookup table
            pk_column: Primary key column name
            pk_value: Primary key value

        Returns:
            Row data or None
        """
        try:
            query = f"""
                SELECT * FROM {self.database}.{table_name}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """
            results = hive_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error getting row from {table_name}: {str(e)}")
            return None

    def insert_row(self, table_name: str, data: Dict[str, Any]) -> bool:
        """
        Insert a new row into the lookup table.

        Args:
            table_name: Name of the lookup table
            data: Column name to value mapping

        Returns:
            True if successful
        """
        try:
            columns = list(data.keys())
            values = []

            for col in columns:
                val = data[col]
                if val is None:
                    values.append('NULL')
                elif isinstance(val, bool):
                    values.append(str(val).lower())
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                else:
                    values.append(f"'{self._escape_sql(str(val))}'")

            query = f"""
                INSERT INTO {self.database}.{table_name}
                ({', '.join(columns)})
                VALUES ({', '.join(values)})
            """

            hive_manager.execute_write(query, database=self.database)
            logger.info(f"Inserted row into {table_name}")
            return True

        except Exception as e:
            logger.error(f"Error inserting row into {table_name}: {str(e)}")
            raise

    def update_row(self, table_name: str, pk_column: str, pk_value: Any, data: Dict[str, Any]) -> bool:
        """
        Update an existing row in the lookup table.

        Note: Hive ACID uses DELETE + INSERT pattern for updates.

        Args:
            table_name: Name of the lookup table
            pk_column: Primary key column name
            pk_value: Primary key value
            data: Column name to value mapping (excluding PK)

        Returns:
            True if successful
        """
        try:
            # Get existing row to preserve PK and other columns
            existing = self.get_row_by_pk(table_name, pk_column, pk_value)
            if not existing:
                raise Exception(f"Row not found: {pk_column}={pk_value}")

            # Merge existing with new data
            merged_data = dict(existing)
            merged_data.update(data)

            # Delete existing row
            delete_query = f"""
                DELETE FROM {self.database}.{table_name}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """
            hive_manager.execute_write(delete_query, database=self.database)

            # Insert updated row
            self.insert_row(table_name, merged_data)

            logger.info(f"Updated row in {table_name} where {pk_column}={pk_value}")
            return True

        except Exception as e:
            logger.error(f"Error updating row in {table_name}: {str(e)}")
            raise

    def delete_row(self, table_name: str, pk_column: str, pk_value: Any) -> bool:
        """
        Delete a row from the lookup table.

        Args:
            table_name: Name of the lookup table
            pk_column: Primary key column name
            pk_value: Primary key value

        Returns:
            True if successful
        """
        try:
            query = f"""
                DELETE FROM {self.database}.{table_name}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """

            hive_manager.execute_write(query, database=self.database)
            logger.info(f"Deleted row from {table_name} where {pk_column}={pk_value}")
            return True

        except Exception as e:
            logger.error(f"Error deleting row from {table_name}: {str(e)}")
            raise

    def check_pk_exists(self, table_name: str, pk_column: str, pk_value: Any) -> bool:
        """
        Check if a primary key value already exists.

        Args:
            table_name: Name of the lookup table
            pk_column: Primary key column name
            pk_value: Primary key value to check

        Returns:
            True if exists
        """
        try:
            # Simple query without COUNT (Hive ACID limitation)
            query = f"""
                SELECT {pk_column} FROM {self.database}.{table_name}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """
            result = hive_manager.execute_query(query, database=self.database)
            return len(result) > 0 if result else False

        except Exception as e:
            logger.error(f"Error checking PK existence: {str(e)}")
            return False

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _format_table_name(self, table_name: str) -> str:
        """Convert table name to display name."""
        # Remove common prefixes
        name = table_name
        for prefix in ('cis_', 'gmp_', 'ref_'):
            if name.lower().startswith(prefix):
                name = name[len(prefix):]

        # Remove _lookup suffix
        if name.lower().endswith('_lookup'):
            name = name[:-7]

        # Convert to title case
        return name.replace('_', ' ').title()

    def _format_column_name(self, column_name: str) -> str:
        """Convert column name to display name."""
        return column_name.replace('_', ' ').title()

    def _identify_pk_column(self, columns: List[Dict[str, Any]]) -> Optional[str]:
        """Identify the primary key column from column list."""
        if not columns:
            return None

        # Common PK patterns
        pk_patterns = ['_code', '_id', '_key']

        for col in columns:
            col_name = col['name'].lower()
            for pattern in pk_patterns:
                if col_name.endswith(pattern):
                    return col['name']

        # Default to first column
        return columns[0]['name']

    def _escape_sql(self, value: str) -> str:
        """Escape SQL string to prevent injection."""
        if value is None:
            return ''
        return str(value).replace("'", "''").replace("\\", "\\\\")


# Singleton instance
lookup_hive_repository = LookupHiveRepository()

# Backward compatibility alias
lookup_kudu_repository = lookup_hive_repository
