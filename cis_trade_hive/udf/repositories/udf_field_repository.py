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

    def get_next_id(self) -> int:
        """
        Get next UDF field ID using timestamp-based generation.

        Returns:
            Next unique field_id (timestamp in milliseconds)
        """
        return int(datetime.now().timestamp() * 1000)

    def get_object_types(self) -> List[str]:
        """
        Get all available entity types (where label is empty - entity type records).

        Returns:
            List of entity type strings (e.g., ['PORTFOLIO', 'TRADE', 'SECURITY'])
        """
        try:
            query = f"""
            SELECT DISTINCT object_type
            FROM {self.TABLE_NAME}
            WHERE (label IS NULL OR label = '')
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
        Field definitions are records where label IS empty (admin-created).

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
              AND (label IS NULL OR label = '')
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
        Values are records where label IS NOT empty.

        Args:
            object_type: Entity type (e.g., 'TRADE')
            field_name: Field definition name (e.g., 'Fund Type')

        Returns:
            List of value dictionaries with field_value (mapped from label)
        """
        try:
            escaped_entity = self._escape_string(object_type)
            escaped_field = self._escape_string(field_name)

            query = f"""
            SELECT
                field_id as udf_id,
                object_type,
                field_name,
                label as field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            WHERE object_type = '{escaped_entity}'
              AND field_name = '{escaped_field}'
              AND label IS NOT NULL
              AND label != ''
              AND is_active = true
            ORDER BY label
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
                field_id as udf_id,
                object_type,
                field_name,
                label as field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            """

            conditions = []

            # Exclude field definition records (where label is empty)
            conditions.append("(label IS NOT NULL AND label != '')")

            if object_type:
                escaped_entity = self._escape_string(object_type)
                conditions.append(f"object_type = '{escaped_entity}'")

            if is_active is not None:
                conditions.append(f"is_active = {'true' if is_active else 'false'}")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY object_type, field_name, label"

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved {len(results) if results else 0} UDF fields")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving UDF fields: {str(e)}")
            raise

    def get_by_key(self, object_type: str, field_name: str, field_value: str) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by composite key (object_type, field_name, label).

        Args:
            object_type: Entity type
            field_name: Field name
            field_value: Field value (maps to label column)

        Returns:
            UDF field dictionary or None
        """
        try:
            escaped_entity = self._escape_string(object_type)
            escaped_field = self._escape_string(field_name)
            escaped_value = self._escape_string(field_value or '')

            query = f"""
            SELECT
                field_id as udf_id,
                object_type,
                field_name,
                label as field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            WHERE object_type = '{escaped_entity}'
              AND field_name = '{escaped_field}'
              AND label = '{escaped_value}'
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error retrieving UDF field {object_type}.{field_name}.{field_value}: {str(e)}")
            raise

    def get_by_id(self, udf_id: int) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by field_id (primary key).

        Args:
            udf_id: UDF field ID (field_id in database)

        Returns:
            UDF field dictionary or None
        """
        try:
            query = f"""
            SELECT
                field_id as udf_id,
                object_type,
                field_name,
                label as field_value,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {self.TABLE_NAME}
            WHERE field_id = {udf_id}
            LIMIT 1
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error retrieving UDF field by ID {udf_id}: {str(e)}")
            return None

    def create(self, field_data: Dict[str, Any]) -> int:
        """
        Create a new UDF field.

        Args:
            field_data: Dictionary with UDF field data
                Required keys: object_type, field_name, created_by
                Optional: field_value (maps to label column)

        Returns:
            field_id if successful, 0 otherwise
        """
        try:
            # Validate required fields
            required = ['object_type', 'field_name', 'created_by']
            for field in required:
                if field not in field_data:
                    raise ValueError(f"Missing required field: {field}")

            # Generate field_id (timestamp-based)
            field_id = self.get_next_id()

            # Set timestamps
            timestamp = int(datetime.now().timestamp() * 1000)

            # Set defaults
            is_active = field_data.get('is_active', True)
            display_order = field_data.get('display_order', 0)

            # Map field_value to label (table uses 'label' column, not 'field_value')
            label = field_data.get('field_value', '')

            # Escape string values
            object_type = self._escape_string(field_data.get('object_type', ''))
            field_name = self._escape_string(field_data.get('field_name', ''))
            label_escaped = self._escape_string(label)
            created_by = self._escape_string(field_data.get('created_by', ''))
            updated_by = self._escape_string(field_data.get('updated_by', created_by))

            # Build UPSERT query matching actual table schema:
            # field_id, entity_type, object_type, field_name, label, is_active, display_order,
            # created_by, created_at, updated_by, updated_at
            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (field_id, object_type, field_name, label, is_active, display_order,
             created_by, created_at, updated_by, updated_at)
            VALUES (
                {field_id},
                '{object_type}',
                '{field_name}',
                '{label_escaped}',
                {'true' if is_active else 'false'},
                {display_order},
                '{created_by}',
                {timestamp},
                '{updated_by}',
                {timestamp}
            )
            """

            success = impala_manager.execute_write(upsert_query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully created UDF field: {field_data.get('object_type')}.{field_data.get('field_name')}.{label} (ID: {field_id})")
                return field_id

            return 0

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            logger.error(f"Field data: {field_data}")
            return 0

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

    def soft_delete(self, udf_id: int, updated_by: str) -> bool:
        """
        Soft delete UDF field by field_id, setting is_active = false.

        Args:
            udf_id: UDF field ID (field_id in database)
            updated_by: Username performing the delete

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)
            escaped_user = self._escape_string(updated_by)

            # Update is_active to false
            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (field_id, object_type, field_name, label, is_active, display_order,
             created_by, created_at, updated_by, updated_at)
            SELECT
                field_id,
                object_type,
                field_name,
                label,
                false,
                display_order,
                created_by,
                created_at,
                '{escaped_user}',
                {timestamp}
            FROM {self.TABLE_NAME}
            WHERE field_id = {udf_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully soft deleted UDF field with ID: {udf_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting UDF field {udf_id}: {str(e)}")
            return False

    def restore(self, udf_id: int, updated_by: str) -> bool:
        """
        Restore soft-deleted UDF field by field_id, setting is_active = true.

        Args:
            udf_id: UDF field ID (field_id in database)
            updated_by: Username performing the restore

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)
            escaped_user = self._escape_string(updated_by)

            # Update is_active to true
            query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (field_id, object_type, field_name, label, is_active, display_order,
             created_by, created_at, updated_by, updated_at)
            SELECT
                field_id,
                object_type,
                field_name,
                label,
                true,
                display_order,
                created_by,
                created_at,
                '{escaped_user}',
                {timestamp}
            FROM {self.TABLE_NAME}
            WHERE field_id = {udf_id}
            """

            success = impala_manager.execute_write(query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully restored UDF field with ID: {udf_id}")

            return success

        except Exception as e:
            logger.error(f"Error restoring UDF field {udf_id}: {str(e)}")
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
            WHERE label IS NOT NULL AND label != ''
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
