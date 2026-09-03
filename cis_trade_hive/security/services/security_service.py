"""
Security Service

Business logic layer for security operations with maker-checker workflow.
All data operations use Kudu tables via repository layer.

Status Flow:
  INITIAL → VALIDATED (new security created → validated by checker)
  VALIDATED → MODIFIED → VALIDATED (edit validated record → re-validate)
"""

import logging
import json
from typing import Dict, Optional, Any
from datetime import datetime

from security.repositories.security_hive_repository import security_hive_repository
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


class SecurityService:
    """Service for security business logic with maker-checker workflow"""

    # Status constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_VALIDATED = 'VALIDATED'

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

            # Check for a true duplicate — same natural key (ISIN+exchange,
            # ISIN+country, or ISIN alone as a fallback), not just the same
            # ISIN. Cross-listed securities legitimately share an ISIN across
            # different exchanges (e.g. ANZ Banking Group on ASX vs NZX), so
            # a bare ISIN match is not itself a duplicate.
            isin = security_data.get('isin')
            existing_id = security_hive_repository.natural_key_exists(security_data)
            if existing_id:
                return False, None, (
                    f"A security with this natural key already exists "
                    f"(security_id={existing_id}) — "
                    f"{'same ISIN and exchange/country' if isin else 'same name/exchange'}"
                )

            # Set initial status
            security_data['status'] = 'INITIAL'

            # Insert security
            success, security_id = security_hive_repository.insert_security(security_data, created_by=username)

            if not success:
                return False, None, "Failed to create security in database"

            if not security_id:
                return False, None, "Security created but could not retrieve ID"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security_data.get('security_name', ''),
                isin=isin or '',
                action='CREATE',
                status='INITIAL',
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
        Status changes to MODIFIED after edit (if was INITIAL or VALIDATED).

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

            # Only CIS src_system records can be edited
            src_system = security.get('src_system', '')
            if src_system and src_system.upper() != 'CIS':
                return False, f"Cannot edit security with source system '{src_system}'. Only CIS records can be edited."

            def _normalise(v):
                if v is None or v == '' or str(v).strip() in ('None', 'null'):
                    return None
                return v

            # Track changes (treat None and '' as equivalent)
            changes = {}
            for field, new_value in security_data.items():
                old_value = security.get(field)
                if _normalise(old_value) != _normalise(new_value):
                    changes[field] = {'old': old_value, 'new': new_value}

            logger.info(f"Security {security_id} edit: detected {len(changes)} changed fields: {list(changes.keys())}")

            if not changes:
                logger.info(f"No meaningful changes for security {security_id}, forcing status update")
                security_data['status'] = 'MODIFIED'
                security_hive_repository.update_security(
                    security_id=security_id,
                    security_data={'status': 'MODIFIED'},
                    updated_by=username
                )
                return True, None

            # Merge: preserve existing DB values for fields the form sent as empty
            # (prevents wiping data when dropdown pre-selection didn't match)
            merged_data = dict(security)  # start with full existing record
            for field, new_value in security_data.items():
                if _normalise(new_value) is not None:
                    merged_data[field] = new_value  # use submitted value if non-empty
                # else: keep existing DB value for this field

            # Set status to MODIFIED after edit
            merged_data['status'] = 'MODIFIED'
            security_data['status'] = 'MODIFIED'

            # Update security
            success = security_hive_repository.update_security(
                security_id=security_id,
                security_data=merged_data,
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
                status='MODIFIED',
                changes=changes,
                comments=f'Security updated by {username}',
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
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Updated security: {security.get("security_name")} - Changed fields: {", ".join(changed_fields)}',
                old_value=json.dumps(old_values, default=str),
                new_value=json.dumps(new_values, default=str),
                field_name=', '.join(changed_fields),
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error updating security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def validate_security(
        security_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Validate security (Checker action).
        INITIAL/MODIFIED → VALIDATED

        Args:
            security_id: Security ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Validation comments

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
            if current_status not in ['INITIAL', 'MODIFIED']:
                return False, f"Cannot validate security with status {current_status}. Only INITIAL or MODIFIED securities can be validated."

            # Four-Eyes check: validator cannot be the creator
            created_by = security.get('created_by', '')
            if created_by == username:
                return False, "You cannot validate your own security (Four-Eyes principle)"

            # Update status to VALIDATED
            success = security_hive_repository.update_security_status(
                security_id=security_id,
                status='VALIDATED',
                updated_by=username
            )

            if not success:
                return False, "Failed to validate security"

            # Insert history record
            security_hive_repository.insert_security_history(
                security_id=security_id,
                security_name=security.get('security_name', ''),
                isin=security.get('isin', ''),
                action='VALIDATE',
                status='VALIDATED',
                changes={'status': {'old': current_status, 'new': 'VALIDATED'}},
                comments=comments or f'Validated by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='VALIDATE',
                entity_type='SECURITY',
                entity_id=str(security_id),
                entity_name=security.get('security_name', ''),
                action_description=f'Validated security: {security.get("security_name")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error validating security {security_id}: {str(e)}")
            return False, str(e)

    @staticmethod
    def can_user_edit(security: Dict[str, Any], user_id: str) -> bool:
        """
        Check if user can edit a security.
        Only CIS src_system records can be edited.

        Args:
            security: Security dictionary
            user_id: User ID

        Returns:
            True if user can edit, False otherwise
        """
        if not security:
            return False

        # Only CIS records can be edited
        src_system = security.get('src_system', '')
        if src_system and src_system.upper() != 'CIS':
            return False

        return True

    @staticmethod
    def can_user_validate(security: Dict[str, Any], username: str) -> bool:
        """
        Check if user can validate a security.

        Args:
            security: Security dictionary
            username: Username

        Returns:
            True if user can validate, False otherwise
        """
        if not security:
            return False

        # Can validate if status is INITIAL or MODIFIED and user is not the creator
        status = security.get('status', '')
        created_by = security.get('created_by', '')

        return status in ['INITIAL', 'MODIFIED'] and created_by != username

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
            'INITIAL': 'secondary',
            'MODIFIED': 'info',
            'VALIDATED': 'success',
        }
        return colors.get(status, 'secondary')


# Create singleton instance
security_service = SecurityService()
