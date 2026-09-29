"""
Core Models for CisTrade Application

Includes:
- AuditLog: Comprehensive audit logging for all system actions
- BaseModel: Abstract base model with common fields
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class BaseModel(models.Model):
    """
    Abstract base model with common timestamp fields.
    Following DRY principle.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        db_column='created_by_id'
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
        db_column='updated_by_id'
    )

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Comprehensive audit log for all system actions.

    Tracks:
    - User actions (create, read, update, delete)
    - System changes
    - Four-Eyes principle workflow (maker-checker)
    - ACL permission checks
    """

    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('READ', 'Read'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('ACCESS_DENIED', 'Access Denied'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]

    SEVERITY_CHOICES = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    # Audit Information
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, db_index=True)  # Stored for history even if user deleted

    # Action Details
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='INFO')

    # Object Details
    object_type = models.CharField(max_length=100, db_index=True)  # Model name
    object_id = models.CharField(max_length=100, db_index=True, blank=True)
    object_repr = models.CharField(max_length=500, blank=True)  # String representation

    # Change Details
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    changes = models.JSONField(null=True, blank=True)  # Dict of field changes

    # Request Details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    request_method = models.CharField(max_length=10, blank=True)

    # Additional Context
    description = models.TextField(blank=True)
    additional_data = models.JSONField(null=True, blank=True)

    # Four-Eyes Principle
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_audit_logs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
        ],
        default='PENDING',
        blank=True
    )

    class Meta:
        db_table = 'core_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'user']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['approval_status']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {self.username} | {self.action} | {self.object_type}"

    @classmethod
    def log_action(cls, action, user, object_type, object_id=None, object_repr='',
                   old_value=None, new_value=None, description='',
                   ip_address=None, user_agent='', request_path='', request_method='',
                   requires_approval=False, severity='INFO', additional_data=None):
        """
        Convenience method to create audit log entries.

        Usage:
            AuditLog.log_action(
                action='CREATE',
                user=request.user,
                object_type='Portfolio',
                object_id=portfolio.id,
                object_repr=str(portfolio),
                description='Created new portfolio'
            )
        """
        username = user.username if user and user.is_authenticated else 'anonymous'

        # Calculate changes if both old and new values provided
        changes = None
        if old_value and new_value and isinstance(old_value, dict) and isinstance(new_value, dict):
            changes = {
                key: {'old': old_value.get(key), 'new': new_value.get(key)}
                for key in set(old_value.keys()) | set(new_value.keys())
                if old_value.get(key) != new_value.get(key)
            }

        return cls.objects.create(
            user=user if user and user.is_authenticated else None,
            username=username,
            action=action,
            severity=severity,
            object_type=object_type,
            object_id=str(object_id) if object_id else '',
            object_repr=object_repr,
            old_value=old_value,
            new_value=new_value,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method,
            description=description,
            requires_approval=requires_approval,
            additional_data=additional_data,
        )

    def get_changes_display(self):
        """Get human-readable changes"""
        if not self.changes:
            return ''

        lines = []
        for field, change in self.changes.items():
            old = change.get('old', 'N/A')
            new = change.get('new', 'N/A')
            lines.append(f"{field}: {old} → {new}")
        return '\n'.join(lines)
