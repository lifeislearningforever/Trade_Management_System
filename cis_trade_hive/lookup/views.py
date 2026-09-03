"""
Lookup Table Views

Views for managing dynamic lookup tables from Kudu.
Provides list of tables, row management (CRUD), and CSV export.
"""

import json
import logging
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views import View
from django.utils.safestring import mark_safe

from lookup.services.lookup_service import lookup_service
from core.audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Helper to get client IP address. Uses REMOTE_ADDR (actual TCP peer),
    not the client/proxy-supplied X-Forwarded-For header."""
    return request.META.get('REMOTE_ADDR')


class LookupTableListView(View):
    """View to list all discovered lookup tables"""

    template_name = 'lookup/lookup_table_list.html'

    def get(self, request):
        try:
            username = request.session.get('user_login', 'anonymous')
            tables = lookup_service.get_all_lookup_tables(username)

            context = {
                'tables': tables,
                'total_count': len(tables),
            }
            return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error loading lookup tables: {str(e)}")
            messages.error(request, f"Error loading lookup tables: {str(e)}")
            return render(request, self.template_name, {'tables': [], 'total_count': 0})


class LookupTableDetailView(View):
    """View to display and manage rows in a lookup table"""

    template_name = 'lookup/lookup_table_detail.html'

    def get(self, request, table_name):
        try:
            # Get table metadata
            table_info = lookup_service.get_table_metadata(table_name)
            if not table_info:
                messages.error(request, f"Table '{table_name}' not found")
                return redirect('lookup:table_list')

            # Get filters
            search = request.GET.get('search', '')
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 25))

            # Check for CSV export
            if request.GET.get('export') == 'csv':
                return self._export_csv(table_name, table_info, search)

            # Get rows
            result = lookup_service.get_table_rows(
                table_name=table_name,
                search=search,
                page=page,
                page_size=page_size
            )

            # Prepare columns for JavaScript (only name and type)
            columns = table_info.get('columns', [])
            col_names_ordered = [col['name'] for col in columns]
            columns_for_js = [{'name': col['name'], 'type': col['type']} for col in columns]

            # Serialize rows to JSON for JS rendering (avoids get_item filter issues)
            import decimal
            def _json_safe(v):
                if isinstance(v, decimal.Decimal):
                    return float(v)
                return v

            def _row_to_dict(row, col_names):
                """Ensure row is a dict keyed by column name, not int index."""
                if isinstance(row, dict):
                    # Guard: if keys are all ints, remap to col names
                    keys = list(row.keys())
                    if keys and isinstance(keys[0], int):
                        return dict(zip(col_names, row.values()))
                    return row
                # list/tuple fallback
                return dict(zip(col_names, row))

            rows_safe = [_row_to_dict(r, col_names_ordered) for r in result['rows']]
            rows_for_js = [
                {k: _json_safe(v) for k, v in row.items()}
                for row in rows_safe
            ]

            pk_column = table_info.get('pk_column') or (col_names_ordered[0] if col_names_ordered else '')
            logger.warning(
                f"LookupDetailView: {table_name} | columns={len(columns)} | rows={len(rows_for_js)} "
                f"| pk={pk_column!r} | col_names={col_names_ordered[:5]} "
                f"| first_row_keys={list(rows_for_js[0].keys())[:5] if rows_for_js else []}"
            )

            try:
                rows_json_str = json.dumps(rows_for_js, default=str)
            except Exception as je:
                logger.error(f"rows_json serialization failed for {table_name}: {je}")
                rows_json_str = '[]'
            try:
                columns_json_str = json.dumps(columns_for_js)
            except Exception as je:
                logger.error(f"columns_json serialization failed for {table_name}: {je}")
                columns_json_str = '[]'

            context = {
                'table_info': table_info,
                'table_name': table_name,
                'rows': rows_safe,
                'rows_json': mark_safe(rows_json_str),
                'columns': columns,
                'columns_json': mark_safe(columns_json_str),
                'pk_column': pk_column,
                'total_count': result['total_count'],
                'page': result['page'],
                'page_size': result['page_size'],
                'total_pages': result['total_pages'],
                'has_previous': result['has_previous'],
                'has_next': result['has_next'],
                'previous_page': result['previous_page'],
                'next_page': result['next_page'],
                'search': search,
            }
            return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error loading table {table_name}: {str(e)}", exc_info=True)
            messages.error(request, f"Error loading table '{table_name}': {str(e)}")
            return redirect('lookup:table_list')

    def _export_csv(self, table_name, table_info, search):
        """Export table to CSV"""
        csv_content = lookup_service.export_to_csv(table_name, search=search)

        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{table_name}.csv"'
        return response


class LookupRowCreateView(View):
    """View to create a new row in lookup table"""

    template_name = 'lookup/lookup_row_form.html'

    def get(self, request, table_name):
        try:
            table_info = lookup_service.get_table_metadata(table_name)
            if not table_info:
                messages.error(request, f"Table '{table_name}' not found")
                return redirect('lookup:table_list')

            context = {
                'table_info': table_info,
                'table_name': table_name,
                'columns': table_info.get('columns', []),
                'pk_column': table_info.get('pk_column'),
                'row': {},
                'is_edit': False,
            }
            return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error loading create form for {table_name}: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
            return redirect('lookup:table_detail', table_name=table_name)

    def post(self, request, table_name):
        try:
            table_info = lookup_service.get_table_metadata(table_name)
            if not table_info:
                messages.error(request, f"Table '{table_name}' not found")
                return redirect('lookup:table_list')

            # Collect form data
            data = {}
            for col in table_info.get('columns', []):
                col_name = col['name']
                value = request.POST.get(col_name)

                # Handle boolean checkboxes
                if col['type'] in ('BOOLEAN', 'BOOL'):
                    value = col_name in request.POST
                elif value == '':
                    value = None

                data[col_name] = value

            # Create row
            result = lookup_service.create_row(table_name, data)

            if result['success']:
                username = request.session.get('user_login', 'anonymous')
                user_id = str(request.session.get('user_id', ''))
                user_email = request.session.get('user_email', '')
                pk_value = result.get('pk_value')

                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='CREATE',
                    entity_type='LOOKUP_TABLE',
                    entity_name=table_name,
                    entity_id=str(pk_value) if pk_value is not None else table_name,
                    action_description=f"Created row in lookup table '{table_name}' (pk={pk_value})",
                    new_value=json.dumps(data, default=str),
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, result['message'])
                return redirect('lookup:table_detail', table_name=table_name)
            else:
                messages.error(request, result['error'])
                context = {
                    'table_info': table_info,
                    'table_name': table_name,
                    'columns': table_info.get('columns', []),
                    'pk_column': table_info.get('pk_column'),
                    'row': data,
                    'is_edit': False,
                }
                return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error creating row in {table_name}: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
            return redirect('lookup:table_detail', table_name=table_name)


class LookupRowEditView(View):
    """View to edit an existing row in lookup table"""

    template_name = 'lookup/lookup_row_form.html'

    def get(self, request, table_name, pk_value):
        try:
            table_info = lookup_service.get_table_metadata(table_name)
            if not table_info:
                messages.error(request, f"Table '{table_name}' not found")
                return redirect('lookup:table_list')

            row = lookup_service.get_row(table_name, pk_value)
            if not row:
                messages.error(request, f"Row with key '{pk_value}' not found")
                return redirect('lookup:table_detail', table_name=table_name)

            context = {
                'table_info': table_info,
                'table_name': table_name,
                'columns': table_info.get('columns', []),
                'pk_column': table_info.get('pk_column'),
                'pk_value': pk_value,
                'row': row,
                'is_edit': True,
            }
            return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error loading edit form for {table_name}: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
            return redirect('lookup:table_detail', table_name=table_name)

    def post(self, request, table_name, pk_value):
        try:
            table_info = lookup_service.get_table_metadata(table_name)
            if not table_info:
                messages.error(request, f"Table '{table_name}' not found")
                return redirect('lookup:table_list')

            # Collect form data
            data = {}
            for col in table_info.get('columns', []):
                col_name = col['name']
                value = request.POST.get(col_name)

                # Handle boolean checkboxes
                if col['type'] in ('BOOLEAN', 'BOOL'):
                    value = col_name in request.POST
                elif value == '':
                    value = None

                data[col_name] = value

            # Capture old state before update so the audit log can record a diff
            old_row = lookup_service.get_row(table_name, pk_value) or {}

            # Update row
            result = lookup_service.update_row(table_name, pk_value, data)

            if result['success']:
                username = request.session.get('user_login', 'anonymous')
                user_id = str(request.session.get('user_id', ''))
                user_email = request.session.get('user_email', '')

                old_values = {}
                new_values = {}
                changed_fields = []
                for field, new_val in data.items():
                    old_val = old_row.get(field, '')
                    if str(old_val) != str(new_val):
                        old_values[field] = old_val
                        new_values[field] = new_val
                        changed_fields.append(field)

                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='UPDATE',
                    entity_type='LOOKUP_TABLE',
                    entity_name=table_name,
                    entity_id=str(pk_value),
                    action_description=(
                        f"Updated row in lookup table '{table_name}' (pk={pk_value}) - "
                        f"Changed fields: {', '.join(changed_fields) if changed_fields else 'No changes'}"
                    ),
                    old_value=json.dumps(old_values, default=str) if old_values else None,
                    new_value=json.dumps(new_values, default=str) if new_values else None,
                    field_name=', '.join(changed_fields) if changed_fields else None,
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, result['message'])
                return redirect('lookup:table_detail', table_name=table_name)
            else:
                messages.error(request, result['error'])
                context = {
                    'table_info': table_info,
                    'table_name': table_name,
                    'columns': table_info.get('columns', []),
                    'pk_column': table_info.get('pk_column'),
                    'pk_value': pk_value,
                    'row': data,
                    'is_edit': True,
                }
                return render(request, self.template_name, context)

        except Exception as e:
            logger.error(f"Error updating row in {table_name}: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
            return redirect('lookup:table_detail', table_name=table_name)


class LookupRowDeleteView(View):
    """View to delete a row from lookup table"""

    def post(self, request, table_name, pk_value):
        try:
            # Capture the row before deletion so the audit log has old_value
            old_row = lookup_service.get_row(table_name, pk_value) or {}

            result = lookup_service.delete_row(table_name, pk_value)

            if result['success']:
                username = request.session.get('user_login', 'anonymous')
                user_id = str(request.session.get('user_id', ''))
                user_email = request.session.get('user_email', '')

                audit_log_kudu_repository.log_action(
                    user_id=user_id,
                    username=username,
                    user_email=user_email,
                    action_type='DELETE',
                    entity_type='LOOKUP_TABLE',
                    entity_name=table_name,
                    entity_id=str(pk_value),
                    action_description=f"Deleted row from lookup table '{table_name}' (pk={pk_value})",
                    old_value=json.dumps(old_row, default=str) if old_row else None,
                    request_method=request.method,
                    request_path=request.path,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, result['message'])
            else:
                messages.error(request, result['error'])

        except Exception as e:
            logger.error(f"Error deleting row from {table_name}: {str(e)}")
            messages.error(request, f"Error: {str(e)}")

        return redirect('lookup:table_detail', table_name=table_name)


# =========================================================================
# API VIEWS (for AJAX/JSON responses)
# =========================================================================

class LookupTableAPIView(View):
    """API view for lookup table operations"""

    def get(self, request, table_name):
        """Get rows from lookup table as JSON"""
        try:
            search = request.GET.get('search', '')
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 25))

            result = lookup_service.get_table_rows(
                table_name=table_name,
                search=search,
                page=page,
                page_size=page_size
            )

            return JsonResponse(result)

        except Exception as e:
            logger.error(f"API error for {table_name}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)


def lookup_debug_view(request, table_name):
    """Temporary plain-HTML debug view — bypasses base template to isolate rendering."""
    from django.http import HttpResponse
    import decimal

    table_info = lookup_service.get_table_metadata(table_name)
    result = lookup_service.get_table_rows(table_name=table_name, page=1, page_size=10)
    columns = table_info.get('columns', []) if table_info else []
    rows = result['rows']

    html = [f'<h2>{table_name}</h2>']
    html.append(f'<p>pk_column: {table_info.get("pk_column") if table_info else "NONE"}</p>')
    html.append(f'<p>columns ({len(columns)}): {[c["name"] for c in columns]}</p>')
    html.append(f'<p>rows returned: {len(rows)} / total: {result["total_count"]}</p>')
    html.append('<table border="1"><thead><tr>')
    for col in columns:
        html.append(f'<th>{col["name"]}<br/><small>{col["type"]}</small></th>')
    html.append('</tr></thead><tbody>')
    for row in rows:
        html.append('<tr>')
        for col in columns:
            val = row.get(col['name'], 'KEY_MISSING')
            html.append(f'<td>{val}</td>')
        html.append('</tr>')
    html.append('</tbody></table>')
    return HttpResponse('\n'.join(html))


def lookup_debug_api(request, table_name):
    """Temporary debug endpoint — returns raw context data as JSON."""
    import decimal
    def safe(v):
        if isinstance(v, decimal.Decimal):
            return float(v)
        if isinstance(v, bool):
            return v
        return v

    table_info = lookup_service.get_table_metadata(table_name)
    result = lookup_service.get_table_rows(table_name=table_name, page=1, page_size=5)
    columns = table_info.get('columns', []) if table_info else []
    rows = result['rows']
    safe_rows = [{k: safe(v) for k, v in row.items()} for row in rows]
    return JsonResponse({
        'pk_column': table_info.get('pk_column') if table_info else None,
        'column_names': [c['name'] for c in columns],
        'column_types': {c['name']: c['type'] for c in columns},
        'row_count_db': table_info.get('row_count') if table_info else 0,
        'rows_returned': len(rows),
        'total_count': result['total_count'],
        'first_row_keys': list(rows[0].keys()) if rows else [],
        'keys_match_columns': (
            sorted([c['name'] for c in columns]) == sorted(list(rows[0].keys()))
            if rows and columns else None
        ),
        'rows': safe_rows,
    })


class LookupDropdownAPIView(View):
    """API view to get dropdown options from a lookup table"""

    def get(self, request, table_name):
        """Get dropdown options as JSON"""
        try:
            value_col = request.GET.get('value_column')
            label_col = request.GET.get('label_column')

            options = lookup_service.get_dropdown_options(
                table_name=table_name,
                value_column=value_col,
                label_column=label_col
            )

            return JsonResponse({'options': options})

        except Exception as e:
            logger.error(f"API error for dropdown {table_name}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
