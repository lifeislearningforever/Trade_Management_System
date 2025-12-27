"""
Portfolio Service
Business logic for Portfolio operations following SOLID principles.

SOLID Principles Applied:
- Single Responsibility: Each method has one clear purpose
- Open/Closed: Extensible for new workflow states
- Liskov Substitution: Service layer can be substituted
- Interface Segregation: Clean service interface
- Dependency Inversion: Depends on abstractions (models), not concrete implementations
"""

from typing import List, Dict, Optional
from django.db.models import Q, QuerySet
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import User

from portfolio.models import Portfolio, PortfolioHistory
from core.models import AuditLog
from core.audit.audit_kudu_repository import audit_log_kudu_repository


class PortfolioService:
    """
    Service for Portfolio business logic.

    Handles:
    - Portfolio CRUD operations
    - Four-Eyes workflow (Maker-Checker)
    - Status transitions
    - Audit logging
    """

    @staticmethod
    def create_portfolio(user: User, data: Dict) -> Portfolio:
        """
        Create a new portfolio in DRAFT status.

        Args:
            user: User creating the portfolio
            data: Portfolio data dictionary

        Returns:
            Created Portfolio instance

        Raises:
            ValidationError: If data is invalid
        """
        # Validate required fields
        required_fields = ['code', 'name', 'currency', 'manager']
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"{field} is required")

        # Check for duplicate code
        if Portfolio.objects.filter(code=data['code']).exists():
            raise ValidationError(f"Portfolio with code {data['code']} already exists")

        # Create portfolio
        portfolio = Portfolio.objects.create(
            code=data['code'],
            name=data['name'],
            action_description=data.get('description', ''),
            currency=data['currency'],
            manager=data['manager'],
            portfolio_client=data.get('portfolio_client', ''),
            cash_balance=data.get('cash_balance', 0),
            cost_centre_code=data.get('cost_centre_code', ''),
            corp_code=data.get('corp_code', ''),
            account_group=data.get('account_group', ''),
            portfolio_group=data.get('portfolio_group', ''),
            report_group=data.get('report_group', ''),
            entity_group=data.get('entity_group', ''),
            status='DRAFT',
            is_active=False,
            created_by=user,
            updated_by=user
        )

        # Log creation to Kudu
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            user_email=user.email or '',
            action_type='CREATE',
            entity_type='PORTFOLIO',
            entity_id=str(portfolio.id),
            entity_name=portfolio.code,
            action_description=f"Created portfolio {portfolio.code}: {portfolio.name}",
            request_method='POST',
            status='SUCCESS'
        )

        return portfolio

    @staticmethod
    def update_portfolio(portfolio: Portfolio, user: User, data: Dict) -> Portfolio:
        """
        Update portfolio (only allowed in DRAFT or REJECTED status).

        Args:
            portfolio: Portfolio instance to update
            user: User performing the update
            data: Updated data dictionary

        Returns:
            Updated Portfolio instance

        Raises:
            PermissionDenied: If portfolio is not editable
            ValidationError: If data is invalid
        """
        # Check if editable
        if portfolio.status not in ['DRAFT', 'REJECTED']:
            raise PermissionDenied(
                f"Portfolio in {portfolio.status} status cannot be edited. "
                "Only DRAFT and REJECTED portfolios can be modified."
            )

        # Track changes
        changes = []

        # Update fields
        editable_fields = [
            'name', 'description', 'currency', 'manager', 'portfolio_client',
            'cash_balance', 'cost_centre_code', 'corp_code', 'account_group',
            'portfolio_group', 'report_group', 'entity_group'
        ]

        for field in editable_fields:
            if field in data:
                old_value = getattr(portfolio, field)
                new_value = data[field]
                if old_value != new_value:
                    changes.append(f"{field}: {old_value} → {new_value}")
                    setattr(portfolio, field, new_value)

        portfolio.updated_by = user
        portfolio.save()

        # Log update
        if changes:
            audit_log_kudu_repository.log_action(
                user_id=str(user.id),
                username=user.username,
                user_email=user.email or '',
                action_type='UPDATE',
                entity_type='PORTFOLIO',
                entity_id=str(portfolio.id),
                entity_name=portfolio.code,
                action_description=f"Updated portfolio {portfolio.code}: {'; '.join(changes)}",
                request_method='POST',
                status='SUCCESS'
            )

        return portfolio

    @staticmethod
    def submit_for_approval(portfolio: Portfolio, user: User) -> Portfolio:
        """
        Submit portfolio for approval (Maker action).

        Args:
            portfolio: Portfolio to submit
            user: User submitting (must be creator or maker)

        Returns:
            Updated Portfolio instance

        Raises:
            PermissionDenied: If user is not authorized
            ValidationError: If portfolio is not in correct status
        """
        # Validate status
        if portfolio.status != 'DRAFT':
            raise ValidationError(
                f"Only DRAFT portfolios can be submitted. Current status: {portfolio.status}"
            )

        # Submit for approval
        portfolio.submit_for_approval(user)

        # Log submission
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            user_email=user.email or '',
            action_type='SUBMIT',
            entity_type='PORTFOLIO',
            entity_id=str(portfolio.id),
            entity_name=portfolio.code,
            action_description=f"Submitted portfolio {portfolio.code} for approval",
            request_method='POST',
            status='SUCCESS'
        )

        return portfolio

    @staticmethod
    def approve_portfolio(portfolio: Portfolio, user: User, comments: str = '') -> Portfolio:
        """
        Approve portfolio (Checker action - Four-Eyes).

        Args:
            portfolio: Portfolio to approve
            user: User approving (must be different from creator)
            comments: Approval comments

        Returns:
            Approved Portfolio instance

        Raises:
            PermissionDenied: If user is not authorized
            ValidationError: If Four-Eyes principle violated
        """
        # Validate status
        if portfolio.status != 'PENDING_APPROVAL':
            raise ValidationError(
                f"Only PENDING_APPROVAL portfolios can be approved. Current status: {portfolio.status}"
            )

        # Approve (Four-Eyes validation is in model)
        portfolio.approve(user, comments)

        # Log approval
        comment_text = f" - {comments}" if comments else ""
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            user_email=user.email or '',
            action_type='APPROVE',
            entity_type='PORTFOLIO',
            entity_id=str(portfolio.id),
            entity_name=portfolio.code,
            action_description=f"Approved portfolio {portfolio.code}{comment_text}",
            request_method='POST',
            status='SUCCESS'
        )

        return portfolio

    @staticmethod
    def reject_portfolio(portfolio: Portfolio, user: User, comments: str) -> Portfolio:
        """
        Reject portfolio (Checker action).

        Args:
            portfolio: Portfolio to reject
            user: User rejecting
            comments: Rejection reason (required)

        Returns:
            Rejected Portfolio instance

        Raises:
            PermissionDenied: If user is not authorized
            ValidationError: If comments not provided
        """
        # Validate status
        if portfolio.status != 'PENDING_APPROVAL':
            raise ValidationError(
                f"Only PENDING_APPROVAL portfolios can be rejected. Current status: {portfolio.status}"
            )

        # Validate comments
        if not comments or not comments.strip():
            raise ValidationError("Rejection comments are required")

        # Reject
        portfolio.reject(user, comments)

        # Log rejection
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            user_email=user.email or '',
            action_type='REJECT',
            entity_type='PORTFOLIO',
            entity_id=str(portfolio.id),
            entity_name=portfolio.code,
            action_description=f"Rejected portfolio {portfolio.code} - Reason: {comments}",
            request_method='POST',
            status='SUCCESS'
        )

        return portfolio

    @staticmethod
    def close_portfolio(portfolio_code: str, user_id: str, username: str, user_email: str, reason: str = '') -> bool:
        """
        Close an active portfolio (soft delete) - Kudu/Impala only.

        Args:
            portfolio_code: Portfolio code to close
            user_id: User ID closing the portfolio
            username: Username
            user_email: User email
            reason: Closure reason (optional but recommended)

        Returns:
            True if successful

        Raises:
            ValidationError: If portfolio cannot be closed
        """
        from portfolio.repositories.portfolio_hive_repository import portfolio_hive_repository

        # Get portfolio from Kudu
        portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_code)

        if not portfolio:
            raise ValidationError(f"Portfolio {portfolio_code} not found")

        # Validate status
        current_status = portfolio.get('status', '')
        if current_status != 'Active':
            raise ValidationError(
                f"Only Active portfolios can be closed. Current status: {current_status}"
            )

        # Store old values for history
        old_status = current_status
        old_is_active = portfolio.get('is_active', True)

        # Update portfolio in Kudu
        success = portfolio_hive_repository.update_portfolio_status(
            portfolio_code=portfolio_code,
            status='Inactive',
            is_active=False,
            updated_by=username
        )

        if not success:
            raise ValidationError(f"Failed to update portfolio {portfolio_code} in Kudu")

        # Insert history record into Kudu
        portfolio_hive_repository.insert_portfolio_history(
            portfolio_code=portfolio_code,
            action='CLOSE',
            status='Inactive',
            changes={
                'status': {'old': old_status, 'new': 'Inactive'},
                'is_active': {'old': old_is_active, 'new': False},
                'reason': reason
            },
            comments=reason,
            performed_by=username
        )

        # Log to Kudu audit
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='CLOSE',
            entity_type='PORTFOLIO',
            entity_id=portfolio_code,
            entity_name=portfolio_code,
            action_description=f"Closed portfolio {portfolio_code}" + (f" - Reason: {reason}" if reason else ""),
            request_method='POST',
            status='SUCCESS'
        )

        return True

    @staticmethod
    def reactivate_portfolio(portfolio_code: str, user_id: str, username: str, user_email: str, comments: str) -> bool:
        """
        Reactivate a closed portfolio - Kudu/Impala only.

        Args:
            portfolio_code: Portfolio code to reactivate
            user_id: User ID reactivating the portfolio
            username: Username
            user_email: User email
            comments: Reactivation justification/comments (required)

        Returns:
            True if successful

        Raises:
            ValidationError: If portfolio cannot be reactivated or comments missing
        """
        from portfolio.repositories.portfolio_hive_repository import portfolio_hive_repository

        # Validate comments
        if not comments or not comments.strip():
            raise ValidationError("Reactivation comments/justification are required")

        # Get portfolio from Kudu
        portfolio = portfolio_hive_repository.get_portfolio_by_code(portfolio_code)

        if not portfolio:
            raise ValidationError(f"Portfolio {portfolio_code} not found")

        # Validate status
        current_status = portfolio.get('status', '')
        if current_status != 'Inactive':
            raise ValidationError(
                f"Only Inactive portfolios can be reactivated. Current status: {current_status}"
            )

        # Store old values for history
        old_status = current_status
        old_is_active = portfolio.get('is_active', False)

        # Update portfolio in Kudu
        success = portfolio_hive_repository.update_portfolio_status(
            portfolio_code=portfolio_code,
            status='Active',
            is_active=True,
            updated_by=username
        )

        if not success:
            raise ValidationError(f"Failed to update portfolio {portfolio_code} in Kudu")

        # Insert history record into Kudu
        portfolio_hive_repository.insert_portfolio_history(
            portfolio_code=portfolio_code,
            action='REACTIVATE',
            status='Active',
            changes={
                'status': {'old': old_status, 'new': 'Active'},
                'is_active': {'old': old_is_active, 'new': True},
                'reason': comments
            },
            comments=comments,
            performed_by=username
        )

        # Log to Kudu audit
        audit_log_kudu_repository.log_action(
            user_id=user_id,
            username=username,
            user_email=user_email,
            action_type='REACTIVATE',
            entity_type='PORTFOLIO',
            entity_id=portfolio_code,
            entity_name=portfolio_code,
            action_description=f"Reactivated portfolio {portfolio_code} - Reason: {comments}",
            request_method='POST',
            status='SUCCESS'
        )

        return True

    @staticmethod
    def get_portfolio_by_id(portfolio_id: int) -> Optional[Portfolio]:
        """Get portfolio by ID."""
        try:
            return Portfolio.objects.select_related(
                'created_by', 'updated_by', 'submitted_by', 'approved_by'
            ).get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return None

    @staticmethod
    def get_portfolio_by_code(code: str) -> Optional[Portfolio]:
        """Get portfolio by code."""
        try:
            return Portfolio.objects.select_related(
                'created_by', 'updated_by'
            ).get(code=code)
        except Portfolio.DoesNotExist:
            return None

    @staticmethod
    def list_portfolios(
        status: Optional[str] = None,
        search: Optional[str] = None,
        currency: Optional[str] = None,
        created_by: Optional[User] = None
    ) -> QuerySet:
        """
        List portfolios with optional filtering.

        Args:
            status: Filter by status
            search: Search in code, name, manager
            currency: Filter by currency
            created_by: Filter by creator

        Returns:
            QuerySet of portfolios
        """
        queryset = Portfolio.objects.select_related(
            'created_by', 'updated_by', 'submitted_by', 'approved_by'
        ).order_by('-created_at')

        if status:
            queryset = queryset.filter(status=status)

        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) |
                Q(name__icontains=search) |
                Q(manager__icontains=search)
            )

        if currency:
            queryset = queryset.filter(currency=currency)

        if created_by:
            queryset = queryset.filter(created_by=created_by)

        return queryset

    @staticmethod
    def get_pending_approvals() -> QuerySet:
        """Get all portfolios pending approval."""
        return Portfolio.objects.filter(
            status='PENDING_APPROVAL'
        ).select_related(
            'created_by', 'submitted_by'
        ).order_by('-submitted_for_approval_at')

    @staticmethod
    def get_portfolio_history(portfolio: Portfolio) -> QuerySet:
        """Get change history for a portfolio."""
        return PortfolioHistory.objects.filter(
            portfolio=portfolio
        ).select_related('changed_by').order_by('-changed_at')

    @staticmethod
    def can_user_edit(portfolio: Portfolio, user: User) -> bool:
        """Check if user can edit the portfolio."""
        # Only creator can edit, and only in DRAFT or REJECTED status
        return (
            portfolio.created_by == user and
            portfolio.status in ['DRAFT', 'REJECTED']
        )

    @staticmethod
    def can_user_approve(portfolio: Portfolio, user: User) -> bool:
        """Check if user can approve the portfolio (Four-Eyes check)."""
        # Must be in PENDING_APPROVAL status
        # User must not be the creator (Four-Eyes principle)
        # User must be in Checkers group
        return (
            portfolio.status == 'PENDING_APPROVAL' and
            portfolio.created_by != user and
            user.groups.filter(name='Checkers').exists()
        )

    @staticmethod
    def can_user_close(portfolio_status: str, user: User) -> bool:
        """
        Check if user can close the portfolio.

        Args:
            portfolio_status: Current portfolio status from Kudu
            user: Django user object

        Returns:
            True if user can close
        """
        # DEV MODE: Allow all users to close Active portfolios
        return portfolio_status == 'Active'

        # PRODUCTION: Uncomment below to enforce permissions
        # return (
        #     portfolio_status == 'Active' and
        #     (user.has_perm('portfolio.close_portfolio') or user.is_superuser)
        # )

    @staticmethod
    def can_user_reactivate(portfolio_status: str, user: User) -> bool:
        """
        Check if user can reactivate the portfolio.

        Args:
            portfolio_status: Current portfolio status from Kudu
            user: Django user object

        Returns:
            True if user can reactivate
        """
        # DEV MODE: Allow all users to reactivate Inactive portfolios
        return portfolio_status == 'Inactive'

        # PRODUCTION: Uncomment below to enforce permissions
        # return (
        #     portfolio_status == 'Inactive' and
        #     (user.has_perm('portfolio.reactivate_portfolio') or user.is_superuser)
        # )
