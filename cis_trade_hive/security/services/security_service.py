"""
Security Service

Business logic layer for security operations with Four-Eyes workflow.
All data operations use Kudu tables via repository layer.
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

from security.repositories.security_hive_repository import security_hive_repository
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


class SecurityService:
    """Service for security business logic with Four-Eyes principle"""

    @staticmethod
    def create_security(
        security_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[int], Optional[str]]:
        """
        Create a new security.

        Args:
            security_data: Dictionary of security fields
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, security_id, error_message)
        """
        try:
            # Validate required fields
            if not security_data.get('security_name'):
                return False, None, "Security name is required"

            # Check for duplicate ISIN if provided
            isin = security_data.get('isin')
            if isin:
                existing = security_hive_repository.get_security_by_isin(isin)
                if existing:
                    return False, None, f"Security with ISIN '{isin}' already exists"

            # Set initial status
            security_data['status'] = 'DRAFT'

            # Insert security
            success = security_hive_repository.insert_security(security_data, created_by=username)

            if not success:
                return False, None, "Failed to create security in database"

            # Get the created security (to get security_id)
            if isin:
                created_security = security_hive_repository.get_security_by_isin(isin)
            else:
                # Query by name if no ISIN
                securities = security_hive_repository.get_all_securities(
                    limit=1,
                    search=security_data.get('security_name')
                )
                created_security = securities[0] if securities else None

            if not created_security:
                return False, None, "Security created but could not retrieve ID"

            security_id = created_security.get('security_id')

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security_data.get('security_name', ''),
                isin=isin or '',
                action='CREATE',
                status='DRAFT',
                changes={'created': True},
                comments=f'Security created by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security_data.get('security_name', ''),
                action_description=f'Created security: {security_data.get("security_name")}',
                status='SUCCESS'
            )

            return True, security_id, None

        except Exception as e:
            logger.error(f"Error creating security: {str(e)}")
            return False, None, str(e)

    @staticmethod
    def update_security(
        security_id: int,
        security_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Update an existing security.

        Args:
            security_id: Security ID
            security_data: Dictionary of fields to update
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get existing security
            security = security_hive_repository.get_security_by_id(security_id)
            if not security:
                return False, f"Security {security_id} not found"

            # Validate status (only DRAFT or REJECTED can be edited)
            current_status = security.get('status', '')
            if current_status not in ['DRAFT', 'REJECTED']:
                return False, f"Cannot edit security with status {current_status}. Only DRAFT or REJECTED securities can be edited."

            # Validate user is the creator (optional - can be removed for demo)
            # if security.get('created_by') != username:
            #     return False, "You can only edit securities you created"

            # Track changes
            changes = {}
            for field, new_value in security_data.items():
                old_value = security.get(field)
                if old_value != new_value:
                    changes[field] = {'old': old_value, 'new': new_value}

            if not changes:
                return False, "No changes to update"

            # Update security
            success = security_hive_repository.update_security(
                security_id=security_id,
                security_data=security_data,
                updated_by=username
            )

            if not success:
                return False, "Failed to update security in database"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security.get('security_name', ''),
                isin=security.get('isin', ''),
                action='UPDATE',
                status=current_status,
                changes=changes,
                comments=f'Security updated by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='UPDATE',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Updated security: {security.get("security_name")}',
                old_value=str(changes),
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error updating security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def submit_for_approval(
        security_id: int,
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Submit security for approval (Maker action).

        Args:
            security_id: Security ID
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get security
            security = security_hive_repository.get_security_by_id(security_id)
            if not security:
                return False, f"Security {security_id} not found"

            # Validate status
            current_status = security.get('status', '')
            if current_status not in ['DRAFT', 'REJECTED']:
                return False, f"Cannot submit security with status {current_status}. Only DRAFT or REJECTED securities can be submitted."

            # Update status to PENDING_APPROVAL
            success = security_hive_repository.update_security_status(
                security_id=security_id,
                status='PENDING_APPROVAL',
                updated_by=username,
                submitted_by=username
            )

            if not success:
                return False, "Failed to update security status"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security.get('security_name', ''),
                isin=security.get('isin', ''),
                action='SUBMIT',
                status='PENDING_APPROVAL',
                changes={'status': {'old': current_status, 'new': 'PENDING_APPROVAL'}},
                comments=f'Submitted for approval by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='SUBMIT',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Submitted security for approval: {security.get("security_name")}',
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error submitting security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def approve_security(
        security_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Approve security (Checker action).

        Args:
            security_id: Security ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Approval comments

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get security
            security = security_hive_repository.get_security_by_id(security_id)
            if not security:
                return False, f"Security {security_id} not found"

            # Validate status
            current_status = security.get('status', '')
            if current_status != 'PENDING_APPROVAL':
                return False, f"Cannot approve security with status {current_status}. Only PENDING_APPROVAL securities can be approved."

            # Four-Eyes check: approver cannot be the creator
            created_by = security.get('created_by', '')
            if created_by == username:
                return False, "You cannot approve your own security (Four-Eyes principle)"

            # Update status to ACTIVE
            success = security_hive_repository.update_security_status(
                security_id=security_id,
                status='ACTIVE',
                updated_by=username,
                reviewed_by=username,
                review_comments=comments
            )

            if not success:
                return False, "Failed to approve security"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security.get('security_name', ''),
                isin=security.get('isin', ''),
                action='APPROVE',
                status='ACTIVE',
                changes={'status': {'old': current_status, 'new': 'ACTIVE'}},
                comments=comments or f'Approved by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='APPROVE',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Approved security: {security.get("security_name")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error approving security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def reject_security(
        security_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str
    ) -> tuple[bool, Optional[str]]:
        """
        Reject security (Checker action).

        Args:
            security_id: Security ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Rejection comments (required)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Validate comments are provided
            if not comments or not comments.strip():
                return False, "Rejection comments are required"

            # Get security
            security = security_hive_repository.get_security_by_id(security_id)
            if not security:
                return False, f"Security {security_id} not found"

            # Validate status
            current_status = security.get('status', '')
            if current_status != 'PENDING_APPROVAL':
                return False, f"Cannot reject security with status {current_status}. Only PENDING_APPROVAL securities can be rejected."

            # Update status to REJECTED
            success = security_hive_repository.update_security_status(
                security_id=security_id,
                status='REJECTED',
                updated_by=username,
                reviewed_by=username,
                review_comments=comments
            )

            if not success:
                return False, "Failed to reject security"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security.get('security_name', ''),
                isin=security.get('isin', ''),
                action='REJECT',
                status='REJECTED',
                changes={'status': {'old': current_status, 'new': 'REJECTED'}},
                comments=comments,
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='REJECT',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Rejected security: {security.get("security_name")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error rejecting security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def can_user_edit(security: Dict[str, Any], user_id: str) -> bool:
        """
        Check if user can edit a security.

        Args:
            security: Security dictionary
            user_id: User ID

        Returns:
            True if user can edit, False otherwise
        """
        if not security:
            return False

        # Can edit if status is DRAFT or REJECTED
        status = security.get('status', '')
        return status in ['DRAFT', 'REJECTED']

    @staticmethod
    def can_user_approve(security: Dict[str, Any], username: str) -> bool:
        """
        Check if user can approve a security.

        Args:
            security: Security dictionary
            username: Username

        Returns:
            True if user can approve, False otherwise
        """
        if not security:
            return False

        # Can approve if status is PENDING_APPROVAL and user is not the creator
        status = security.get('status', '')
        created_by = security.get('created_by', '')

        return status == 'PENDING_APPROVAL' and created_by != username

    @staticmethod
    def get_status_display_color(status: str) -> str:
        """
        Get Bootstrap color class for status badge.

        Args:
            status: Security status

        Returns:
            Bootstrap color class
        """
        colors = {
            'DRAFT': 'secondary',
            'PENDING_APPROVAL': 'warning',
            'APPROVED': 'success',
            'ACTIVE': 'success',
            'REJECTED': 'danger',
            'INACTIVE': 'dark',
        }
        return colors.get(status, 'secondary')


# Create singleton instance
security_service = SecurityService()
