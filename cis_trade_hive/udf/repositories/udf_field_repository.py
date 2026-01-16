"""
UDF Field Repository - Composite Primary Key Schema

Schema with Composite Primary Key:
- object_type: Entity this UDF belongs to (TRADE, PORTFOLIO, SECURITY, etc.)
- field_name: Field definition name (e.g., 'Fund Type', 'Selling Rule') - ADMIN CREATES
- field_value: Dropdown option value - PRIMARY KEY COMPONENT
  - Empty ('') for field definition records (admin-created)
  - Non-empty for dropdown option records (admin/system adds values)
- is_active: Soft delete flag
- Audit fields: created_by, created_at, updated_by, updated_at

Primary Key: (object_type, field_name, field_value)

Cascading Logic:
1. Object Types: Get distinct object_type where field_value = ''
2. Field Definitions: WHERE object_type = '<selected>' AND field_value = ''
3. Dropdown Values: WHERE object_type = '<selected>' AND field_name = '<selected>' AND field_value != ''
"""

from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import logging
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


# ============================================================================
# INTERFACE
# ============================================================================

class UDFFieldRepositoryInterface(ABC):
    """Abstract interface for UDF field repository."""

    @abstractmethod
    def get_object_types(self) -> List[str]:
        """Get all entity types (where field_value is empty)."""
        pass

    @abstractmethod
    def get_fields_by_entity(self, object_type: str) -> List[Dict[str, Any]]:
        """Get all fields for a specific entity type."""
        pass

    @abstractmethod
    def get_field_values(self, object_type: str, field_name: str) -> List[Dict[str, Any]]:
        """Get all dropdown values for a specific field."""
        pass

    @abstractmethod
    def get_all(self, object_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get all UDF fields with optional filters."""
        pass

    @abstractmethod
    def get_by_key(self, object_type: str, field_name: str, field_value: str) -> Optional[Dict[str, Any]]:
        """Get UDF field by composite key."""
        pass

    @abstractmethod
    def create(self, field_data: Dict[str, Any]) -> bool:
        """Create a new UDF field."""
        pass

    @abstractmethod
    def update(self, object_type: str, field_name: str, field_value: str, field_data: Dict[str, Any]) -> bool:
        """Update existing UDF field."""
        pass

    @abstractmethod
    def soft_delete(self, object_type: str, field_name: str, field_value: str, updated_by: str) -> bool:
        """Soft delete UDF field by setting is_active = false."""
        pass

    @abstractmethod
    def restore(self, object_type: str, field_name: str, field_value: str, updated_by: str) -> bool:
        """Restore soft-deleted UDF field by setting is_active = true."""
        pass


# ============================================================================
# IMPLEMENTATION
# ============================================================================

class UDFFieldRepository(UDFFieldRepositoryInterface):
    """Repository for UDF field data access operations with composite primary key."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_udf_field'

    def _escape_string(self, value: str) -> str:
        """Escape single quotes in string for SQL."""
        if value is None:
            return ''
        return value.replace("'", "\\'")

    def get_object_types(self) -> List[str]:
        """
        Get all available entity types (where field_value is empty).

        Returns:
            List of entity type strings (e.g., ['PORTFOLIO', 'TRADE', 'SECURITY'])
        """
        try:
            query = f"""
            SELECT DISTINCT object_type
            FROM {self.TABLE_NAME}
            WHERE (field_value IS NULL OR field_value = '')
              AND is_active = true
            ORDER BY object_type
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            object_types = [row['object_type'] for row in results] if results else []

            logger.info(f"Retrieved {len(object_types)} object types")
            return object_types

        except Exception as e:
            logger.error(f"Error retrieving object types: {str(e)}")
            return []

    def get_fields_by_entity(self, object_type: str) -> List[Dict[str, Any]]:
        """
        Get all FIELD DEFINITIONS for a specific entity type.
        Field definitions are records where field_value IS empty (admin-created).

        Args:
            object_type: Entity type to filter by (e.g., 'TRADE', 'PORTFOLIO')

        Returns:
            List of field definition dictionaries with field_name
        """
        try:
            escaped_entity = self._escape_string(object_type)

            query = f"""
            SELECT DISTINCT field_name
            FROM {self.TABLE_NAME}
            WHERE object_type = '{escaped_entity}'
              AND (field_value IS NULL OR field_value = '')
              AND is_active = true
            ORDER BY field_name
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            fields = [{'field_name': row['field_name']} for row in (results or [])]

            logger.info(f"Retrieved {len(fields)} field definitions for: {object_type}")
            return fields

        except Exception as e:
            logger.error(f"Error retrieving field definitions for {object_type}: {str(e)}")
            return []

    def get_field_values(self, object_type: str, field_name: str) -> List[Dict[str, Any]]:
        """
        Get all VALUES (dropdown options) for a specific field.
        Values are records where field_value IS NOT empty.

        Args:
            object_type: Entity type (e.g., 'TRADE')
            field_name: Field definition name (e.g., 'Fund Type')

        Returns:
            List of value dictionaries with field_value
        """
        try:
            escaped_entity = self._escape_string(object_type)
            escaped_field = self._escape_string(field_name)

            query = f"""
            SELECT
                object_type,
                field_name,
                field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            WHERE object_type = '{escaped_entity}'
              AND field_name = '{escaped_field}'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND is_active = true
            ORDER BY field_value
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved {len(results) if results else 0} values for {object_type}.{field_name}")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving values for {object_type}.{field_name}: {str(e)}")
            return []

    def get_all(self, object_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get all UDF fields with optional filters.

        Args:
            object_type: Filter by entity type
            is_active: Filter by active status

        Returns:
            List of UDF field dictionaries
        """
        try:
            query = f"""
            SELECT
                object_type,
                field_name,
                field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            """

            conditions = []

            # Exclude field definition records (where field_value is empty)
            conditions.append("(field_value IS NOT NULL AND field_value != '')")

            if object_type:
                escaped_entity = self._escape_string(object_type)
                conditions.append(f"object_type = '{escaped_entity}'")

            if is_active is not None:
                conditions.append(f"is_active = {'true' if is_active else 'false'}")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY object_type, field_name, field_value"

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved {len(results) if results else 0} UDF fields")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving UDF fields: {str(e)}")
            raise

    def get_by_key(self, object_type: str, field_name: str, field_value: str) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by composite primary key.

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: Field value

        Returns:
            UDF field dictionary or None
        """
        try:
            escaped_entity = self._escape_string(object_type)
            escaped_field = self._escape_string(field_name)
            escaped_value = self._escape_string(field_value or '')

            query = f"""
            SELECT
                object_type,
                field_name,
                field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            WHERE object_type = '{escaped_entity}'
              AND field_name = '{escaped_field}'
              AND field_value = '{escaped_value}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error retrieving UDF field {object_type}.{field_name}.{field_value}: {str(e)}")
            raise

    # Legacy method for backward compatibility
    def get_by_id(self, udf_id: int) -> Optional[Dict[str, Any]]:
        """
        DEPRECATED: Use get_by_key() instead.
        This method is kept for backward compatibility.
        """
        logger.warning("get_by_id() is deprecated. Use get_by_key() instead.")
        return None

    def create(self, field_data: Dict[str, Any]) -> bool:
        """
        Create a new UDF field.

        Args:
            field_data: Dictionary with UDF field data
                Required keys: object_type, field_name, field_value, created_by

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate required fields
            required = ['object_type', 'field_name', 'created_by']
            for field in required:
                if field not in field_data:
                    raise ValueError(f"Missing required field: {field}")

            # Ensure field_value exists (empty string for definitions)
            field_data.setdefault('field_value', '')

            # Set timestamps
            timestamp = int(datetime.now().timestamp() * 1000)
            field_data['created_at'] = field_data.get('created_at', timestamp)
            field_data['updated_at'] = timestamp
            field_data['updated_by'] = field_data.get('updated_by', field_data['created_by'])

            # Set defaults
            field_data.setdefault('is_active', True)

            # Build UPSERT query
            columns = ['object_type', 'field_name', 'field_value', 'is_active',
                       'created_by', 'created_at', 'updated_by', 'updated_at']
            values = []

            for col in columns:
                value = field_data.get(col)
                if isinstance(value, str):
                    escaped_value = self._escape_string(value)
                    values.append(f"'{escaped_value}'")
                elif isinstance(value, bool):
                    values.append('true' if value else 'false')
                elif isinstance(value, (int, float)):
                    values.append(str(value))
                else:
                    values.append("''")  # Default to empty string

            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully created UDF field: {field_data.get('object_type')}.{field_data.get('field_name')}.{field_data.get('field_value', '')}")

            return success

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            logger.error(f"Field data: {field_data}")
            return False

    def update(self, object_type: str, field_name: str, field_value: str, field_data: Dict[str, Any]) -> bool:
        """
        Update existing UDF field by composite key.

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: Field value
            field_data: Dictionary with updated field data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Set composite key values
            field_data['object_type'] = object_type
            field_data['field_name'] = field_name
            field_data['field_value'] = field_value or ''

            # Update timestamp
            timestamp = int(datetime.now().timestamp() * 1000)
            field_data['updated_at'] = timestamp

            # Use create method (UPSERT will update if exists)
            return self.create(field_data)

        except Exception as e:
            logger.error(f"Error updating UDF field {object_type}.{field_name}.{field_value}: {str(e)}")
            return False

    def soft_delete(self, object_type: str, field_name: str, field_value: str, updated_by: str) -> bool:
        """
        Soft delete UDF field by setting is_active = false.

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: Field value
            updated_by: Username performing the delete

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            # Fetch existing record first
            existing = self.get_by_key(object_type, field_name, field_value)
            if not existing:
                logger.error(f"UDF field not found for soft delete: {object_type}.{field_name}.{field_value}")
                return False

            # Update with is_active = false
            update_data = {
                'object_type': object_type,
                'field_name': field_name,
                'field_value': field_value or '',
                'is_active': False,
                'created_by': existing['created_by'],
                'created_at': existing['created_at'],
                'updated_by': updated_by,
                'updated_at': timestamp,
            }

            success = self.create(update_data)

            if success:
                logger.info(f"Successfully soft deleted UDF field: {object_type}.{field_name}.{field_value}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting UDF field: {str(e)}")
            return False

    def restore(self, object_type: str, field_name: str, field_value: str, updated_by: str) -> bool:
        """
        Restore soft-deleted UDF field by setting is_active = true.

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: Field value
            updated_by: Username performing the restore

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            # Fetch existing record first
            existing = self.get_by_key(object_type, field_name, field_value)
            if not existing:
                logger.error(f"UDF field not found for restore: {object_type}.{field_name}.{field_value}")
                return False

            # Update with is_active = true
            update_data = {
                'object_type': object_type,
                'field_name': field_name,
                'field_value': field_value or '',
                'is_active': True,
                'created_by': existing['created_by'],
                'created_at': existing['created_at'],
                'updated_by': updated_by,
                'updated_at': timestamp,
            }

            success = self.create(update_data)

            if success:
                logger.info(f"Successfully restored UDF field: {object_type}.{field_name}.{field_value}")

            return success

        except Exception as e:
            logger.error(f"Error restoring UDF field: {str(e)}")
            return False

    def get_stats_by_entity(self) -> List[Dict[str, Any]]:
        """
        Get statistics grouped by entity type.

        Returns:
            List of dictionaries with object_type, total_fields, active_fields, inactive_fields
        """
        try:
            query = f"""
            SELECT
                object_type,
                COUNT(*) as total_fields,
                SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END) as active_fields,
                SUM(CASE WHEN is_active = false THEN 1 ELSE 0 END) as inactive_fields
            FROM {self.TABLE_NAME}
            WHERE field_value IS NOT NULL AND field_value != ''
            GROUP BY object_type
            ORDER BY object_type
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved stats for {len(results) if results else 0} entity types")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving UDF stats: {str(e)}")
            raise

    def add_field_definition(self, object_type: str, field_name: str, created_by: str) -> bool:
        """
        Add a new field definition (empty field_value).

        Args:
            object_type: Entity type
            field_name: Field name
            created_by: Username

        Returns:
            True if successful
        """
        return self.create({
            'object_type': object_type,
            'field_name': field_name,
            'field_value': '',
            'created_by': created_by
        })

    def add_field_value(self, object_type: str, field_name: str, field_value: str, created_by: str) -> bool:
        """
        Add a new dropdown value for a field.

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: The dropdown value to add
            created_by: Username

        Returns:
            True if successful
        """
        if not field_value:
            raise ValueError("field_value cannot be empty for dropdown values")

        return self.create({
            'object_type': object_type,
            'field_name': field_name,
            'field_value': field_value,
            'created_by': created_by
        })


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

udf_field_repository = UDFFieldRepository()
