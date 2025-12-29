"""
Market Data Models

Implements FX Rate tracking with comprehensive data fields.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import BaseModel
from decimal import Decimal


class FXRate(BaseModel):
    """
    Foreign Exchange Rate model.

    Stores FX rates with bid/ask spreads and metadata.
    Supports historical rate tracking.
    """

    SOURCE_CHOICES = [
        ('BLOOMBERG', 'Bloomberg'),
        ('REUTERS', 'Reuters'),
        ('MANUAL', 'Manual Entry'),
        ('API', 'API Feed'),
        ('HIVE', 'Hive Import'),
    ]

    # Currency Pair Information
    currency_pair = models.CharField(
        max_length=10,
        db_index=True,
        help_text="Currency pair (e.g., USD/EUR, GBP/USD)"
    )
    base_currency = models.CharField(
        max_length=3,
        db_index=True,
        help_text="Base currency code (ISO 4217)"
    )
    quote_currency = models.CharField(
        max_length=3,
        db_index=True,
        help_text="Quote currency code (ISO 4217)"
    )

    # Rate Information
    rate = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        help_text="Exchange rate (up to 10 decimal places)"
    )
    bid_rate = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
        help_text="Bid rate (buy price)"
    )
    ask_rate = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
        help_text="Ask rate (sell price)"
    )
    mid_rate = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
        help_text="Mid rate ((bid + ask) / 2)"
    )

    # Temporal Information
    rate_date = models.DateField(
        db_index=True,
        help_text="Date of the rate"
    )
    rate_time = models.DateTimeField(
        db_index=True,
        help_text="Timestamp of the rate"
    )

    # Source and Status
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='MANUAL',
        db_index=True,
        help_text="Source of the rate"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this rate is currently active"
    )

    # Additional Information
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'market_data_fx_rate'
        ordering = ['-rate_date', '-rate_time']
        verbose_name = 'FX Rate'
        verbose_name_plural = 'FX Rates'
        indexes = [
            models.Index(fields=['currency_pair', '-rate_date']),
            models.Index(fields=['base_currency', 'quote_currency']),
            models.Index(fields=['rate_date', 'is_active']),
            models.Index(fields=['source', '-rate_time']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['currency_pair', 'rate_date', 'rate_time', 'source'],
                name='unique_fx_rate_per_source'
            )
        ]

    def __str__(self):
        return f"{self.currency_pair} @ {self.rate} ({self.rate_date})"

    def clean(self):
        """Validation rules"""
        super().clean()

        # Validate currency pair format
        if '/' not in self.currency_pair:
            raise ValidationError('Currency pair must be in format: BASE/QUOTE (e.g., USD/EUR)')

        # Auto-populate base and quote from currency_pair if not set
        if not self.base_currency or not self.quote_currency:
            parts = self.currency_pair.split('/')
            if len(parts) == 2:
                self.base_currency = parts[0].strip().upper()
                self.quote_currency = parts[1].strip().upper()

        # Validate rate is positive
        if self.rate and self.rate <= 0:
            raise ValidationError('Rate must be positive')

        # Validate bid/ask relationship
        if self.bid_rate and self.ask_rate:
            if self.bid_rate > self.ask_rate:
                raise ValidationError('Bid rate cannot be greater than ask rate')

            # Auto-calculate mid rate
            if not self.mid_rate:
                self.mid_rate = (self.bid_rate + self.ask_rate) / Decimal('2')

        # Ensure rate_date is not in the future
        if self.rate_date and self.rate_date > timezone.now().date():
            raise ValidationError('Rate date cannot be in the future')

    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    def get_spread(self):
        """Calculate bid-ask spread"""
        if self.bid_rate and self.ask_rate:
            return self.ask_rate - self.bid_rate
        return None

    def get_spread_percentage(self):
        """Calculate bid-ask spread as percentage"""
        spread = self.get_spread()
        if spread and self.mid_rate:
            return (spread / self.mid_rate) * Decimal('100')
        return None

    def is_fresh(self, hours=1):
        """Check if rate is fresh (within specified hours)"""
        if not self.rate_time:
            return False
        age = timezone.now() - self.rate_time
        return age.total_seconds() < (hours * 3600)

    def is_stale(self, hours=24):
        """Check if rate is stale (older than specified hours)"""
        if not self.rate_time:
            return True
        age = timezone.now() - self.rate_time
        return age.total_seconds() > (hours * 3600)

    def get_freshness_status(self):
        """Get freshness status for display"""
        if self.is_fresh(1):
            return 'fresh'
        elif self.is_stale(24):
            return 'stale'
        else:
            return 'normal'

    def get_freshness_color(self):
        """Get Bootstrap color class for freshness status"""
        status = self.get_freshness_status()
        colors = {
            'fresh': 'success',
            'normal': 'info',
            'stale': 'warning',
        }
        return colors.get(status, 'secondary')
