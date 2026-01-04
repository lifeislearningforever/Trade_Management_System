"""
UDF Views - Simplified Free Text Approach
Clean, focused views following Single Responsibility Principle
"""

import logging
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core.views.auth_views import require_login
from udf.services.udf_field_service import udf_field_service

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_info_from_request(request: HttpRequest) -> dict:
    """Extract user information from request for audit logging."""
    return {
        'user_id': request.session.get('user_id', 0),
        'username': request.session.get('user_login', 'anonymous'),
        'user_email': request.session.get('user_email', ''),
        'ip_address': request.META.get('REMOTE_ADDR', ''),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
    }


# ============================================================================
# DASHBOARD VIEW
# ============================================================================

@require_login
def udf_dashboard(request: HttpRequest) -> HttpResponse:
    """
    UDF Dashboard showing entity cards with field statistics.

    Features:
    - Card view for each entity type (Portfolio, Trade, Comments, etc.)
    - Shows total fields, active count, inactive count per entity
    - Quick "Add Field" button
    """
    try:
        # Get statistics from service
        stats = udf_field_service.get_dashboard_stats()

        # Get all entity types (including those with 0 fields)
        entity_types = udf_field_service.VALID_ENTITY_TYPES

        # Build stats map
        stats_map = {stat['entity_type']: stat for stat in stats}

        # Ensure all entity types are present
        dashboard_stats = []
        for entity_type in entity_types:
            if entity_type in stats_map:
                dashboard_stats.append(stats_map[entity_type])
            else:
                dashboard_stats.append({
                    'entity_type': entity_type,
                    'total_fields': 0,
                    'active_fields': 0,
                    'inactive_fields': 0,
                })

        context = {
            'stats': dashboard_stats,
            'page_title': 'UDF Dashboard',
        }

        return render(request, 'udf/dashboard.html', context)

    except Exception as e:
        logger.error(f"Error loading UDF dashboard: {str(e)}")
        return HttpResponse(f"Error loading dashboard: {str(e)}", status=500)


# ============================================================================
# LIST VIEW
# ============================================================================

@require_login
def udf_list(request: HttpRequest) -> HttpResponse:
    """
    UDF List view with search and filter capabilities.

    Features:
    - Search by field name or label
    - Filter by entity type
    - Filter by active/inactive status
    - Actions: Edit, Soft Delete, Restore
    """
    try:
        # Get query parameters
        search_query = request.GET.get('search', '').strip()
        entity_filter = request.GET.get('entity', '').strip()
        status_filter = request.GET.get('status', 'active')  # active, inactive, all

        # Determine is_active filter
        is_active = None
        if status_filter == 'active':
            is_active = True
        elif status_filter == 'inactive':
            is_active = False

        # Get fields from service
        fields = udf_field_service.get_all_fields(
            entity_type=entity_filter if entity_filter else None,
            is_active=is_active
        )

        # Apply search filter (client-side for simplicity)
        if search_query:
            search_lower = search_query.lower()
            fields = [
                f for f in fields
                if search_lower in f['field_name'].lower() or search_lower in f['label'].lower()
            ]

        context = {
            'fields': fields,
            'search_query': search_query,
            'entity_filter': entity_filter,
            'status_filter': status_filter,
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'UDF Fields',
        }

        return render(request, 'udf/list.html', context)

    except Exception as e:
        logger.error(f"Error loading UDF list: {str(e)}")
        return HttpResponse(f"Error loading list: {str(e)}", status=500)


# ============================================================================
# CREATE VIEW
# ============================================================================

@require_login
@require_http_methods(["GET", "POST"])
def udf_create(request: HttpRequest) -> HttpResponse:
    """
    Create new UDF field.

    GET: Display form
    POST: Process form and create field
    """
    if request.method == 'GET':
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Create UDF Field',
            'form_action': 'create',
        }
        return render(request, 'udf/form.html', context)

    # POST - Process form
    try:
        user_info = get_user_info_from_request(request)

        field_data = {
            'field_name': request.POST.get('field_name', '').strip(),
            'label': request.POST.get('label', '').strip(),
            'entity_type': request.POST.get('entity_type', '').strip(),
            'is_required': request.POST.get('is_required') == 'on',
        }

        # Create via service
        success, error_msg, udf_id = udf_field_service.create_field(field_data, user_info)

        if success:
            logger.info(f"UDF field created successfully: {udf_id}")
            return redirect('udf:list')

        # Show error
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Create UDF Field',
            'form_action': 'create',
            'error': error_msg,
            'field_data': field_data,  # Pre-fill form
        }
        return render(request, 'udf/form.html', context)

    except Exception as e:
        logger.error(f"Error creating UDF field: {str(e)}")
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Create UDF Field',
            'form_action': 'create',
            'error': f"System error: {str(e)}",
        }
        return render(request, 'udf/form.html', context)


# ============================================================================
# EDIT VIEW
# ============================================================================

@require_login
@require_http_methods(["GET", "POST"])
def udf_edit(request: HttpRequest, udf_id: int) -> HttpResponse:
    """
    Edit existing UDF field.

    GET: Display form with existing data
    POST: Process form and update field
    """
    # Get existing field
    field = udf_field_service.get_field_by_id(udf_id)
    if not field:
        return HttpResponse(f"UDF field {udf_id} not found", status=404)

    if request.method == 'GET':
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Edit UDF Field',
            'form_action': 'edit',
            'udf_id': udf_id,
            'field_data': field,
        }
        return render(request, 'udf/form.html', context)

    # POST - Process form
    try:
        user_info = get_user_info_from_request(request)

        field_data = {
            'field_name': request.POST.get('field_name', '').strip(),
            'label': request.POST.get('label', '').strip(),
            'entity_type': request.POST.get('entity_type', '').strip(),
            'is_required': request.POST.get('is_required') == 'on',
            'is_active': request.POST.get('is_active') == 'on',
        }

        # Update via service
        success, error_msg = udf_field_service.update_field(udf_id, field_data, user_info)

        if success:
            logger.info(f"UDF field updated successfully: {udf_id}")
            return redirect('udf:list')

        # Show error
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Edit UDF Field',
            'form_action': 'edit',
            'udf_id': udf_id,
            'error': error_msg,
            'field_data': field_data,  # Pre-fill form with submitted data
        }
        return render(request, 'udf/form.html', context)

    except Exception as e:
        logger.error(f"Error updating UDF field: {str(e)}")
        context = {
            'entity_types': udf_field_service.VALID_ENTITY_TYPES,
            'page_title': 'Edit UDF Field',
            'form_action': 'edit',
            'udf_id': udf_id,
            'error': f"System error: {str(e)}",
            'field_data': field,
        }
        return render(request, 'udf/form.html', context)


# ============================================================================
# DELETE VIEW (Soft Delete)
# ============================================================================

@require_login
@require_http_methods(["POST"])
def udf_delete(request: HttpRequest, udf_id: int) -> HttpResponse:
    """
    Soft delete UDF field (sets is_active = false).

    POST only - requires confirmation from UI
    """
    try:
        user_info = get_user_info_from_request(request)

        # Delete via service
        success, error_msg = udf_field_service.delete_field(udf_id, user_info)

        if success:
            logger.info(f"UDF field soft deleted: {udf_id}")
            return redirect('udf:list')

        return HttpResponse(f"Error deleting field: {error_msg}", status=400)

    except Exception as e:
        logger.error(f"Error deleting UDF field: {str(e)}")
        return HttpResponse(f"Error: {str(e)}", status=500)


# ============================================================================
# RESTORE VIEW
# ============================================================================

@require_login
@require_http_methods(["POST"])
def udf_restore(request: HttpRequest, udf_id: int) -> HttpResponse:
    """
    Restore soft-deleted UDF field (sets is_active = true).

    POST only - requires confirmation from UI
    """
    try:
        user_info = get_user_info_from_request(request)

        # Restore via service
        success, error_msg = udf_field_service.restore_field(udf_id, user_info)

        if success:
            logger.info(f"UDF field restored: {udf_id}")
            return redirect('udf:list')

        return HttpResponse(f"Error restoring field: {error_msg}", status=400)

    except Exception as e:
        logger.error(f"Error restoring UDF field: {str(e)}")
        return HttpResponse(f"Error: {str(e)}", status=500)


# ============================================================================
# API ENDPOINTS (Optional - for AJAX operations)
# ============================================================================

@require_login
@require_http_methods(["GET"])
def udf_get_fields_by_entity(request: HttpRequest, entity_type: str) -> JsonResponse:
    """
    API endpoint to get all active fields for a specific entity type.

    Used by other modules (Portfolio, Trade, etc.) to fetch UDF fields dynamically.

    Returns:
        JSON array of field objects
    """
    try:
        fields = udf_field_service.get_all_fields(entity_type=entity_type.upper(), is_active=True)
        return JsonResponse({'success': True, 'fields': fields})

    except Exception as e:
        logger.error(f"Error fetching fields for entity {entity_type}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
