"""
Reporting Models - Report Generation with UDF Integration
Integrates with UDF system for dynamic report types and categories
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Report(models.Model):
    """
    Report with UDF integration for dynamic report types
    """

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('GENERATING', 'Generating'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    FORMAT_CHOICES = [
        ('PDF', 'PDF'),
        ('EXCEL', 'Excel'),
        ('CSV', 'CSV'),
        ('JSON', 'JSON'),
    ]

    # Report Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_id = models.CharField(max_length=50, unique=True, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    # UDF Fields - Dynamic values from UDF system
    report_type = models.CharField(
        max_length=50,
        help_text="From UDF: REPORT.TYPE (e.g., PORTFOLIO_SUMMARY, TRADE_HISTORY, PNL_STATEMENT)"
    )
    report_category = models.CharField(
        max_length=50,
        blank=True,
        help_text="From UDF: REPORT.CATEGORY (e.g., DAILY, WEEKLY, MONTHLY, ANNUAL)"
    )
    report_format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default='PDF'
    )

    # Report Parameters
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional report parameters as JSON"
    )

    # Generation Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    file_path = models.CharField(max_length=500, blank=True, help_text="Path to generated file")
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    error_message = models.TextField(blank=True)

    # User & Timestamps
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='requested_reports'
    )
    requested_by_name = models.CharField(
        max_length=300,
        editable=False,
        help_text="Real name of requester (auto-filled)"
    )

    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'report'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['requested_by', 'status']),
            models.Index(fields=['report_type', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate report_id
        if not self.report_id:
            self.report_id = f"RPT-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Auto-fill requester real name
        if self.requested_by:
            self.requested_by_name = self.requested_by.get_display_name()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.report_id} - {self.title}"

    def mark_as_generating(self):
        """Mark report as being generated"""
        self.status = 'GENERATING'
        self.save()

    def mark_as_completed(self, file_path, file_size=None):
        """Mark report as completed"""
        self.status = 'COMPLETED'
        self.file_path = file_path
        self.file_size = file_size
        self.generated_at = timezone.now()
        self.save()

    def mark_as_failed(self, error_message):
        """Mark report as failed"""
        self.status = 'FAILED'
        self.error_message = error_message
        self.save()
