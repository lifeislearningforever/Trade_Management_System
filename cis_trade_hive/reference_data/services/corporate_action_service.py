"""
Corporate Action Service

Business logic layer for corporate action operations with maker-checker workflow.
All data operations use Kudu tables via repository layer.

Status Flow:
  INITIAL → VALIDATED (new record created → validated by checker)
  VALIDATED → MODIFIED → VALIDATED (edit validated record → re-validate)
"""

import logging
import json
from typing import Dict, Optional, Any, List
from datetime import datetime

from reference_data.repositories.corporate_action_repository import corporate_action_repository
from reference_data.services.ca_cash_flow_service import ca_cash_flow_service
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


class CorporateActionService:
    """Service for corporate action business logic with maker-checker workflow"""

    # Status constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_VALIDATED = 'VALIDATED'
    STATUS_REJECTED = 'REJECTED'

    def __init__(self):
        self.repository = corporate_action_repository

    def list_all(
        self,
        limit: int = 1000,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
        ca_type: Optional[str] = None,
        security_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all corporate actions with optional filters.

        Args:
            limit: Maximum records to return
            offset: Number of records to skip
            status: Filter by status
            search: Search term
            ca_type: Filter by CA type
            security_name: Filter by security

        Returns:
            List of corporate action dictionaries
        """
        return self.repository.get_all(
            limit=limit,
            offset=offset,
            status=status,
            search=search,
            ca_type=ca_type,
            security_name=security_name
        )

    def get_by_id(self, ca_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a corporate action by ID.

        Args:
            ca_id: Corporate Action ID

        Returns:
            Corporate action dictionary or None
        """
        return self.repository.get_by_id(ca_id)

    def get_pending_approvals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get corporate actions pending approval.

        Args:
            limit: Maximum records

        Returns:
            List of pending corporate actions
        """
        return self.repository.get_pending_approvals(limit=limit)

    def create(
        self,
        ca_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[int], Optional[str]]:
        """
        Create a new corporate action.

        Args:
            ca_data: Dictionary of corporate action fields
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, ca_id, error_message)
        """
        try:
            # Validate required fields
            if not ca_data.get('security_name'):
                return False, None, "Security is required"
            if not ca_data.get('ca_type'):
                return False, None, "Corporate Action Type is required"

            # Generate CA number if not provided
            if not ca_data.get('ca_number'):
                ca_data['ca_number'] = self.repository.generate_ca_number()

            # Check for duplicate CA number
            existing = self.repository.get_by_ca_number(ca_data['ca_number'])
            if existing:
                return False, None, f"Corporate Action with number '{ca_data['ca_number']}' already exists"

            # Set initial status
            ca_data['status'] = self.STATUS_INITIAL

            # Insert corporate action
            success, ca_id = self.repository.insert(ca_data, created_by=username)

            if not success:
                return False, None, "Failed to create corporate action in database"

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca_data.get('ca_number', ''),
                security_name=ca_data.get('security_name', ''),
                action='CREATE',
                status=self.STATUS_INITIAL,
                changes={'created': True},
                comments=f'Corporate action created by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca_data.get('ca_number', ''),
                action_description=f'Created corporate action: {ca_data.get("ca_number")} for {ca_data.get("security_name")}',
                status='SUCCESS'
            )

            return True, ca_id, None

        except Exception as e:
            logger.error(f"Error creating corporate action: {str(e)}")
            return False, None, str(e)

    def update(
        self,
        ca_id: int,
        ca_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Update an existing corporate action.
        Status changes to MODIFIED after edit (if was INITIAL or VALIDATED).

        Args:
            ca_id: Corporate Action ID
            ca_data: Dictionary of fields to update
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get existing corporate action
            ca = self.repository.get_by_id(ca_id)
            if not ca:
                return False, f"Corporate action {ca_id} not found"

            # Only CIS src_system records can be edited
            src_system = ca.get('src_system', '')
            if src_system and src_system.upper() != 'CIS':
                return False, f"Cannot edit corporate action with source system '{src_system}'. Only CIS records can be edited."

            # Track changes
            changes = {}
            for field, new_value in ca_data.items():
                old_value = ca.get(field)
                if old_value != new_value:
                    changes[field] = {'old': old_value, 'new': new_value}

            if not changes:
                return False, "No changes to update"

            # Set status to MODIFIED after edit
            ca_data['status'] = self.STATUS_MODIFIED

            # Update corporate action
            success = self.repository.update(
                ca_id=ca_id,
                ca_data=ca_data,
                updated_by=username
            )

            if not success:
                return False, "Failed to update corporate action in database"

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca.get('ca_number', ''),
                security_name=ca.get('security_name', ''),
                action='UPDATE',
                status=self.STATUS_MODIFIED,
                changes=changes,
                comments=f'Corporate action updated by {username}',
                performed_by=username
            )

            # Prepare old and new values for audit
            old_values = {field: change['old'] for field, change in changes.items()}
            new_values = {field: change['new'] for field, change in changes.items()}
            changed_fields = list(changes.keys())

            # Log to audit with old_value and new_value
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='UPDATE',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca.get('ca_number', ''),
                action_description=f'Updated corporate action: {ca.get("ca_number")} - Changed fields: {", ".join(changed_fields)}',
                old_value=json.dumps(old_values, default=str),
                new_value=json.dumps(new_values, default=str),
                field_name=', '.join(changed_fields),
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error updating corporate action {ca_id}: {str(e)}")
            return False, str(e)

    def validate(
        self,
        ca_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Validate corporate action (Checker action).
        INITIAL/MODIFIED → VALIDATED

        Args:
            ca_id: Corporate Action ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Validation comments

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get corporate action
            ca = self.repository.get_by_id(ca_id)
            if not ca:
                return False, f"Corporate action {ca_id} not found"

            # Validate status
            current_status = ca.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                return False, f"Cannot validate corporate action with status {current_status}. Only INITIAL or MODIFIED can be validated."

            # Four-Eyes check: validator cannot be the last modifier
            # Use updated_by (whoever last edited) not created_by, so that if U2 edits
            # a validated CA the original creator U1 can act as checker.
            last_modified_by = ca.get('updated_by') or ca.get('created_by', '')
            if last_modified_by == username:
                return False, "You cannot validate your own corporate action (Four-Eyes principle)"

            # Update status to VALIDATED
            success = self.repository.update_status(
                ca_id=ca_id,
                status=self.STATUS_VALIDATED,
                updated_by=username,
                reviewed_comments=comments
            )

            if not success:
                return False, "Failed to validate corporate action"

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca.get('ca_number', ''),
                security_name=ca.get('security_name', ''),
                action='VALIDATE',
                status=self.STATUS_VALIDATED,
                changes={'status': {'old': current_status, 'new': self.STATUS_VALIDATED}},
                comments=comments or f'Validated by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='VALIDATE',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca.get('ca_number', ''),
                action_description=f'Validated corporate action: {ca.get("ca_number")}',
                new_value=comments,
                status='SUCCESS'
            )

            # Queue CA for cash flow generation (for DIVIDEND, INTEREST, COUPON types)
            try:
                ca_cash_flow_service.queue_ca_for_processing(
                    ca_id=ca_id,
                    ca_data=ca,
                    username=username
                )
            except Exception as cf_error:
                # Log but don't fail validation if cash flow queue fails
                logger.warning(f"Failed to queue CA {ca_id} for cash flow processing: {str(cf_error)}")

            return True, None

        except Exception as e:
            logger.error(f"Error validating corporate action {ca_id}: {str(e)}")
            return False, str(e)

    def reject(
        self,
        ca_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Reject corporate action (Checker action).
        INITIAL/MODIFIED → REJECTED

        Args:
            ca_id: Corporate Action ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Rejection comments

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get corporate action
            ca = self.repository.get_by_id(ca_id)
            if not ca:
                return False, f"Corporate action {ca_id} not found"

            # Validate status
            current_status = ca.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                return False, f"Cannot reject corporate action with status {current_status}."

            # Four-Eyes check: checker cannot be the last modifier
            last_modified_by = ca.get('updated_by') or ca.get('created_by', '')
            if last_modified_by == username:
                return False, "You cannot reject your own corporate action (Four-Eyes principle)"

            # Update status to REJECTED
            success = self.repository.update_status(
                ca_id=ca_id,
                status=self.STATUS_REJECTED,
                updated_by=username,
                reviewed_comments=comments
            )

            if not success:
                return False, "Failed to reject corporate action"

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca.get('ca_number', ''),
                security_name=ca.get('security_name', ''),
                action='REJECT',
                status=self.STATUS_REJECTED,
                changes={'status': {'old': current_status, 'new': self.STATUS_REJECTED}},
                comments=comments or f'Rejected by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='REJECT',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca.get('ca_number', ''),
                action_description=f'Rejected corporate action: {ca.get("ca_number")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error rejecting corporate action {ca_id}: {str(e)}")
            return False, str(e)

    def delete(
        self,
        ca_id: int,
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Soft delete a corporate action.

        Args:
            ca_id: Corporate Action ID
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get corporate action
            ca = self.repository.get_by_id(ca_id)
            if not ca:
                return False, f"Corporate action {ca_id} not found"

            # Only CIS records can be deleted
            src_system = ca.get('src_system', '')
            if src_system and src_system.upper() != 'CIS':
                return False, f"Cannot delete corporate action with source system '{src_system}'."

            # Soft delete
            success = self.repository.soft_delete(ca_id, deleted_by=username)

            if not success:
                return False, "Failed to delete corporate action"

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca.get('ca_number', ''),
                security_name=ca.get('security_name', ''),
                action='DELETE',
                status='DELETED',
                changes={'is_deleted': {'old': False, 'new': True}},
                comments=f'Deleted by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='DELETE',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca.get('ca_number', ''),
                action_description=f'Deleted corporate action: {ca.get("ca_number")}',
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error deleting corporate action {ca_id}: {str(e)}")
            return False, str(e)

    def restore(
        self,
        ca_id: int,
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Restore a soft-deleted corporate action.

        Args:
            ca_id: Corporate Action ID
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Restore
            success = self.repository.restore(ca_id, restored_by=username)

            if not success:
                return False, "Failed to restore corporate action"

            # Get restored record
            ca = self.repository.get_by_id(ca_id)

            # Insert history record
            self.repository.insert_history(
                ca_id=ca_id,
                ca_number=ca.get('ca_number', '') if ca else '',
                security_name=ca.get('security_name', '') if ca else '',
                action='RESTORE',
                status=self.STATUS_MODIFIED,
                changes={'is_deleted': {'old': True, 'new': False}},
                comments=f'Restored by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='RESTORE',
                entity_type='CORPORATE_ACTION',
                entity_id=str(ca_id),
                entity_name=ca.get('ca_number', '') if ca else '',
                action_description=f'Restored corporate action: {ca.get("ca_number") if ca else ca_id}',
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error restoring corporate action {ca_id}: {str(e)}")
            return False, str(e)

    def get_history(self, ca_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history for a corporate action.

        Args:
            ca_id: Corporate Action ID
            limit: Maximum records

        Returns:
            List of history records
        """
        return self.repository.get_history(ca_id, limit=limit)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get corporate action statistics.

        Returns:
            Dictionary of statistics
        """
        return self.repository.get_statistics()

    def can_user_edit(self, ca: Dict[str, Any], username: str) -> bool:
        """
        Check if user can edit a corporate action.

        Args:
            ca: Corporate action dictionary
            username: Username

        Returns:
            True if user can edit
        """
        if not ca:
            return False

        # Only CIS records can be edited
        src_system = ca.get('src_system', '')
        if src_system and src_system.upper() != 'CIS':
            return False

        # Cannot edit validated records unless you're the checker
        # (for now, allow editing validated records - they become MODIFIED)
        return True

    def can_user_validate(self, ca: Dict[str, Any], username: str) -> bool:
        """
        Check if user can validate a corporate action.

        Args:
            ca: Corporate action dictionary
            username: Username

        Returns:
            True if user can validate
        """
        if not ca:
            return False

        # Can validate if status is INITIAL or MODIFIED and user is not the last modifier.
        # updated_by reflects whoever last touched the record (create or edit), so if U2
        # edits a validated CA the original creator U1 is unblocked as checker.
        status = ca.get('status', '')
        last_modified_by = ca.get('updated_by') or ca.get('created_by', '')

        return status in [self.STATUS_INITIAL, self.STATUS_MODIFIED] and last_modified_by != username

    @staticmethod
    def get_status_display_color(status: str) -> str:
        """
        Get Bootstrap color class for status badge.

        Args:
            status: Corporate action status

        Returns:
            Bootstrap color class
        """
        colors = {
            'INITIAL': 'secondary',
            'MODIFIED': 'info',
            'VALIDATED': 'success',
            'REJECTED': 'danger',
        }
        return colors.get(status, 'secondary')


# Create singleton instance
corporate_action_service = CorporateActionService()
