"""
Lookup Table Kudu Repository

Dynamically discovers and manages any tables containing 'lut' in their name.
Excludes tables with '_rep' prefix or suffix (report tables).
Pure Kudu/Impala implementation - no Django ORM.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class LookupKuduRepository:
    """Repository for dynamic lookup table management in Kudu"""

    def __init__(self, database: str = 'gmp_cis'):
        self.database = database

    # =========================================================================
    # TABLE DISCOVERY
    # =========================================================================

    def discover_lookup_tables(self) -> List[Dict[str, Any]]:
        """
        Discover all tables containing 'lut' in their name.
        Excludes tables with '_rep' prefix or suffix (report tables).

        Returns:
            List of table metadata with name, columns, row count
        """
        try:
            # Get all tables with 'lut' in name (lookup tables)
            query = f"SHOW TABLES IN {self.database} LIKE '*lut*'"
            results = impala_manager.execute_query(query)

            tables = []
            if results:
                for row in results:
                    # Impala SHOW TABLES returns column 'tab_name' (not 'name')
                    table_name = row.get('tab_name', row.get('name', row.get('NAME', list(row.values())[0] if row else '')))
                    if table_name:
                        # Exclude tables with '_rep' prefix or suffix (report tables)
                        table_name_lower = table_name.lower()
                        if table_name_lower.startswith('rep_') or table_name_lower.endswith('_rep'):
                            logger.debug(f"Skipping report table: {table_name}")
                            continue

                        table_info = self.get_table_info(table_name)
                        if table_info:
                            tables.append(table_info)

            logger.info(f"Discovered {len(tables)} lookup tables (lut)")
            return sorted(tables, key=lambda x: x.get('table_name', ''))

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
            # Get column info (SELECT * probe + DESCRIBE fallback)
            columns = self.get_table_columns(table_name)

            # Get row count
            count_query = f"SELECT COUNT(*) as cnt FROM {self.database}.{table_name}"
            count_result = impala_manager.execute_query(count_query)
            row_count = count_result[0].get('cnt', 0) if count_result else 0

            # Derive display name from table name
            display_name = self._format_table_name(table_name)

            # Identify primary key column — also check extended DESCRIBE primary_key field
            pk_column = self._identify_pk_column_from_describe(table_name) or self._identify_pk_column(columns)

            return {
                'table_name': table_name,
                'display_name': display_name,
                'columns': columns,
                'row_count': row_count,
                'pk_column': pk_column,
                'database': self.database
            }

        except Exception as e:
            logger.error(f"Error getting table info for {table_name}: {str(e)}", exc_info=True)
            return None

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get column metadata for a table.
        Uses SELECT * LIMIT 0 to get column names from cursor.description — this is
        immune to DESCRIBE format differences across Impala versions and avoids the
        issue where Impala's extended DESCRIBE drops Kudu PK columns from the output.
        Falls back to DESCRIBE if the SELECT approach fails.
        """
        try:
            # Primary approach: derive columns from actual query result metadata
            # cursor.description always matches what SELECT * returns — no filtering needed
            probe_query = f"SELECT * FROM {self.database}.{table_name} LIMIT 1"
            results = impala_manager.execute_query(probe_query)

            if results:
                # Build columns from the actual row keys (cursor.description mapped by execute_query)
                first_row = results[0]
                columns = []
                for col_name in first_row.keys():
                    # Infer type from value
                    val = first_row[col_name]
                    if isinstance(val, bool):
                        col_type = 'BOOLEAN'
                    elif isinstance(val, int):
                        col_type = 'BIGINT'
                    elif isinstance(val, float):
                        col_type = 'DECIMAL'
                    else:
                        col_type = 'STRING'
                    columns.append({
                        'name': col_name,
                        'type': col_type,
                        'display_name': self._format_column_name(col_name),
                        'is_nullable': True
                    })
                logger.debug(f"get_table_columns {table_name}: {len(columns)} cols from SELECT *")
                return columns

            # Fallback: DESCRIBE (works even on empty tables)
            desc_query = f"DESCRIBE {self.database}.{table_name}"
            desc_results = impala_manager.execute_query(desc_query)

            columns = []
            if desc_results:
                for row in desc_results:
                    col_name = row.get('name') or row.get('col_name') or row.get('NAME') or ''
                    col_type = row.get('type') or row.get('data_type') or row.get('TYPE') or 'STRING'
                    # Skip blank separator rows and comment rows (#...) from extended DESCRIBE
                    if not col_name or col_name.startswith('#') or col_name.startswith(' '):
                        continue
                    columns.append({
                        'name': col_name,
                        'type': col_type.upper(),
                        'display_name': self._format_column_name(col_name),
                        'is_nullable': True
                    })

            logger.debug(f"get_table_columns {table_name}: {len(columns)} cols from DESCRIBE fallback")
            return columns

        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {str(e)}", exc_info=True)
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

        Args:
            table_name: Name of the lookup table
            search: Search string to filter across all text columns
            filters: Column-specific filters
            order_by: Column to order by
            limit: Max rows to return
            offset: Offset for pagination

        Returns:
            Tuple of (rows, total_count)
        """
        try:
            columns = self.get_table_columns(table_name)
            col_names = [c['name'] for c in columns]
            # Always SELECT * so we get all columns including PK even if DESCRIBE
            # omits it (Impala extended DESCRIBE can drop Kudu PK from regular section)
            select_cols = '*'

            # Build WHERE clause
            where_clauses = []

            # Search across text columns
            if search:
                search_conditions = []
                for col in columns:
                    col_type_base = col['type'].split('(')[0]
                    if col_type_base in ('STRING', 'VARCHAR', 'CHAR'):
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

            # Determine order by
            if not order_by:
                # Default: order by display_order if exists, then pk
                if 'display_order' in col_names:
                    order_by = 'display_order'
                elif col_names:
                    order_by = col_names[0]

            order_sql = f"ORDER BY {order_by}" if order_by else ""

            # Get total count
            count_query = f"""
                SELECT COUNT(*) as cnt
                FROM {self.database}.{table_name}
                {where_sql}
            """
            count_result = impala_manager.execute_query(count_query)
            total_count = count_result[0].get('cnt', 0) if count_result else 0

            # Get paginated rows
            data_query = f"""
                SELECT {select_cols}
                FROM {self.database}.{table_name}
                {where_sql}
                {order_sql}
                LIMIT {limit} OFFSET {offset}
            """
            logger.warning(f"get_all_rows query for {table_name}: SELECT {select_cols} ... total_count={total_count}")
            rows = impala_manager.execute_query(data_query) or []
            logger.warning(f"get_all_rows {table_name}: got {len(rows)} rows")

            return rows, total_count

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
            results = impala_manager.execute_query(query)
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
                UPSERT INTO {self.database}.{table_name}
                ({', '.join(columns)})
                VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(query, database=self.database)
            if not success:
                raise RuntimeError(f"execute_write returned False — row was not inserted into {table_name}")
            logger.info(f"Inserted row into {table_name}")
            return True

        except Exception as e:
            logger.error(f"Error inserting row into {table_name}: {str(e)}")
            raise

    def update_row(self, table_name: str, pk_column: str, pk_value: Any, data: Dict[str, Any]) -> bool:
        """
        Update an existing row in the lookup table.

        Args:
            table_name: Name of the lookup table
            pk_column: Primary key column name
            pk_value: Primary key value
            data: Column name to value mapping (excluding PK)

        Returns:
            True if successful
        """
        try:
            set_clauses = []

            for col, val in data.items():
                if col == pk_column:
                    continue  # Skip PK

                if val is None:
                    set_clauses.append(f"{col} = NULL")
                elif isinstance(val, bool):
                    set_clauses.append(f"{col} = {str(val).lower()}")
                elif isinstance(val, (int, float)):
                    set_clauses.append(f"{col} = {val}")
                else:
                    set_clauses.append(f"{col} = '{self._escape_sql(str(val))}'")

            if not set_clauses:
                return True  # Nothing to update

            query = f"""
                UPDATE {self.database}.{table_name}
                SET {', '.join(set_clauses)}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """

            success = impala_manager.execute_write(query, database=self.database)
            if not success:
                raise RuntimeError(f"execute_write returned False — row was not updated in {table_name}")
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

            success = impala_manager.execute_write(query, database=self.database)
            if not success:
                raise RuntimeError(f"execute_write returned False — row was not deleted from {table_name}")
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
            query = f"""
                SELECT COUNT(*) as cnt FROM {self.database}.{table_name}
                WHERE {pk_column} = '{self._escape_sql(str(pk_value))}'
            """
            result = impala_manager.execute_query(query)
            return result[0].get('cnt', 0) > 0 if result else False

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
        for prefix in ('cis_', 'gmp_', 'ref_', 'lut_'):
            if name.lower().startswith(prefix):
                name = name[len(prefix):]

        # Remove _lut or _lookup suffix
        if name.lower().endswith('_lut'):
            name = name[:-4]
        elif name.lower().endswith('_lookup'):
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

    def _identify_pk_column_from_describe(self, table_name: str) -> Optional[str]:
        """
        Use Impala extended DESCRIBE to find the column with primary_key = 'true'.
        Impala's extended DESCRIBE returns a 'primary_key' column — use it directly.
        """
        try:
            query = f"DESCRIBE {self.database}.{table_name}"
            results = impala_manager.execute_query(query)
            for row in (results or []):
                col_name = row.get('name') or row.get('col_name') or ''
                is_pk = str(row.get('primary_key', '')).lower() == 'true'
                if col_name and not col_name.startswith('#') and is_pk:
                    return col_name
        except Exception:
            pass
        return None

    def _escape_sql(self, value: str) -> str:
        """Escape SQL string to prevent injection."""
        if value is None:
            return ''
        return str(value).replace("'", "''").replace("\\", "\\\\")


# Singleton instance
lookup_kudu_repository = LookupKuduRepository()
