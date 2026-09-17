"""
Lookup Table Service

Business logic layer for lookup table management.
Handles validation, data transformation, and CSV export.
"""

import csv
import io
import logging
from typing import Dict, List, Any, Optional, Tuple

from lookup.repositories.lookup_kudu_repository import lookup_kudu_repository

logger = logging.getLogger(__name__)


class LookupService:
    """Service for lookup table management"""

    def __init__(self):
        self.repository = lookup_kudu_repository

    # =========================================================================
    # TABLE DISCOVERY
    # =========================================================================

    def get_all_lookup_tables(self, username: str = None) -> List[Dict[str, Any]]:
        """
        Get all lookup tables with metadata.

        Args:
            username: Logged-in user requesting the list. Not yet used to
                filter results -- threaded through so per-user table
                visibility can be added later without another signature
                change.

        Returns:
            List of table info dictionaries
        """
        return self.repository.discover_lookup_tables(username)

    def get_table_metadata(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific lookup table.

        Args:
            table_name: Name of the table

        Returns:
            Table metadata or None
        """
        return self.repository.get_table_info(table_name)

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_table_rows(
        self,
        table_name: str,
        search: str = None,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        page: int = 1,
        page_size: int = 25
    ) -> Dict[str, Any]:
        """
        Get paginated rows from a lookup table.

        Args:
            table_name: Name of the lookup table
            search: Search string
            filters: Column filters
            order_by: Sort column
            page: Page number (1-based)
            page_size: Rows per page

        Returns:
            Dictionary with rows, pagination info, and metadata
        """
        offset = (page - 1) * page_size

        rows, total_count = self.repository.get_all_rows(
            table_name=table_name,
            search=search,
            filters=filters,
            order_by=order_by,
            limit=page_size,
            offset=offset
        )

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        return {
            'rows': rows,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None
        }

    def get_row(self, table_name: str, pk_value: Any) -> Optional[Dict[str, Any]]:
        """
        Get a single row by primary key.

        Args:
            table_name: Name of the lookup table
            pk_value: Primary key value

        Returns:
            Row data or None
        """
        table_info = self.get_table_metadata(table_name)
        if not table_info or not table_info.get('pk_column'):
            return None

        return self.repository.get_row_by_pk(
            table_name=table_name,
            pk_column=table_info['pk_column'],
            pk_value=pk_value
        )

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def create_row(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new row in the lookup table.

        Args:
            table_name: Name of the lookup table
            data: Column values

        Returns:
            Result with success status and message
        """
        try:
            table_info = self.get_table_metadata(table_name)
            if not table_info:
                return {'success': False, 'error': 'Table not found'}

            pk_column = table_info.get('pk_column')
            columns = table_info.get('columns', [])

            # Validate required PK
            if pk_column and not data.get(pk_column):
                return {'success': False, 'error': f'Primary key ({pk_column}) is required'}

            # Check PK uniqueness
            if pk_column and data.get(pk_column):
                if self.repository.check_pk_exists(table_name, pk_column, data[pk_column]):
                    return {'success': False, 'error': f'Primary key value already exists: {data[pk_column]}'}

            # Convert data types
            processed_data = self._process_input_data(data, columns)

            # Insert row
            self.repository.insert_row(table_name, processed_data)

            return {
                'success': True,
                'message': 'Row created successfully',
                'pk_value': data.get(pk_column)
            }

        except Exception as e:
            logger.error(f"Error creating row in {table_name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_row(self, table_name: str, pk_value: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing row in the lookup table.

        Args:
            table_name: Name of the lookup table
            pk_value: Primary key value
            data: Column values to update

        Returns:
            Result with success status and message
        """
        try:
            table_info = self.get_table_metadata(table_name)
            if not table_info:
                return {'success': False, 'error': 'Table not found'}

            pk_column = table_info.get('pk_column')
            columns = table_info.get('columns', [])

            # Check row exists
            existing = self.repository.get_row_by_pk(table_name, pk_column, pk_value)
            if not existing:
                return {'success': False, 'error': 'Row not found'}

            # Convert data types
            processed_data = self._process_input_data(data, columns)

            # Update row
            self.repository.update_row(table_name, pk_column, pk_value, processed_data)

            return {
                'success': True,
                'message': 'Row updated successfully',
                'pk_value': pk_value
            }

        except Exception as e:
            logger.error(f"Error updating row in {table_name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_row(self, table_name: str, pk_value: Any) -> Dict[str, Any]:
        """
        Delete a row from the lookup table.

        Args:
            table_name: Name of the lookup table
            pk_value: Primary key value

        Returns:
            Result with success status and message
        """
        try:
            table_info = self.get_table_metadata(table_name)
            if not table_info:
                return {'success': False, 'error': 'Table not found'}

            pk_column = table_info.get('pk_column')

            # Check row exists
            existing = self.repository.get_row_by_pk(table_name, pk_column, pk_value)
            if not existing:
                return {'success': False, 'error': 'Row not found'}

            # Delete row
            self.repository.delete_row(table_name, pk_column, pk_value)

            return {
                'success': True,
                'message': 'Row deleted successfully',
                'pk_value': pk_value
            }

        except Exception as e:
            logger.error(f"Error deleting row from {table_name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_to_csv(self, table_name: str, search: str = None, filters: Dict[str, Any] = None) -> str:
        """
        Export lookup table to CSV.

        Args:
            table_name: Name of the lookup table
            search: Search string
            filters: Column filters

        Returns:
            CSV content as string
        """
        try:
            # Get all rows (no pagination for export)
            rows, _ = self.repository.get_all_rows(
                table_name=table_name,
                search=search,
                filters=filters,
                limit=10000,  # Max export limit
                offset=0
            )

            if not rows:
                return ''

            # Create CSV
            output = io.StringIO()
            columns = list(rows[0].keys())

            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

            return output.getvalue()

        except Exception as e:
            logger.error(f"Error exporting {table_name} to CSV: {str(e)}")
            return ''

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _process_input_data(self, data: Dict[str, Any], columns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process and validate input data based on column types.

        Args:
            data: Input data dictionary
            columns: Column metadata

        Returns:
            Processed data dictionary
        """
        processed = {}
        column_types = {c['name']: c['type'] for c in columns}

        for col_name, value in data.items():
            if col_name not in column_types:
                continue

            col_type = column_types[col_name]
            col_type_base = col_type.split('(')[0]  # handle DECIMAL(20,8), VARCHAR(255) etc.

            if value is None or value == '':
                processed[col_name] = None
            elif col_type_base in ('INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT'):
                # Accept "423" or "423.00" — parse via float then truncate to int
                try:
                    processed[col_name] = int(float(str(value).strip()))
                except (ValueError, TypeError):
                    # Not parseable as number — keep as string and let DB reject it
                    processed[col_name] = str(value)
            elif col_type_base in ('FLOAT', 'DOUBLE', 'DECIMAL', 'REAL'):
                try:
                    processed[col_name] = float(str(value).strip())
                except (ValueError, TypeError):
                    processed[col_name] = str(value)
            elif col_type_base in ('BOOLEAN', 'BOOL'):
                if isinstance(value, bool):
                    processed[col_name] = value
                elif isinstance(value, str):
                    processed[col_name] = value.lower() in ('true', '1', 'yes', 'on')
                else:
                    processed[col_name] = bool(value)
            else:
                # STRING / VARCHAR / DATE / TIMESTAMP / anything else — pass through as-is
                processed[col_name] = str(value)

        return processed

    def get_dropdown_options(self, table_name: str, value_column: str = None, label_column: str = None) -> List[Dict[str, str]]:
        """
        Get dropdown options from a lookup table.

        Args:
            table_name: Name of the lookup table
            value_column: Column to use as value (defaults to PK)
            label_column: Column to use as label (defaults to *_name column)

        Returns:
            List of {value, label} dictionaries
        """
        try:
            table_info = self.get_table_metadata(table_name)
            if not table_info:
                return []

            columns = table_info.get('columns', [])
            col_names = [c['name'] for c in columns]

            # Determine value column
            if not value_column:
                value_column = table_info.get('pk_column', col_names[0] if col_names else None)

            # Determine label column (look for *_name column)
            if not label_column:
                for col in col_names:
                    if col.endswith('_name') or col == 'label' or col == 'description':
                        label_column = col
                        break
                if not label_column:
                    label_column = value_column

            if not value_column:
                return []

            # Get active rows
            rows, _ = self.repository.get_all_rows(
                table_name=table_name,
                filters={'is_active': True} if 'is_active' in col_names else None,
                order_by='display_order' if 'display_order' in col_names else None,
                limit=500
            )

            return [
                {
                    'value': row.get(value_column, ''),
                    'label': row.get(label_column, row.get(value_column, ''))
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Error getting dropdown options from {table_name}: {str(e)}")
            return []


# Singleton instance
lookup_service = LookupService()
