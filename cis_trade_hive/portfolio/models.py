"""
Portfolio Models

Implements Four-Eyes Principle (Maker-Checker workflow):
1. Maker creates/modifies portfolio (status: PENDING)
2. Checker reviews and approves/rejects
3. Only APPROVED portfolios are active
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import BaseModel


class Portfolio(BaseModel):
    """
    Portfolio model with Four-Eyes principle.

    Workflow:
    - Maker creates portfolio → status = PENDING_APPROVAL
    - Checker approves → status = ACTIVE
    - Checker rejects → status = REJECTED
    """

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('ACTIVE', 'Active'),
        ('REJECTED', 'Rejected'),
        ('INACTIVE', 'Inactive'),
        ('CLOSED', 'Closed'),
    ]

    # Basic Information
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique portfolio code"
    )
    name = models.CharField(max_length=200, help_text="Portfolio name")
    description = models.TextField(blank=True)

    # Currency
    currency = models.CharField(max_length=3, help_text="Base currency (e.g., USD, SGD)")

    # Management
    manager = models.CharField(max_length=200, blank=True, help_text="Portfolio manager")
    portfolio_client = models.CharField(max_length=200, blank=True)

    # Financial
    cash_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0,
        help_text="Current cash balance"
    )
    cash_balance_list = models.CharField(max_length=200, blank=True)

    # Classification
    cost_centre_code = models.CharField(max_length=50, blank=True)
    corp_code = models.CharField(max_length=50, blank=True)
    account_group = models.CharField(max_length=100, blank=True)
    portfolio_group = models.CharField(max_length=100, blank=True)
    report_group = models.CharField(max_length=100, blank=True)
    entity_group = models.CharField(max_length=100, blank=True)

    # Revaluation
    revaluation_status = models.CharField(max_length=50, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    is_active = models.BooleanField(default=False)

    # Four-Eyes Principle Fields
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portfolios_submitted'
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portfolios_reviewed'
    )
    review_comments = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'portfolio'
        ordering = ['-created_at']
        verbose_name = 'Portfolio'
        verbose_name_plural = 'Portfolios'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['currency']),
        ]
        permissions = [
            ('approve_portfolio', 'Can approve portfolio'),
            ('reject_portfolio', 'Can reject portfolio'),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """Validation rules"""
        # Four-Eyes: Reviewer cannot be the same as creator
        if self.reviewed_by and self.created_by:
            if self.reviewed_by == self.created_by:
                raise ValidationError('Reviewer cannot be the same as the creator (Four-Eyes principle)')

    def submit_for_approval(self, user):
        """Submit portfolio for approval"""
        if self.status not in ['DRAFT', 'REJECTED']:
            raise ValidationError('Only DRAFT or REJECTED portfolios can be submitted for approval')

        self.status = 'PENDING_APPROVAL'
        self.submitted_for_approval_at = timezone.now()
        self.submitted_by = user
        self.save()

    def approve(self, user, comments=''):
        """Approve portfolio (Checker action)"""
        if self.status != 'PENDING_APPROVAL':
            raise ValidationError('Only PENDING_APPROVAL portfolios can be approved')

        # Four-Eyes check
        if user == self.created_by:
            raise ValidationError('You cannot approve your own portfolio (Four-Eyes principle)')

        self.status = 'APPROVED'
        self.is_active = True
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.review_comments = comments
        self.save()

    def reject(self, user, comments=''):
        """Reject portfolio (Checker action)"""
        if self.status != 'PENDING_APPROVAL':
            raise ValidationError('Only PENDING_APPROVAL portfolios can be rejected')

        self.status = 'REJECTED'
        self.is_active = False
        self.reviewed_at = timezone.now()
        self.reviewed_by = user
        self.review_comments = comments
        self.save()

    def get_status_display_color(self):
        """Get Bootstrap color class for status"""
        colors = {
            'DRAFT': 'secondary',
            'PENDING_APPROVAL': 'warning',
            'APPROVED': 'success',
            'ACTIVE': 'success',
            'REJECTED': 'danger',
            'INACTIVE': 'secondary',
            'CLOSED': 'dark',
        }
        return colors.get(self.status, 'secondary')


class PortfolioHistory(BaseModel):
    """
    Tracks all changes to portfolios.
    Automatically created on portfolio save.
    """

    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name='history'
    )
    action = models.CharField(
        max_length=20,
        choices=[
            ('CREATE', 'Created'),
            ('UPDATE', 'Updated'),
            ('SUBMIT', 'Submitted for Approval'),
            ('APPROVE', 'Approved'),
            ('REJECT', 'Rejected'),
            ('ACTIVATE', 'Activated'),
            ('DEACTIVATE', 'Deactivated'),
        ]
    )
    status = models.CharField(max_length=20)
    changes = models.JSONField(default=dict)
    comments = models.TextField(blank=True)

    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='portfolio_history_actions'
    )

    class Meta:
        db_table = 'portfolio_history'
        ordering = ['-created_at']
        verbose_name = 'Portfolio History'
        verbose_name_plural = 'Portfolio Histories'

    def __str__(self):
        return f"{self.portfolio.code} - {self.action} - {self.created_at}"
