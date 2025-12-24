"""
Reference Data Admin Configuration
"""

from django.contrib import admin
from .models import Currency, Country, Calendar, Counterparty


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'decimal_places', 'is_active', 'created_at']
    list_filter = ['is_active', 'is_base_currency', 'created_at']
    search_fields = ['code', 'name', 'full_name', 'symbol']
    ordering = ['code']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'last_synced_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'full_name', 'symbol')
        }),
        ('Details', {
            'fields': ('decimal_places', 'rate_precision', 'calendar', 'spot_schedule')
        }),
        ('Status', {
            'fields': ('is_active', 'is_base_currency')
        }),
        ('ETL Information', {
            'fields': ('source_system', 'source_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'region', 'currency_code', 'is_active', 'created_at']
    list_filter = ['is_active', 'continent', 'region', 'created_at']
    search_fields = ['code', 'name', 'full_name']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'last_synced_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'full_name')
        }),
        ('Geographic', {
            'fields': ('region', 'continent', 'currency_code')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('ETL Information', {
            'fields': ('source_system', 'source_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ['calendar_label', 'holiday_date', 'holiday_name', 'exchange',
                   'is_trading_day', 'is_half_day', 'created_at']
    list_filter = ['exchange', 'is_trading_day', 'is_settlement_day', 'is_half_day',
                  'holiday_type', 'created_at']
    search_fields = ['calendar_label', 'calendar_description', 'holiday_name']
    date_hierarchy = 'holiday_date'
    ordering = ['-holiday_date']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'last_synced_at']

    fieldsets = (
        ('Calendar Information', {
            'fields': ('calendar_label', 'calendar_description', 'holiday_date')
        }),
        ('Holiday Details', {
            'fields': ('holiday_name', 'holiday_type')
        }),
        ('Trading Information', {
            'fields': ('exchange', 'is_trading_day', 'is_settlement_day',
                      'market_open_time', 'market_close_time', 'is_half_day')
        }),
        ('ETL Information', {
            'fields': ('source_system', 'source_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'counterparty_type', 'city', 'country',
                   'status', 'risk_category', 'created_at']
    list_filter = ['counterparty_type', 'status', 'risk_category', 'country', 'created_at']
    search_fields = ['code', 'name', 'legal_name', 'email', 'tax_id']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by', 'last_synced_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'legal_name', 'short_name', 'counterparty_type')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'website')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'state',
                      'country', 'postal_code')
        }),
        ('Regulatory', {
            'fields': ('tax_id', 'registration_number')
        }),
        ('Status & Risk', {
            'fields': ('status', 'is_active', 'risk_category', 'credit_rating')
        }),
        ('Metadata', {
            'fields': ('metadata', 'notes'),
            'classes': ('collapse',)
        }),
        ('ETL Information', {
            'fields': ('source_system', 'source_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
