"""
UDF (User-Defined Fields) Hive Repository (ORC + ACID)

Data access layer for UDF fields and values in Hive managed tables.
Allows dynamic field extension for any entity type.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from core.repositories.hive_connection import hive_manager
from core.repositories.hive_base_repository import HiveBaseRepository

logger = logging.getLogger(__name__)


# =============================================================================
# HIVE CONNECTION (Backward compatibility)
# =============================================================================

class HiveConnection:
    """Manages Hive database connections for UDF module."""

    DATABASE = 'gmp_cis'

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """Execute a Hive query and return results as list of dictionaries."""
        try:
            results = hive_manager.execute_query(query, database=HiveConnection.DATABASE)
            logger.info(f"Query returned {len(results) if results else 0} rows")
            return results if results else []
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"Query: {query}")
            raise


# =============================================================================
# UDF FIELD REPOSITORY
# =============================================================================

class UDFFieldHiveRepository(HiveBaseRepository):
    """Repository for UDF field definitions with Hive managed tables."""

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

    def get_fields_by_object_type(
        self,
        object_type: str,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all UDF fields for a specific object type."""
        try:
            where_clauses = [
                f"object_type = '{object_type}'",
                "deleted_at IS NULL"
            ]

            if not include_inactive:
                where_clauses.append("is_active = TRUE")

            where_clause = " AND ".join(where_clauses)

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by display_order
            if results:
                results.sort(key=lambda x: x.get('display_order', 999))

            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching UDF fields for {object_type}: {str(e)}")
            return []

    def get_all_fields(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all UDF fields."""
        try:
            where_clause = "deleted_at IS NULL"
            if not include_inactive:
                where_clause += " AND is_active = TRUE"

            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE {where_clause}
            """

            results = self.conn_manager.execute_query(query, database=self.database)

            # Sort by object_type then display_order
            if results:
                results.sort(key=lambda x: (x.get('object_type', ''), x.get('display_order', 999)))

            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching all UDF fields: {str(e)}")
            return []

    def get_field_by_id(self, field_id: str) -> Optional[Dict[str, Any]]:
        """Get UDF field by ID."""
        return self.find_by_id(field_id)

    def get_field_by_name(self, object_type: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Get UDF field by object type and field name."""
        try:
            field_name_escaped = field_name.replace("'", "''")
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE object_type = '{object_type}'
                  AND field_name = '{field_name_escaped}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error fetching UDF field by name: {str(e)}")
            return None

    def create_field(self, data: Dict[str, Any], created_by: str) -> Optional[str]:
        """Create a new UDF field definition."""
        try:
            field_id = self._generate_id('UDF')
            now = datetime.now()

            # Convert options list to JSON string
            options = data.get('options')
            if options and isinstance(options, list):
                options = json.dumps(options)

            record = {
                'field_id': field_id,
                'object_type': data.get('object_type'),
                'field_name': data.get('field_name'),
                'field_label': data.get('field_label'),
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

    def update_field(self, field_id: str, data: Dict[str, Any],
                    updated_by: str) -> bool:
        """Update UDF field definition."""
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

    def delete_field(self, field_id: str, deleted_by: str) -> bool:
        """Soft delete a UDF field."""
        return self.soft_delete(field_id, deleted_by)

    def get_statistics(self) -> Dict[str, Any]:
        """Get UDF field statistics."""
        try:
            query = f"""
                SELECT object_type, field_type, is_active
                FROM {self._get_full_table_name()}
                WHERE deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)

            total = len(results) if results else 0
            object_type_counts = {}
            field_type_counts = {}
            active_count = 0

            if results:
                for row in results:
                    obj_type = row.get('object_type', 'Unknown')
                    object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

                    f_type = row.get('field_type', 'Unknown')
                    field_type_counts[f_type] = field_type_counts.get(f_type, 0) + 1

                    if row.get('is_active'):
                        active_count += 1

            return {
                'total_fields': total,
                'active_fields': active_count,
                'by_object_type': [
                    {'object_type': k, 'count': v}
                    for k, v in sorted(object_type_counts.items())
                ],
                'by_field_type': [
                    {'field_type': k, 'count': v}
                    for k, v in sorted(field_type_counts.items(), key=lambda x: x[1], reverse=True)
                ]
            }

        except Exception as e:
            logger.error(f"Error getting UDF field statistics: {str(e)}")
            return {'total_fields': 0, 'active_fields': 0, 'by_object_type': [], 'by_field_type': []}


# =============================================================================
# UDF VALUE REPOSITORY
# =============================================================================

class UDFValueHiveRepository(HiveBaseRepository):
    """Repository for UDF field values with Hive managed tables."""

    @property
    def table_name(self) -> str:
        return 'cis_udf_value'

    @property
    def primary_key(self) -> str:
        return 'value_id'

    @property
    def columns(self) -> List[str]:
        return [
            'value_id', 'field_id', 'object_type', 'object_id', 'field_value',
            'created_at', 'created_by', 'updated_at', 'updated_by', 'deleted_at'
        ]

    def get_values_for_object(
        self,
        object_type: str,
        object_id: str
    ) -> List[Dict[str, Any]]:
        """Get all UDF values for a specific object."""
        try:
            query = f"""
                SELECT v.*, f.field_name, f.field_label, f.field_type
                FROM {self._get_full_table_name()} v
                JOIN {self.database}.cis_udf_field f ON v.field_id = f.field_id
                WHERE v.object_type = '{object_type}'
                  AND v.object_id = '{object_id}'
                  AND v.deleted_at IS NULL
                  AND f.deleted_at IS NULL
            """

            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching UDF values for {object_type}/{object_id}: {str(e)}")
            return []

    def get_value(
        self,
        field_id: str,
        object_type: str,
        object_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get specific UDF value."""
        try:
            query = f"""
                SELECT *
                FROM {self._get_full_table_name()}
                WHERE field_id = '{field_id}'
                  AND object_type = '{object_type}'
                  AND object_id = '{object_id}'
                  AND deleted_at IS NULL
                LIMIT 1
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error fetching UDF value: {str(e)}")
            return None

    def set_value(
        self,
        field_id: str,
        object_type: str,
        object_id: str,
        field_value: str,
        updated_by: str
    ) -> bool:
        """Set or update a UDF value."""
        try:
            now = datetime.now()

            # Check if value exists
            existing = self.get_value(field_id, object_type, object_id)

            if existing:
                # Update existing value
                return self.update(existing['value_id'], {
                    'field_value': field_value,
                    'updated_by': updated_by
                })
            else:
                # Create new value
                value_id = self._generate_id('UV')

                record = {
                    'value_id': value_id,
                    'field_id': field_id,
                    'object_type': object_type,
                    'object_id': object_id,
                    'field_value': field_value,
                    'created_at': now,
                    'created_by': updated_by,
                    'updated_at': now,
                    'updated_by': updated_by,
                    'deleted_at': None
                }

                return self.create(record)

        except Exception as e:
            logger.error(f"Error setting UDF value: {str(e)}")
            return False

    def set_values_bulk(
        self,
        object_type: str,
        object_id: str,
        values: Dict[str, str],
        updated_by: str
    ) -> bool:
        """Set multiple UDF values for an object at once."""
        try:
            success = True
            for field_id, field_value in values.items():
                if not self.set_value(field_id, object_type, object_id, field_value, updated_by):
                    success = False
                    logger.warning(f"Failed to set UDF value for field {field_id}")

            return success

        except Exception as e:
            logger.error(f"Error setting bulk UDF values: {str(e)}")
            return False

    def delete_values_for_object(
        self,
        object_type: str,
        object_id: str,
        deleted_by: str
    ) -> bool:
        """Soft delete all UDF values for an object."""
        try:
            now = datetime.now()

            query = f"""
                UPDATE {self._get_full_table_name()}
                SET deleted_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                    updated_by = '{deleted_by}'
                WHERE object_type = '{object_type}'
                  AND object_id = '{object_id}'
                  AND deleted_at IS NULL
            """

            return self.conn_manager.execute_write(query, database=self.database)

        except Exception as e:
            logger.error(f"Error deleting UDF values for object: {str(e)}")
            return False

    def get_objects_with_value(
        self,
        field_id: str,
        field_value: str
    ) -> List[Dict[str, Any]]:
        """Find all objects that have a specific UDF value."""
        try:
            field_value_escaped = field_value.replace("'", "''")
            query = f"""
                SELECT object_type, object_id
                FROM {self._get_full_table_name()}
                WHERE field_id = '{field_id}'
                  AND field_value = '{field_value_escaped}'
                  AND deleted_at IS NULL
            """
            results = self.conn_manager.execute_query(query, database=self.database)
            return results if results else []

        except Exception as e:
            logger.error(f"Error finding objects with UDF value: {str(e)}")
            return []


# =============================================================================
# REFERENCE DATA REPOSITORY (Backward compatibility)
# =============================================================================

class ReferenceDataRepository:
    """
    Repository for fetching reference data from Hive tables.
    Used to populate UDF dropdown options from Currency, Country, Counterparty tables.
    """

    @staticmethod
    def get_currencies() -> List[Dict[str, Any]]:
        """Fetch all currencies for dropdown options."""
        query = "SELECT * FROM gmp_cis.cis_currency WHERE deleted_at IS NULL AND is_active = TRUE"
        return HiveConnection.execute_query(query)

    @staticmethod
    def get_countries() -> List[Dict[str, Any]]:
        """Fetch all countries for dropdown options."""
        query = "SELECT * FROM gmp_cis.cis_country WHERE deleted_at IS NULL AND is_active = TRUE"
        return HiveConnection.execute_query(query)

    @staticmethod
    def get_counterparties() -> List[Dict[str, Any]]:
        """Fetch all counterparties for dropdown options."""
        query = "SELECT * FROM gmp_cis.cis_counterparty WHERE deleted_at IS NULL AND is_active = TRUE"
        return HiveConnection.execute_query(query)

    @staticmethod
    def get_account_groups() -> List[Dict[str, Any]]:
        """Fetch account groups for Portfolio UDF dropdown."""
        # Return predefined list
        return [
            {'value': 'TRADING', 'label': 'Trading'},
            {'value': 'INVESTMENT', 'label': 'Investment'},
            {'value': 'HEDGING', 'label': 'Hedging'},
            {'value': 'TREASURY', 'label': 'Treasury'},
            {'value': 'OPERATIONS', 'label': 'Operations'},
        ]

    @staticmethod
    def get_entity_groups() -> List[Dict[str, Any]]:
        """Fetch entity groups for Portfolio UDF dropdown."""
        return [
            {'value': 'CORPORATE', 'label': 'Corporate'},
            {'value': 'INSTITUTIONAL', 'label': 'Institutional'},
            {'value': 'RETAIL', 'label': 'Retail'},
            {'value': 'GOVERNMENT', 'label': 'Government'},
            {'value': 'FUND', 'label': 'Fund'},
        ]


# Singleton instances
udf_field_hive_repository = UDFFieldHiveRepository()
udf_value_hive_repository = UDFValueHiveRepository()
reference_data_repository = ReferenceDataRepository()

# Backward compatibility aliases
udf_definition_repository = udf_field_hive_repository
udf_option_repository = None  # Options are now stored in field.options JSON
udf_value_repository = udf_value_hive_repository

# Class alias for imports expecting the old class name
UDFDefinitionRepository = UDFFieldHiveRepository
