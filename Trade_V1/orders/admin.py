from django.contrib import admin
from django.utils.html import format_html
from .models import Stock, Order, Trade


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    """Enhanced Stock Admin with better accessibility"""

    list_display = (
        'symbol_display',
        'name_display',
        'exchange_badge',
        'asset_class_badge',
        'sector',
        'is_active_badge'
    )
    list_filter = ('exchange', 'asset_class', 'is_active', 'sector', 'industry')
    search_fields = ('symbol', 'name', 'isin', 'sector', 'industry')
    ordering = ('symbol',)
    list_per_page = 25

    fieldsets = (
        ('📊 Stock Information', {
            'fields': (('symbol', 'name'), 'isin')
        }),
        ('🏢 Classification', {
            'fields': (
                ('exchange', 'asset_class'),
                ('sector', 'industry'),
                'currency'
            )
        }),
        ('⚙️ Settings', {
            'fields': ('is_active',)
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def symbol_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50; font-size: 13px;">{}</strong>',
            obj.symbol
        )
    symbol_display.short_description = '📈 Symbol'

    def name_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.name[:50] + '...' if len(obj.name) > 50 else obj.name
        )
    name_display.short_description = 'Name'

    def exchange_badge(self, obj):
        colors = {
            'NSE': '#3498db',
            'BSE': '#9b59b6',
            'NYSE': '#e74c3c',
            'NASDAQ': '#2ecc71',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.exchange, '#95a5a6'),
            obj.exchange
        )
    exchange_badge.short_description = '🏦 Exchange'

    def asset_class_badge(self, obj):
        colors = {
            'EQUITY': '#27ae60',
            'DEBT': '#3498db',
            'DERIVATIVE': '#e67e22',
            'COMMODITY': '#f39c12',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.asset_class, '#95a5a6'),
            obj.asset_class
        )
    asset_class_badge.short_description = '💼 Asset Class'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Enhanced Order Admin with Maker-Checker display"""

    list_display = (
        'order_id_display',
        'stock_display',
        'side_badge',
        'quantity_display',
        'price_display',
        'status_badge',
        'created_by_display',
        'approved_by_display'
    )
    list_filter = ('status', 'side', 'order_type', 'created_at')
    search_fields = (
        'order_id',
        'stock__symbol',
        'stock__name',
        'created_by_name',
        'approved_by_name',
        'created_by_employee_id',
        'approved_by_employee_id'
    )
    date_hierarchy = 'created_at'
    list_per_page = 25
    autocomplete_fields = ['stock', 'created_by', 'approved_by']

    fieldsets = (
        ('📋 Order Information', {
            'fields': ('order_id', ('stock', 'side'), ('order_type', 'quantity'), ('price', 'stop_price'))
        }),
        ('👤 Maker Information', {
            'fields': (
                'created_by',
                ('created_by_name', 'created_by_employee_id'),
                'created_at'
            ),
            'description': 'Information about who created this order'
        }),
        ('✅ Checker Information', {
            'fields': (
                'approved_by',
                ('approved_by_name', 'approved_by_employee_id'),
                'approved_at'
            ),
            'description': 'Information about who approved this order'
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
        'order_id',
        'created_by_name',
        'created_by_employee_id',
        'approved_by_name',
        'approved_by_employee_id',
        'created_at',
        'updated_at'
    )

    def order_id_display(self, obj):
        return format_html(
            '<code style="background: #ecf0f1; padding: 3px 6px; border-radius: 3px; font-size: 11px;">{}</code>',
            obj.order_id
        )
    order_id_display.short_description = '🆔 Order ID'

    def stock_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.stock.symbol
        )
    stock_display.short_description = '📈 Stock'

    def side_badge(self, obj):
        colors = {
            'BUY': '#27ae60',
            'SELL': '#e74c3c',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            colors.get(obj.side, '#95a5a6'),
            obj.side
        )
    side_badge.short_description = '↔️ Side'

    def quantity_display(self, obj):
        return format_html(
            '<span style="color: #2c3e50; font-weight: bold;">{:,}</span>',
            obj.quantity
        )
    quantity_display.short_description = '🔢 Quantity'

    def price_display(self, obj):
        if obj.price:
            return format_html(
                '<span style="color: #16a085; font-weight: bold;">₹ {:,.2f}</span>',
                obj.price
            )
        return '-'
    price_display.short_description = '💰 Price'

    def status_badge(self, obj):
        colors = {
            'PENDING': '#f39c12',
            'APPROVED': '#27ae60',
            'REJECTED': '#e74c3c',
            'EXECUTED': '#3498db',
            'CANCELLED': '#95a5a6',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#95a5a6'),
            obj.status
        )
    status_badge.short_description = '📊 Status'

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


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    """Enhanced Trade Admin"""

    list_display = (
        'trade_id_display',
        'stock_display',
        'side_badge',
        'quantity_display',
        'price_display',
        'value_display',
        'executed_at_display',
        'executed_by_display'
    )
    list_filter = ('side', 'executed_at', 'stock__exchange')
    search_fields = (
        'trade_id',
        'stock__symbol',
        'stock__name',
        'executed_by_name',
        'broker_ref'
    )
    date_hierarchy = 'executed_at'
    list_per_page = 25
    autocomplete_fields = ['stock', 'order']

    fieldsets = (
        ('📋 Trade Information', {
            'fields': (
                'trade_id',
                ('stock', 'order'),
                'side'
            )
        }),
        ('💰 Execution Details', {
            'fields': (
                ('quantity', 'price'),
                ('executed_at', 'settlement_date'),
                'broker_ref'
            )
        }),
        ('👤 Executed By', {
            'fields': (
                'executed_by_name',
                'notes'
            )
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('trade_id', 'executed_by_name', 'created_at', 'updated_at')

    def trade_id_display(self, obj):
        return format_html(
            '<code style="background: #e8f5e9; padding: 3px 6px; border-radius: 3px; font-size: 11px; color: #2e7d32;">{}</code>',
            obj.trade_id
        )
    trade_id_display.short_description = '🆔 Trade ID'

    def stock_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.stock.symbol
        )
    stock_display.short_description = '📈 Stock'

    def side_badge(self, obj):
        colors = {
            'BUY': '#27ae60',
            'SELL': '#e74c3c',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            colors.get(obj.side, '#95a5a6'),
            obj.side
        )
    side_badge.short_description = '↔️ Side'

    def quantity_display(self, obj):
        return format_html(
            '<span style="color: #2c3e50; font-weight: bold;">{:,}</span>',
            obj.quantity
        )
    quantity_display.short_description = '🔢 Qty'

    def price_display(self, obj):
        return format_html(
            '<span style="color: #16a085; font-weight: bold;">₹ {:,.2f}</span>',
            obj.price
        )
    price_display.short_description = '💰 Price'

    def value_display(self, obj):
        value = obj.quantity * obj.price
        return format_html(
            '<span style="color: #8e44ad; font-weight: bold;">₹ {:,.2f}</span>',
            value
        )
    value_display.short_description = '💵 Value'

    def executed_at_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d;">{}</span>',
            obj.executed_at.strftime('%Y-%m-%d %H:%M')
        )
    executed_at_display.short_description = '🕐 Executed At'

    def executed_by_display(self, obj):
        return format_html(
            '<strong style="color: #34495e;">{}</strong>',
            obj.executed_by_name
        )
    executed_by_display.short_description = '👤 Executed By'
