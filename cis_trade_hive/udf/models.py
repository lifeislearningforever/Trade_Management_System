"""
UDF (User-Defined Fields) Models

Allows dynamic field definitions for portfolios and other entities.
Supports multiple data types and validation rules.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from core.models import BaseModel


class UDF(BaseModel):
    """
    User-Defined Field definition.

    Defines custom fields that can be attached to various entities.
    """

    FIELD_TYPE_CHOICES = [
        ('TEXT', 'Text'),
        ('NUMBER', 'Number'),
        ('DATE', 'Date'),
        ('DATETIME', 'Date Time'),
        ('BOOLEAN', 'Boolean'),
        ('DROPDOWN', 'Dropdown'),
        ('MULTI_SELECT', 'Multi Select'),
        ('CURRENCY', 'Currency'),
        ('PERCENTAGE', 'Percentage'),
    ]

    ENTITY_TYPE_CHOICES = [
        ('PORTFOLIO', 'Portfolio'),
        ('TRADE', 'Trade'),
        ('POSITION', 'Position'),
        ('COUNTERPARTY', 'Counterparty'),
    ]

    # Basic Information
    field_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique field name (e.g., risk_rating, compliance_status)"
    )
    label = models.CharField(
        max_length=200,
        help_text="Display label for the field"
    )
    description = models.TextField(blank=True)

    # Type and Configuration
    field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPE_CHOICES,
        default='TEXT'
    )
    entity_type = models.CharField(
        max_length=50,
        choices=ENTITY_TYPE_CHOICES,
        default='PORTFOLIO',
        help_text="Entity this field applies to"
    )

    # Validation Rules
    is_required = models.BooleanField(default=False)
    is_unique = models.BooleanField(default=False)
    default_value = models.TextField(blank=True, null=True)

    # For DROPDOWN and MULTI_SELECT types
    dropdown_options = models.JSONField(
        blank=True,
        null=True,
        help_text="JSON array of dropdown options, e.g., ['High', 'Medium', 'Low']"
    )

    # For NUMBER and CURRENCY types
    min_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        blank=True,
        null=True
    )
    max_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        blank=True,
        null=True
    )

    # For TEXT type
    max_length = models.IntegerField(blank=True, null=True)

    # Display and Ordering
    display_order = models.IntegerField(default=0)
    group_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Group related fields together"
    )

    # Status
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'udf'
        ordering = ['entity_type', 'display_order', 'field_name']
        indexes = [
            models.Index(fields=['entity_type', 'is_active']),
            models.Index(fields=['field_name']),
        ]
        verbose_name = 'User-Defined Field'
        verbose_name_plural = 'User-Defined Fields'

    def __str__(self):
        return f"{self.entity_type} - {self.label}"

    def clean(self):
        """Validation rules."""
        # Validate dropdown options for DROPDOWN and MULTI_SELECT
        if self.field_type in ['DROPDOWN', 'MULTI_SELECT']:
            if not self.dropdown_options or not isinstance(self.dropdown_options, list):
                raise ValidationError('Dropdown options must be a non-empty list')

        # Validate min/max for NUMBER and CURRENCY
        if self.field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
            if self.min_value is not None and self.max_value is not None:
                if self.min_value > self.max_value:
                    raise ValidationError('Minimum value cannot be greater than maximum value')


class UDFValue(BaseModel):
    """
    Stores values for User-Defined Fields.

    Links UDF definitions to specific entity instances.
    """

    # Link to UDF definition
    udf = models.ForeignKey(
        UDF,
        on_delete=models.CASCADE,
        related_name='values'
    )

    # Entity reference (polymorphic)
    entity_type = models.CharField(max_length=50)
    entity_id = models.IntegerField(help_text="ID of the related entity")

    # Value storage (polymorphic - store all types as text/JSON)
    value_text = models.TextField(blank=True, null=True)
    value_number = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        blank=True,
        null=True
    )
    value_date = models.DateField(blank=True, null=True)
    value_datetime = models.DateTimeField(blank=True, null=True)
    value_boolean = models.BooleanField(blank=True, null=True)
    value_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = 'udf_value'
        unique_together = [['udf', 'entity_type', 'entity_id']]
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['udf', 'entity_type']),
        ]
        verbose_name = 'UDF Value'
        verbose_name_plural = 'UDF Values'

    def __str__(self):
        return f"{self.udf.field_name} for {self.entity_type}#{self.entity_id}"

    def get_value(self):
        """Get the appropriate value based on UDF field type."""
        field_type = self.udf.field_type

        if field_type == 'TEXT':
            return self.value_text
        elif field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
            return self.value_number
        elif field_type == 'DATE':
            return self.value_date
        elif field_type == 'DATETIME':
            return self.value_datetime
        elif field_type == 'BOOLEAN':
            return self.value_boolean
        elif field_type in ['DROPDOWN', 'MULTI_SELECT']:
            return self.value_json or self.value_text
        else:
            return self.value_text

    def set_value(self, value):
        """Set the appropriate value field based on UDF field type."""
        field_type = self.udf.field_type

        if field_type == 'TEXT':
            self.value_text = str(value) if value else None
        elif field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
            self.value_number = value
        elif field_type == 'DATE':
            self.value_date = value
        elif field_type == 'DATETIME':
            self.value_datetime = value
        elif field_type == 'BOOLEAN':
            self.value_boolean = bool(value)
        elif field_type in ['DROPDOWN', 'MULTI_SELECT']:
            if isinstance(value, (list, dict)):
                self.value_json = value
            else:
                self.value_text = str(value) if value else None

    def clean(self):
        """Validation rules."""
        # Ensure entity_type matches UDF
        if self.entity_type != self.udf.entity_type:
            raise ValidationError(
                f"Entity type mismatch: UDF is for {self.udf.entity_type}, "
                f"but value is for {self.entity_type}"
            )

        # Validate required fields
        if self.udf.is_required:
            value = self.get_value()
            if value is None or value == '':
                raise ValidationError(f"{self.udf.label} is required")

        # Validate dropdown options
        if self.udf.field_type == 'DROPDOWN' and self.value_text:
            if self.value_text not in self.udf.dropdown_options:
                raise ValidationError(
                    f"Invalid option. Must be one of: {', '.join(self.udf.dropdown_options)}"
                )

        # Validate min/max for numbers
        if self.udf.field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE'] and self.value_number:
            if self.udf.min_value and self.value_number < self.udf.min_value:
                raise ValidationError(f"Value must be at least {self.udf.min_value}")
            if self.udf.max_value and self.value_number > self.udf.max_value:
                raise ValidationError(f"Value must be at most {self.udf.max_value}")


class UDFHistory(BaseModel):
    """
    Tracks changes to UDF values for audit trail.
    """

    udf_value = models.ForeignKey(
        UDFValue,
        on_delete=models.CASCADE,
        related_name='history'
    )

    action = models.CharField(
        max_length=20,
        choices=[
            ('CREATE', 'Created'),
            ('UPDATE', 'Updated'),
            ('DELETE', 'Deleted'),
        ]
    )

    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='udf_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'udf_history'
        ordering = ['-changed_at']
        verbose_name = 'UDF History'
        verbose_name_plural = 'UDF Histories'

    def __str__(self):
        return f"{self.action} - {self.udf_value} at {self.changed_at}"
