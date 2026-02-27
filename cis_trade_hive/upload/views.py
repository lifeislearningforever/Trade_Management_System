"""
Upload Views

HTTP request handlers for file upload functionality.
Implements:
- File upload with drag & drop support
- File validation and preview
- Schema editing before ingestion
- Hive external table creation
- Upload history and management
"""

import json
import os
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.conf import settings

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from .services.upload_service import UploadService, FileValidationService
from .repositories.upload_kudu_repository import UploadKuduRepository

# Initialize services
upload_service = UploadService()
validation_service = FileValidationService()


def get_user_info(request):
    """Get user info from session."""
    return {
        'username': request.session.get('user_login', 'anonymous'),
        'user_id': str(request.session.get('user_id', '')),
        'user_email': request.session.get('user_email', '')
    }


# =============================================================================
# UPLOAD LIST & DASHBOARD
# =============================================================================

def upload_list(request):
    """List all uploads with search, filter, and pagination."""
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    file_type_filter = request.GET.get('file_type', '').strip()

    uploads = upload_service.get_all_uploads(
        status=status_filter if status_filter else None,
        file_type=file_type_filter if file_type_filter else None,
        search=search_query if search_query else None
    )

    # Pagination
    paginator = Paginator(uploads, 25)
    page = request.GET.get('page', 1)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Get statistics
    stats = upload_service.get_statistics()

    context = {
        'page_obj': page_obj,
        'uploads': page_obj.object_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'file_type_filter': file_type_filter,
        'status_choices': upload_service.get_status_choices(),
        'file_type_choices': upload_service.get_file_type_choices(),
        'stats': stats,
        'total_count': len(uploads),
    }

    return render(request, 'upload/upload_list.html', context)


def upload_dashboard(request):
    """Upload dashboard with statistics."""
    stats = upload_service.get_statistics()

    # Get recent uploads
    recent_uploads = upload_service.get_all_uploads()[:10]

    context = {
        'stats': stats,
        'recent_uploads': recent_uploads,
    }

    return render(request, 'upload/upload_dashboard.html', context)


# =============================================================================
# UPLOAD CREATE (File Upload & Validation)
# =============================================================================

@require_http_methods(["GET", "POST"])
def upload_create(request):
    """
    Upload new file with validation.
    GET: Show upload form
    POST: Process file upload and validate
    """
    user_info = get_user_info(request)

    if request.method == 'POST':
        try:
            # Check if file was uploaded
            if 'file' not in request.FILES:
                messages.error(request, 'No file was uploaded')
                return redirect('upload:create')

            uploaded_file = request.FILES['file']
            file_name = uploaded_file.name
            description = request.POST.get('description', '').strip()

            # Validate and create upload record
            upload_id, validation_result = upload_service.validate_and_create_upload(
                file_obj=uploaded_file,
                file_name=file_name,
                description=description,
                created_by=user_info['username']
            )

            if upload_id:
                # Log audit
                audit_log_kudu_repository.log_action(
                    user_id=user_info['user_id'],
                    username=user_info['username'],
                    user_email=user_info['user_email'],
                    action_type='CREATE',
                    entity_type='FILE_UPLOAD',
                    entity_id=upload_id,
                    entity_name=file_name,
                    action_description=f"Uploaded file: {file_name} ({validation_result.row_count} rows, {validation_result.column_count} columns)",
                    new_value=json.dumps({
                        'file_name': file_name,
                        'file_size': validation_result.file_size,
                        'file_type': validation_result.file_type,
                        'row_count': validation_result.row_count,
                        'column_count': validation_result.column_count
                    }),
                    request_method='POST',
                    request_path=request.path,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    status='SUCCESS'
                )

                messages.success(request, f'File "{file_name}" uploaded and validated successfully!')
                return redirect('upload:preview', upload_id=upload_id)
            else:
                # Validation failed
                for error in validation_result.errors:
                    messages.error(request, error)
                for warning in validation_result.warnings:
                    messages.warning(request, warning)

        except Exception as e:
            messages.error(request, f'Upload error: {str(e)}')

    context = {
        'supported_formats': ', '.join(FileValidationService.SUPPORTED_EXTENSIONS.keys()),
        'max_file_size': FileValidationService.MAX_FILE_SIZE,
        'max_file_size_mb': FileValidationService.MAX_FILE_SIZE // (1024 * 1024),
    }

    return render(request, 'upload/upload_form.html', context)


# =============================================================================
# UPLOAD PREVIEW & SCHEMA EDITING
# =============================================================================

def upload_preview(request, upload_id: str):
    """
    Preview uploaded file and edit schema before ingestion.
    """
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        raise Http404("Upload not found")

    # Parse JSON fields
    schema = []
    sample_data = []

    try:
        schema_json = upload.get('schema_json', '[]')
        if schema_json:
            schema = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
    except json.JSONDecodeError:
        schema = []

    try:
        sample_json = upload.get('sample_data_json', '[]')
        if sample_json:
            sample_data = json.loads(sample_json) if isinstance(sample_json, str) else sample_json
    except json.JSONDecodeError:
        sample_data = []

    # Available Hive types for schema editing
    hive_types = [
        'STRING', 'BIGINT', 'INT', 'SMALLINT', 'TINYINT',
        'DOUBLE', 'FLOAT', 'DECIMAL(20,6)', 'BOOLEAN',
        'DATE', 'TIMESTAMP'
    ]

    context = {
        'upload': upload,
        'schema': schema,
        'sample_data': sample_data[:20],  # Limit preview rows
        'hive_types': hive_types,
        'can_ingest': upload.get('status') in [
            UploadKuduRepository.STATUS_VALIDATED,
            UploadKuduRepository.STATUS_VALIDATION_FAILED  # Allow retry
        ],
    }

    return render(request, 'upload/upload_preview.html', context)


@require_http_methods(["POST"])
def upload_update_schema(request, upload_id: str):
    """
    Update schema for uploaded file.
    """
    user_info = get_user_info(request)
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        return JsonResponse({'success': False, 'error': 'Upload not found'}, status=404)

    try:
        # Parse schema from form
        schema_data = json.loads(request.body)
        columns = schema_data.get('columns', [])

        # Update upload record
        success = upload_service.update_upload(
            upload_id,
            {'schema_json': columns},
            user_info['username']
        )

        if success:
            return JsonResponse({'success': True, 'message': 'Schema updated'})
        else:
            return JsonResponse({'success': False, 'error': 'Failed to update schema'})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =============================================================================
# INGEST TO HIVE
# =============================================================================

@require_http_methods(["POST"])
def upload_ingest(request, upload_id: str):
    """
    Ingest uploaded file to Hive external table.
    """
    user_info = get_user_info(request)
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        messages.error(request, 'Upload not found')
        return redirect('upload:list')

    try:
        # Get custom table name if provided
        table_name = request.POST.get('table_name', '').strip()

        # Parse schema from form
        schema_json = upload.get('schema_json', '[]')
        columns = json.loads(schema_json) if isinstance(schema_json, str) else schema_json

        # Get HDFS path (in production, file would be copied to HDFS)
        hdfs_path = upload.get('hdfs_path', '')

        # Perform ingestion
        success, message = upload_service.ingest_to_hive(
            upload_id=upload_id,
            table_name=table_name if table_name else None,
            columns=columns,
            file_path=hdfs_path,
            updated_by=user_info['username']
        )

        if success:
            # Log audit
            audit_log_kudu_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='INGEST',
                entity_type='FILE_UPLOAD',
                entity_id=upload_id,
                entity_name=upload.get('file_name', ''),
                action_description=message,
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, message)
        else:
            messages.error(request, message)

    except Exception as e:
        messages.error(request, f'Ingestion error: {str(e)}')

    return redirect('upload:detail', upload_id=upload_id)


# =============================================================================
# UPLOAD DETAIL
# =============================================================================

def upload_detail(request, upload_id: str):
    """View upload details."""
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        raise Http404("Upload not found")

    # Parse JSON fields
    schema = []
    sample_data = []
    validation_errors = []

    try:
        schema_json = upload.get('schema_json', '[]')
        schema = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
    except:
        pass

    try:
        sample_json = upload.get('sample_data_json', '[]')
        sample_data = json.loads(sample_json) if isinstance(sample_json, str) else sample_json
    except:
        pass

    try:
        errors_json = upload.get('validation_errors_json', '[]')
        validation_errors = json.loads(errors_json) if isinstance(errors_json, str) else errors_json
    except:
        pass

    # Get table preview if completed
    table_preview = []
    if upload.get('status') == UploadKuduRepository.STATUS_COMPLETED:
        table_name = upload.get('target_table_name')
        if table_name:
            from .repositories.upload_kudu_repository import upload_kudu_repository
            table_preview = upload_kudu_repository.get_table_preview(table_name, limit=10)

    context = {
        'upload': upload,
        'schema': schema,
        'sample_data': sample_data[:10],
        'validation_errors': validation_errors,
        'table_preview': table_preview,
        'can_edit': upload.get('status') in [
            UploadKuduRepository.STATUS_PENDING,
            UploadKuduRepository.STATUS_VALIDATED,
            UploadKuduRepository.STATUS_VALIDATION_FAILED
        ],
        'can_ingest': upload.get('status') == UploadKuduRepository.STATUS_VALIDATED,
        'can_delete': upload.get('status') not in [
            UploadKuduRepository.STATUS_INGESTING
        ],
    }

    return render(request, 'upload/upload_detail.html', context)


# =============================================================================
# UPLOAD DELETE
# =============================================================================

@require_http_methods(["POST"])
def upload_delete(request, upload_id: str):
    """Soft delete upload."""
    user_info = get_user_info(request)
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        messages.error(request, 'Upload not found')
        return redirect('upload:list')

    try:
        success = upload_service.delete_upload(upload_id, user_info['username'])

        if success:
            # Log audit
            audit_log_kudu_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='DELETE',
                entity_type='FILE_UPLOAD',
                entity_id=upload_id,
                entity_name=upload.get('file_name', ''),
                action_description=f"Deleted upload: {upload.get('file_name', '')}",
                request_method='POST',
                request_path=request.path,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                status='SUCCESS'
            )

            messages.success(request, 'Upload deleted successfully')
        else:
            messages.error(request, 'Failed to delete upload')

    except Exception as e:
        messages.error(request, f'Delete error: {str(e)}')

    return redirect('upload:list')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@require_http_methods(["POST"])
def api_validate_file(request):
    """
    API: Validate file without creating upload record.
    Used for real-time validation during upload.
    """
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'valid': False, 'error': 'No file provided'})

        uploaded_file = request.FILES['file']
        result = validation_service.validate_file(uploaded_file, uploaded_file.name)

        return JsonResponse({
            'valid': result.is_valid,
            'errors': result.errors,
            'warnings': result.warnings,
            'file_type': result.file_type,
            'encoding': result.encoding,
            'delimiter': result.delimiter,
            'has_header': result.has_header,
            'row_count': result.row_count,
            'column_count': result.column_count,
            'columns': result.columns,
            'sample_data': result.sample_data[:5],  # First 5 rows for preview
            'file_size': result.file_size,
        })

    except Exception as e:
        return JsonResponse({'valid': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_upload_status(request, upload_id: str):
    """
    API: Get upload status.
    Used for polling during ingestion.
    """
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        return JsonResponse({'error': 'Upload not found'}, status=404)

    return JsonResponse({
        'upload_id': upload_id,
        'status': upload.get('status', ''),
        'file_name': upload.get('file_name', ''),
        'target_table_name': upload.get('target_table_name', ''),
        'row_count': upload.get('row_count', 0),
    })


@require_http_methods(["GET"])
def api_table_preview(request, upload_id: str):
    """
    API: Get preview data from created Hive table.
    """
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        return JsonResponse({'error': 'Upload not found'}, status=404)

    if upload.get('status') != UploadKuduRepository.STATUS_COMPLETED:
        return JsonResponse({'error': 'Table not yet created'}, status=400)

    table_name = upload.get('target_table_name')
    if not table_name:
        return JsonResponse({'error': 'No table name'}, status=400)

    from .repositories.upload_kudu_repository import upload_kudu_repository
    preview = upload_kudu_repository.get_table_preview(table_name, limit=20)

    return JsonResponse({
        'table_name': table_name,
        'preview': preview,
        'row_count': len(preview),
    })
