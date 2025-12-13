"""
User Defined Fields (UDF) Models
Provides flexible dropdown values for dynamic fields across the application
"""

from django.db import models
from django.core.validators import MinLengthValidator


class UDFType(models.Model):
    """
    Defines the main category of user-defined fields
    Examples: PORTFOLIO, TRADE, ORDER, REPORT
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="Unique code for UDF type (e.g., 'PORTFOLIO', 'TRADE')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name for the UDF type"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of this UDF type"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this UDF type is active"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Order for displaying in lists"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'udf_type'
        ordering = ['display_order', 'name']
        verbose_name = 'UDF Type'
        verbose_name_plural = 'UDF Types'

    def __str__(self):
        return f"{self.name} ({self.code})"


class UDFSubtype(models.Model):
    """
    Defines subcategories within a UDF type
    Examples: For PORTFOLIO type -> GROUP, SUBGROUP, MANAGER, STRATEGY
    """
    udf_type = models.ForeignKey(
        UDFType,
        on_delete=models.CASCADE,
        related_name='subtypes',
        help_text="Parent UDF type"
    )
    code = models.CharField(
        max_length=50,
        validators=[MinLengthValidator(2)],
        help_text="Unique code for UDF subtype (e.g., 'GROUP', 'MANAGER')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name for the UDF subtype"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of this UDF subtype"
    )
    field_label = models.CharField(
        max_length=100,
        help_text="Label to display on forms (e.g., 'Portfolio Group')"
    )
    is_required = models.BooleanField(
        default=False,
        help_text="Whether this field is required"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this UDF subtype is active"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Order for displaying in lists"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'udf_subtype'
        ordering = ['udf_type', 'display_order', 'name']
        unique_together = [['udf_type', 'code']]
        verbose_name = 'UDF Subtype'
        verbose_name_plural = 'UDF Subtypes'

    def __str__(self):
        return f"{self.udf_type.code}.{self.code} - {self.name}"


class UDFField(models.Model):
    """
    Defines the actual field values/options for dropdowns
    Examples: For PORTFOLIO.GROUP -> 'Equity', 'Fixed Income', 'Derivatives'
    """
    udf_subtype = models.ForeignKey(
        UDFSubtype,
        on_delete=models.CASCADE,
        related_name='fields',
        help_text="Parent UDF subtype"
    )
    code = models.CharField(
        max_length=50,
        validators=[MinLengthValidator(1)],
        help_text="Unique code for the field value"
    )
    value = models.CharField(
        max_length=200,
        help_text="Display value shown to users"
    )
    description = models.TextField(
        blank=True,
        help_text="Additional description or notes"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this field value is active/available"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default selection"
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Order for displaying in dropdown lists"
    )

    # Additional metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata as JSON"
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="User who created this field"
    )
    updated_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="User who last updated this field"
    )

    class Meta:
        db_table = 'udf_field'
        ordering = ['udf_subtype', 'display_order', 'value']
        unique_together = [['udf_subtype', 'code']]
        verbose_name = 'UDF Field'
        verbose_name_plural = 'UDF Fields'
        indexes = [
            models.Index(fields=['udf_subtype', 'is_active']),
            models.Index(fields=['is_default']),
        ]

    def __str__(self):
        return f"{self.udf_subtype.udf_type.code}.{self.udf_subtype.code}.{self.code} - {self.value}"

    def save(self, *args, **kwargs):
        # Ensure only one default per subtype
        if self.is_default:
            UDFField.objects.filter(
                udf_subtype=self.udf_subtype,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_fields(cls, udf_type_code, udf_subtype_code):
        """
        Get all active field values for a specific UDF type and subtype
        Usage: UDFField.get_active_fields('PORTFOLIO', 'GROUP')
        """
        return cls.objects.filter(
            udf_subtype__udf_type__code=udf_type_code,
            udf_subtype__code=udf_subtype_code,
            udf_subtype__is_active=True,
            udf_subtype__udf_type__is_active=True,
            is_active=True
        ).order_by('display_order', 'value')

    @classmethod
    def get_default_field(cls, udf_type_code, udf_subtype_code):
        """
        Get the default field value for a specific UDF type and subtype
        """
        try:
            return cls.objects.get(
                udf_subtype__udf_type__code=udf_type_code,
                udf_subtype__code=udf_subtype_code,
                is_default=True,
                is_active=True
            )
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_choices(cls, udf_type_code, udf_subtype_code, include_blank=False):
        """
        Get choices tuple for Django form fields
        Returns: [(code, value), (code, value), ...]
        """
        fields = cls.get_active_fields(udf_type_code, udf_subtype_code)
        choices = [(f.code, f.value) for f in fields]
        if include_blank:
            choices.insert(0, ('', '--- Select ---'))
        return choices
