"""
UDF Views
Handles User-Defined Fields CRUD operations and value management.
"""

import csv
from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required  # Commented for development
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.contrib.auth.models import User

from .models import UDF, UDFValue, UDFHistory
from .services import UDFService
from .repositories.udf_hive_repository import (
    udf_definition_repository,
    udf_value_repository,
    udf_option_repository
)
from core.audit.audit_kudu_repository import audit_log_kudu_repository


class UDFWrapper:
    """Wrapper to convert Kudu dict data to object with attributes for template compatibility."""
    def __init__(self, data, index=0):
        self.data = data
        # Map all Kudu fields to attributes
        self.udf_id = data.get('udf_id', 0)
        self.field_name = data.get('field_name', '')
        self.label = data.get('label', '')
        self.description = data.get('description', '')
        self.field_type = data.get('field_type', 'TEXT')
        self.entity_type = data.get('entity_type', 'PORTFOLIO')
        self.is_required = data.get('is_required', False)
        self.is_unique = data.get('is_unique', False)
        self.default_value = data.get('default_value', '')
        self.dropdown_options = data.get('dropdown_options', [])
        self.min_value = data.get('min_value')
        self.max_value = data.get('max_value')
        self.max_length = data.get('max_length')
        self.display_order = data.get('display_order', 0)
        self.group_name = data.get('group_name', '')
        self.is_active = data.get('is_active', True)
        self.created_at = data.get('created_at', '')
        self.updated_at = data.get('updated_at', '')
        self.created_by = data.get('created_by', '-')
        self.updated_by = data.get('updated_by', '-')

        # For backwards compatibility with templates using pk/id
        self.id = self.udf_id
        self.pk = self.udf_id

    def get_field_type_display(self):
        """Get human-readable field type."""
        type_map = {
            'TEXT': 'Text',
            'NUMBER': 'Number',
            'DATE': 'Date',
            'DATETIME': 'Date Time',
            'BOOLEAN': 'Boolean',
            'DROPDOWN': 'Dropdown',
            'MULTI_SELECT': 'Multi Select',
            'CURRENCY': 'Currency',
            'PERCENTAGE': 'Percentage',
        }
        return type_map.get(self.field_type, self.field_type)

    def get_entity_type_display(self):
        """Get human-readable entity type."""
        type_map = {
            'PORTFOLIO': 'Portfolio',
            'TRADE': 'Trade',
            'POSITION': 'Position',
            'COUNTERPARTY': 'Counterparty',
        }
        return type_map.get(self.entity_type, self.entity_type)


def get_request_user_info(request):
    """
    Get user information from ACL session.

    Returns:
        dict: Dictionary with user_id, username, user_email
    """
    return {
        'username': request.session.get('user_login', 'anonymous'),
        'user_id': str(request.session.get('user_id', '')),
        'user_email': request.session.get('user_email', '')
    }


# ========================
# UDF Definition Views
# ========================

# @login_required  # Commented for development
def udf_list(request):
    """
    List all UDF definitions with search, filter, and CSV export - FROM KUDU.
    """
    # Get filter parameters
    entity_type = request.GET.get('entity_type', '')
    is_active_filter = request.GET.get('is_active', '')
    search = request.GET.get('search', '')

    # Fetch from Kudu repository
    if is_active_filter == '1':
        # Only active
        udfs_data = udf_definition_repository.get_active_definitions(
            entity_type=entity_type if entity_type else None
        )
    else:
        # All or only inactive
        udfs_data = udf_definition_repository.get_all_definitions(
            entity_type=entity_type if entity_type else None
        )

        # Filter inactive if requested
        if is_active_filter == '0':
            udfs_data = [udf for udf in udfs_data if not udf.get('is_active', True)]

    # Apply search filter
    if search:
        search_lower = search.lower()
        udfs_data = [
            udf for udf in udfs_data
            if search_lower in udf.get('field_name', '').lower() or
               search_lower in udf.get('label', '').lower() or
               search_lower in udf.get('description', '').lower()
        ]

    # Wrap in UDFWrapper objects
    wrapped_udfs = [UDFWrapper(udf, idx) for idx, udf in enumerate(udfs_data)]

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="udf_definitions.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Field Name', 'Label', 'Field Type', 'Entity Type',
            'Required', 'Unique', 'Active', 'Display Order',
            'Group Name', 'Created By', 'Created At'
        ])

        for udf in wrapped_udfs:
            writer.writerow([
                udf.field_name,
                udf.label,
                udf.get_field_type_display(),
                udf.get_entity_type_display(),
                'Yes' if udf.is_required else 'No',
                'Yes' if udf.is_unique else 'No',
                'Yes' if udf.is_active else 'No',
                udf.display_order,
                udf.group_name or '',
                udf.created_by,
                udf.created_at
            ])

        # Log export to Kudu
        user_info = get_request_user_info(request)
        audit_log_kudu_repository.log_action(
            user_id=user_info['user_id'],
            username=user_info['username'],
            user_email=user_info['user_email'],
            action_type='EXPORT',
            entity_type='UDF',
            entity_name='UDF Definitions',
            action_description=f'Exported {len(wrapped_udfs)} UDF definitions to CSV',
            status='SUCCESS',
            request_method='GET',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        return response

    # Pagination
    paginator = Paginator(wrapped_udfs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Log view to Kudu
    user_info = get_request_user_info(request)
    audit_log_kudu_repository.log_action(
        user_id=user_info['user_id'],
        username=user_info['username'],
        user_email=user_info['user_email'],
        action_type='VIEW' if not search else 'SEARCH',
        entity_type='UDF',
        entity_name='UDF List',
        action_description=f'Viewed UDF list from Kudu ({len(udfs_data)} definitions)' + (f' - Search: {search}' if search else ''),
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'page_obj': page_obj,
        'entity_type': entity_type,
        'is_active': is_active_filter,
        'search': search,
        'total_count': len(udfs_data),
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_list.html', context)


# @login_required  # Commented for development
def udf_detail(request, field_name):
    """
    View UDF definition details - FROM KUDU.
    """
    # Fetch from Kudu by field_name
    udf_data = udf_definition_repository.get_definition_by_name(field_name)

    if not udf_data:
        from django.http import Http404
        raise Http404(f"UDF with field name '{field_name}' not found in Kudu")

    # Wrap in UDFWrapper
    udf = UDFWrapper(udf_data)

    # Get usage statistics (Note: UDF values not yet in Kudu)
    value_count = 0  # TODO: Implement when UDF values are in Kudu

    # Log view to Kudu
    user_info = get_request_user_info(request)
    audit_log_kudu_repository.log_action(
        user_id=user_info['user_id'],
        username=user_info['username'],
        user_email=user_info['user_email'],
        action_type='VIEW',
        entity_type='UDF',
        entity_id=field_name,
        entity_name=udf.label,
        action_description=f'Viewed UDF detail: {field_name}',
        status='SUCCESS',
        request_method='GET',
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )

    context = {
        'udf': udf,
        'value_count': value_count,
    }

    return render(request, 'udf/udf_detail.html', context)


# @login_required  # Commented for development
def udf_create(request):
    """
    Create new UDF definition - INSERTS TO KUDU.
    """
    if request.method == 'POST':
        try:
            from datetime import datetime
            import json

            # Get user info from session
            user_info = get_request_user_info(request)

            # Generate new UDF ID (timestamp-based for uniqueness)
            udf_id = int(datetime.now().timestamp() * 1000)
            field_name = request.POST.get('field_name')

            # Prepare data for Kudu
            data = {
                'udf_id': udf_id,
                'field_name': field_name,
                'label': request.POST.get('label'),
                'description': request.POST.get('description', ''),
                'field_type': request.POST.get('field_type'),
                'entity_type': request.POST.get('entity_type'),
                'is_required': request.POST.get('is_required') == 'on',
                'is_unique': request.POST.get('is_unique') == 'on',
                'default_value': request.POST.get('default_value', ''),
                'display_order': int(request.POST.get('display_order', 0)),
                'group_name': request.POST.get('group_name', ''),
                'is_active': True,  # Always active on creation
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': user_info['username'],
                'updated_by': user_info['username'],
            }

            # Handle dropdown options (store as JSON string)
            if data['field_type'] in ['DROPDOWN', 'MULTI_SELECT']:
                options_str = request.POST.get('dropdown_options', '')
                if options_str:
                    options = [opt.strip() for opt in options_str.split(',') if opt.strip()]
                    data['dropdown_options'] = json.dumps(options)

            # Handle numeric constraints
            if data['field_type'] in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
                min_val = request.POST.get('min_value')
                max_val = request.POST.get('max_value')
                if min_val:
                    data['min_value'] = float(min_val)
                if max_val:
                    data['max_value'] = float(max_val)

            # Handle text constraints
            if data['field_type'] == 'TEXT':
                max_len = request.POST.get('max_length')
                if max_len:
                    data['max_length'] = int(max_len)

            # Insert into Kudu
            success = udf_definition_repository.insert_definition(data)

            if success:
                # Log to Kudu audit
                audit_log_kudu_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    user_email=user_info['user_email'],
                    action_type='CREATE',
                    entity_type='UDF',
                    entity_id=field_name,
                    entity_name=data['label'],
                    action_description=f'Created UDF definition: {field_name}',
                    status='SUCCESS',
                    request_method='POST',
                    request_path=request.path,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

                messages.success(request, f'UDF "{data["label"]}" created successfully in Kudu.')
                return redirect('udf:detail', field_name=field_name)
            else:
                messages.error(request, 'Failed to create UDF in Kudu.')

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating UDF: {str(e)}')

    context = {
        'field_type_choices': UDF.FIELD_TYPE_CHOICES,
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_form.html', context)


# @login_required  # Commented for development
def udf_edit(request, field_name):
    """
    Edit existing UDF definition - UPDATES IN KUDU.
    """
    # Fetch from Kudu
    udf_data = udf_definition_repository.get_definition_by_name(field_name)

    if not udf_data:
        from django.http import Http404
        raise Http404(f"UDF with field name '{field_name}' not found in Kudu")

    # Wrap in UDFWrapper
    udf = UDFWrapper(udf_data)

    if request.method == 'POST':
        try:
            from datetime import datetime
            import json

            # Get user info from session
            user_info = get_request_user_info(request)

            # Prepare update data
            data = {
                'udf_id': udf.udf_id,  # Keep same ID
                'field_name': field_name,  # Field name cannot be changed
                'field_type': udf.field_type,  # Field type cannot be changed
                'entity_type': udf.entity_type,  # Entity type cannot be changed
                'label': request.POST.get('label'),
                'description': request.POST.get('description', ''),
                'is_required': request.POST.get('is_required') == 'on',
                'is_unique': request.POST.get('is_unique') == 'on',
                'default_value': request.POST.get('default_value', ''),
                'display_order': int(request.POST.get('display_order', 0)),
                'group_name': request.POST.get('group_name', ''),
                'is_active': request.POST.get('is_active') == 'on',
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': user_info['username'],
                'created_at': udf.created_at,  # Preserve original
                'created_by': udf.created_by,  # Preserve original
            }

            # Handle dropdown options
            if udf.field_type in ['DROPDOWN', 'MULTI_SELECT']:
                options_str = request.POST.get('dropdown_options', '')
                if options_str:
                    options = [opt.strip() for opt in options_str.split(',') if opt.strip()]
                    data['dropdown_options'] = json.dumps(options)

            # Handle numeric constraints
            if udf.field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
                min_val = request.POST.get('min_value')
                max_val = request.POST.get('max_value')
                if min_val:
                    data['min_value'] = float(min_val)
                if max_val:
                    data['max_value'] = float(max_val)

            # Handle text constraints
            if udf.field_type == 'TEXT':
                max_len = request.POST.get('max_length')
                if max_len:
                    data['max_length'] = int(max_len)

            # Update in Kudu
            success = udf_definition_repository.update_definition(udf.udf_id, data)

            if success:
                # Log to Kudu audit
                audit_log_kudu_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    user_email=user_info['user_email'],
                    action_type='UPDATE',
                    entity_type='UDF',
                    entity_id=field_name,
                    entity_name=data['label'],
                    action_description=f'Updated UDF definition: {field_name}',
                    status='SUCCESS',
                    request_method='POST',
                    request_path=request.path,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

                messages.success(request, f'UDF "{data["label"]}" updated successfully in Kudu.')
                return redirect('udf:detail', field_name=field_name)
            else:
                messages.error(request, 'Failed to update UDF in Kudu.')

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error updating UDF: {str(e)}')

    # Prepare dropdown options as comma-separated string
    dropdown_options_str = ''
    if udf.dropdown_options:
        import json
        try:
            if isinstance(udf.dropdown_options, str):
                options = json.loads(udf.dropdown_options)
            else:
                options = udf.dropdown_options
            dropdown_options_str = ', '.join(options)
        except:
            dropdown_options_str = str(udf.dropdown_options)

    context = {
        'udf': udf,
        'dropdown_options_str': dropdown_options_str,
        'field_type_choices': UDF.FIELD_TYPE_CHOICES,
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_form.html', context)


# @login_required  # Commented for development
def udf_delete(request, field_name):
    """
    Deactivate UDF definition (soft delete) - UPDATES IN KUDU.
    """
    # Fetch from Kudu
    udf_data = udf_definition_repository.get_definition_by_name(field_name)

    if not udf_data:
        from django.http import Http404
        raise Http404(f"UDF with field name '{field_name}' not found in Kudu")

    # Wrap in UDFWrapper
    udf = UDFWrapper(udf_data)

    if request.method == 'POST':
        try:
            # Get user info from session
            user_info = get_request_user_info(request)

            # Soft delete in Kudu (set is_active = false)
            success = udf_definition_repository.delete_definition(udf.udf_id)

            if success:
                # Log to Kudu audit
                audit_log_kudu_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    user_email=user_info['user_email'],
                    action_type='DELETE',
                    entity_type='UDF',
                    entity_id=field_name,
                    entity_name=udf.label,
                    action_description=f'Deactivated UDF definition: {field_name}',
                    status='SUCCESS',
                    request_method='POST',
                    request_path=request.path,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

                messages.success(request, f'UDF "{udf.label}" deactivated successfully in Kudu.')
                return redirect('udf:list')
            else:
                messages.error(request, 'Failed to deactivate UDF in Kudu.')

        except Exception as e:
            messages.error(request, f'Error deactivating UDF: {str(e)}')

    return redirect('udf:detail', field_name=field_name)


# ========================
# UDF Value Management Views
# ========================

# @login_required  # Commented for development
def entity_udf_values(request, entity_type, entity_id):
    """
    View and manage UDF values for an entity.
    """
    # Get all UDFs for this entity type
    udfs = UDF.objects.filter(
        entity_type=entity_type.upper(),
        is_active=True
    ).order_by('display_order', 'field_name')

    # Get current values
    current_values = UDFService.get_entity_udf_values(entity_type.upper(), entity_id)

    if request.method == 'POST':
        try:
            # Collect values from form
            values = {}
            for udf in udfs:
                field_name = udf.field_name

                if udf.field_type == 'BOOLEAN':
                    values[field_name] = request.POST.get(field_name) == 'on'
                elif udf.field_type == 'MULTI_SELECT':
                    values[field_name] = request.POST.getlist(field_name)
                else:
                    value = request.POST.get(field_name)
                    if value:  # Only include non-empty values
                        values[field_name] = value

            # Validate and set values
            UDFService.validate_udf_values(entity_type.upper(), values)
            UDFService.set_entity_udf_values(
                entity_type.upper(),
                entity_id,
                values,
                get_request_user(request)
            )

            messages.success(request, 'UDF values saved successfully.')
            return redirect(request.path)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error saving UDF values: {str(e)}')

    # Combine UDFs with their current values
    udf_data = []
    for udf in udfs:
        udf_data.append({
            'udf': udf,
            'value': current_values.get(udf.field_name),
        })

    context = {
        'entity_type': entity_type,
        'entity_id': entity_id,
        'udf_data': udf_data,
    }

    return render(request, 'udf/entity_udf_values.html', context)


# @login_required  # Commented for development
def udf_value_history(request, entity_type, entity_id):
    """
    View UDF value change history for an entity.
    """
    history = UDFService.get_entity_udf_history(entity_type.upper(), entity_id)

    # Pagination
    paginator = Paginator(history, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'entity_type': entity_type,
        'entity_id': entity_id,
        'page_obj': page_obj,
    }

    return render(request, 'udf/udf_value_history.html', context)


# ========================
# AJAX Views
# ========================

# @login_required  # Commented for development
def ajax_get_entity_udf_values(request, entity_type, entity_id):
    """
    AJAX endpoint to get UDF values for an entity.
    """
    try:
        values = UDFService.get_entity_udf_values(entity_type.upper(), entity_id)
        return JsonResponse({'success': True, 'values': values})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# @login_required  # Commented for development
def ajax_validate_udf_values(request):
    """
    AJAX endpoint to validate UDF values.
    """
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            entity_type = data.get('entity_type')
            values = data.get('values', {})

            UDFService.validate_udf_values(entity_type.upper(), values)
            return JsonResponse({'success': True, 'message': 'Validation successful'})

        except ValidationError as e:
            return JsonResponse({'success': False, 'errors': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)


# @login_required  # Commented for development
def ajax_get_dropdown_options(request, field_name):
    """
    AJAX endpoint to get dropdown options for a UDF field from Hive.
    """
    try:
        options = UDFService.get_udf_dropdown_options(field_name)
        return JsonResponse({
            'success': True,
            'field_name': field_name,
            'options': options,
            'count': len(options)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
