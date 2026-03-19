"""
Cash Flow Service

Business logic layer for cash flow operations with maker-checker workflow.
All data operations use Kudu tables via repository layer.

Status Flow (same as Portfolio):
  INITIAL → APPROVED (new record created → approved by checker)
  INITIAL → REJECTED (new record rejected)
  APPROVED → MODIFIED → APPROVED (edit approved record → re-approve)
"""

import logging
import json
from typing import Dict, Optional, Any, List
from datetime import datetime

from trade.repositories.cash_flow_repository import cash_flow_repository
from trade.repositories.trade_validation_repository import trade_validation_repository
from core.audit.audit_kudu_repository import AuditLogKuduRepository

logger = logging.getLogger(__name__)


class CashFlowService:
    """Service for cash flow business logic with maker-checker workflow"""

    # Status constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'

    def __init__(self):
        self.repository = cash_flow_repository

    def list_all(
        self,
        limit: int = 1000,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
        portfolio_short_name: Optional[str] = None,
        cash_flow_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all cash flows with optional filters.

        Args:
            limit: Maximum records to return
            offset: Number of records to skip
            status: Filter by status
            search: Search term
            portfolio_short_name: Filter by portfolio
            cash_flow_type: Filter by cash flow type

        Returns:
            List of cash flow dictionaries
        """
        return self.repository.get_all(
            limit=limit,
            offset=offset,
            status=status,
            search=search,
            portfolio_short_name=portfolio_short_name,
            cash_flow_type=cash_flow_type
        )

    def get_by_id(self, cf_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a cash flow by ID.

        Args:
            cf_id: Cash Flow ID

        Returns:
            Cash flow dictionary or None
        """
        return self.repository.get_by_id(cf_id)

    def get_pending_approvals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get cash flows pending approval.

        Args:
            limit: Maximum records

        Returns:
            List of pending cash flows
        """
        return self.repository.get_pending_approvals(limit=limit)

    def get_by_portfolio(self, portfolio_short_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get cash flows for a specific portfolio.

        Args:
            portfolio_short_name: Portfolio short name
            limit: Maximum records

        Returns:
            List of cash flows
        """
        return self.repository.get_by_portfolio(portfolio_short_name, limit=limit)

    def validate_portfolio(self, portfolio_short_name: str) -> Dict[str, Any]:
        """
        Validate portfolio for cash flow creation.

        Args:
            portfolio_short_name: Portfolio short name

        Returns:
            Dictionary with validation result and message
        """
        return trade_validation_repository.validate_portfolio(portfolio_short_name)

    def validate_security(self, security_name: str) -> Dict[str, Any]:
        """
        Validate security for cash flow creation.

        Args:
            security_name: Security label/name

        Returns:
            Dictionary with validation result and message
        """
        return trade_validation_repository.validate_security(security_name)

    def create(
        self,
        cf_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[int], Optional[str]]:
        """
        Create a new cash flow.

        Args:
            cf_data: Dictionary of cash flow fields
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, cf_id, error_message)
        """
        try:
            # Validate required fields
            required_fields = ['portfolio_short_name', 'cash_flow_type', 'value_date', 'payment_date', 'local_ccy']
            for field in required_fields:
                if not cf_data.get(field):
                    return False, None, f"{field.replace('_', ' ').title()} is required"

            # Validate portfolio
            portfolio_validation = self.validate_portfolio(cf_data['portfolio_short_name'])
            if not portfolio_validation.get('valid', False):
                return False, None, portfolio_validation.get('message', 'Invalid portfolio')

            # Validate security if provided
            if cf_data.get('security_name'):
                security_validation = self.validate_security(cf_data['security_name'])
                if not security_validation.get('valid', False):
                    return False, None, security_validation.get('message', 'Invalid security')

            # Generate CF number if not provided
            if not cf_data.get('cash_flow_number'):
                cf_data['cash_flow_number'] = self.repository.generate_cash_flow_number()

            # Check for duplicate CF number
            existing = self.repository.get_by_cash_flow_number(cf_data['cash_flow_number'])
            if existing:
                return False, None, f"Cash Flow with number '{cf_data['cash_flow_number']}' already exists"

            # Set initial status
            cf_data['status'] = self.STATUS_INITIAL

            # Insert cash flow
            success, cf_id = self.repository.insert(cf_data, created_by=username)

            if not success:
                return False, None, "Failed to create cash flow in database"

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf_data.get('cash_flow_number', ''),
                portfolio_short_name=cf_data.get('portfolio_short_name', ''),
                action='CREATE',
                status=self.STATUS_INITIAL,
                changes={'created': True},
                comments=f'Cash flow created by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='CREATE',
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf_data.get('cash_flow_number', ''),
                action_description=f'Created cash flow: {cf_data.get("cash_flow_number")} for portfolio {cf_data.get("portfolio_short_name")}',
                status='SUCCESS'
            )

            return True, cf_id, None

        except Exception as e:
            logger.error(f"Error creating cash flow: {str(e)}")
            return False, None, str(e)

    def update(
        self,
        cf_id: int,
        cf_data: Dict[str, Any],
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Update an existing cash flow.
        Status changes to MODIFIED after edit (if was INITIAL or APPROVED).

        Args:
            cf_id: Cash Flow ID
            cf_data: Dictionary of fields to update
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get existing cash flow
            cf = self.repository.get_by_id(cf_id)
            if not cf:
                return False, f"Cash flow {cf_id} not found"

            # Only CIS src_system records can be edited
            src_system = cf.get('src_system', '')
            if src_system and src_system.upper() != 'CIS':
                return False, f"Cannot edit cash flow with source system '{src_system}'. Only CIS records can be edited."

            # Validate portfolio if changed
            if cf_data.get('portfolio_short_name') and cf_data['portfolio_short_name'] != cf.get('portfolio_short_name'):
                portfolio_validation = self.validate_portfolio(cf_data['portfolio_short_name'])
                if not portfolio_validation.get('valid', False):
                    return False, portfolio_validation.get('message', 'Invalid portfolio')

            # Validate security if changed
            if cf_data.get('security_name') and cf_data['security_name'] != cf.get('security_name'):
                security_validation = self.validate_security(cf_data['security_name'])
                if not security_validation.get('valid', False):
                    return False, security_validation.get('message', 'Invalid security')

            # Track changes
            changes = {}
            for field, new_value in cf_data.items():
                old_value = cf.get(field)
                if old_value != new_value:
                    changes[field] = {'old': old_value, 'new': new_value}

            if not changes:
                return False, "No changes to update"

            # Set status to MODIFIED after edit
            cf_data['status'] = self.STATUS_MODIFIED

            # Update cash flow
            success = self.repository.update(
                cash_flow_id=cf_id,
                cf_data=cf_data,
                updated_by=username
            )

            if not success:
                return False, "Failed to update cash flow in database"

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf.get('cash_flow_number', ''),
                portfolio_short_name=cf.get('portfolio_short_name', ''),
                action='UPDATE',
                status=self.STATUS_MODIFIED,
                changes=changes,
                comments=f'Cash flow updated by {username}',
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
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf.get('cash_flow_number', ''),
                action_description=f'Updated cash flow: {cf.get("cf_number")} - Changed fields: {", ".join(changed_fields)}',
                old_value=json.dumps(old_values, default=str),
                new_value=json.dumps(new_values, default=str),
                field_name=', '.join(changed_fields),
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error updating cash flow {cf_id}: {str(e)}")
            return False, str(e)

    def approve(
        self,
        cf_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Approve cash flow (Checker action).
        INITIAL/MODIFIED → APPROVED

        Args:
            cf_id: Cash Flow ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Approval comments

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get cash flow
            cf = self.repository.get_by_id(cf_id)
            if not cf:
                return False, f"Cash flow {cf_id} not found"

            # Validate status
            current_status = cf.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                return False, f"Cannot approve cash flow with status {current_status}. Only INITIAL or MODIFIED can be approved."

            # Four-Eyes check: approver cannot be the creator
            created_by = cf.get('created_by', '')
            if created_by == username:
                return False, "You cannot approve your own cash flow (Four-Eyes principle)"

            # Update status to APPROVED
            success = self.repository.update_status(
                cf_id=cf_id,
                status=self.STATUS_APPROVED,
                updated_by=username,
                reviewed_comments=comments
            )

            if not success:
                return False, "Failed to approve cash flow"

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf.get('cash_flow_number', ''),
                portfolio_short_name=cf.get('portfolio_short_name', ''),
                action='APPROVE',
                status=self.STATUS_APPROVED,
                changes={'status': {'old': current_status, 'new': self.STATUS_APPROVED}},
                comments=comments or f'Approved by {username}',
                performed_by=username
            )

            # Log to audit
            AuditLogKuduRepository.log_action(
                user_id=user_id,
                username=username,
                user_email=user_email,
                action_type='APPROVE',
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf.get('cash_flow_number', ''),
                action_description=f'Approved cash flow: {cf.get("cf_number")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error approving cash flow {cf_id}: {str(e)}")
            return False, str(e)

    def reject(
        self,
        cf_id: int,
        user_id: str,
        username: str,
        user_email: str,
        comments: str = ''
    ) -> tuple[bool, Optional[str]]:
        """
        Reject cash flow (Checker action).
        INITIAL/MODIFIED → REJECTED

        Args:
            cf_id: Cash Flow ID
            user_id: User ID
            username: Username
            user_email: User email
            comments: Rejection comments

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get cash flow
            cf = self.repository.get_by_id(cf_id)
            if not cf:
                return False, f"Cash flow {cf_id} not found"

            # Validate status
            current_status = cf.get('status', '')
            if current_status not in [self.STATUS_INITIAL, self.STATUS_MODIFIED]:
                return False, f"Cannot reject cash flow with status {current_status}."

            # Four-Eyes check
            created_by = cf.get('created_by', '')
            if created_by == username:
                return False, "You cannot reject your own cash flow (Four-Eyes principle)"

            # Update status to REJECTED
            success = self.repository.update_status(
                cf_id=cf_id,
                status=self.STATUS_REJECTED,
                updated_by=username,
                reviewed_comments=comments
            )

            if not success:
                return False, "Failed to reject cash flow"

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf.get('cash_flow_number', ''),
                portfolio_short_name=cf.get('portfolio_short_name', ''),
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
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf.get('cash_flow_number', ''),
                action_description=f'Rejected cash flow: {cf.get("cf_number")}',
                new_value=comments,
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error rejecting cash flow {cf_id}: {str(e)}")
            return False, str(e)

    def delete(
        self,
        cf_id: int,
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Soft delete a cash flow.

        Args:
            cf_id: Cash Flow ID
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Get cash flow
            cf = self.repository.get_by_id(cf_id)
            if not cf:
                return False, f"Cash flow {cf_id} not found"

            # Only CIS records can be deleted
            src_system = cf.get('src_system', '')
            if src_system and src_system.upper() != 'CIS':
                return False, f"Cannot delete cash flow with source system '{src_system}'."

            # Soft delete
            success = self.repository.soft_delete(cf_id, deleted_by=username)

            if not success:
                return False, "Failed to delete cash flow"

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf.get('cash_flow_number', ''),
                portfolio_short_name=cf.get('portfolio_short_name', ''),
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
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf.get('cash_flow_number', ''),
                action_description=f'Deleted cash flow: {cf.get("cf_number")}',
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error deleting cash flow {cf_id}: {str(e)}")
            return False, str(e)

    def restore(
        self,
        cf_id: int,
        user_id: str,
        username: str,
        user_email: str
    ) -> tuple[bool, Optional[str]]:
        """
        Restore a soft-deleted cash flow.

        Args:
            cf_id: Cash Flow ID
            user_id: User ID
            username: Username
            user_email: User email

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Restore
            success = self.repository.restore(cf_id, restored_by=username)

            if not success:
                return False, "Failed to restore cash flow"

            # Get restored record
            cf = self.repository.get_by_id(cf_id)

            # Insert history record
            self.repository.insert_history(
                cash_flow_id=cf_id,
                cash_flow_number=cf.get('cash_flow_number', '') if cf else '',
                portfolio_short_name=cf.get('portfolio_short_name', '') if cf else '',
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
                entity_type='CASH_FLOW',
                entity_id=str(cf_id),
                entity_name=cf.get('cash_flow_number', '') if cf else '',
                action_description=f'Restored cash flow: {cf.get("cf_number") if cf else cf_id}',
                status='SUCCESS'
            )

            return True, None

        except Exception as e:
            logger.error(f"Error restoring cash flow {cf_id}: {str(e)}")
            return False, str(e)

    def get_history(self, cf_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history for a cash flow.

        Args:
            cf_id: Cash Flow ID
            limit: Maximum records

        Returns:
            List of history records
        """
        return self.repository.get_history(cf_id, limit=limit)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get cash flow statistics.

        Returns:
            Dictionary of statistics
        """
        return self.repository.get_statistics()

    def can_user_edit(self, cf: Dict[str, Any], username: str) -> bool:
        """
        Check if user can edit a cash flow.

        Args:
            cf: Cash flow dictionary
            username: Username

        Returns:
            True if user can edit
        """
        if not cf:
            return False

        # Only CIS records can be edited
        src_system = cf.get('src_system', '')
        if src_system and src_system.upper() != 'CIS':
            return False

        # Can edit INITIAL, MODIFIED, REJECTED status
        status = cf.get('status', '')
        return status in [self.STATUS_INITIAL, self.STATUS_MODIFIED, self.STATUS_REJECTED]

    def can_user_approve(self, cf: Dict[str, Any], username: str) -> bool:
        """
        Check if user can approve a cash flow.

        Args:
            cf: Cash flow dictionary
            username: Username

        Returns:
            True if user can approve
        """
        if not cf:
            return False

        # Can approve if status is INITIAL or MODIFIED and user is not the creator
        status = cf.get('status', '')
        created_by = cf.get('created_by', '')

        return status in [self.STATUS_INITIAL, self.STATUS_MODIFIED] and created_by != username

    @staticmethod
    def get_status_display_color(status: str) -> str:
        """
        Get Bootstrap color class for status badge.

        Args:
            status: Cash flow status

        Returns:
            Bootstrap color class
        """
        colors = {
            'INITIAL': 'secondary',
            'MODIFIED': 'info',
            'APPROVED': 'success',
            'REJECTED': 'danger',
        }
        return colors.get(status, 'secondary')


# Create singleton instance
cash_flow_service = CashFlowService()
