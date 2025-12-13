"""
Reference Data Models
Static reference tables for Currency, Brokers, Calendars, and Clients
Designed for ETL import from upstream systems
"""

from django.db import models
from django.core.validators import MinLengthValidator, RegexValidator


class Currency(models.Model):
    """Currency reference data"""
    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[RegexValidator(r'^[A-Z]{3}$', 'Must be 3 uppercase letters')],
        help_text="ISO 4217 currency code (e.g., 'USD', 'EUR', 'INR')"
    )
    name = models.CharField(max_length=100, help_text="Currency name")
    symbol = models.CharField(max_length=10, blank=True, help_text="Currency symbol (e.g., '$', '€', '₹')")
    country = models.CharField(max_length=100, blank=True, help_text="Primary country")
    decimal_places = models.IntegerField(default=2, help_text="Number of decimal places")
    is_active = models.BooleanField(default=True, help_text="Whether this currency is active")
    is_base_currency = models.BooleanField(default=False, help_text="Whether this is the base currency")

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True, help_text="Source system for ETL")
    source_id = models.CharField(max_length=100, blank=True, help_text="ID in source system")
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text="Last ETL sync timestamp")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'currency'
        ordering = ['code']
        verbose_name = 'Currency'
        verbose_name_plural = 'Currencies'

    def __str__(self):
        return f"{self.code} - {self.name}"


class Broker(models.Model):
    """Broker reference data"""
    code = models.CharField(
        max_length=50,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="Unique broker code"
    )
    name = models.CharField(max_length=200, help_text="Broker name")
    full_name = models.CharField(max_length=300, blank=True, help_text="Full legal name")
    broker_type = models.CharField(
        max_length=50,
        choices=[
            ('FULL_SERVICE', 'Full Service'),
            ('DISCOUNT', 'Discount'),
            ('DIRECT_MARKET_ACCESS', 'Direct Market Access'),
            ('INSTITUTIONAL', 'Institutional'),
        ],
        default='FULL_SERVICE'
    )

    # Contact Information
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='India')
    postal_code = models.CharField(max_length=20, blank=True)

    # Regulatory
    registration_number = models.CharField(max_length=100, blank=True, help_text="Registration/License number")
    sebi_registration = models.CharField(max_length=100, blank=True, help_text="SEBI registration number")

    # Status
    is_active = models.BooleanField(default=True)
    is_preferred = models.BooleanField(default=False, help_text="Preferred broker")

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'broker'
        ordering = ['name']
        verbose_name = 'Broker'
        verbose_name_plural = 'Brokers'

    def __str__(self):
        return f"{self.code} - {self.name}"


class TradingCalendar(models.Model):
    """Trading calendar and holidays"""
    date = models.DateField(db_index=True, help_text="Calendar date")
    exchange = models.CharField(
        max_length=50,
        default='NSE',
        choices=[
            ('NSE', 'National Stock Exchange'),
            ('BSE', 'Bombay Stock Exchange'),
            ('NYSE', 'New York Stock Exchange'),
            ('NASDAQ', 'NASDAQ'),
            ('LSE', 'London Stock Exchange'),
        ],
        help_text="Exchange name"
    )
    is_trading_day = models.BooleanField(default=True, help_text="Whether trading occurs")
    is_settlement_day = models.BooleanField(default=True, help_text="Whether settlement occurs")
    is_holiday = models.BooleanField(default=False, help_text="Whether it's a holiday")
    holiday_name = models.CharField(max_length=200, blank=True, help_text="Name of holiday")
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
    market_open_time = models.TimeField(null=True, blank=True)
    market_close_time = models.TimeField(null=True, blank=True)
    is_half_day = models.BooleanField(default=False)

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trading_calendar'
        ordering = ['-date']
        unique_together = [['date', 'exchange']]
        verbose_name = 'Trading Calendar'
        verbose_name_plural = 'Trading Calendars'
        indexes = [
            models.Index(fields=['date', 'exchange', 'is_trading_day']),
        ]

    def __str__(self):
        status = "Holiday" if self.is_holiday else "Trading Day"
        return f"{self.date} - {self.exchange} - {status}"


class Client(models.Model):
    """Client/Customer reference data"""
    client_id = models.CharField(
        max_length=50,
        unique=True,
        validators=[MinLengthValidator(2)],
        help_text="Unique client identifier"
    )
    client_type = models.CharField(
        max_length=20,
        choices=[
            ('INDIVIDUAL', 'Individual'),
            ('CORPORATE', 'Corporate'),
            ('HNI', 'High Net Worth Individual'),
            ('INSTITUTIONAL', 'Institutional'),
            ('PROPRIETARY', 'Proprietary'),
        ],
        default='INDIVIDUAL'
    )

    # Basic Information
    name = models.CharField(max_length=300, help_text="Client name")
    legal_name = models.CharField(max_length=300, blank=True, help_text="Legal/registered name")
    short_name = models.CharField(max_length=100, blank=True)

    # Contact Information
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='India')
    postal_code = models.CharField(max_length=20, blank=True)

    # Regulatory Information
    pan_number = models.CharField(max_length=10, blank=True, help_text="PAN number")
    tax_id = models.CharField(max_length=50, blank=True, help_text="Tax identification number")

    # Account Details
    account_number = models.CharField(max_length=50, blank=True)
    demat_account = models.CharField(max_length=50, blank=True, help_text="Demat account number")
    trading_account = models.CharField(max_length=50, blank=True)

    # Relationship
    relationship_manager = models.CharField(max_length=200, blank=True)
    account_opening_date = models.DateField(null=True, blank=True)
    account_closing_date = models.DateField(null=True, blank=True)

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
    kyc_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('VERIFIED', 'Verified'),
            ('REJECTED', 'Rejected'),
            ('EXPIRED', 'Expired'),
        ],
        default='PENDING'
    )

    # Risk Classification
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

    # ETL fields
    source_system = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=200, blank=True)
    updated_by = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'client'
        ordering = ['name']
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        indexes = [
            models.Index(fields=['client_id']),
            models.Index(fields=['client_type', 'status']),
            models.Index(fields=['pan_number']),
        ]

    def __str__(self):
        return f"{self.client_id} - {self.name}"

    def get_display_name(self):
        """Returns name with client ID"""
        return f"{self.name} ({self.client_id})"
