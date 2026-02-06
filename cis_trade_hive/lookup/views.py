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

logger = logging.getLogger(__name__)


class LookupTableListView(View):
    """View to list all discovered lookup tables"""

    template_name = 'lookup/lookup_table_list.html'

    def get(self, request):
        try:
            tables = lookup_service.get_all_lookup_tables()

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
            columns_for_js = [{'name': col['name'], 'type': col['type']} for col in columns]

            context = {
                'table_info': table_info,
                'table_name': table_name,
                'rows': result['rows'],
                'columns': columns,
                'columns_json': mark_safe(json.dumps(columns_for_js)),
                'pk_column': table_info.get('pk_column'),
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
            logger.error(f"Error loading table {table_name}: {str(e)}")
            messages.error(request, f"Error loading table: {str(e)}")
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

            # Update row
            result = lookup_service.update_row(table_name, pk_value, data)

            if result['success']:
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
            result = lookup_service.delete_row(table_name, pk_value)

            if result['success']:
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
