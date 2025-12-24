"""
Core Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for Audit Logs"""

    list_display = ['timestamp', 'username', 'action', 'object_type', 'object_id',
                   'severity', 'approval_status_badge', 'ip_address']
    list_filter = ['action', 'severity', 'approval_status', 'timestamp', 'object_type']
    search_fields = ['username', 'object_type', 'object_id', 'object_repr',
                    'description', 'ip_address']
    readonly_fields = ['timestamp', 'user', 'username', 'action', 'severity',
                      'object_type', 'object_id', 'object_repr', 'old_value',
                      'new_value', 'changes', 'ip_address', 'user_agent',
                      'request_path', 'request_method', 'description',
                      'additional_data', 'requires_approval', 'approved_by',
                      'approved_at', 'approval_status', 'changes_display']

    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('Basic Information', {
            'fields': ('timestamp', 'user', 'username', 'action', 'severity')
        }),
        ('Object Details', {
            'fields': ('object_type', 'object_id', 'object_repr')
        }),
        ('Change Details', {
            'fields': ('old_value', 'new_value', 'changes', 'changes_display'),
            'classes': ('collapse',)
        }),
        ('Request Details', {
            'fields': ('ip_address', 'user_agent', 'request_path', 'request_method'),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('description', 'additional_data'),
            'classes': ('collapse',)
        }),
        ('Approval Workflow', {
            'fields': ('requires_approval', 'approval_status', 'approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
    )

    def approval_status_badge(self, obj):
        """Display approval status with color coding"""
        if not obj.requires_approval:
            return format_html('<span style="color: gray;">N/A</span>')

        colors = {
            'PENDING': '#ffc107',
            'APPROVED': '#28a745',
            'REJECTED': '#dc3545',
        }
        color = colors.get(obj.approval_status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.approval_status
        )
    approval_status_badge.short_description = 'Approval'

    def changes_display(self, obj):
        """Display changes in readable format"""
        return obj.get_changes_display()
    changes_display.short_description = 'Changes'

    def has_add_permission(self, request):
        """Audit logs should not be manually added"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Audit logs should not be deleted"""
        return request.user.is_superuser
