"""
UDF Field Repository - Composite Primary Key Schema

Schema (from work environment):
- object_type: STRING - Entity type (TRADE, PORTFOLIO, SECURITY, etc.)
- field_name: STRING - Field name (e.g., 'Fund Type', 'Selling Rule')
- field_value: STRING - Field value/dropdown option
- is_active: BOOLEAN - Soft delete flag
- created_by: STRING - User who created
- created_at: BIGINT - Unix timestamp in milliseconds
- updated_by: STRING - User who last updated
- updated_at: BIGINT - Unix timestamp in milliseconds

Primary Key: (object_type, field_name, field_value) - COMPOSITE KEY
"""

from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import logging
from datetime import datetime

from .impala_connection import impala_manager
from .config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# IMPLEMENTATION
# ============================================================================

class UDFFieldRepository:
    """Repository for UDF field data access with composite primary key (object_type, field_name, field_value)."""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_udf_field'

    def _escape_string(self, value: str) -> str:
        """Escape single quotes in string for SQL."""
        if value is None:
            return ''
        return str(value).replace("'", "\\'")

    def _generate_composite_id(self, object_type: str, field_name: str, field_value: str) -> str:
        """
        Generate a deterministic ID from composite key for URL routing.
        Uses MD5 hash of composite key (always same for same inputs).
        """
        import hashlib
        key = f"{object_type}|{field_name}|{field_value}"
        # Use full hash for uniqueness - deterministic, same ID every time
        return hashlib.md5(key.encode()).hexdigest()

    # ========================================================================
    # READ OPERATIONS
    # ========================================================================

    def get_object_types(self) -> List[str]:
        """
        Get all available object types.
        Object types are identified by records where field_value is empty.

        Returns:
            List of object type strings (e.g., ['PORTFOLIO', 'TRADE', 'SECURITY'])
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
        Get all field definitions for a specific object type.
        Field definitions are records where field_value is empty.

        Args:
            object_type: Entity type to filter by (e.g., 'TRADE', 'PORTFOLIO')

        Returns:
            List of field dictionaries with field_name
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
        Get all dropdown values for a specific field.
        Values are records where field_value is NOT empty.

        Args:
            object_type: Entity type (e.g., 'TRADE')
            field_name: Field name (e.g., 'Fund Type')

        Returns:
            List of value dictionaries
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
            logger.info(f"Retrieved {len(results) if results else 0} values for: {object_type}.{field_name}")
            return results or []

        except Exception as e:
            logger.error(f"Error retrieving field values for {object_type}.{field_name}: {str(e)}")
            return []

    def get_all(self, object_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get all UDF fields with optional filters.
        Returns records where field_value is NOT empty (actual field values, not definitions).

        Args:
            object_type: Optional filter by object type
            is_active: Optional filter by active status

        Returns:
            List of UDF field dictionaries
        """
        try:
            conditions = []

            # Only return field value records (not object type definitions)
            conditions.append("(field_value IS NOT NULL AND field_value != '')")

            if object_type:
                escaped_entity = self._escape_string(object_type)
                conditions.append(f"object_type = '{escaped_entity}'")

            if is_active is not None:
                conditions.append(f"is_active = {'true' if is_active else 'false'}")

            where_clause = " AND ".join(conditions) if conditions else "1=1"

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
            WHERE {where_clause}
            ORDER BY object_type, field_name, field_value
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)

            # Add a generated udf_id for URL routing (hash of composite key)
            if results:
                for row in results:
                    row['udf_id'] = self._generate_composite_id(
                        row['object_type'],
                        row['field_name'],
                        row['field_value']
                    )

            logger.info(f"Retrieved {len(results) if results else 0} UDF fields")
            return results or []

        except Exception as e:
            logger.error(f"Error retrieving UDF fields: {str(e)}")
            return []

    def get_by_key(self, object_type: str, field_name: str, field_value: str) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by composite key.

        Args:
            object_type: Object type
            field_name: Field name
            field_value: Field value

        Returns:
            UDF field dictionary or None
        """
        try:
            escaped_entity = self._escape_string(object_type)
            escaped_field = self._escape_string(field_name)
            escaped_value = self._escape_string(field_value)

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

            if results:
                row = results[0]
                row['udf_id'] = self._generate_composite_id(
                    row['object_type'],
                    row['field_name'],
                    row['field_value']
                )
                return row

            return None

        except Exception as e:
            logger.error(f"Error retrieving UDF field by key {object_type}.{field_name}.{field_value}: {str(e)}")
            return None

    def get_by_id(self, udf_id: str) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by generated ID (MD5 hash of composite key).

        NOTE: Since table uses composite key, we search all records and match by generated ID.
        This is not efficient for large datasets - consider using get_by_key instead.

        Args:
            udf_id: Generated UDF ID (MD5 hash string from URL)

        Returns:
            UDF field dictionary or None
        """
        try:
            # Get all records and find matching ID
            all_records = self.get_all(is_active=None)  # Include inactive

            for record in all_records:
                if str(record.get('udf_id', '')) == str(udf_id):
                    return record

            logger.warning(f"UDF field with ID {udf_id} not found")
            return None

        except Exception as e:
            logger.error(f"Error retrieving UDF field by ID {udf_id}: {str(e)}")
            return None

    # ========================================================================
    # WRITE OPERATIONS
    # ========================================================================

    def create(self, field_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new UDF field using UPSERT.

        Args:
            field_data: Dictionary with UDF field data
                Required: object_type, field_name, created_by
                Optional: field_value (defaults to empty for definitions)

        Returns:
            Generated udf_id (hash string) if successful, None otherwise
        """
        try:
            # Validate required fields
            required = ['object_type', 'field_name', 'created_by']
            for field in required:
                if field not in field_data:
                    raise ValueError(f"Missing required field: {field}")

            # Set timestamps
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Extract and escape values
            object_type = self._escape_string(field_data.get('object_type', ''))
            field_name = self._escape_string(field_data.get('field_name', ''))
            field_value = self._escape_string(field_data.get('field_value', ''))
            created_by = self._escape_string(field_data.get('created_by', ''))
            updated_by = self._escape_string(field_data.get('updated_by', created_by))
            is_active = field_data.get('is_active', True)

            # Build UPSERT query matching actual table schema
            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (object_type, field_name, field_value, is_active,
             created_by, created_at, updated_by, updated_at)
            VALUES (
                '{object_type}',
                '{field_name}',
                '{field_value}',
                {'true' if is_active else 'false'},
                '{created_by}',
                '{timestamp}',
                '{updated_by}',
                '{timestamp}'
            )
            """

            success = impala_manager.execute_write(upsert_query, database=self.DATABASE)

            if success:
                # Generate ID for return value (hash string)
                udf_id = self._generate_composite_id(
                    field_data.get('object_type', ''),
                    field_data.get('field_name', ''),
                    field_data.get('field_value', '')
                )

                logger.info(f"Created UDF field: {object_type}.{field_name}.{field_value}")
                return udf_id

            return None

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            logger.error(f"Field data: {field_data}")
            return None

    def update(self, udf_id: str, field_data: Dict[str, Any]) -> bool:
        """
        Update existing UDF field.
        Since table uses composite key, we need the original key to update.

        Args:
            udf_id: Generated UDF ID (used to find original record)
            field_data: Dictionary with updated field data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Find existing record by ID
            existing = self.get_by_id(udf_id)
            if not existing:
                logger.error(f"UDF field with ID {udf_id} not found for update")
                return False

            # Set timestamps
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Use existing composite key values
            object_type = self._escape_string(existing['object_type'])
            field_name = self._escape_string(existing['field_name'])
            field_value = self._escape_string(existing['field_value'])

            # Updated values
            updated_by = self._escape_string(field_data.get('updated_by', ''))
            is_active = field_data.get('is_active', existing.get('is_active', True))
            created_by = self._escape_string(existing.get('created_by', ''))
            created_at = existing.get('created_at', timestamp)

            # Build UPSERT query
            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            (object_type, field_name, field_value, is_active,
             created_by, created_at, updated_by, updated_at)
            VALUES (
                '{object_type}',
                '{field_name}',
                '{field_value}',
                {'true' if is_active else 'false'},
                '{created_by}',
                '{created_at}',
                '{updated_by}',
                '{timestamp}'
            )
            """

            success = impala_manager.execute_write(upsert_query, database=self.DATABASE)

            if success:
                logger.info(f"Updated UDF field: {object_type}.{field_name}.{field_value}")

            return success

        except Exception as e:
            logger.error(f"Error updating UDF field: {str(e)}")
            return False

    def soft_delete(self, udf_id: str, updated_by: str) -> bool:
        """
        Soft delete UDF field by setting is_active = false.

        Args:
            udf_id: Generated UDF ID
            updated_by: Username of person deleting

        Returns:
            True if successful, False otherwise
        """
        try:
            # Find existing record by ID
            existing = self.get_by_id(udf_id)
            if not existing:
                logger.error(f"UDF field with ID {udf_id} not found for delete")
                return False

            # Update with is_active = false
            field_data = {
                'is_active': False,
                'updated_by': updated_by
            }

            return self.update(udf_id, field_data)

        except Exception as e:
            logger.error(f"Error soft deleting UDF field: {str(e)}")
            return False

    def restore(self, udf_id: str, updated_by: str) -> bool:
        """
        Restore soft-deleted UDF field by setting is_active = true.

        Args:
            udf_id: Generated UDF ID
            updated_by: Username of person restoring

        Returns:
            True if successful, False otherwise
        """
        try:
            # Find existing record by ID
            existing = self.get_by_id(udf_id)
            if not existing:
                logger.error(f"UDF field with ID {udf_id} not found for restore")
                return False

            # Update with is_active = true
            field_data = {
                'is_active': True,
                'updated_by': updated_by
            }

            return self.update(udf_id, field_data)

        except Exception as e:
            logger.error(f"Error restoring UDF field: {str(e)}")
            return False

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def add_field_definition(self, object_type: str, field_name: str, created_by: str) -> bool:
        """Create a field definition (field_value='') as a placeholder."""
        return bool(self.create({
            'object_type': object_type,
            'field_name': field_name,
            'field_value': '',
            'is_active': True,
            'created_by': created_by,
        }))

    def add_field_value(self, object_type: str, field_name: str, field_value: str, created_by: str) -> bool:
        """Create a field value entry. Raises ValueError if field_value is empty."""
        if not field_value:
            raise ValueError("field_value cannot be empty or None")
        return bool(self.create({
            'object_type': object_type,
            'field_name': field_name,
            'field_value': field_value,
            'is_active': True,
            'created_by': created_by,
        }))

    def get_next_id(self) -> int:
        """Return a timestamp-based unique ID (milliseconds)."""
        import time
        return int(time.time() * 1000)

    def update_by_id(self, udf_id: str, field_data: Dict[str, Any]) -> bool:
        """Alias for update() — update by composite-key-derived ID."""
        return self.update(udf_id, field_data)

    def get_stats_by_entity(self) -> List[Dict[str, Any]]:
        """Alias for get_dashboard_stats()."""
        return self.get_dashboard_stats()

    # ========================================================================
    # DASHBOARD STATISTICS
    # ========================================================================

    def get_dashboard_stats(self) -> List[Dict[str, Any]]:
        """
        Get statistics for UDF dashboard - count of fields per object type.

        Returns:
            List of stats dictionaries with object_type, total, active, inactive counts
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

            stats = []
            for row in (results or []):
                stats.append({
                    'object_type': row['object_type'],
                    'total_fields': int(row['total_fields'] or 0),
                    'active_fields': int(row['active_fields'] or 0),
                    'inactive_fields': int(row['inactive_fields'] or 0)
                })

            logger.info(f"Retrieved dashboard stats for {len(stats)} object types")
            return stats

        except Exception as e:
            logger.error(f"Error retrieving dashboard stats: {str(e)}")
            return []


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

udf_field_repository = UDFFieldRepository()
