from django.contrib import admin
from django.utils.html import format_html
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Enhanced Report Admin with UDF integration"""

    list_display = (
        'report_id_display',
        'title_display',
        'report_type_badge',
        'report_format_badge',
        'status_badge',
        'requested_by_display',
        'created_at_display'
    )
    list_filter = ('status', 'report_type', 'report_format', 'created_at')
    search_fields = (
        'report_id',
        'title',
        'requested_by_name',
        'description'
    )
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('📊 Report Information', {
            'fields': (
                'report_id',
                'title',
                'description'
            )
        }),
        ('🏷️ Classification', {
            'fields': (
                ('report_type', 'report_format'),
                ('period_start', 'period_end')
            ),
            'description': 'Report type from UDF system'
        }),
        ('📁 Parameters & Filters', {
            'fields': ('parameters', 'filters'),
            'classes': ('collapse',)
        }),
        ('👤 Request Information', {
            'fields': (
                'requested_by_name',
                'created_at'
            )
        }),
        ('📊 Status & Output', {
            'fields': (
                'status',
                ('file_path', 'file_size'),
                'error_message'
            )
        }),
        ('📅 Processing Timeline', {
            'fields': (
                ('started_at', 'completed_at'),
                'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = (
        'report_id',
        'requested_by_name',
        'created_at',
        'updated_at',
        'file_size'
    )

    def report_id_display(self, obj):
        return format_html(
            '<code style="background: #f3e5f5; padding: 3px 6px; border-radius: 3px; font-size: 11px; color: #6a1b9a;">{}</code>',
            obj.report_id
        )
    report_id_display.short_description = '🆔 Report ID'

    def title_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.title[:60] + '...' if len(obj.title) > 60 else obj.title
        )
    title_display.short_description = '📄 Title'

    def report_type_badge(self, obj):
        colors = {
            'PORTFOLIO_SUMMARY': '#3498db',
            'TRADE_HISTORY': '#27ae60',
            'PNL_STATEMENT': '#9b59b6',
            'HOLDINGS_REPORT': '#e67e22',
            'TRANSACTION_REPORT': '#1abc9c',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.report_type, '#95a5a6'),
            obj.report_type
        )
    report_type_badge.short_description = '📊 Type'

    def report_format_badge(self, obj):
        colors = {
            'PDF': '#e74c3c',
            'EXCEL': '#27ae60',
            'CSV': '#3498db',
            'JSON': '#f39c12',
        }
        icons = {
            'PDF': '📕',
            'EXCEL': '📗',
            'CSV': '📘',
            'JSON': '📙',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{} {}</span>',
            colors.get(obj.report_format, '#95a5a6'),
            icons.get(obj.report_format, '📄'),
            obj.report_format
        )
    report_format_badge.short_description = '📋 Format'

    def status_badge(self, obj):
        colors = {
            'PENDING': '#f39c12',
            'PROCESSING': '#3498db',
            'COMPLETED': '#27ae60',
            'FAILED': '#e74c3c',
            'CANCELLED': '#95a5a6',
        }
        icons = {
            'PENDING': '⏳',
            'PROCESSING': '⚙️',
            'COMPLETED': '✅',
            'FAILED': '❌',
            'CANCELLED': '🚫',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{} {}</span>',
            colors.get(obj.status, '#95a5a6'),
            icons.get(obj.status, ''),
            obj.status
        )
    status_badge.short_description = '📊 Status'

    def requested_by_display(self, obj):
        return format_html(
            '<strong style="color: #34495e;">{}</strong>',
            obj.requested_by_name
        )
    requested_by_display.short_description = '👤 Requested By'

    def created_at_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d;">{}</span>',
            obj.created_at.strftime('%Y-%m-%d %H:%M')
        )
    created_at_display.short_description = '🕐 Created At'
