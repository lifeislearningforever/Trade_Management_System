# udf/views.py — Kudu-only views (no Django ORM)
import csv
from io import TextIOWrapper
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from udf.services.udf_service import UDFService  # <-- our Kudu-only service


def udf_list(request):
    entity_type = request.GET.get('entity_type', '')
    is_active = request.GET.get('is_active', '')
    search = request.GET.get('search', '')
    active_only = True if is_active == '1' else (False if is_active == '0' else True)

    defs = UDFService.list_udfs(entity_type or None, active_only=active_only, search=search or None)
    paginator = Paginator(defs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'udf/udf_list.html', {
        'page_obj': page_obj,
        'entity_type': entity_type,
        'is_active': is_active,
        'search': search,
        'total_count': len(defs),
        'entity_type_choices': [('PORTFOLIO', 'Portfolio'),
                                ('TRADE', 'Trade'),
                                ('COUNTERPARTY', 'Counterparty'),
                                ('GLOBAL', 'Global')],
    })


def udf_create(request):
    if request.method == 'POST':
        try:
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
            if data['field_type'] in ['DROPDOWN', 'MULTI_SELECT']:
                opts_str = request.POST.get('dropdown_options', '')
                if opts_str:
                    data['dropdown_options'] = [o.strip() for o in opts_str.split(',') if o.strip()]

            d = UDFService.create_udf(request, data)
            messages.success(request, f"UDF '{d['label']}' created successfully.")
            return redirect('udf:list')
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error creating UDF: {e}')

    field_type_choices = [('TEXT', 'Text'), ('NUMBER', 'Number'), ('CURRENCY', 'Currency'),
                          ('PERCENTAGE', 'Percentage'), ('DATE', 'Date'), ('DATETIME', 'Datetime'),
                          ('BOOLEAN', 'Boolean'), ('DROPDOWN', 'Dropdown'), ('MULTI_SELECT', 'Multi Select')]
    entity_type_choices = [('PORTFOLIO', 'Portfolio'), ('TRADE', 'Trade'),
                           ('COUNTERPARTY', 'Counterparty'), ('GLOBAL', 'Global')]
    return render(request, 'udf/udf_form.html', {
        'field_type_choices': field_type_choices,
        'entity_type_choices': entity_type_choices,
    })


def udf_detail(request, field_name):
    defs = UDFService.list_udfs(active_only=True)
    d = next((x for x in defs if x['field_name'] == field_name), None)
    if not d:
        messages.error(request, f"UDF '{field_name}' not found.")
        return redirect('udf:list')
    options = UDFService.get_udf_options(field_name) if d['field_type'] in ('DROPDOWN', 'MULTI_SELECT') else []
    return render(request, 'udf/udf_detail.html', {'udf': d, 'options': options})


def udf_edit(request, field_name):
    defs = UDFService.list_udfs(active_only=True)
    d = next((x for x in defs if x['field_name'] == field_name), None)

    if request.method == 'POST':
        try:
            data = {
                'label': request.POST.get('label'),
                'description': request.POST.get('description', ''),
                'is_required': request.POST.get('is_required') == 'on',
                'is_unique': request.POST.get('is_unique') == 'on',
                'default_value': request.POST.get('default_value'),
                'display_order': int(request.POST.get('display_order', 0)),
                'group_name': request.POST.get('group_name', ''),
                'is_active': request.POST.get('is_active') == 'on',
                'field_type': d['field_type'] if d else request.POST.get('field_type'),
                'dropdown_options': [o.strip() for o in (request.POST.get('dropdown_options', '')).split(',') if
                                     o.strip()]
                if (d and d['field_type'] in ('DROPDOWN', 'MULTI_SELECT')) else None
            }
            UDFService.update_udf(request, field_name, (d['entity_type'] if d else request.POST.get('entity_type')),
                                  data)
            messages.success(request, f"UDF '{field_name}' updated successfully.")
            return redirect('udf:detail', field_name=field_name)
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error updating UDF: {e}')

    opts_str = ', '.join([o for o, _ in (
        UDFService.get_udf_options(field_name) if d and d['field_type'] in ('DROPDOWN', 'MULTI_SELECT') else [])])
    field_type_choices = [('TEXT', 'Text'), ('NUMBER', 'Number'), ('CURRENCY', 'Currency'),
                          ('PERCENTAGE', 'Percentage'), ('DATE', 'Date'), ('DATETIME', 'Datetime'),
                          ('BOOLEAN', 'Boolean'), ('DROPDOWN', 'Dropdown'), ('MULTI_SELECT', 'Multi Select')]
    entity_type_choices = [('PORTFOLIO', 'Portfolio'), ('TRADE', 'Trade'),
                           ('COUNTERPARTY', 'Counterparty'), ('GLOBAL', 'Global')]
    return render(request, 'udf/udf_form.html', {
        'udf': d,
        'dropdown_options_str': opts_str,
        'field_type_choices': field_type_choices,
        'entity_type_choices': entity_type_choices,
    })


def udf_delete(request, field_name):
    if request.method == 'POST':
        try:
            UDFService.deactivate_udf(request, field_name)
            messages.success(request, f"UDF '{field_name}' deactivated successfully.")
            return redirect('udf:list')
        except Exception as e:
            messages.error(request, f'Error deactivating UDF: {e}')
    return redirect('udf:detail', field_name=field_name)


def entity_udf_values(request, entity_type, entity_id):
    udefs = UDFService.list_udfs(entity_type=entity_type, active_only=True)
    for d in udefs:
        if d['field_type'] in ('DROPDOWN', 'MULTI_SELECT'):
            d['options'] = [o for o, _ in UDFService.get_udf_options(d['field_name'])]

    current_values = UDFService.get_entity_udf_values(entity_type, entity_id)

    if request.method == 'POST':
        try:
            values = {}
            for d in udefs:
                fn = d['field_name']
                if d['field_type'] == 'BOOLEAN':
                    values[fn] = request.POST.get(fn) == 'on'
                elif d['field_type'] == 'MULTI_SELECT':
                    values[fn] = request.POST.getlist(fn)  # if needed, add value_multi repo
                else:
                    val = request.POST.get(fn)
                    if val:
                        values[fn] = val
            UDFService.set_entity_udf_values(request, entity_type, entity_id, values)
            messages.success(request, 'UDF values saved successfully.')
            return redirect(request.path)
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error saving UDF values: {e}')

    udf_data = [{'udf': u, 'value': current_values.get(u['field_name'])} for u in udefs]
    return render(request, 'udf/entity_udf_values.html', {
        'entity_type': entity_type,
        'entity_id': entity_id,
        'udf_data': udf_data,
    })


def udf_bulk_upload(request):
    if request.method == 'POST' and request.FILES.get('file'):
        try:
            f = request.FILES['file']
            csv_file = TextIOWrapper(f.file, encoding='utf-8')
            reader = csv.DictReader(csv_file)
            rows = [r for r in reader]
            inserted = UDFService.bulk_upsert_options(request, scope=None, rows=rows)
            messages.success(request, f'Bulk upload complete. Inserted options: {inserted}')
            return redirect('udf:list')
        except Exception as e:
            messages.error(request, f'Bulk upload failed: {e}')
    return render(request, 'udf/udf_bulk_upload.html')
