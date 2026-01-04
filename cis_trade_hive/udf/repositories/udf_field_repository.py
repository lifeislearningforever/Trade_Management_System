"""
UDF Field Repository - Simplified Free Text Approach
Follows SOLID Principles:
- Single Responsibility: Only handles data access for UDF fields
- Open/Closed: Extensible without modification
- Liskov Substitution: Implements clear interface
- Interface Segregation: Focused interface for UDF fields
- Dependency Inversion: Depends on abstractions (impala_manager)
"""

from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import logging
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


# ============================================================================
# INTERFACE (Dependency Inversion Principle)
# ============================================================================

class UDFFieldRepositoryInterface(ABC):
    """Abstract interface for UDF field repository."""

    @abstractmethod
    def get_all(self, entity_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get all UDF fields with optional filters."""
        pass

    @abstractmethod
    def get_by_id(self, udf_id: int) -> Optional[Dict[str, Any]]:
        """Get UDF field by ID."""
        pass

    @abstractmethod
    def create(self, field_data: Dict[str, Any]) -> bool:
        """Create a new UDF field."""
        pass

    @abstractmethod
    def update(self, udf_id: int, field_data: Dict[str, Any]) -> bool:
        """Update existing UDF field."""
        pass

    @abstractmethod
    def soft_delete(self, udf_id: int, updated_by: str) -> bool:
        """Soft delete UDF field by setting is_active = false."""
        pass

    @abstractmethod
    def restore(self, udf_id: int, updated_by: str) -> bool:
        """Restore soft-deleted UDF field by setting is_active = true."""
        pass

    @abstractmethod
    def get_stats_by_entity(self) -> List[Dict[str, Any]]:
        """Get statistics grouped by entity type."""
        pass


# ============================================================================
# IMPLEMENTATION (Single Responsibility Principle)
# ============================================================================

class UDFFieldRepository(UDFFieldRepositoryInterface):
    """Repository for UDF field data access operations."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_udf_field'

    def get_all(self, entity_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get all UDF fields with optional filters.

        Args:
            entity_type: Filter by entity type (PORTFOLIO, TRADE, etc.)
            is_active: Filter by active status (True/False/None for all)

        Returns:
            List of UDF field dictionaries
        """
        try:
            query = f"SELECT * FROM {self.TABLE_NAME}"
            conditions = []

            if entity_type:
                conditions.append(f"entity_type = '{entity_type.upper()}'")

            if is_active is not None:
                conditions.append(f"is_active = {'true' if is_active else 'false'}")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY entity_type, field_name"

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved {len(results) if results else 0} UDF fields")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving UDF fields: {str(e)}")
            logger.error(f"Query: {query}")
            raise

    def get_by_id(self, udf_id: int) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by ID.

        Args:
            udf_id: UDF field ID

        Returns:
            UDF field dictionary or None
        """
        try:
            query = f"SELECT * FROM {self.TABLE_NAME} WHERE udf_id = {udf_id} LIMIT 1"
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"Error retrieving UDF field {udf_id}: {str(e)}")
            raise

    def create(self, field_data: Dict[str, Any]) -> bool:
        """
        Create a new UDF field.

        Args:
            field_data: Dictionary with UDF field data
                Required keys: udf_id, field_name, label, entity_type, created_by

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate required fields
            required = ['udf_id', 'field_name', 'label', 'entity_type', 'created_by']
            for field in required:
                if field not in field_data:
                    raise ValueError(f"Missing required field: {field}")

            # Set timestamps
            timestamp = int(datetime.now().timestamp() * 1000)
            field_data['created_at'] = timestamp
            field_data['updated_at'] = timestamp
            field_data['updated_by'] = field_data['created_by']

            # Set defaults
            field_data.setdefault('is_required', False)
            field_data.setdefault('is_active', True)

            # Build UPSERT query
            columns = []
            values = []

            for key, value in field_data.items():
                columns.append(f"`{key}`")
                if isinstance(value, str):
                    escaped_value = value.replace("'", "''")
                    values.append(f"'{escaped_value}'")
                elif isinstance(value, bool):
                    values.append('true' if value else 'false')
                elif isinstance(value, (int, float)):
                    values.append(str(value))
                else:
                    values.append('NULL')

            upsert_query = f"""
            UPSERT INTO {self.DATABASE}.{self.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_query, database=self.DATABASE)

            if success:
                logger.info(f"Successfully created UDF field: {field_data.get('field_name')}")

            return success

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            logger.error(f"Field data: {field_data}")
            return False

    def update(self, udf_id: int, field_data: Dict[str, Any]) -> bool:
        """
        Update existing UDF field.

        Args:
            udf_id: UDF field ID
            field_data: Dictionary with updated field data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure udf_id is in the data
            field_data['udf_id'] = udf_id

            # Update timestamp
            timestamp = int(datetime.now().timestamp() * 1000)
            field_data['updated_at'] = timestamp

            # Use create method (UPSERT will update if exists)
            return self.create(field_data)

        except Exception as e:
            logger.error(f"Error updating UDF field {udf_id}: {str(e)}")
            return False

    def soft_delete(self, udf_id: int, updated_by: str) -> bool:
        """
        Soft delete UDF field by setting is_active = false.

        Args:
            udf_id: UDF field ID to delete
            updated_by: Username performing the delete

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            # Fetch existing record first
            existing = self.get_by_id(udf_id)
            if not existing:
                logger.error(f"UDF field {udf_id} not found for soft delete")
                return False

            # Update with is_active = false
            update_data = {
                'udf_id': udf_id,
                'field_name': existing['field_name'],
                'label': existing['label'],
                'entity_type': existing['entity_type'],
                'is_required': existing.get('is_required', False),
                'is_active': False,  # Soft delete
                'created_by': existing['created_by'],
                'created_at': existing['created_at'],
                'updated_by': updated_by,
                'updated_at': timestamp,
            }

            success = self.create(update_data)  # UPSERT

            if success:
                logger.info(f"Successfully soft deleted UDF field ID: {udf_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting UDF field: {str(e)}")
            return False

    def restore(self, udf_id: int, updated_by: str) -> bool:
        """
        Restore soft-deleted UDF field by setting is_active = true.

        Args:
            udf_id: UDF field ID to restore
            updated_by: Username performing the restore

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            # Fetch existing record first
            existing = self.get_by_id(udf_id)
            if not existing:
                logger.error(f"UDF field {udf_id} not found for restore")
                return False

            # Update with is_active = true
            update_data = {
                'udf_id': udf_id,
                'field_name': existing['field_name'],
                'label': existing['label'],
                'entity_type': existing['entity_type'],
                'is_required': existing.get('is_required', False),
                'is_active': True,  # Restore
                'created_by': existing['created_by'],
                'created_at': existing['created_at'],
                'updated_by': updated_by,
                'updated_at': timestamp,
            }

            success = self.create(update_data)  # UPSERT

            if success:
                logger.info(f"Successfully restored UDF field ID: {udf_id}")

            return success

        except Exception as e:
            logger.error(f"Error restoring UDF field: {str(e)}")
            return False

    def get_stats_by_entity(self) -> List[Dict[str, Any]]:
        """
        Get statistics grouped by entity type.

        Returns:
            List of dictionaries with entity_type, total_fields, active_fields, inactive_fields
        """
        try:
            query = f"""
            SELECT
                entity_type,
                COUNT(*) as total_fields,
                SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END) as active_fields,
                SUM(CASE WHEN is_active = false THEN 1 ELSE 0 END) as inactive_fields
            FROM {self.TABLE_NAME}
            GROUP BY entity_type
            ORDER BY entity_type
            """

            results = impala_manager.execute_query(query, database=self.DATABASE)
            logger.info(f"Retrieved stats for {len(results) if results else 0} entity types")
            return results if results else []

        except Exception as e:
            logger.error(f"Error retrieving UDF stats: {str(e)}")
            raise


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

udf_field_repository = UDFFieldRepository()
