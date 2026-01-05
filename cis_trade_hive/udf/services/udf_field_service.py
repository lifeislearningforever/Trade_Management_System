"""
UDF Field Service - Business Logic Layer (Simplified Schema)

New Schema Support:
- object_type: PORTFOLIO, EQUITY_PRICE, SECURITY, etc.
- field_name: Technical name (e.g., 'portfolio_type', 'market')
- field_value: Display label (e.g., 'Portfolio Type', 'Market')
  - Empty ('') for entity type records
  - Non-empty for field records

Cascading Dropdown Logic:
1. Get entity types: WHERE field_value = ''
2. Get fields by entity: WHERE object_type = '<selected>' AND field_value != ''
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from udf.repositories.udf_field_repository import udf_field_repository, UDFFieldRepositoryInterface
from core.audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)


class UDFFieldService:
    """Service for UDF field business logic operations with audit logging."""

    def __init__(self, repository: UDFFieldRepositoryInterface):
        """
        Initialize service with dependency injection.

        Args:
            repository: UDF field repository implementation
        """
        self.repository = repository

    # ========================================================================
    # CASCADING DROPDOWN OPERATIONS
    # ========================================================================

    def get_object_types(self) -> List[str]:
        """
        Get all available entity types for cascading dropdown.

        Returns:
            List of entity type strings
        """
        try:
            return self.repository.get_object_types()
        except Exception as e:
            logger.error(f"Service error getting entity types: {str(e)}")
            return []

    def get_fields_by_entity(self, object_type: str) -> List[Dict[str, Any]]:
        """
        Get all fields for a specific entity type (for cascading dropdown).

        Args:
            object_type: Entity type to filter by

        Returns:
            List of field dictionaries
        """
        try:
            return self.repository.get_fields_by_entity(object_type)
        except Exception as e:
            logger.error(f"Service error getting fields for entity {object_type}: {str(e)}")
            return []

    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================

    def get_all_fields(self, object_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get all UDF fields with optional filters.

        Args:
            object_type: Filter by entity type
            is_active: Filter by active status (True = active, False = deleted, None = all)

        Returns:
            List of UDF field dictionaries
        """
        try:
            return self.repository.get_all(object_type=object_type, is_active=is_active)
        except Exception as e:
            logger.error(f"Service error getting UDF fields: {str(e)}")
            return []

    def get_field_by_id(self, udf_id: int) -> Optional[Dict[str, Any]]:
        """
        Get UDF field by ID.

        Args:
            udf_id: UDF field ID

        Returns:
            UDF field dictionary or None
        """
        try:
            return self.repository.get_by_id(udf_id)
        except Exception as e:
            logger.error(f"Service error getting UDF field {udf_id}: {str(e)}")
            return None

    def get_dashboard_stats(self) -> List[Dict[str, Any]]:
        """
        Get dashboard statistics by entity type.

        Returns:
            List of stats dictionaries with object_type, total_fields, active_fields, inactive_fields
        """
        try:
            return self.repository.get_stats_by_entity()
        except Exception as e:
            logger.error(f"Service error getting dashboard stats: {str(e)}")
            return []

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def validate_field_data(self, field_data: Dict[str, Any], udf_id: Optional[int] = None) -> tuple[bool, Optional[str]]:
        """
        Validate UDF field data.

        Args:
            field_data: Field data to validate
            udf_id: UDF ID (for update operations, None for create)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        if not field_data.get('field_name'):
            return False, "Field Name is required"

        if not field_data.get('field_value'):
            return False, "Field Value (Label) is required"

        if not field_data.get('object_type'):
            return False, "Entity Type is required"

        # Validate field name format
        field_name = field_data['field_name'].strip()
        if not field_name:
            return False, "Field Name cannot be empty"

        if len(field_name) > 200:
            return False, "Field Name must be 200 characters or less"

        # Update field_data with stripped values
        field_data['field_name'] = field_name
        field_data['field_value'] = field_data['field_value'].strip()
        field_data['object_type'] = field_data['object_type'].upper()

        # Check uniqueness of (object_type, field_name) combination
        existing_fields = self.repository.get_all(object_type=field_data['object_type'], is_active=True)

        for existing in existing_fields:
            # Skip self when updating
            if udf_id and existing.get('udf_id') == udf_id:
                continue

            # Skip entity type records (field_value is empty)
            if not existing.get('field_value'):
                continue

            # Check if combination already exists
            if (existing.get('object_type') == field_data['object_type'] and
                existing.get('field_name') == field_name):
                return False, f"Field Name '{field_name}' already exists for entity type '{field_data['object_type']}'"

        return True, None

    # ========================================================================
    # CREATE OPERATION
    # ========================================================================

    def create_field(self, field_data: Dict[str, Any], user_info: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Create a new UDF field with validation and audit logging.

        Args:
            field_data: Dictionary with object_type, field_name, field_value
            user_info: Dictionary with user_id, username, user_email

        Returns:
            Tuple of (success, error_message, udf_id)
        """
        try:
            # Validate
            is_valid, error_msg = self.validate_field_data(field_data)
            if not is_valid:
                return False, error_msg, None

            # Get next UDF ID
            udf_id = self.repository.get_next_id()

            # Prepare data
            create_data = {
                'udf_id': udf_id,
                'object_type': field_data['object_type'].upper(),
                'field_name': field_data['field_name'],
                'field_value': field_data['field_value'],
                'is_active': True,
                'created_by': user_info['username'],
            }

            # Create in repository
            success = self.repository.create(create_data)

            if success:
                # Log to audit
                audit_log_kudu_repository.log_action(
                    user_id=str(user_info['user_id']),
                    username=user_info['username'],
                    user_email=user_info.get('user_email', ''),
                    action_type='CREATE',
                    object_type='UDF',
                    entity_name=create_data['field_value'],
                    entity_id=str(udf_id),
                    action_description=f"Created UDF field '{create_data['field_value']}' ({create_data['field_name']}) for {create_data['object_type']}",
                    request_method='POST',
                    request_path='/udf/create/',
                    ip_address=user_info.get('ip_address', ''),
                    user_agent=user_info.get('user_agent', ''),
                    status='SUCCESS'
                )

                logger.info(f"Created UDF field: {create_data['field_name']} (ID: {udf_id})")
                return True, None, udf_id

            return False, "Failed to create UDF field in database", None

        except Exception as e:
            error_msg = f"Error creating UDF field: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None

    # ========================================================================
    # UPDATE OPERATION
    # ========================================================================

    def update_field(self, udf_id: int, field_data: Dict[str, Any], user_info: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Update existing UDF field with validation and audit logging.

        Args:
            udf_id: UDF field ID to update
            field_data: Dictionary with object_type, field_name, field_value, is_active
            user_info: Dictionary with user_id, username, user_email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check if field exists
            existing = self.repository.get_by_id(udf_id)
            if not existing:
                return False, f"UDF field {udf_id} not found"

            # Validate (pass udf_id to allow updating the same record)
            is_valid, error_msg = self.validate_field_data(field_data, udf_id=udf_id)
            if not is_valid:
                return False, error_msg

            # Prepare update data (preserve created_by and created_at)
            update_data = {
                'udf_id': udf_id,
                'object_type': field_data['object_type'].upper(),
                'field_name': field_data['field_name'],
                'field_value': field_data['field_value'],
                'is_active': field_data.get('is_active', True),
                'created_by': existing['created_by'],
                'created_at': existing['created_at'],
                'updated_by': user_info['username'],
            }

            # Update in repository
            success = self.repository.update(udf_id, update_data)

            if success:
                # Log to audit
                audit_log_kudu_repository.log_action(
                    user_id=str(user_info['user_id']),
                    username=user_info['username'],
                    user_email=user_info.get('user_email', ''),
                    action_type='UPDATE',
                    object_type='UDF',
                    entity_name=update_data['field_value'],
                    entity_id=str(udf_id),
                    action_description=f"Updated UDF field '{update_data['field_value']}' ({update_data['field_name']}) for {update_data['object_type']}",
                    request_method='POST',
                    request_path=f'/udf/{udf_id}/edit/',
                    ip_address=user_info.get('ip_address', ''),
                    user_agent=user_info.get('user_agent', ''),
                    status='SUCCESS'
                )

                logger.info(f"Updated UDF field: {update_data['field_name']} (ID: {udf_id})")
                return True, None

            return False, "Failed to update UDF field in database"

        except Exception as e:
            error_msg = f"Error updating UDF field: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    # ========================================================================
    # DELETE OPERATION (Soft Delete)
    # ========================================================================

    def delete_field(self, udf_id: int, user_info: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Soft delete UDF field with audit logging.

        Args:
            udf_id: UDF field ID to delete
            user_info: Dictionary with user_id, username, user_email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check if field exists
            existing = self.repository.get_by_id(udf_id)
            if not existing:
                return False, f"UDF field {udf_id} not found"

            if not existing.get('is_active', True):
                return False, "UDF field is already deleted"

            # Soft delete
            success = self.repository.soft_delete(udf_id, user_info['username'])

            if success:
                # Log to audit
                audit_log_kudu_repository.log_action(
                    user_id=str(user_info['user_id']),
                    username=user_info['username'],
                    user_email=user_info.get('user_email', ''),
                    action_type='DELETE',
                    object_type='UDF',
                    entity_name=existing['field_value'],
                    entity_id=str(udf_id),
                    action_description=f"Deleted UDF field '{existing['field_value']}' ({existing['field_name']}) for {existing['object_type']}",
                    request_method='POST',
                    request_path=f'/udf/{udf_id}/delete/',
                    ip_address=user_info.get('ip_address', ''),
                    user_agent=user_info.get('user_agent', ''),
                    status='SUCCESS'
                )

                logger.info(f"Deleted UDF field: {existing['field_name']} (ID: {udf_id})")
                return True, None

            return False, "Failed to delete UDF field in database"

        except Exception as e:
            error_msg = f"Error deleting UDF field: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    # ========================================================================
    # RESTORE OPERATION
    # ========================================================================

    def restore_field(self, udf_id: int, user_info: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Restore soft-deleted UDF field with audit logging.

        Args:
            udf_id: UDF field ID to restore
            user_info: Dictionary with user_id, username, user_email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Check if field exists
            existing = self.repository.get_by_id(udf_id)
            if not existing:
                return False, f"UDF field {udf_id} not found"

            if existing.get('is_active', True):
                return False, "UDF field is already active"

            # Restore
            success = self.repository.restore(udf_id, user_info['username'])

            if success:
                # Log to audit
                audit_log_kudu_repository.log_action(
                    user_id=str(user_info['user_id']),
                    username=user_info['username'],
                    user_email=user_info.get('user_email', ''),
                    action_type='RESTORE',
                    object_type='UDF',
                    entity_name=existing['field_value'],
                    entity_id=str(udf_id),
                    action_description=f"Restored UDF field '{existing['field_value']}' ({existing['field_name']}) for {existing['object_type']}",
                    request_method='POST',
                    request_path=f'/udf/{udf_id}/restore/',
                    ip_address=user_info.get('ip_address', ''),
                    user_agent=user_info.get('user_agent', ''),
                    status='SUCCESS'
                )

                logger.info(f"Restored UDF field: {existing['field_name']} (ID: {udf_id})")
                return True, None

            return False, "Failed to restore UDF field in database"

        except Exception as e:
            error_msg = f"Error restoring UDF field: {str(e)}"
            logger.error(error_msg)
            return False, error_msg


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

udf_field_service = UDFFieldService(repository=udf_field_repository)
