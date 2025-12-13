from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, Role, Permission, RolePermission, UserRole, AuditLog


class UserRoleInline(admin.TabularInline):
    """Inline for user roles"""
    model = UserRole
    extra = 1
    fields = ('role', 'is_primary', 'valid_from', 'valid_until', 'notes')
    autocomplete_fields = ['role']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced User Admin with better organization and accessibility"""

    list_display = (
        'username',
        'display_full_name',
        'employee_id_display',
        'email',
        'department',
        'employment_status_badge',
        'is_staff',
        'is_active'
    )
    list_filter = (
        'is_staff',
        'is_active',
        'employment_status',
        'department',
        'designation',
        'joining_date'
    )
    search_fields = (
        'username',
        'email',
        'first_name',
        'last_name',
        'middle_name',
        'employee_id',
        'department',
        'phone_number',
        'mobile_number'
    )
    ordering = ('full_name',)
    list_per_page = 25

    # Enhanced fieldsets for better form organization
    fieldsets = (
        ('🔐 Authentication', {
            'fields': ('username', 'password')
        }),
        ('👤 Personal Information', {
            'fields': (
                ('first_name', 'middle_name', 'last_name'),
                'full_name',
                'email',
                'alternate_email'
            ),
            'description': 'Basic personal details'
        }),
        ('💼 Employee Information', {
            'fields': (
                ('employee_id', 'department'),
                ('designation', 'reporting_manager'),
                ('joining_date', 'leaving_date'),
                'employment_status'
            ),
            'description': 'Professional and organizational details'
        }),
        ('📱 Contact Information', {
            'fields': (
                ('phone_number', 'mobile_number'),
                ('address_line1', 'address_line2'),
                ('city', 'state'),
                ('country', 'postal_code')
            ),
            'classes': ('collapse',)
        }),
        ('👔 Profile & Preferences', {
            'fields': (
                'profile_picture',
                'bio',
                ('timezone', 'language')
            ),
            'classes': ('collapse',)
        }),
        ('🔒 Security & Access', {
            'fields': (
                ('last_login', 'last_login_ip'),
                ('failed_login_attempts', 'account_locked_until'),
                ('password_changed_at', 'must_change_password')
            ),
            'classes': ('collapse',)
        }),
        ('⚙️ Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            ),
            'classes': ('collapse',)
        }),
        ('📅 Timestamps', {
            'fields': (
                ('date_joined', 'created_at', 'updated_at'),
                ('created_by', 'updated_by')
            ),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('full_name', 'last_login', 'date_joined', 'created_at', 'updated_at')
    inlines = [UserRoleInline]

    def display_full_name(self, obj):
        """Display full name with emoji"""
        return format_html(
            '<strong>{}</strong>',
            obj.full_name
        )
    display_full_name.short_description = '📛 Full Name'

    def employee_id_display(self, obj):
        """Display employee ID with badge"""
        if obj.employee_id:
            return format_html(
                '<span style="background: #3498db; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
                obj.employee_id
            )
        return '-'
    employee_id_display.short_description = '🆔 Employee ID'

    def employment_status_badge(self, obj):
        """Display employment status with color badge"""
        colors = {
            'ACTIVE': '#27ae60',
            'ON_LEAVE': '#f39c12',
            'SUSPENDED': '#e74c3c',
            'TERMINATED': '#95a5a6',
            'RESIGNED': '#95a5a6',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.employment_status, '#95a5a6'),
            obj.get_employment_status_display()
        )
    employment_status_badge.short_description = '📊 Status'


class RolePermissionInline(admin.TabularInline):
    """Inline for role permissions"""
    model = RolePermission
    extra = 1
    fields = ('permission', 'granted_by', 'notes')
    autocomplete_fields = ['permission']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Enhanced Role Admin"""

    list_display = ('code_display', 'name', 'permission_count', 'user_count', 'is_active_badge', 'display_order')
    list_filter = ('is_active', 'is_system_role')
    search_fields = ('code', 'name', 'description')
    ordering = ('display_order', 'name')
    list_per_page = 25
    inlines = [RolePermissionInline]

    fieldsets = (
        ('Role Information', {
            'fields': (('code', 'name'), 'description')
        }),
        ('Settings', {
            'fields': (('is_active', 'is_system_role'), 'display_order')
        }),
        ('Timestamps', {
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
    code_display.short_description = 'Code'

    def permission_count(self, obj):
        count = obj.permissions.filter(is_active=True).count()
        return format_html(
            '<span style="background: #3498db; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            count
        )
    permission_count.short_description = '🔑 Permissions'

    def user_count(self, obj):
        count = obj.users.filter(is_active=True).count()
        return format_html(
            '<span style="background: #27ae60; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            count
        )
    user_count.short_description = '👥 Users'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color: #27ae60;">✅ Active</span>'
            )
        return format_html(
            '<span style="color: #e74c3c;">❌ Inactive</span>'
        )
    is_active_badge.short_description = 'Status'


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Enhanced Permission Admin"""

    list_display = ('code_display', 'name', 'category_badge', 'role_count', 'is_active_badge')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name', 'description', 'category')
    ordering = ('category', 'name')
    list_per_page = 25

    fieldsets = (
        ('Permission Information', {
            'fields': (('code', 'name'), 'category', 'description')
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def code_display(self, obj):
        return format_html(
            '<code style="background: #ecf0f1; padding: 2px 6px; border-radius: 3px;">{}</code>',
            obj.code
        )
    code_display.short_description = 'Code'

    def category_badge(self, obj):
        colors = {
            'orders': '#3498db',
            'portfolio': '#9b59b6',
            'reporting': '#e67e22',
            'users': '#1abc9c',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.category, '#95a5a6'),
            obj.category.upper()
        )
    category_badge.short_description = '📂 Category'

    def role_count(self, obj):
        count = obj.roles.filter(is_active=True).count()
        return format_html(
            '<span style="background: #27ae60; color: white; padding: 2px 6px; border-radius: 10px;">{}</span>',
            count
        )
    role_count.short_description = '🎭 Roles'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    """Enhanced Role Permission Admin"""

    list_display = ('role', 'permission', 'granted_at', 'granted_by')
    list_filter = ('role', 'permission__category', 'granted_at')
    search_fields = ('role__name', 'permission__name', 'granted_by')
    date_hierarchy = 'granted_at'
    list_per_page = 25
    autocomplete_fields = ['role', 'permission']

    fieldsets = (
        ('Assignment', {
            'fields': (('role', 'permission'),)
        }),
        ('Details', {
            'fields': ('granted_by', 'notes')
        }),
        ('Timestamp', {
            'fields': ('granted_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('granted_at',)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    """Enhanced User Role Admin"""

    list_display = (
        'user_display',
        'role_display',
        'is_primary_badge',
        'validity_status',
        'assigned_at'
    )
    list_filter = ('role', 'is_primary', 'assigned_at')
    search_fields = ('user__username', 'user__email', 'user__full_name', 'role__name')
    date_hierarchy = 'assigned_at'
    list_per_page = 25
    autocomplete_fields = ['user', 'role']

    fieldsets = (
        ('Assignment', {
            'fields': (('user', 'role'), 'is_primary')
        }),
        ('Validity Period', {
            'fields': (('valid_from', 'valid_until'),)
        }),
        ('Details', {
            'fields': ('assigned_by', 'notes')
        }),
        ('Timestamp', {
            'fields': ('assigned_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('assigned_at',)

    def user_display(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.user.get_display_name()
        )
    user_display.short_description = '👤 User'

    def role_display(self, obj):
        return format_html(
            '<span style="background: #3498db; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            obj.role.name
        )
    role_display.short_description = '🎭 Role'

    def is_primary_badge(self, obj):
        if obj.is_primary:
            return format_html('<span style="color: #f39c12;">⭐ Primary</span>')
        return '-'
    is_primary_badge.short_description = 'Primary'

    def validity_status(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: #27ae60;">✅ Valid</span>')
        return format_html('<span style="color: #e74c3c;">❌ Expired</span>')
    validity_status.short_description = 'Status'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Enhanced Audit Log Admin - Read Only"""

    list_display = (
        'timestamp_display',
        'user_display',
        'action_badge',
        'level_badge',
        'category_badge',
        'description_short',
        'success_badge'
    )
    list_filter = (
        'action',
        'level',
        'category',
        'success',
        'timestamp'
    )
    search_fields = (
        'username',
        'user_full_name',
        'user_employee_id',
        'description',
        'object_type',
        'ip_address'
    )
    date_hierarchy = 'timestamp'
    list_per_page = 50

    fieldsets = (
        ('📅 Basic Information', {
            'fields': ('timestamp', 'level', 'success')
        }),
        ('👤 User Information', {
            'fields': (
                ('username', 'user_full_name'),
                'user_employee_id',
                'user'
            )
        }),
        ('🎬 Action Details', {
            'fields': (
                ('action', 'category'),
                'description',
                ('object_type', 'object_id'),
                'object_repr'
            )
        }),
        ('🔄 Changes', {
            'fields': ('changes',),
            'classes': ('collapse',)
        }),
        ('🌐 Request Information', {
            'fields': (
                ('request_method', 'request_path'),
                'ip_address',
                'user_agent'
            ),
            'classes': ('collapse',)
        }),
        ('❌ Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('📦 Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = (
        'id', 'timestamp', 'user', 'username', 'user_full_name', 'user_employee_id',
        'action', 'level', 'category', 'description', 'object_type', 'object_id',
        'object_repr', 'changes', 'ip_address', 'user_agent', 'request_method',
        'request_path', 'success', 'error_message', 'metadata'
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def timestamp_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d;">{}</span>',
            obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        )
    timestamp_display.short_description = '🕐 Timestamp'

    def user_display(self, obj):
        if obj.user_employee_id:
            return format_html(
                '<strong>{}</strong><br><small style="color: #7f8c8d;">{}</small>',
                obj.user_full_name or obj.username,
                obj.user_employee_id
            )
        return format_html('<strong>{}</strong>', obj.username)
    user_display.short_description = '👤 User'

    def action_badge(self, obj):
        colors = {
            'CREATE': '#27ae60',
            'UPDATE': '#3498db',
            'DELETE': '#e74c3c',
            'APPROVE': '#2ecc71',
            'REJECT': '#e67e22',
            'LOGIN': '#1abc9c',
            'LOGOUT': '#95a5a6',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.action, '#95a5a6'),
            obj.action
        )
    action_badge.short_description = '⚡ Action'

    def level_badge(self, obj):
        colors = {
            'USER': '#3498db',
            'APPLICATION': '#9b59b6',
            'SYSTEM': '#e67e22',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.level, '#95a5a6'),
            obj.level
        )
    level_badge.short_description = '📊 Level'

    def category_badge(self, obj):
        return format_html(
            '<span style="background: #ecf0f1; color: #2c3e50; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            obj.category
        )
    category_badge.short_description = '📂 Category'

    def description_short(self, obj):
        if len(obj.description) > 50:
            return format_html(
                '<span title="{}">{}</span>',
                obj.description,
                obj.description[:50] + '...'
            )
        return obj.description
    description_short.short_description = '📝 Description'

    def success_badge(self, obj):
        if obj.success:
            return format_html('<span style="color: #27ae60;">✅ Success</span>')
        return format_html('<span style="color: #e74c3c;">❌ Failed</span>')
    success_badge.short_description = 'Result'
