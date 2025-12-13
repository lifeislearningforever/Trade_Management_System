from django.contrib import admin
from django.utils.html import format_html
from .models import UDFType, UDFSubtype, UDFField


class UDFSubtypeInline(admin.TabularInline):
    """Inline for UDF Subtypes"""
    model = UDFSubtype
    extra = 0
    fields = ('code', 'name', 'field_label', 'is_required', 'is_active', 'display_order')
    ordering = ('display_order',)


class UDFFieldInline(admin.TabularInline):
    """Inline for UDF Fields"""
    model = UDFField
    extra = 0
    fields = ('code', 'value', 'is_active', 'is_default', 'display_order')
    ordering = ('display_order',)


@admin.register(UDFType)
class UDFTypeAdmin(admin.ModelAdmin):
    """Enhanced UDF Type Admin"""

    list_display = (
        'code_display',
        'name_display',
        'subtype_count',
        'is_active_badge',
        'display_order'
    )
    list_filter = ('is_active',)
    search_fields = ('code', 'name', 'description')
    ordering = ('display_order', 'name')
    list_per_page = 25
    inlines = [UDFSubtypeInline]

    fieldsets = (
        ('🏷️ UDF Type Information', {
            'fields': (
                ('code', 'name'),
                'description'
            )
        }),
        ('⚙️ Settings', {
            'fields': (
                ('is_active', 'display_order'),
            )
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
    code_display.short_description = '🔑 Code'

    def name_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.name
        )
    name_display.short_description = '📛 Name'

    def subtype_count(self, obj):
        count = obj.subtypes.filter(is_active=True).count()
        return format_html(
            '<span style="background: #3498db; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
            count
        )
    subtype_count.short_description = '📋 Subtypes'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'


@admin.register(UDFSubtype)
class UDFSubtypeAdmin(admin.ModelAdmin):
    """Enhanced UDF Subtype Admin"""

    list_display = (
        'udf_type_display',
        'code_display',
        'name_display',
        'field_label_display',
        'field_count',
        'is_required_badge',
        'is_active_badge',
        'display_order'
    )
    list_filter = ('udf_type', 'is_active', 'is_required')
    search_fields = ('code', 'name', 'field_label', 'udf_type__name')
    ordering = ('udf_type', 'display_order')
    list_per_page = 25
    autocomplete_fields = ['udf_type']
    inlines = [UDFFieldInline]

    fieldsets = (
        ('🏷️ UDF Subtype Information', {
            'fields': (
                'udf_type',
                ('code', 'name'),
                'field_label',
                'description'
            )
        }),
        ('⚙️ Settings', {
            'fields': (
                ('is_required', 'is_active'),
                'display_order'
            )
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def udf_type_display(self, obj):
        return format_html(
            '<span style="background: #9b59b6; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            obj.udf_type.code
        )
    udf_type_display.short_description = '📂 Type'

    def code_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.code
        )
    code_display.short_description = '🔑 Code'

    def name_display(self, obj):
        return format_html(
            '<span style="color: #34495e;">{}</span>',
            obj.name
        )
    name_display.short_description = '📛 Name'

    def field_label_display(self, obj):
        return format_html(
            '<span style="color: #7f8c8d; font-style: italic;">{}</span>',
            obj.field_label
        )
    field_label_display.short_description = '🏷️ Field Label'

    def field_count(self, obj):
        count = obj.fields.filter(is_active=True).count()
        default_count = obj.fields.filter(is_active=True, is_default=True).count()
        return format_html(
            '<span style="background: #27ae60; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span> '
            '<small style="color: #f39c12;">({} default)</small>',
            count,
            default_count
        )
    field_count.short_description = '📋 Fields'

    def is_required_badge(self, obj):
        if obj.is_required:
            return format_html('<span style="color: #e74c3c;">⚠️ Required</span>')
        return format_html('<span style="color: #95a5a6;">Optional</span>')
    is_required_badge.short_description = 'Required'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'


@admin.register(UDFField)
class UDFFieldAdmin(admin.ModelAdmin):
    """Enhanced UDF Field Admin"""

    list_display = (
        'udf_type_display',
        'udf_subtype_display',
        'code_display',
        'value_display',
        'is_default_badge',
        'is_active_badge',
        'display_order'
    )
    list_filter = ('udf_subtype__udf_type', 'udf_subtype', 'is_active', 'is_default')
    search_fields = ('code', 'value', 'udf_subtype__name', 'udf_subtype__code')
    ordering = ('udf_subtype__udf_type', 'udf_subtype', 'display_order')
    list_per_page = 50
    autocomplete_fields = ['udf_subtype']

    fieldsets = (
        ('🏷️ UDF Field Information', {
            'fields': (
                'udf_subtype',
                ('code', 'value'),
                'description'
            )
        }),
        ('⚙️ Settings', {
            'fields': (
                ('is_active', 'is_default'),
                'display_order'
            )
        }),
        ('📅 Timestamps', {
            'fields': (('created_at', 'updated_at'),),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def udf_type_display(self, obj):
        return format_html(
            '<span style="background: #9b59b6; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{}</span>',
            obj.udf_subtype.udf_type.code
        )
    udf_type_display.short_description = '📂 Type'

    def udf_subtype_display(self, obj):
        return format_html(
            '<strong style="color: #3498db;">{}</strong>',
            obj.udf_subtype.code
        )
    udf_subtype_display.short_description = '📋 Subtype'

    def code_display(self, obj):
        return format_html(
            '<code style="background: #ecf0f1; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</code>',
            obj.code
        )
    code_display.short_description = '🔑 Code'

    def value_display(self, obj):
        return format_html(
            '<strong style="color: #2c3e50;">{}</strong>',
            obj.value
        )
    value_display.short_description = '💎 Value'

    def is_default_badge(self, obj):
        if obj.is_default:
            return format_html('<span style="color: #f39c12;">⭐ Default</span>')
        return '-'
    is_default_badge.short_description = 'Default'

    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="color: #27ae60;">✅ Active</span>')
        return format_html('<span style="color: #e74c3c;">❌ Inactive</span>')
    is_active_badge.short_description = 'Status'
