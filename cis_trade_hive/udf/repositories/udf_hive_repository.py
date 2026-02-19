"""
UDF (User-Defined Fields) Hive Repository

Single table repository for cis_udf_field with full CRUD operations:
- Create: Add new UDF field definition
- Read: Get field by ID, list all fields, filter by object_type
- Update: Modify field attributes
- Soft Delete: Set deleted_at timestamp
- Restore: Clear deleted_at timestamp

Field Types: TEXT, NUMBER, DATE, BOOLEAN, SELECT, MULTISELECT
Object Types: PORTFOLIO, TRADE, SECURITY, COUNTERPARTY
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


class UDFFieldHiveRepository(HiveBaseRepository):
    """
    Repository for UDF field definitions with Hive managed tables.

    Provides full CRUD operations including soft delete and restore.
    """

    # Field Types
    FIELD_TYPE_TEXT = 'TEXT'
    FIELD_TYPE_NUMBER = 'NUMBER'
    FIELD_TYPE_DATE = 'DATE'
    FIELD_TYPE_BOOLEAN = 'BOOLEAN'
    FIELD_TYPE_SELECT = 'SELECT'
    FIELD_TYPE_MULTISELECT = 'MULTISELECT'

    ALL_FIELD_TYPES = [
        FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_DATE,
        FIELD_TYPE_BOOLEAN, FIELD_TYPE_SELECT, FIELD_TYPE_MULTISELECT
    ]

    # Object Types that support UDF
    OBJECT_TYPE_PORTFOLIO = 'PORTFOLIO'
    OBJECT_TYPE_TRADE = 'TRADE'
    OBJECT_TYPE_SECURITY = 'SECURITY'
    OBJECT_TYPE_COUNTERPARTY = 'COUNTERPARTY'

    ALL_OBJECT_TYPES = [
        OBJECT_TYPE_PORTFOLIO, OBJECT_TYPE_TRADE,
        OBJECT_TYPE_SECURITY, OBJECT_TYPE_COUNTERPARTY
    ]

    @property
    def table_name(self) -> str:
        return 'cis_udf_field'

    @property
    def primary_key(self) -> str:
        return 'field_id'

    @property
    def columns(self) -> List[str]:
        return [
            'field_id', 'object_type', 'field_name', 'field_label', 'field_type',
            'is_required', 'default_value', 'options', 'display_order', 'is_active',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    # =========================================================================
    # CREATE
    # =========================================================================

    def create_field(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """
        Create a new UDF field definition.

        Args:
            data: Dictionary with field data
                - object_type: Entity type (PORTFOLIO, TRADE, etc.)
                - field_name: Technical field name
                - field_label: Display label
                - field_type: Field type (TEXT, NUMBER, etc.)
                - is_required: Whether field is required (default: False)
                - default_value: Default value (optional)
                - options: List of options for SELECT/MULTISELECT (optional)
                - display_order: Display order (default: 100)
            created_by: Username of creator

        Returns:
            field_id if successful, None otherwise
        """
        try:
            field_id = self._generate_id('UDF')
            now = datetime.now()

            # Convert options list to JSON string
            options = data.get('options')
            if options and isinstance(options, list):
                options = json.dumps(options)
            elif options and isinstance(options, str):
                # Already a string, validate it's valid JSON or convert
                try:
                    json.loads(options)
                except json.JSONDecodeError:
                    # Convert comma-separated to JSON
                    options = json.dumps([opt.strip() for opt in options.split(',') if opt.strip()])

            record = {
                'field_id': field_id,
                'object_type': data.get('object_type', '').upper(),
                'field_name': data.get('field_name', ''),
                'field_label': data.get('field_label', ''),
                'field_type': data.get('field_type', self.FIELD_TYPE_TEXT),
                'is_required': data.get('is_required', False),
                'default_value': data.get('default_value'),
                'options': options,
                'display_order': data.get('display_order', 100),
                'is_active': True,
                'created_at': now,
                'created_by': created_by,
                'updated_at': now,
                'updated_by': created_by,
                'deleted_at': None
            }

            if self.create(record):
                logger.info(f"Created UDF field {field_id} for {data.get('object_type')}")
                return field_id
            return None

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            return None

    # =========================================================================
    # READ
    # =========================================================================

    def get_field_by_id(self, field_id: str) -> Optional[Dict[str, Any]]:
        """Get UDF field by ID (including soft-deleted)."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE field_id = '{field_id}'
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            if results:
                return self._parse_options(results[0])
            return None
        except Exception as e:
            logger.error(f"Error fetching UDF field {field_id}: {str(e)}")
            return None

    def get_fields_by_object_type(
        self,
        object_type: str,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all UDF fields for a specific object type.

        Args:
            object_type: Entity type to filter by
            include_deleted: Whether to include soft-deleted fields

        Returns:
            List of field dictionaries sorted by display_order
        """
        try:
            where_clauses = [f"object_type = '{object_type.upper()}'"]

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            where_clause = " AND ".join(where_clauses)

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                ORDER BY display_order, field_name
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return [self._parse_options(r) for r in (results or [])]

        except Exception as e:
            logger.error(f"Error fetching UDF fields for {object_type}: {str(e)}")
            return []

    def get_all_fields(
        self,
        include_deleted: bool = False,
        object_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all UDF fields with optional filters.

        Args:
            include_deleted: Whether to include soft-deleted fields
            object_type: Optional filter by object type

        Returns:
            List of field dictionaries
        """
        try:
            where_clauses = []

            if not include_deleted:
                where_clauses.append("deleted_at IS NULL")

            if object_type:
                where_clauses.append(f"object_type = '{object_type.upper()}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                ORDER BY object_type, display_order, field_name
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return [self._parse_options(r) for r in (results or [])]

        except Exception as e:
            logger.error(f"Error fetching all UDF fields: {str(e)}")
            return []

    def get_deleted_fields(self, object_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get only soft-deleted fields."""
        try:
            where_clauses = ["deleted_at IS NOT NULL"]

            if object_type:
                where_clauses.append(f"object_type = '{object_type.upper()}'")

            where_clause = " AND ".join(where_clauses)

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
                ORDER BY deleted_at DESC
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return [self._parse_options(r) for r in (results or [])]

        except Exception as e:
            logger.error(f"Error fetching deleted UDF fields: {str(e)}")
            return []

    def get_field_by_name(self, object_type: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Get UDF field by object type and field name."""
        try:
            field_name_escaped = field_name.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE object_type = '{object_type.upper()}'
                  AND field_name = '{field_name_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            if results:
                return self._parse_options(results[0])
            return None

        except Exception as e:
            logger.error(f"Error fetching UDF field by name: {str(e)}")
            return None

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_field(self, field_id: str, data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update UDF field definition.

        Args:
            field_id: Field ID to update
            data: Dictionary with fields to update
            updated_by: Username performing update

        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {}
            updatable_fields = [
                'field_label', 'field_type', 'is_required',
                'default_value', 'options', 'display_order', 'is_active'
            ]

            for field in updatable_fields:
                if field in data:
                    value = data[field]
                    if field == 'options' and isinstance(value, list):
                        value = json.dumps(value)
                    update_data[field] = value

            update_data['updated_by'] = updated_by

            return self.update(field_id, update_data)

        except Exception as e:
            logger.error(f"Error updating UDF field: {str(e)}")
            return False

    # =========================================================================
    # SOFT DELETE
    # =========================================================================

    def delete_field(self, field_id: str, deleted_by: str) -> bool:
        """
        Soft delete a UDF field (sets deleted_at timestamp).

        Args:
            field_id: Field ID to delete
            deleted_by: Username performing delete

        Returns:
            True if successful, False otherwise
        """
        return self.soft_delete(field_id, deleted_by)

    # =========================================================================
    # RESTORE
    # =========================================================================

    def restore_field(self, field_id: str, restored_by: str) -> bool:
        """
        Restore a soft-deleted UDF field (clears deleted_at timestamp).

        Args:
            field_id: Field ID to restore
            restored_by: Username performing restore

        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')

            query = f"""
                UPDATE {self._get_full_table_name()}
                SET deleted_at = NULL,
                    is_active = TRUE,
                    updated_at = '{now_str}',
                    updated_by = '{restored_by}'
                WHERE field_id = '{field_id}'
            """

            success = self.conn_manager.execute_write(query, database=self.database)

            if success:
                logger.info(f"Restored UDF field {field_id} by {restored_by}")

            return success

        except Exception as e:
            logger.error(f"Error restoring UDF field {field_id}: {str(e)}")
            return False

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get UDF field statistics."""
        try:
            query = f"""
                SELECT object_type, field_type, deleted_at
                FROM {self._get_full_table_name()}
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            object_type_counts = {}
            field_type_counts = {}
            active_count = 0
            deleted_count = 0

            if results:
                for row in results:
                    obj_type = row.get('object_type') or 'Unknown'
                    object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

                    f_type = row.get('field_type') or 'Unknown'
                    field_type_counts[f_type] = field_type_counts.get(f_type, 0) + 1

                    # Check if deleted_at is None or empty
                    if row.get('deleted_at') is None:
                        active_count += 1
                    else:
                        deleted_count += 1

            # Sort safely, filtering out None keys
            sorted_obj_types = sorted(
                [(k, v) for k, v in object_type_counts.items() if k is not None],
                key=lambda x: x[0]
            )
            sorted_field_types = sorted(
                [(k, v) for k, v in field_type_counts.items() if k is not None],
                key=lambda x: x[1],
                reverse=True
            )

            return {
                'total_fields': total,
                'active_fields': active_count,
                'deleted_fields': deleted_count,
                'by_object_type': [
                    {'object_type': k, 'count': v}
                    for k, v in sorted_obj_types
                ],
                'by_field_type': [
                    {'field_type': k, 'count': v}
                    for k, v in sorted_field_types
                ]
            }

        except Exception as e:
            logger.error(f"Error getting UDF field statistics: {str(e)}")
            return {
                'total_fields': 0,
                'active_fields': 0,
                'deleted_fields': 0,
                'by_object_type': [],
                'by_field_type': []
            }

    def get_object_types(self) -> List[str]:
        """Get list of distinct object types in use."""
        try:
            query = f"""
                SELECT DISTINCT object_type
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
                ORDER BY object_type
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return [r['object_type'] for r in (results or [])]

        except Exception as e:
            logger.error(f"Error fetching object types: {str(e)}")
            return self.ALL_OBJECT_TYPES

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _parse_options(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Parse options JSON string to list if present."""
        if record and record.get('options'):
            try:
                record['options_list'] = json.loads(record['options'])
            except (json.JSONDecodeError, TypeError):
                record['options_list'] = []
        else:
            record['options_list'] = []
        return record


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

udf_field_hive_repository = UDFFieldHiveRepository()

# Backward compatibility aliases
udf_hive_repository = udf_field_hive_repository
udf_definition_repository = udf_field_hive_repository
UDFDefinitionRepository = UDFFieldHiveRepository
