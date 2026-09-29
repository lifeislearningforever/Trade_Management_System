"""
Market Data Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import FXRate


@admin.register(FXRate)
class FXRateAdmin(admin.ModelAdmin):
    """Admin interface for FX Rate model"""

    list_display = [
        'currency_pair',
        'rate_display',
        'bid_rate',
        'ask_rate',
        'spread_display',
        'rate_date',
        'source',
        'freshness_badge',
        'is_active',
    ]

    list_filter = [
        'is_active',
        'source',
        'rate_date',
        'base_currency',
        'quote_currency',
    ]

    search_fields = [
        'currency_pair',
        'base_currency',
        'quote_currency',
        'source',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'created_by',
        'updated_by',
        'get_spread',
        'get_spread_percentage',
        'get_freshness_status',
    ]

    fieldsets = (
        ('Currency Information', {
            'fields': ('currency_pair', 'base_currency', 'quote_currency')
        }),
        ('Rate Information', {
            'fields': ('rate', 'bid_rate', 'ask_rate', 'mid_rate', 'get_spread', 'get_spread_percentage')
        }),
        ('Temporal Information', {
            'fields': ('rate_date', 'rate_time', 'get_freshness_status')
        }),
        ('Source and Status', {
            'fields': ('source', 'is_active')
        }),
        ('Additional Information', {
            'fields': ('notes', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Audit Information', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    date_hierarchy = 'rate_date'

    ordering = ['-rate_date', '-rate_time']

    list_per_page = 50

    def rate_display(self, obj):
        """Display rate with formatting"""
        return format_html('<strong>{:.6f}</strong>', obj.rate)
    rate_display.short_description = 'Rate'

    def spread_display(self, obj):
        """Display spread with percentage"""
        spread = obj.get_spread()
        spread_pct = obj.get_spread_percentage()
        if spread and spread_pct:
            return format_html('{:.6f} ({:.4f}%)', spread, spread_pct)
        return '-'
    spread_display.short_description = 'Spread'

    def freshness_badge(self, obj):
        """Display freshness as colored badge"""
        status = obj.get_freshness_status()
        color = obj.get_freshness_color()

        color_map = {
            'success': '#10b981',
            'info': '#06b6d4',
            'warning': '#f59e0b',
            'secondary': '#64748b',
        }

        bg_color = color_map.get(color, '#64748b')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">{}</span>',
            bg_color,
            status.upper()
        )
    freshness_badge.short_description = 'Freshness'

    def save_model(self, request, obj, form, change):
        """Override save to set user information"""
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    actions = ['make_active', 'make_inactive']

    def make_active(self, request, queryset):
        """Mark selected rates as active"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} rate(s) marked as active.')
    make_active.short_description = 'Mark selected rates as active'

    def make_inactive(self, request, queryset):
        """Mark selected rates as inactive"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} rate(s) marked as inactive.')
    make_inactive.short_description = 'Mark selected rates as inactive'
