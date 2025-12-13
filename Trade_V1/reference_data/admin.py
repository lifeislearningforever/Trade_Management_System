from django.contrib import admin
from django.utils.html import format_html
from .models import Currency, Broker, TradingCalendar, Client


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    """Enhanced Currency Admin with ETL support"""

    list_display = (
        'code_display',
        'name_display',
        'symbol_display',
        'country',
        'is_base_badge',
        'is_active_badge',
        'last_synced_display'
    )
    list_filter = ('is_active', 'is_base_currency', 'country')
    search_fields = ('code', 'name', 'country', 'source_system')
    ordering = ('code',)
    list_per_page = 25

    fieldsets = (
        ('💱 Currency Information', {
            'fields': (
                ('code', 'name'),
                ('symbol', 'country')
            )
        }),
        ('⚙️ Settings', {
            'fields': (
                ('is_active', 'is_base_currency'),
            )
        }),
        ('🔄 ETL Information', {
            'fields': (
                ('source_system', 'source_id'),
                'last_synced_at'
            ),
            'classes': ('collapse',),
            'description': 'Fields for data integration and synchronization'
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def code_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50; font-size: 13px;">{}</strong>',
            obj.code
        )
    code_display.short_description = '💱 Code'

    def name_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.name
        )
    name_display.short_description = 'Name'

    def symbol_display(self, obj):
        return format_html(
            '<span style="background: #3498db; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; font-weight: bold;">{}</span>',
            obj.symbol
        )
    symbol_display.short_description = '💲 Symbol'

    def is_base_badge(self, obj):
        if obj.is_base_currency:
            return format_html('<span style="color: #f39c12;">⭐ Base</span>')
        return '-'
    is_base_badge.short_description = 'Base'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'

    def last_synced_display(self, obj):
        if obj.last_synced_at:
            return format_html(
                '<span style="color: #7f8c8d; font-size: 11px;">{}</span>',
                obj.last_synced_at.strftime('%Y-%m-%d %H:%M')
            )
        return '-'
    last_synced_display.short_description = '🔄 Last Synced'


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    """Enhanced Broker Admin with ETL support"""

    list_display = (
        'code_display',
        'name_display',
        'broker_type_badge',
        'sebi_registration_display',
        'is_preferred_badge',
        'is_active_badge'
    )
    list_filter = ('broker_type', 'is_active', 'is_preferred')
    search_fields = ('code', 'name', 'sebi_registration', 'contact_email')
    ordering = ('name',)
    list_per_page = 25

    fieldsets = (
        ('🏢 Broker Information', {
            'fields': (
                ('code', 'name'),
                'broker_type',
                'sebi_registration'
            )
        }),
        ('📞 Contact Information', {
            'fields': (
                ('contact_person', 'contact_email'),
                'contact_phone',
                'address'
            ),
            'classes': ('collapse',)
        }),
        ('⚙️ Settings', {
            'fields': (
                ('is_active', 'is_preferred'),
            )
        }),
        ('🔄 ETL Information', {
            'fields': (
                ('source_system', 'source_id'),
                'last_synced_at'
            ),
            'classes': ('collapse',)
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def code_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.code
        )
    code_display.short_description = '🏢 Code'

    def name_display(self, obj):
        return format_html(
            '<strong style="color: #34495e;">{}</strong>',
            obj.name
        )
    name_display.short_description = 'Name'

    def broker_type_badge(self, obj):
        colors = {
            'FULL_SERVICE': '#3498db',
            'DISCOUNT': '#27ae60',
            'DIRECT': '#9b59b6',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.broker_type, '#95a5a6'),
            obj.broker_type
        )
    broker_type_badge.short_description = '🏷️ Type'

    def sebi_registration_display(self, obj):
        if obj.sebi_registration:
            return format_html(
                '<code style="background: #ecf0f1; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</code>',
                obj.sebi_registration
            )
        return '-'
    sebi_registration_display.short_description = '🔖 SEBI Reg'

    def is_preferred_badge(self, obj):
        if obj.is_preferred:
            return format_html('<span style="color: #f39c12;">⭐ Preferred</span>')
        return '-'
    is_preferred_badge.short_description = 'Preferred'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'


@admin.register(TradingCalendar)
class TradingCalendarAdmin(admin.ModelAdmin):
    """Enhanced Trading Calendar Admin"""

    list_display = (
        'date_display',
        'exchange_badge',
        'day_type_badge',
        'holiday_name_display',
        'is_settlement_badge'
    )
    list_filter = ('exchange', 'is_trading_day', 'is_holiday', 'is_settlement_day')
    search_fields = ('holiday_name', 'exchange')
    date_hierarchy = 'date'
    list_per_page = 50

    fieldsets = (
        ('📅 Calendar Information', {
            'fields': (
                ('date', 'exchange'),
            )
        }),
        ('📊 Day Details', {
            'fields': (
                ('is_trading_day', 'is_settlement_day'),
                ('is_holiday', 'holiday_name'),
                'notes'
            )
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def date_display(self, obj):
        weekday = obj.date.strftime('%A')
        color = '#e74c3c' if obj.is_holiday else '#27ae60' if obj.is_trading_day else '#95a5a6'
        return format_html(
            '<strong style="color: {};">{}</strong><br><small style="color: #7f8c8d;">{}</small>',
            color,
            obj.date.strftime('%Y-%m-%d'),
            weekday
        )
    date_display.short_description = '📅 Date'

    def exchange_badge(self, obj):
        colors = {
            'NSE': '#3498db',
            'BSE': '#9b59b6',
            'MCX': '#e67e22',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.exchange, '#95a5a6'),
            obj.exchange
        )
    exchange_badge.short_description = '🏦 Exchange'

    def day_type_badge(self, obj):
        if obj.is_holiday:
            return format_html(
                '<span style="background: #e74c3c; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">🚫 Holiday</span>'
            )
        elif obj.is_trading_day:
            return format_html(
                '<span style="background: #27ae60; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">✅ Trading Day</span>'
            )
        else:
            return format_html(
                '<span style="background: #95a5a6; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">⏸️ Closed</span>'
            )
    day_type_badge.short_description = '📊 Type'

    def holiday_name_display(self, obj):
        if obj.holiday_name:
            return format_html(
                '<span style="color: #e74c3c;">{}</span>',
                obj.holiday_name
            )
        return '-'
    holiday_name_display.short_description = '🎉 Holiday'

    def is_settlement_badge(self, obj):
        if obj.is_settlement_day:
            return format_html('<span style="color: #27ae60;">✅</span>')
        return format_html('<span style="color: #95a5a6;">—</span>')
    is_settlement_badge.short_description = '💳 Settlement'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Enhanced Client Admin with ETL support"""

    list_display = (
        'client_id_display',
        'name_display',
        'client_type_badge',
        'status_badge',
        'kyc_status_badge',
        'risk_category_badge'
    )
    list_filter = ('client_type', 'status', 'kyc_status', 'risk_category')
    search_fields = ('client_id', 'name', 'pan_number', 'email', 'phone')
    ordering = ('name',)
    list_per_page = 25

    fieldsets = (
        ('👤 Client Information', {
            'fields': (
                ('client_id', 'name'),
                ('client_type', 'pan_number')
            )
        }),
        ('📞 Contact Information', {
            'fields': (
                ('email', 'phone'),
                'address'
            ),
            'classes': ('collapse',)
        }),
        ('📊 Status & Risk', {
            'fields': (
                ('status', 'kyc_status'),
                'risk_category'
            )
        }),
        ('🔄 ETL Information', {
            'fields': (
                ('source_system', 'source_id'),
                'last_synced_at'
            ),
            'classes': ('collapse',)
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def client_id_display(self, obj):
        return format_html(
            '<code style="background: #e8f5e9; padding: 3px 6px; border-radius: 3px; font-size: 11px; color: #2e7d32;">{}</code>',
            obj.client_id
        )
    client_id_display.short_description = '🆔 Client ID'

    def name_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.name
        )
    name_display.short_description = '👤 Name'

    def client_type_badge(self, obj):
        colors = {
            'INDIVIDUAL': '#3498db',
            'CORPORATE': '#9b59b6',
            'INSTITUTIONAL': '#e67e22',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.client_type, '#95a5a6'),
            obj.client_type
        )
    client_type_badge.short_description = '🏷️ Type'

    def status_badge(self, obj):
        colors = {
            'ACTIVE': '#27ae60',
            'INACTIVE': '#95a5a6',
            'SUSPENDED': '#e74c3c',
            'CLOSED': '#7f8c8d',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#95a5a6'),
            obj.status
        )
    status_badge.short_description = '📊 Status'

    def kyc_status_badge(self, obj):
        colors = {
            'VERIFIED': '#27ae60',
            'PENDING': '#f39c12',
            'REJECTED': '#e74c3c',
            'EXPIRED': '#95a5a6',
        }
        icons = {
            'VERIFIED': '✅',
            'PENDING': '⏳',
            'REJECTED': '❌',
            'EXPIRED': '⌛',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{} {}</span>',
            colors.get(obj.kyc_status, '#95a5a6'),
            icons.get(obj.kyc_status, ''),
            obj.kyc_status
        )
    kyc_status_badge.short_description = '🔐 KYC'

    def risk_category_badge(self, obj):
        if obj.risk_category:
            colors = {
                'LOW': '#27ae60',
                'MEDIUM': '#f39c12',
                'HIGH': '#e74c3c',
            }
            return format_html(
                '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
                colors.get(obj.risk_category, '#95a5a6'),
                obj.risk_category
            )
        return '-'
    risk_category_badge.short_description = '⚠️ Risk'
