"""
Query Builder Views

Single responsibility: HTTP request/response handling only.
All business logic delegated to services.
Audit logging called directly from views (project pattern).
"""

import json
import logging

from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from query_builder.services.query_execution_service import query_execution_service
from query_builder.services.report_template_service import report_template_service
from query_builder.services.export_service import export_service

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# Auth helpers — read session, no business logic
# ----------------------------------------------------------------

def _user_role(request) -> str:
    raw = request.session.get('user_groups', [])
    # user_groups is a list of dicts: [{'group_name': 'CIS-SYSOPS', ...}]
    groups = [
        (g.get('group_name', '') if isinstance(g, dict) else str(g)).upper()
        for g in raw
    ]
    for role in ('RBAC_ADMIN', 'ADMIN', 'RISK_MANAGER', 'TRADER'):
        if role in groups:
            return role
    # CIS-SYSOPS maps to ADMIN for row-limit purposes
    if 'CIS-SYSOPS' in groups:
        return 'ADMIN'
    return 'VIEWER'


def _is_admin(request) -> bool:
    return _user_role(request) in ('ADMIN', 'RBAC_ADMIN')


def _audit(request, action_type: str, entity_id: str, entity_name: str, description: str):
    audit_log_kudu_repository.log_action(
        user_id=str(request.session.get('user_id', '')),
        username=request.session.get('user_login', 'SYSTEM'),
        user_email=request.session.get('user_email', ''),
        action_type=action_type,
        entity_type='QUERY_BUILDER',
        entity_id=entity_id,
        entity_name=entity_name,
        action_description=description,
        status='SUCCESS',
        request_method=request.method,
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


# ----------------------------------------------------------------
# Pages
# ----------------------------------------------------------------

def builder(request):
    """Main visual query builder page."""
    from query_builder.services.sql_builder_service import SqlBuilderService
    schemas = query_execution_service.get_all_schemas()
    role = _user_role(request)

    context = {
        'tables':   query_execution_service.get_table_list(),
        'schemas':  json.dumps(schemas),
        'user_role': role,
        'max_rows': SqlBuilderService.ROLE_LIMITS.get(role, SqlBuilderService.DEFAULT_LIMIT),
        'is_admin': _is_admin(request),
    }
    return render(request, 'query_builder/builder.html', context)


def saved_reports(request):
    user_groups = request.session.get('user_groups', [])
    templates = report_template_service.get_accessible_templates(user_groups)
    return render(request, 'query_builder/saved_reports.html', {
        'templates': templates,
        'is_admin': _is_admin(request),
    })


def sql_editor(request):
    """Raw SQL editor — admin only."""
    if not _is_admin(request):
        return redirect('query_builder:builder')
    return render(request, 'query_builder/sql_editor.html', {'is_admin': True})


# ----------------------------------------------------------------
# APIs
# ----------------------------------------------------------------

@require_http_methods(['POST'])
def run_query(request):
    try:
        config = json.loads(request.body)
        config['user_role'] = _user_role(request)

        results, from_cache, sql = query_execution_service.run(config)

        _audit(
            request, 'QUERY',
            config.get('primary_table', ''),
            f"Query on {config.get('primary_table', '')}",
            f"Returned {len(results)} rows",
        )

        return JsonResponse({
            'success':    True,
            'rows':       results,
            'count':      len(results),
            'from_cache': from_cache,
            'sql':        sql if _is_admin(request) else None,
            'columns':    list(results[0].keys()) if results else [],
        })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except RuntimeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=503)
    except Exception as e:
        logger.error("Query builder run error: %s", e)
        return JsonResponse({'success': False, 'error': 'Query execution failed.'}, status=500)


@require_http_methods(['POST'])
def export(request):
    try:
        body   = json.loads(request.body)
        config = body.get('config', {})
        fmt    = body.get('format', 'csv').lower()
        config['user_role'] = _user_role(request)

        results, _, _ = query_execution_service.run(config)
        columns = list(results[0].keys()) if results else []

        if fmt == 'csv':
            response = StreamingHttpResponse(
                export_service.to_csv_streaming(results, columns),
                content_type='text/csv',
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.csv"'
            return response

        if fmt == 'excel':
            data = export_service.to_excel_bytes(results, columns)
            response = HttpResponse(
                data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.xlsx"'
            return response

        if fmt == 'json':
            response = StreamingHttpResponse(
                export_service.to_json_streaming(results),
                content_type='application/json',
            )
            response['Content-Disposition'] = 'attachment; filename="query_results.json"'
            return response

        if fmt == 'pdf':
            title    = body.get('title', 'Query Results')
            subtitle = body.get('subtitle', '')
            username = request.session.get('user_login', '')
            data = export_service.to_pdf_bytes(
                results, columns,
                title=title,
                subtitle=subtitle or f"Table: {config.get('primary_table', '')}  |  Rows: {len(results):,}",
                generated_by=username,
            )
            response = HttpResponse(data, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="query_results.pdf"'
            return response

        return JsonResponse({'error': f'Unsupported format: {fmt}'}, status=400)

    except Exception as e:
        logger.error("Export error: %s", e)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def api_schema(request):
    table = request.GET.get('table', '').strip()
    from query_builder.services.sql_builder_service import SqlBuilderService
    if table not in SqlBuilderService.TABLES:
        return JsonResponse({'error': 'Invalid table'}, status=400)
    schema = query_execution_service.get_table_schema(table)
    return JsonResponse({'table': table, 'columns': schema})


@require_http_methods(['GET'])
def api_join_options(request):
    table = request.GET.get('table', '').strip()
    from query_builder.services.sql_builder_service import SqlBuilderService
    if table not in SqlBuilderService.TABLES:
        return JsonResponse({'error': 'Invalid table'}, status=400)
    return JsonResponse({'options': query_execution_service.get_join_options(table)})


@require_http_methods(['POST'])
def save_template(request):
    try:
        data = json.loads(request.body)
        username = request.session.get('user_login', 'SYSTEM')
        report_template_service.save(data, username)
        _audit(request, 'CREATE', 'template', data.get('template_name', ''), 'Saved report template')
        return JsonResponse({'success': True})
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(['POST'])
def delete_template(request, template_id: int):
    if not _is_admin(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        username = request.session.get('user_login', 'SYSTEM')
        report_template_service.delete(template_id, username)
        _audit(request, 'DELETE', str(template_id), 'Report Template', 'Deleted report template')
        return JsonResponse({'success': True})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['POST'])
def run_raw_sql(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        body = json.loads(request.body)
        sql  = body.get('sql', '').strip()

        blocked = ('INSERT', 'UPSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE')
        sql_upper = sql.upper()
        for kw in blocked:
            if sql_upper.startswith(kw) or f' {kw} ' in sql_upper:
                return JsonResponse({'error': f'Write operation "{kw}" is not allowed.'}, status=400)

        from query_builder.repositories.query_builder_repository import query_builder_repository
        results, _ = query_builder_repository.execute(sql, [], 'cis_trade', use_cache=False)

        _audit(request, 'QUERY', 'raw_sql', 'SQL Editor', f"Raw SQL: {sql[:200]}")

        return JsonResponse({
            'success': True,
            'rows':    results,
            'count':   len(results),
            'columns': list(results[0].keys()) if results else [],
        })

    except RuntimeError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=503)
    except Exception as e:
        logger.error("Raw SQL error: %s", e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
