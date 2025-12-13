"""
Portfolio Models - Portfolio Management with Maker-Checker Workflow
Integrates with UDF system for dynamic fields (Portfolio Group, Manager, etc.)
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid


class Portfolio(models.Model):
    """
    Portfolio with Maker-Checker workflow and UDF integration
    Uses real names for maker and checker
    """

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING_APPROVAL', 'Pending Approval'),
        ('ACTIVE', 'Active'),
        ('REJECTED', 'Rejected'),
        ('SUSPENDED', 'Suspended'),
        ('CLOSED', 'Closed'),
    ]

    # Portfolio Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio_id = models.CharField(max_length=50, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Owner
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='portfolios'
    )
    client = models.ForeignKey(
        'reference_data.Client',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='portfolios'
    )

    # UDF Fields - Dynamic values from UDF system
    portfolio_group = models.CharField(
        max_length=50,
        blank=True,
        help_text="From UDF: PORTFOLIO.GROUP (e.g., Equity, Fixed Income)"
    )
    portfolio_subgroup = models.CharField(
        max_length=50,
        blank=True,
        help_text="From UDF: PORTFOLIO.SUBGROUP"
    )
    portfolio_manager = models.CharField(
        max_length=50,
        blank=True,
        help_text="From UDF: PORTFOLIO.MANAGER"
    )
    strategy = models.CharField(
        max_length=50,
        blank=True,
        help_text="From UDF: PORTFOLIO.STRATEGY"
    )

    # Financial Data
    initial_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    current_cash = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    base_currency = models.CharField(max_length=3, default='INR')

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    # Maker-Checker Fields with Real Names
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_portfolios',
        help_text="Maker - User who created this portfolio"
    )
    created_by_name = models.CharField(
        max_length=300,
        editable=False,
        help_text="Real name of maker (auto-filled)"
    )
    created_by_employee_id = models.CharField(
        max_length=50,
        blank=True,
        editable=False
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_portfolios',
        help_text="Checker - User who approved this portfolio"
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
        editable=False
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portfolio'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['portfolio_group', 'status']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate portfolio_id
        if not self.portfolio_id:
            self.portfolio_id = f"PF-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Auto-fill maker real name
        if self.created_by:
            self.created_by_name = self.created_by.get_display_name()
            self.created_by_employee_id = self.created_by.employee_id or ''

        # Auto-fill checker real name
        if self.approved_by:
            self.approved_by_name = self.approved_by.get_display_name()
            self.approved_by_employee_id = self.approved_by.employee_id or ''

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.portfolio_id} - {self.name}"

    def can_be_approved_by(self, user):
        """Check if user can approve (prevent self-approval)"""
        return user != self.created_by and user.has_permission('approve_portfolio')

    def approve(self, user, notes=''):
        """Approve the portfolio"""
        if not self.can_be_approved_by(user):
            raise ValueError("User cannot approve this portfolio")

        self.status = 'ACTIVE'
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes += f"\n[Approved by {user.get_display_name()}]: {notes}"
        self.save()

    def reject(self, user, reason):
        """Reject the portfolio"""
        if not self.can_be_approved_by(user):
            raise ValueError("User cannot reject this portfolio")

        self.status = 'REJECTED'
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    @property
    def total_invested(self):
        """Calculate total amount invested"""
        return self.initial_capital - self.current_cash

    @property
    def current_value(self):
        """Calculate current portfolio value (cash + holdings)"""
        holdings_value = sum(h.current_value for h in self.holdings.all())
        return self.current_cash + holdings_value

    @property
    def total_pnl(self):
        """Calculate total P&L"""
        return self.current_value - self.initial_capital

    @property
    def total_pnl_percentage(self):
        """Calculate total P&L percentage"""
        if self.initial_capital > 0:
            return (self.total_pnl / self.initial_capital) * 100
        return Decimal('0')


class Holding(models.Model):
    """Current stock holdings in a portfolio"""

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='holdings')
    stock = models.ForeignKey('orders.Stock', on_delete=models.PROTECT, related_name='holdings')

    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    average_buy_price = models.DecimalField(max_digits=12, decimal_places=2)
    last_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Latest market price"
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'holding'
        unique_together = [['portfolio', 'stock']]
        ordering = ['portfolio', 'stock']

    def __str__(self):
        return f"{self.portfolio.portfolio_id} - {self.stock.symbol} ({self.quantity})"

    @property
    def total_cost(self):
        """Total cost of holding"""
        return self.quantity * self.average_buy_price

    @property
    def current_value(self):
        """Current market value"""
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self):
        """Unrealized profit/loss"""
        return self.current_value - self.total_cost

    @property
    def unrealized_pnl_percentage(self):
        """Unrealized P&L percentage"""
        if self.total_cost > 0:
            return (self.unrealized_pnl / self.total_cost) * 100
        return Decimal('0')


class Transaction(models.Model):
    """Portfolio transaction history"""

    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('DIVIDEND', 'Dividend'),
        ('INTEREST', 'Interest'),
        ('FEE', 'Fee'),
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=50, unique=True, editable=False)

    portfolio = models.ForeignKey(Portfolio, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    stock = models.ForeignKey(
        'orders.Stock',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='portfolio_transactions'
    )

    quantity = models.IntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    description = models.TextField(blank=True)
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Reference to order/trade ID"
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    transaction_date = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transaction'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['portfolio', '-transaction_date']),
            models.Index(fields=['transaction_type', '-transaction_date']),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate transaction_id
        if not self.transaction_id:
            self.transaction_id = f"TXN-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_id} - {self.transaction_type} {self.amount}"


class Position(models.Model):
    """Historical position snapshots for tracking"""

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='positions')
    stock = models.ForeignKey('orders.Stock', on_delete=models.PROTECT, related_name='positions')

    quantity = models.IntegerField()
    average_price = models.DecimalField(max_digits=12, decimal_places=2)
    market_price = models.DecimalField(max_digits=12, decimal_places=2)

    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    snapshot_date = models.DateField(db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'position'
        ordering = ['-snapshot_date']
        unique_together = [['portfolio', 'stock', 'snapshot_date']]
        indexes = [
            models.Index(fields=['portfolio', '-snapshot_date']),
        ]

    def __str__(self):
        return f"{self.portfolio.portfolio_id} - {self.stock.symbol} on {self.snapshot_date}"
