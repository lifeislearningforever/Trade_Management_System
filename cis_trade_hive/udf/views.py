"""
UDF Views
Handles User-Defined Fields CRUD operations and value management.
"""

import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import UDF, UDFValue, UDFHistory
from .services import UDFService


# ========================
# UDF Definition Views
# ========================

@login_required
def udf_list(request):
    """
    List all UDF definitions with search, filter, and CSV export.
    """
    # Get filter parameters
    entity_type = request.GET.get('entity_type', '')
    is_active = request.GET.get('is_active', '')
    search = request.GET.get('search', '')

    # Build queryset
    udfs = UDFService.list_udfs(
        entity_type=entity_type if entity_type else None,
        is_active=True if is_active == '1' else (False if is_active == '0' else None),
        search=search if search else None
    )

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

        for udf in udfs:
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
                udf.created_by.username if udf.created_by else '',
                udf.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        return response

    # Pagination
    paginator = Paginator(udfs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'entity_type': entity_type,
        'is_active': is_active,
        'search': search,
        'total_count': udfs.count(),
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_list.html', context)


@login_required
def udf_detail(request, pk):
    """
    View UDF definition details.
    """
    udf = get_object_or_404(UDF, pk=pk)

    # Get usage statistics
    value_count = UDFValue.objects.filter(udf=udf).count()

    context = {
        'udf': udf,
        'value_count': value_count,
    }

    return render(request, 'udf/udf_detail.html', context)


@login_required
def udf_create(request):
    """
    Create new UDF definition.
    """
    if request.method == 'POST':
        try:
            # Prepare data
            data = {
                'field_name': request.POST.get('field_name'),
                'label': request.POST.get('label'),
                'description': request.POST.get('description', ''),
                'field_type': request.POST.get('field_type'),
                'entity_type': request.POST.get('entity_type'),
                'is_required': request.POST.get('is_required') == 'on',
                'is_unique': request.POST.get('is_unique') == 'on',
                'default_value': request.POST.get('default_value'),
                'display_order': int(request.POST.get('display_order', 0)),
                'group_name': request.POST.get('group_name', ''),
                'is_active': request.POST.get('is_active') == 'on',
            }

            # Handle dropdown options (JSON array)
            if data['field_type'] in ['DROPDOWN', 'MULTI_SELECT']:
                options_str = request.POST.get('dropdown_options', '')
                if options_str:
                    data['dropdown_options'] = [opt.strip() for opt in options_str.split(',') if opt.strip()]

            # Handle numeric constraints
            if data['field_type'] in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
                min_val = request.POST.get('min_value')
                max_val = request.POST.get('max_value')
                if min_val:
                    data['min_value'] = min_val
                if max_val:
                    data['max_value'] = max_val

            # Handle text constraints
            if data['field_type'] == 'TEXT':
                max_len = request.POST.get('max_length')
                if max_len:
                    data['max_length'] = int(max_len)

            # Create UDF
            udf = UDFService.create_udf(request.user, data)

            messages.success(request, f'UDF "{udf.label}" created successfully.')
            return redirect('udf:detail', pk=udf.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating UDF: {str(e)}')

    context = {
        'field_type_choices': UDF.FIELD_TYPE_CHOICES,
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_form.html', context)


@login_required
def udf_edit(request, pk):
    """
    Edit existing UDF definition.
    """
    udf = get_object_or_404(UDF, pk=pk)

    if request.method == 'POST':
        try:
            # Prepare data
            data = {
                'label': request.POST.get('label'),
                'description': request.POST.get('description', ''),
                'is_required': request.POST.get('is_required') == 'on',
                'is_unique': request.POST.get('is_unique') == 'on',
                'default_value': request.POST.get('default_value'),
                'display_order': int(request.POST.get('display_order', 0)),
                'group_name': request.POST.get('group_name', ''),
                'is_active': request.POST.get('is_active') == 'on',
            }

            # Handle dropdown options
            if udf.field_type in ['DROPDOWN', 'MULTI_SELECT']:
                options_str = request.POST.get('dropdown_options', '')
                if options_str:
                    data['dropdown_options'] = [opt.strip() for opt in options_str.split(',') if opt.strip()]

            # Handle numeric constraints
            if udf.field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE']:
                min_val = request.POST.get('min_value')
                max_val = request.POST.get('max_value')
                if min_val:
                    data['min_value'] = min_val
                if max_val:
                    data['max_value'] = max_val

            # Handle text constraints
            if udf.field_type == 'TEXT':
                max_len = request.POST.get('max_length')
                if max_len:
                    data['max_length'] = int(max_len)

            # Update UDF
            udf = UDFService.update_udf(udf, request.user, data)

            messages.success(request, f'UDF "{udf.label}" updated successfully.')
            return redirect('udf:detail', pk=udf.id)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error updating UDF: {str(e)}')

    # Prepare dropdown options as comma-separated string
    dropdown_options_str = ''
    if udf.dropdown_options:
        dropdown_options_str = ', '.join(udf.dropdown_options)

    context = {
        'udf': udf,
        'dropdown_options_str': dropdown_options_str,
        'field_type_choices': UDF.FIELD_TYPE_CHOICES,
        'entity_type_choices': UDF.ENTITY_TYPE_CHOICES,
    }

    return render(request, 'udf/udf_form.html', context)


@login_required
def udf_delete(request, pk):
    """
    Deactivate UDF definition (soft delete).
    """
    udf = get_object_or_404(UDF, pk=pk)

    if request.method == 'POST':
        try:
            UDFService.delete_udf(udf, request.user)
            messages.success(request, f'UDF "{udf.label}" deactivated successfully.')
            return redirect('udf:list')

        except Exception as e:
            messages.error(request, f'Error deactivating UDF: {str(e)}')

    return redirect('udf:detail', pk=pk)


# ========================
# UDF Value Management Views
# ========================

@login_required
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
                request.user
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


@login_required
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

@login_required
def ajax_get_entity_udf_values(request, entity_type, entity_id):
    """
    AJAX endpoint to get UDF values for an entity.
    """
    try:
        values = UDFService.get_entity_udf_values(entity_type.upper(), entity_id)
        return JsonResponse({'success': True, 'values': values})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
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
