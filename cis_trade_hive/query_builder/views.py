"""
Query Builder Views
"""

import json
import logging

from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from query_builder.repositories.query_builder_repository import query_builder_repository
from query_builder.repositories.report_template_repository import report_template_repository
from query_builder.services.query_builder_service import (
    query_builder_service, TABLES, ROLE_LIMITS
)
from query_builder.services.export_service import export_service

logger = logging.getLogger(__name__)


def _get_user_role(request) -> str:
    groups = request.session.get('user_groups', [])
    for role in ('RBAC_ADMIN', 'ADMIN', 'RISK_MANAGER', 'TRADER'):
        if role in [g.upper() for g in groups]:
            return role
    return 'VIEWER'


def _is_admin(request) -> bool:
    return _get_user_role(request) in ('ADMIN', 'RBAC_ADMIN')


def builder(request):
    """Main query builder page."""
    user_role = _get_user_role(request)
    schemas = query_builder_repository.get_all_schemas(list(TABLES.keys()))

    context = {
        'tables': query_builder_service.get_table_list(),
        'schemas': json.dumps(schemas),
        'user_role': user_role,
        'max_rows': ROLE_LIMITS.get(user_role, 1000),
        'is_admin': _is_admin(request),
    }
    return render(request, 'query_builder/builder.html', context)


@require_http_methods(['POST'])
def run_query(request):
    """API: Build and execute a query from config JSON."""
    try:
        config = json.loads(request.body)
        config['user_role'] = _get_user_role(request)

        sql, params = query_builder_service.build(config)
        results, from_cache = query_builder_repository.execute(
            sql, params,
            primary_table=config['primary_table']
        )

        # Audit log
        username = request.session.get('user_login', 'SYSTEM')
        audit_log_kudu_repository.log_action(
            user_id=str(request.session.get('user_id', '')),
            username=username,
            user_email=request.session.get('user_email', ''),
            action_type='QUERY',
            entity_type='QUERY_BUILDER',
            entity_id=config.get('primary_table', ''),
            entity_name=f"Query on {config.get('primary_table', '')}",
            action_description=f"Executed query: {len(results)} rows returned",
            status='SUCCESS',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return JsonResponse({
            'success': True,
            'rows': results,
            'count': len(results),
            'from_cache': from_cache,
            'sql': sql if _is_admin(request) else None,
            'columns': list(results[0].keys()) if results else [],
        })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except RuntimeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=503)
    except Exception as e:
        logger.error(f"Query builder run error: {e}")
        return JsonResponse({'success': False, 'error': 'Query execution failed. Check your filters and try again.'}, status=500)


@require_http_methods(['GET'])
def api_schema(request):
    """API: Return column schema for a table."""
    table = request.GET.get('table', '').strip()
    if table not in TABLES:
        return JsonResponse({'error': 'Invalid table'}, status=400)
    schema = query_builder_repository.get_table_schema(table)
    return JsonResponse({'table': table, 'columns': schema})


@require_http_methods(['GET'])
def api_join_options(request):
    """API: Return valid join targets for a primary table."""
    table = request.GET.get('table', '').strip()
    if table not in TABLES:
        return JsonResponse({'error': 'Invalid table'}, status=400)
    options = query_builder_service.get_join_options(table)
    return JsonResponse({'options': options})


@require_http_methods(['POST'])
def export(request):
    """Export query results in requested format."""
    try:
        body = json.loads(request.body)
        config = body.get('config', {})
        fmt = body.get('format', 'csv').lower()
        config['user_role'] = _get_user_role(request)

        sql, params = query_builder_service.build(config)
        results, _ = query_builder_repository.execute(sql, params, config['primary_table'])
        columns = list(results[0].keys()) if results else []

        if fmt == 'csv':
            response = StreamingHttpResponse(
                export_service.to_csv_streaming(results, columns),
                content_type='text/csv'
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.csv"'
            return response

        elif fmt == 'excel':
            data = export_service.to_excel_bytes(results, columns)
            response = HttpResponse(
                data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.xlsx"'
            return response

        elif fmt == 'json':
            response = StreamingHttpResponse(
                export_service.to_json_streaming(results),
                content_type='application/json'
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.json"'
            return response

        else:
            return JsonResponse({'error': f'Unsupported format: {fmt}'}, status=400)

    except Exception as e:
        logger.error(f"Export error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ------------------------------------------------------------------
# Saved Report Templates
# ------------------------------------------------------------------

def saved_reports(request):
    """List saved report templates."""
    user_groups = request.session.get('user_groups', [])
    templates = report_template_repository.get_all(user_groups)
    return render(request, 'query_builder/saved_reports.html', {
        'templates': templates,
        'is_admin': _is_admin(request),
    })


@require_http_methods(['POST'])
def save_template(request):
    """Save current query config as a named template."""
    try:
        data = json.loads(request.body)
        username = request.session.get('user_login', 'SYSTEM')
        success = report_template_repository.create(data, username)
        if success:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Failed to save template'}, status=500)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(['POST'])
def delete_template(request, template_id: int):
    """Soft-delete a template (admin only)."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    username = request.session.get('user_login', 'SYSTEM')
    success = report_template_repository.delete(template_id, username)
    return JsonResponse({'success': success})


# ------------------------------------------------------------------
# SQL Editor (admin only)
# ------------------------------------------------------------------

def sql_editor(request):
    """Raw SQL editor — admin only."""
    if not _is_admin(request):
        return redirect('query_builder:builder')
    return render(request, 'query_builder/sql_editor.html', {'is_admin': True})


@require_http_methods(['POST'])
def run_raw_sql(request):
    """Execute raw SQL — admin only. Blocks write statements."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        body = json.loads(request.body)
        sql = body.get('sql', '').strip()

        # Block write operations
        sql_upper = sql.upper()
        blocked = ('INSERT', 'UPSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE')
        for kw in blocked:
            if sql_upper.startswith(kw) or f' {kw} ' in sql_upper:
                return JsonResponse({'error': f'Write operation "{kw}" is not allowed in SQL editor.'}, status=400)

        results, from_cache = query_builder_repository.execute(sql, [], 'cis_trade', use_cache=False)

        username = request.session.get('user_login', 'SYSTEM')
        audit_log_kudu_repository.log_action(
            user_id=str(request.session.get('user_id', '')),
            username=username,
            user_email=request.session.get('user_email', ''),
            action_type='QUERY',
            entity_type='QUERY_BUILDER_SQL',
            entity_id='raw_sql',
            entity_name='Raw SQL Editor',
            action_description=f"Executed raw SQL: {sql[:200]}",
            status='SUCCESS',
            request_method='POST',
            request_path=request.path,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return JsonResponse({
            'success': True,
            'rows': results,
            'count': len(results),
            'columns': list(results[0].keys()) if results else [],
        })
    except RuntimeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=503)
    except Exception as e:
        logger.error(f"Raw SQL error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
