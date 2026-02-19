"""
UDF Views - Single Table CRUD Operations

Full CRUD flow for cis_udf_field table:
- List: View all UDF fields with filters
- Create: Add new UDF field definition
- Detail: View single UDF field
- Edit: Update UDF field
- Delete: Soft delete (sets deleted_at timestamp)
- Restore: Restore soft-deleted field
"""

import logging
import json
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.paginator import Paginator

from udf.repositories import udf_field_hive_repository
from core.audit.audit_hive_repository import audit_hive_repository

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_user_info(request: HttpRequest) -> dict:
    """Extract user information from session."""
    return {
        'user_id': str(request.session.get('user_id', '')),
        'username': request.session.get('user_login', 'anonymous'),
        'user_email': request.session.get('user_email', ''),
        'ip_address': request.META.get('REMOTE_ADDR', ''),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
    }


class UDFFieldWrapper:
    """Wrapper to convert dict data to object for template compatibility."""

    def __init__(self, data: dict):
        self.data = data
        # Map all fields to attributes
        self.field_id = data.get('field_id', '')
        self.object_type = data.get('object_type', '')
        self.field_name = data.get('field_name', '')
        self.field_label = data.get('field_label', '')
        self.field_type = data.get('field_type', 'TEXT')
        self.is_required = data.get('is_required', False)
        self.default_value = data.get('default_value', '')
        self.options = data.get('options', '')
        self.options_list = data.get('options_list', [])
        self.display_order = data.get('display_order', 100)
        self.is_active = data.get('is_active', True)
        self.created_at = data.get('created_at', '')
        self.created_by = data.get('created_by', '')
        self.updated_at = data.get('updated_at', '')
        self.updated_by = data.get('updated_by', '')
        self.deleted_at = data.get('deleted_at')

        # Template compatibility
        self.id = self.field_id
        self.pk = self.field_id

    def get_field_type_display(self):
        """Get human-readable field type."""
        type_map = {
            'TEXT': 'Text',
            'NUMBER': 'Number',
            'DATE': 'Date',
            'BOOLEAN': 'Boolean',
            'SELECT': 'Dropdown',
            'MULTISELECT': 'Multi-Select',
        }
        return type_map.get(self.field_type, self.field_type)

    def get_object_type_display(self):
        """Get human-readable object type."""
        type_map = {
            'PORTFOLIO': 'Portfolio',
            'TRADE': 'Trade',
            'SECURITY': 'Security',
            'COUNTERPARTY': 'Counterparty',
        }
        return type_map.get(self.object_type, self.object_type)

    def is_deleted(self):
        """Check if field is soft-deleted."""
        return self.deleted_at is not None


# =============================================================================
# LIST VIEW
# =============================================================================

def udf_list(request: HttpRequest) -> HttpResponse:
    """
    List all UDF fields with filtering.

    Query params:
    - object_type: Filter by entity type (PORTFOLIO, TRADE, etc.)
    - status: 'active', 'deleted', or 'all'
    - search: Search in field_name and field_label
    """
    try:
        # Get filter parameters
        object_type = request.GET.get('object_type', '')
        status_filter = request.GET.get('status', 'active')
        search = request.GET.get('search', '')

        # Determine include_deleted based on status
        if status_filter == 'deleted':
            fields_data = udf_field_hive_repository.get_deleted_fields(
                object_type=object_type if object_type else None
            )
        elif status_filter == 'all':
            fields_data = udf_field_hive_repository.get_all_fields(
                include_deleted=True,
                object_type=object_type if object_type else None
            )
        else:  # active (default)
            fields_data = udf_field_hive_repository.get_all_fields(
                include_deleted=False,
                object_type=object_type if object_type else None
            )

        # Apply search filter
        if search:
            search_lower = search.lower()
            fields_data = [
                f for f in fields_data
                if search_lower in f.get('field_name', '').lower() or
                   search_lower in f.get('field_label', '').lower()
            ]

        # Wrap in UDFFieldWrapper objects
        wrapped_fields = [UDFFieldWrapper(f) for f in fields_data]

        # Pagination
        paginator = Paginator(wrapped_fields, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Get object types for filter dropdown
        object_types = udf_field_hive_repository.ALL_OBJECT_TYPES

        context = {
            'page_obj': page_obj,
            'object_type': object_type,
            'status_filter': status_filter,
            'search': search,
            'total_count': len(fields_data),
            'object_types': object_types,
            'field_types': udf_field_hive_repository.ALL_FIELD_TYPES,
        }

        return render(request, 'udf/udf_list.html', context)

    except Exception as e:
        logger.error(f"Error loading UDF list: {str(e)}")
        messages.error(request, f"Error loading UDF fields: {str(e)}")
        return render(request, 'udf/udf_list.html', {'page_obj': [], 'total_count': 0})


# =============================================================================
# DETAIL VIEW
# =============================================================================

def udf_detail(request: HttpRequest, field_id: str) -> HttpResponse:
    """View UDF field details."""
    try:
        field_data = udf_field_hive_repository.get_field_by_id(field_id)

        if not field_data:
            messages.error(request, f"UDF field '{field_id}' not found")
            return redirect('udf:list')

        field = UDFFieldWrapper(field_data)

        context = {
            'udf': field,
        }

        return render(request, 'udf/udf_detail.html', context)

    except Exception as e:
        logger.error(f"Error loading UDF detail: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('udf:list')


# =============================================================================
# CREATE VIEW
# =============================================================================

@require_http_methods(["GET", "POST"])
def udf_create(request: HttpRequest) -> HttpResponse:
    """Create new UDF field."""
    if request.method == 'POST':
        try:
            user_info = get_user_info(request)

            # Collect form data
            data = {
                'object_type': request.POST.get('object_type', ''),
                'field_name': request.POST.get('field_name', ''),
                'field_label': request.POST.get('field_label', ''),
                'field_type': request.POST.get('field_type', 'TEXT'),
                'is_required': request.POST.get('is_required') == 'on',
                'default_value': request.POST.get('default_value', ''),
                'options': request.POST.get('options', ''),
                'display_order': int(request.POST.get('display_order', 100)),
            }

            # Validate required fields
            if not data['object_type']:
                messages.error(request, 'Object Type is required')
                return render(request, 'udf/udf_form.html', {
                    'form_data': data,
                    'object_types': udf_field_hive_repository.ALL_OBJECT_TYPES,
                    'field_types': udf_field_hive_repository.ALL_FIELD_TYPES,
                })

            if not data['field_name']:
                messages.error(request, 'Field Name is required')
                return render(request, 'udf/udf_form.html', {
                    'form_data': data,
                    'object_types': udf_field_hive_repository.ALL_OBJECT_TYPES,
                    'field_types': udf_field_hive_repository.ALL_FIELD_TYPES,
                })

            # Create field
            field_id = udf_field_hive_repository.create_field(data, user_info['username'])

            if field_id:
                # Audit log
                audit_hive_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    action='CREATE',
                    entity_type='UDF',
                    entity_id=field_id,
                    new_value=json.dumps(data),
                    ip_address=user_info['ip_address'],
                    user_agent=user_info['user_agent']
                )

                messages.success(request, f"UDF field '{data['field_label'] or data['field_name']}' created successfully")
                return redirect('udf:detail', field_id=field_id)
            else:
                messages.error(request, 'Failed to create UDF field')

        except Exception as e:
            logger.error(f"Error creating UDF field: {str(e)}")
            messages.error(request, f"Error: {str(e)}")

    # GET request - show form
    context = {
        'object_types': udf_field_hive_repository.ALL_OBJECT_TYPES,
        'field_types': udf_field_hive_repository.ALL_FIELD_TYPES,
    }

    return render(request, 'udf/udf_form.html', context)


# =============================================================================
# EDIT VIEW
# =============================================================================

@require_http_methods(["GET", "POST"])
def udf_edit(request: HttpRequest, field_id: str) -> HttpResponse:
    """Edit existing UDF field."""
    try:
        field_data = udf_field_hive_repository.get_field_by_id(field_id)

        if not field_data:
            messages.error(request, f"UDF field '{field_id}' not found")
            return redirect('udf:list')

        if request.method == 'POST':
            user_info = get_user_info(request)

            # Collect form data
            update_data = {
                'field_label': request.POST.get('field_label', ''),
                'field_type': request.POST.get('field_type', 'TEXT'),
                'is_required': request.POST.get('is_required') == 'on',
                'default_value': request.POST.get('default_value', ''),
                'options': request.POST.get('options', ''),
                'display_order': int(request.POST.get('display_order', 100)),
                'is_active': request.POST.get('is_active') == 'on',
            }

            # Update field
            old_data = {k: v for k, v in field_data.items() if k in update_data}

            if udf_field_hive_repository.update_field(field_id, update_data, user_info['username']):
                # Audit log
                audit_hive_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    action='UPDATE',
                    entity_type='UDF',
                    entity_id=field_id,
                    old_value=json.dumps(old_data),
                    new_value=json.dumps(update_data),
                    ip_address=user_info['ip_address'],
                    user_agent=user_info['user_agent']
                )

                messages.success(request, f"UDF field updated successfully")
                return redirect('udf:detail', field_id=field_id)
            else:
                messages.error(request, 'Failed to update UDF field')

        # Show form with existing data
        field = UDFFieldWrapper(field_data)

        context = {
            'udf': field,
            'form_data': field_data,
            'object_types': udf_field_hive_repository.ALL_OBJECT_TYPES,
            'field_types': udf_field_hive_repository.ALL_FIELD_TYPES,
            'is_edit': True,
        }

        return render(request, 'udf/udf_form.html', context)

    except Exception as e:
        logger.error(f"Error editing UDF field: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
        return redirect('udf:list')


# =============================================================================
# DELETE VIEW (Soft Delete)
# =============================================================================

@require_http_methods(["POST"])
def udf_delete(request: HttpRequest, field_id: str) -> HttpResponse:
    """Soft delete UDF field."""
    try:
        user_info = get_user_info(request)

        # Get field data before delete
        field_data = udf_field_hive_repository.get_field_by_id(field_id)

        if not field_data:
            messages.error(request, f"UDF field '{field_id}' not found")
            return redirect('udf:list')

        if field_data.get('deleted_at'):
            messages.warning(request, 'Field is already deleted')
            return redirect('udf:list')

        # Soft delete
        if udf_field_hive_repository.delete_field(field_id, user_info['username']):
            # Audit log
            audit_hive_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                action='DELETE',
                entity_type='UDF',
                entity_id=field_id,
                old_value=json.dumps({
                    'field_name': field_data.get('field_name'),
                    'field_label': field_data.get('field_label'),
                    'object_type': field_data.get('object_type'),
                }),
                ip_address=user_info['ip_address'],
                user_agent=user_info['user_agent']
            )

            messages.success(request, f"UDF field '{field_data.get('field_label') or field_data.get('field_name')}' deleted successfully")
        else:
            messages.error(request, 'Failed to delete UDF field')

    except Exception as e:
        logger.error(f"Error deleting UDF field: {str(e)}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('udf:list')


# =============================================================================
# RESTORE VIEW
# =============================================================================

@require_http_methods(["POST"])
def udf_restore(request: HttpRequest, field_id: str) -> HttpResponse:
    """Restore soft-deleted UDF field."""
    try:
        user_info = get_user_info(request)

        # Get field data
        field_data = udf_field_hive_repository.get_field_by_id(field_id)

        if not field_data:
            messages.error(request, f"UDF field '{field_id}' not found")
            return redirect('udf:list')

        if not field_data.get('deleted_at'):
            messages.warning(request, 'Field is not deleted')
            return redirect('udf:detail', field_id=field_id)

        # Restore
        if udf_field_hive_repository.restore_field(field_id, user_info['username']):
            # Audit log
            audit_hive_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                action='RESTORE',
                entity_type='UDF',
                entity_id=field_id,
                new_value=json.dumps({
                    'field_name': field_data.get('field_name'),
                    'field_label': field_data.get('field_label'),
                    'object_type': field_data.get('object_type'),
                    'restored': True
                }),
                ip_address=user_info['ip_address'],
                user_agent=user_info['user_agent']
            )

            messages.success(request, f"UDF field '{field_data.get('field_label') or field_data.get('field_name')}' restored successfully")
            return redirect('udf:detail', field_id=field_id)
        else:
            messages.error(request, 'Failed to restore UDF field')

    except Exception as e:
        logger.error(f"Error restoring UDF field: {str(e)}")
        messages.error(request, f"Error: {str(e)}")

    return redirect('udf:list')


# =============================================================================
# STATISTICS VIEW
# =============================================================================

def udf_statistics(request: HttpRequest) -> HttpResponse:
    """View UDF statistics dashboard."""
    try:
        stats = udf_field_hive_repository.get_statistics()

        context = {
            'stats': stats,
        }

        return render(request, 'udf/udf_statistics.html', context)

    except Exception as e:
        logger.error(f"Error loading UDF statistics: {str(e)}")
        messages.error(request, f"Error: {str(e)}")
        return render(request, 'udf/udf_statistics.html', {'stats': {}})


# =============================================================================
# API ENDPOINTS
# =============================================================================

def api_get_fields_by_object_type(request: HttpRequest, object_type: str) -> JsonResponse:
    """API: Get all fields for an object type."""
    try:
        fields = udf_field_hive_repository.get_fields_by_object_type(object_type)
        return JsonResponse({
            'success': True,
            'fields': fields,
            'count': len(fields)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_get_field(request: HttpRequest, field_id: str) -> JsonResponse:
    """API: Get single field by ID."""
    try:
        field = udf_field_hive_repository.get_field_by_id(field_id)
        if field:
            return JsonResponse({'success': True, 'field': field})
        return JsonResponse({'success': False, 'error': 'Field not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_get_object_types(request: HttpRequest) -> JsonResponse:
    """API: Get all available object types."""
    try:
        object_types = udf_field_hive_repository.get_object_types()
        # If no types in DB, return defaults
        if not object_types:
            object_types = udf_field_hive_repository.ALL_OBJECT_TYPES
        return JsonResponse({'success': True, 'object_types': object_types})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_get_statistics(request: HttpRequest) -> JsonResponse:
    """API: Get UDF statistics."""
    try:
        stats = udf_field_hive_repository.get_statistics()
        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
