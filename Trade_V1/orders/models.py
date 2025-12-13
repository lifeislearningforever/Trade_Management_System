"""
Orders Models - Trading Orders with Maker-Checker Workflow
Stock, Order, and Trade models with real name display for makers and checkers
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid


class Stock(models.Model):
    """Stock/Security master data"""
    symbol = models.CharField(
        max_length=50,
        unique=True,
        help_text="Stock symbol/ticker"
    )
    name = models.CharField(max_length=200, help_text="Company/Security name")
    isin = models.CharField(max_length=12, blank=True, help_text="ISIN code")

    exchange = models.CharField(
        max_length=50,
        choices=[
            ('NSE', 'National Stock Exchange'),
            ('BSE', 'Bombay Stock Exchange'),
            ('NYSE', 'New York Stock Exchange'),
            ('NASDAQ', 'NASDAQ'),
            ('LSE', 'London Stock Exchange'),
        ],
        default='NSE'
    )

    asset_class = models.CharField(
        max_length=50,
        choices=[
            ('EQUITY', 'Equity'),
            ('DEBT', 'Debt'),
            ('DERIVATIVE', 'Derivative'),
            ('COMMODITY', 'Commodity'),
            ('CURRENCY', 'Currency'),
        ],
        default='EQUITY'
    )

    sector = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default='INR')
    lot_size = models.IntegerField(default=1, help_text="Minimum trading lot size")

    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock'
        ordering = ['symbol']
        indexes = [
            models.Index(fields=['symbol', 'exchange']),
            models.Index(fields=['asset_class', 'is_active']),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.name}"


class Order(models.Model):
    """
    Trading Order with Maker-Checker Workflow
    Uses real names for maker and checker display
    """

    ORDER_TYPE_CHOICES = [
        ('MARKET', 'Market Order'),
        ('LIMIT', 'Limit Order'),
        ('STOP_LOSS', 'Stop Loss'),
        ('STOP_LOSS_LIMIT', 'Stop Loss Limit'),
    ]

    SIDE_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('SUBMITTED', 'Submitted to Exchange'),
        ('PARTIALLY_FILLED', 'Partially Filled'),
        ('FILLED', 'Filled'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]

    # Order Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=50, unique=True, editable=False)

    # Order Details
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name='orders')
    side = models.CharField(max_length=10, choices=SIDE_CHOICES)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='MARKET')

    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price for LIMIT orders"
    )
    stop_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Trigger price for STOP orders"
    )

    # Execution Details
    filled_quantity = models.IntegerField(default=0)
    average_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Status & Workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    # Maker-Checker Fields with Real Names
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_orders',
        help_text="Maker - User who created this order"
    )
    created_by_name = models.CharField(
        max_length=300,
        editable=False,
        help_text="Real name of maker (auto-filled)"
    )
    created_by_employee_id = models.CharField(
        max_length=50,
        blank=True,
        editable=False,
        help_text="Employee ID of maker"
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_orders',
        help_text="Checker - User who approved/rejected this order"
    )
    approved_by_name = models.CharField(
        max_length=300,
        blank=True,
        editable=False,
        help_text="Real name of checker (auto-filled)"
    )
    approved_by_employee_id = models.CharField(
        max_length=50,
        blank=True,
        editable=False,
        help_text="Employee ID of checker"
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Additional Fields
    client = models.ForeignKey(
        'reference_data.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders'
    )
    broker = models.ForeignKey(
        'reference_data.Broker',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders'
    )

    validity = models.CharField(
        max_length=20,
        choices=[
            ('DAY', 'Day Order'),
            ('IOC', 'Immediate or Cancel'),
            ('GTC', 'Good Till Cancelled'),
        ],
        default='DAY'
    )

    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'order'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'status']),
            models.Index(fields=['created_by', 'status']),
            models.Index(fields=['stock', '-created_at']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate order_id
        if not self.order_id:
            self.order_id = f"ORD-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Auto-fill maker real name and employee ID
        if self.created_by:
            self.created_by_name = self.created_by.get_display_name()
            self.created_by_employee_id = self.created_by.employee_id or ''

        # Auto-fill checker real name and employee ID
        if self.approved_by:
            self.approved_by_name = self.approved_by.get_display_name()
            self.approved_by_employee_id = self.approved_by.employee_id or ''

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.side} {self.quantity} {self.stock.symbol}"

    def can_be_approved_by(self, user):
        """Check if user can approve this order (prevent self-approval)"""
        return user != self.created_by and user.has_permission('approve_order')

    def approve(self, user, notes=''):
        """Approve the order"""
        if not self.can_be_approved_by(user):
            raise ValueError("User cannot approve this order")

        self.status = 'APPROVED'
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes += f"\n[Approved by {user.get_display_name()}]: {notes}"
        self.save()

    def reject(self, user, reason):
        """Reject the order"""
        if not self.can_be_approved_by(user):
            raise ValueError("User cannot reject this order")

        self.status = 'REJECTED'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save()


class Trade(models.Model):
    """
    Trade Execution records
    Tracks actual fills/executions of orders
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade_id = models.CharField(max_length=50, unique=True, editable=False)

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='trades')
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name='trades')

    side = models.CharField(
        max_length=10,
        choices=[('BUY', 'Buy'), ('SELL', 'Sell')]
    )

    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=12, decimal_places=2)

    # Costs
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Execution Info
    exchange_trade_id = models.CharField(max_length=100, blank=True)
    executed_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Maker-Checker tracking (inherited from order)
    executed_by_name = models.CharField(
        max_length=300,
        editable=False,
        help_text="Name of person who executed (from order maker)"
    )

    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'trade'
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['-executed_at']),
            models.Index(fields=['order', '-executed_at']),
            models.Index(fields=['stock', '-executed_at']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate trade_id
        if not self.trade_id:
            self.trade_id = f"TRD-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Auto-fill executed by name from order
        if self.order and self.order.created_by:
            self.executed_by_name = self.order.created_by.get_display_name()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trade_id} - {self.side} {self.quantity}@{self.price}"

    @property
    def total_cost(self):
        """Calculate total cost including all charges"""
        base_amount = self.quantity * self.price
        return base_amount + self.commission + self.tax + self.other_charges
