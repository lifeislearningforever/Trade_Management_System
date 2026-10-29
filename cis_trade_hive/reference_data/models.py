"""
Reference Data Models

These models are primarily for display purposes.
Actual data is stored in Kudu/Impala and accessed via services.
SQLite models are used for caching and development.
"""

from django.db import models
from django.core.validators import MinLengthValidator, RegexValidator
from core.models import BaseModel


class Currency(BaseModel):
    """Currency reference data"""

    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[RegexValidator(r'^[A-Z]{3}$', 'Must be 3 uppercase letters')],
        help_text="ISO 4217 currency code (e.g., USD, EUR, SGD)"
    )
    name = models.CharField(max_length=100, help_text="Currency name")
    full_name = models.CharField(max_length=200, blank=True)
    symbol = models.CharField(max_length=10, blank=True, help_text="Currency symbol")

    # Numeric details
    decimal_places = models.IntegerField(default=2)
    rate_precision = models.IntegerField(default=6)

    # Calendar and scheduling
    calendar = models.CharField(max_length=50, blank=True)
    spot_schedule = models.CharField(max_length=50, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_base_currency = models.BooleanField(default=False)

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reference_currency'
        ordering = ['code']
        verbose_name = 'Currency'
        verbose_name_plural = 'Currencies'

    def __str__(self):
        return f"{self.code} - {self.name}"


class Country(BaseModel):
    """Country reference data"""

    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="ISO country code"
    )
    name = models.CharField(max_length=100)
    full_name = models.CharField(max_length=200, blank=True)

    # Geographic
    region = models.CharField(max_length=100, blank=True)
    continent = models.CharField(max_length=50, blank=True)

    # Currency
    currency_code = models.CharField(max_length=3, blank=True)

    # Status
    is_active = models.BooleanField(default=True)

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reference_country'
        ordering = ['name']
        verbose_name = 'Country'
        verbose_name_plural = 'Countries'

    def __str__(self):
        return f"{self.code} - {self.name}"


class Calendar(BaseModel):
    """Trading calendar and holidays"""

    calendar_label = models.CharField(max_length=50, db_index=True)
    calendar_description = models.CharField(max_length=200, blank=True)
    holiday_date = models.DateField(db_index=True)

    # Holiday details
    holiday_name = models.CharField(max_length=200, blank=True)
    holiday_type = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('PUBLIC', 'Public Holiday'),
            ('TRADING', 'Trading Holiday'),
            ('SETTLEMENT', 'Settlement Holiday'),
        ]
    )

    # Trading hours
    is_trading_day = models.BooleanField(default=True)
    is_settlement_day = models.BooleanField(default=True)
    market_open_time = models.TimeField(null=True, blank=True)
    market_close_time = models.TimeField(null=True, blank=True)
    is_half_day = models.BooleanField(default=False)

    # Exchange
    exchange = models.CharField(
        max_length=50,
        default='SGX',
        choices=[
            ('SGX', 'Singapore Exchange'),
            ('NYSE', 'New York Stock Exchange'),
            ('NASDAQ', 'NASDAQ'),
            ('LSE', 'London Stock Exchange'),
            ('HKEX', 'Hong Kong Exchange'),
        ]
    )

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reference_calendar'
        ordering = ['-holiday_date']
        unique_together = [['calendar_label', 'holiday_date']]
        indexes = [
            models.Index(fields=['holiday_date', 'exchange']),
        ]
        verbose_name = 'Trading Calendar'
        verbose_name_plural = 'Trading Calendars'

    def __str__(self):
        return f"{self.calendar_label} - {self.holiday_date}"


class Counterparty(BaseModel):
    """Counterparty/Client reference data"""

    code = models.CharField(
        max_length=50,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="Unique counterparty code"
    )
    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=300, blank=True)
    short_name = models.CharField(max_length=100, blank=True)

    # Type
    counterparty_type = models.CharField(
        max_length=50,
        choices=[
            ('BANK', 'Bank'),
            ('BROKER', 'Broker'),
            ('CORPORATE', 'Corporate'),
            ('INDIVIDUAL', 'Individual'),
            ('INSTITUTIONAL', 'Institutional'),
            ('GOVERNMENT', 'Government'),
        ],
        default='CORPORATE'
    )

    # Contact Information
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    # Regulatory
    tax_id = models.CharField(max_length=50, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('INACTIVE', 'Inactive'),
            ('SUSPENDED', 'Suspended'),
            ('CLOSED', 'Closed'),
        ],
        default='ACTIVE'
    )
    is_active = models.BooleanField(default=True)

    # Risk
    risk_category = models.CharField(
        max_length=20,
        choices=[
            ('LOW', 'Low Risk'),
            ('MEDIUM', 'Medium Risk'),
            ('HIGH', 'High Risk'),
        ],
        default='MEDIUM',
        blank=True
    )
    credit_rating = models.CharField(max_length=20, blank=True)

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'reference_counterparty'
        ordering = ['name']
        verbose_name = 'Counterparty'
        verbose_name_plural = 'Counterparties'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['counterparty_type', 'status']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_display_name(self):
        """Returns name with code"""
        return f"{self.name} ({self.code})"
