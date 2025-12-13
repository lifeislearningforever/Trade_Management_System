from django.contrib import admin
from django.utils.html import format_html
from .models import Portfolio, Holding, Transaction, Position


class HoldingInline(admin.TabularInline):
    """Inline for portfolio holdings"""
    model = Holding
    extra = 0
    fields = ('stock', 'quantity', 'average_buy_price', 'last_price', 'current_value')
    readonly_fields = ('current_value',)
    autocomplete_fields = ['stock']


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    """Enhanced Portfolio Admin with UDF and Maker-Checker"""

    list_display = (
        'portfolio_id_display',
        'name_display',
        'owner_display',
        'portfolio_group_badge',
        'status_badge',
        'value_display',
        'created_by_display',
        'approved_by_display'
    )
    list_filter = ('status', 'portfolio_group', 'portfolio_subgroup', 'created_at')
    search_fields = (
        'portfolio_id',
        'name',
        'owner',
        'created_by_name',
        'approved_by_name',
        'created_by_employee_id',
        'approved_by_employee_id'
    )
    date_hierarchy = 'created_at'
    list_per_page = 25
    autocomplete_fields = ['created_by', 'approved_by']
    inlines = [HoldingInline]

    fieldsets = (
        ('📊 Portfolio Information', {
            'fields': (
                'portfolio_id',
                ('name', 'owner'),
                'description'
            )
        }),
        ('🏷️ UDF Classification', {
            'fields': (
                ('portfolio_group', 'portfolio_subgroup'),
                ('portfolio_manager', 'strategy')
            ),
            'description': 'Dynamic fields from UDF system'
        }),
        ('💰 Financial Details', {
            'fields': (
                ('initial_capital', 'current_value'),
                ('base_currency', 'benchmark')
            )
        }),
        ('👤 Maker Information', {
            'fields': (
                'created_by',
                ('created_by_name', 'created_by_employee_id'),
                'created_at'
            ),
            'description': 'Information about who created this portfolio'
        }),
        ('✅ Checker Information', {
            'fields': (
                'approved_by',
                ('approved_by_name', 'approved_by_employee_id'),
                'approved_at'
            ),
            'description': 'Information about who approved this portfolio'
        }),
        ('📊 Status & Notes', {
            'fields': ('status', 'notes')
        }),
        ('📅 Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = (
        'portfolio_id',
        'created_by_name',
        'created_by_employee_id',
        'approved_by_name',
        'approved_by_employee_id',
        'created_at',
        'updated_at'
    )

    def portfolio_id_display(self, obj):
        return format_html(
            '<code style="background: #e3f2fd; padding: 3px 6px; border-radius: 3px; font-size: 11px; color: #1976d2;">{}</code>',
            obj.portfolio_id
        )
    portfolio_id_display.short_description = '🆔 Portfolio ID'

    def name_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.name
        )
    name_display.short_description = '📁 Name'

    def owner_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.owner
        )
    owner_display.short_description = '👤 Owner'

    def portfolio_group_badge(self, obj):
        if obj.portfolio_group:
            colors = {
                'EQUITY': '#27ae60',
                'FIXED_INCOME': '#3498db',
                'DERIVATIVES': '#e67e22',
                'BALANCED': '#9b59b6',
            }
            return format_html(
                '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
                colors.get(obj.portfolio_group, '#95a5a6'),
                obj.portfolio_group
            )
        return '-'
    portfolio_group_badge.short_description = '🏷️ Group'

    def status_badge(self, obj):
        colors = {
            'PENDING': '#f39c12',
            'APPROVED': '#27ae60',
            'REJECTED': '#e74c3c',
            'ACTIVE': '#3498db',
            'CLOSED': '#95a5a6',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#95a5a6'),
            obj.status
        )
    status_badge.short_description = '📊 Status'

    def value_display(self, obj):
        if obj.current_value:
            return format_html(
                '<span style="color: #16a085; font-weight: bold;">₹ {:,.2f}</span>',
                obj.current_value
            )
        return '-'
    value_display.short_description = '💰 Value'

    def created_by_display(self, obj):
        if obj.created_by_employee_id:
            return format_html(
                '<strong>{}</strong><br><small style="color: #7f8c8d;">{}</small>',
                obj.created_by_name.split('(')[0].strip(),
                obj.created_by_employee_id
            )
        return format_html('<strong>{}</strong>', obj.created_by_name)
    created_by_display.short_description = '👤 Maker'

    def approved_by_display(self, obj):
        if obj.approved_by_name:
            if obj.approved_by_employee_id:
                return format_html(
                    '<strong>{}</strong><br><small style="color: #7f8c8d;">{}</small>',
                    obj.approved_by_name.split('(')[0].strip(),
                    obj.approved_by_employee_id
                )
            return format_html('<strong>{}</strong>', obj.approved_by_name)
        return format_html('<span style="color: #95a5a6;">—</span>')
    approved_by_display.short_description = '✅ Checker'


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    """Enhanced Holding Admin"""

    list_display = (
        'portfolio_display',
        'stock_display',
        'quantity_display',
        'avg_price_display',
        'last_price_display',
        'current_value_display',
        'pnl_display'
    )
    list_filter = ('portfolio', 'stock__exchange', 'stock__asset_class')
    search_fields = ('portfolio__name', 'portfolio__portfolio_id', 'stock__symbol', 'stock__name')
    list_per_page = 25
    autocomplete_fields = ['portfolio', 'stock']

    fieldsets = (
        ('📊 Holding Information', {
            'fields': (('portfolio', 'stock'),)
        }),
        ('💰 Quantity & Pricing', {
            'fields': (
                'quantity',
                ('average_buy_price', 'last_price'),
                'current_value'
            )
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('current_value', 'created_at', 'updated_at')

    def portfolio_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.portfolio.name
        )
    portfolio_display.short_description = '📁 Portfolio'

    def stock_display(self, obj):
        return format_html(
            '<strong style="color: #3498db;">{}</strong>',
            obj.stock.symbol
        )
    stock_display.short_description = '📈 Stock'

    def quantity_display(self, obj):
        return format_html(
            '<span style="color: #2c3e50; font-weight: bold;">{:,}</span>',
            obj.quantity
        )
    quantity_display.short_description = '🔢 Quantity'

    def avg_price_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d;">₹ {:,.2f}</span>',
            obj.average_buy_price
        )
    avg_price_display.short_description = '💵 Avg Price'

    def last_price_display(self, obj):
        if obj.last_price:
            return format_html(
                '<span style="color: #16a085; font-weight: bold;">₹ {:,.2f}</span>',
                obj.last_price
            )
        return '-'
    last_price_display.short_description = '💰 Last Price'

    def current_value_display(self, obj):
        return format_html(
            '<span style="color: #8e44ad; font-weight: bold;">₹ {:,.2f}</span>',
            obj.current_value
        )
    current_value_display.short_description = '💵 Value'

    def pnl_display(self, obj):
        if obj.last_price:
            pnl = (obj.last_price - obj.average_buy_price) * obj.quantity
            color = '#27ae60' if pnl >= 0 else '#e74c3c'
            symbol = '+' if pnl >= 0 else ''
            return format_html(
                '<span style="color: {}; font-weight: bold;">{} ₹ {:,.2f}</span>',
                color,
                symbol,
                pnl
            )
        return '-'
    pnl_display.short_description = '📊 P&L'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Enhanced Transaction Admin"""

    list_display = (
        'transaction_id_display',
        'portfolio_display',
        'transaction_type_badge',
        'amount_display',
        'transaction_date_display',
        'reference_number_display'
    )
    list_filter = ('transaction_type', 'transaction_date', 'portfolio')
    search_fields = ('transaction_id', 'portfolio__name', 'portfolio__portfolio_id', 'reference_number')
    date_hierarchy = 'transaction_date'
    list_per_page = 25
    autocomplete_fields = ['portfolio']

    fieldsets = (
        ('📋 Transaction Information', {
            'fields': (
                'transaction_id',
                ('portfolio', 'transaction_type'),
                ('amount', 'transaction_date')
            )
        }),
        ('📝 Details', {
            'fields': ('reference_number', 'description', 'notes')
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('transaction_id', 'created_at', 'updated_at')

    def transaction_id_display(self, obj):
        return format_html(
            '<code style="background: #fff3e0; padding: 3px 6px; border-radius: 3px; font-size: 11px; color: #e65100;">{}</code>',
            obj.transaction_id
        )
    transaction_id_display.short_description = '🆔 Transaction ID'

    def portfolio_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.portfolio.name
        )
    portfolio_display.short_description = '📁 Portfolio'

    def transaction_type_badge(self, obj):
        colors = {
            'DEPOSIT': '#27ae60',
            'WITHDRAWAL': '#e74c3c',
            'DIVIDEND': '#3498db',
            'FEE': '#e67e22',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.transaction_type, '#95a5a6'),
            obj.transaction_type
        )
    transaction_type_badge.short_description = '💳 Type'

    def amount_display(self, obj):
        color = '#27ae60' if obj.transaction_type in ['DEPOSIT', 'DIVIDEND'] else '#e74c3c'
        symbol = '+' if obj.transaction_type in ['DEPOSIT', 'DIVIDEND'] else '-'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} ₹ {:,.2f}</span>',
            color,
            symbol,
            obj.amount
        )
    amount_display.short_description = '💰 Amount'

    def transaction_date_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d;">{}</span>',
            obj.transaction_date.strftime('%Y-%m-%d')
        )
    transaction_date_display.short_description = '📅 Date'

    def reference_number_display(self, obj):
        if obj.reference_number:
            return format_html(
                '<code style="background: #ecf0f1; padding: 2px 4px; border-radius: 2px; font-size: 10px;">{}</code>',
                obj.reference_number
            )
        return '-'
    reference_number_display.short_description = '🔖 Ref No'


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """Enhanced Position Admin (Historical Snapshots)"""

    list_display = (
        'snapshot_date_display',
        'portfolio_display',
        'stock_display',
        'quantity_display',
        'market_price_display',
        'market_value_display'
    )
    list_filter = ('snapshot_date', 'portfolio', 'stock__exchange')
    search_fields = ('portfolio__name', 'portfolio__portfolio_id', 'stock__symbol', 'stock__name')
    date_hierarchy = 'snapshot_date'
    list_per_page = 25
    autocomplete_fields = ['portfolio', 'stock']

    fieldsets = (
        ('📅 Snapshot Information', {
            'fields': ('snapshot_date',)
        }),
        ('📊 Position Details', {
            'fields': (
                ('portfolio', 'stock'),
                'quantity',
                ('market_price', 'market_value')
            )
        }),
        ('📅 Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at',)

    def snapshot_date_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.snapshot_date.strftime('%Y-%m-%d')
        )
    snapshot_date_display.short_description = '📅 Snapshot Date'

    def portfolio_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.portfolio.name
        )
    portfolio_display.short_description = '📁 Portfolio'

    def stock_display(self, obj):
        return format_html(
            '<strong style="color: #3498db;">{}</strong>',
            obj.stock.symbol
        )
    stock_display.short_description = '📈 Stock'

    def quantity_display(self, obj):
        return format_html(
            '<span style="color: #2c3e50; font-weight: bold;">{:,}</span>',
            obj.quantity
        )
    quantity_display.short_description = '🔢 Quantity'

    def market_price_display(self, obj):
        return format_html(
            '<span style="color: #16a085;">₹ {:,.2f}</span>',
            obj.market_price
        )
    market_price_display.short_description = '💰 Price'

    def market_value_display(self, obj):
        return format_html(
            '<span style="color: #8e44ad; font-weight: bold;">₹ {:,.2f}</span>',
            obj.market_value
        )
    market_value_display.short_description = '💵 Value'
