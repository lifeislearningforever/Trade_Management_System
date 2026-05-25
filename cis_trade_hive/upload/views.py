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
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse, Http404, HttpResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings

from core.audit.audit_kudu_repository import audit_log_kudu_repository
from .services.upload_service import UploadService, FileValidationService
from .repositories.upload_kudu_repository import UploadKuduRepository

logger = logging.getLogger('upload')
logger.warning("upload.views MODULE LOADED — version hdfs-put-27e5e72")
print("upload.views MODULE LOADED — version hdfs-put-27e5e72", flush=True)

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

    # Merge session-only (TEMP-) uploads so they appear in the list
    db_ids = {u.get('upload_id') for u in uploads}
    session_only_count = 0
    for key, val in request.session.items():
        if not key.startswith('upload_TEMP-'):
            continue
        if not isinstance(val, dict):
            continue
        uid = val.get('upload_id', key[len('upload_'):])
        if uid in db_ids:
            continue
        session_only_count += 1
        if status_filter and val.get('status') != status_filter:
            continue
        if file_type_filter and val.get('file_type') != file_type_filter:
            continue
        if search_query:
            haystack = (val.get('file_name', '') + ' ' + val.get('description', '')).lower()
            if search_query.lower() not in haystack:
                continue
        uploads = [val] + list(uploads)

    def _sort_key(u):
        v = u.get('created_at', '')
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return str(v) if v else ''
    uploads = sorted(uploads, key=_sort_key, reverse=True)

    # Pagination
    paginator = Paginator(uploads, 25)
    page = request.GET.get('page', 1)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    # Get statistics — add session-only uploads to total so the count matches the list
    stats = upload_service.get_statistics()
    stats['total_uploads'] = stats.get('total_uploads', 0) + session_only_count

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
        # True if any visible upload is still processing — triggers auto-refresh
        'has_ingesting': any(
            u.get('status') == UploadKuduRepository.STATUS_INGESTING
            for u in page_obj.object_list
        ),
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

    Supports two modes:
    1. Standard upload - auto-detect schema
    2. Metadata-driven upload - use cis_datasource_mng config
    """
    print(f"[UPLOAD_CREATE] method={request.method} path={request.path}", flush=True)
    logger.warning(f"[UPLOAD_CREATE] method={request.method} path={request.path}")
    user_info = get_user_info(request)

    if request.method == 'POST':
        print("[UPLOAD_CREATE] POST received", flush=True)
        logger.warning("[UPLOAD_CREATE] POST received")
        try:
            # GATE0 — first line of try block
            logger.warning("[GATE0] entered try block")
            print("[GATE0] entered try block", flush=True)

            # Check if file was uploaded
            if 'file' not in request.FILES:
                logger.warning("[GATE0a] no file in request.FILES — redirecting")
                messages.error(request, 'No file was uploaded')
                return redirect('upload:create')

            uploaded_file = request.FILES['file']
            file_name = uploaded_file.name
            description = request.POST.get('description', '').strip()
            use_datasource_config = request.POST.get('use_datasource_config', '') == 'true'

            logger.warning(f"[GATE0b] file_name={file_name!r} use_datasource_config={use_datasource_config} post_keys={list(request.POST.keys())}")
            print(f"[GATE0b] file_name={file_name!r} use_datasource_config={use_datasource_config}", flush=True)

            # Check if datasource config exists for this file.
            # NOTE: use_datasource_config checkbox may not be submitted when the
            # datasource config div is hidden (d-none). Always use datasource config
            # if one is found for the filename — don't rely on the checkbox value.
            try:
                datasource_config = upload_service.get_datasource_config(file_name)
                logger.warning(f"[GATE1] file_name={file_name!r} use_datasource_config={use_datasource_config} datasource_config={'FOUND' if datasource_config else 'NONE'}")
                print(f"[GATE1] file_name={file_name!r} use_datasource_config={use_datasource_config} datasource_config={'FOUND' if datasource_config else 'NONE'}", flush=True)
            except Exception as _dse:
                logger.error(f"[GATE1-ERR] get_datasource_config raised: {_dse}", exc_info=True)
                print(f"[GATE1-ERR] get_datasource_config raised: {_dse}", flush=True)
                datasource_config = None

            # Use datasource config whenever one exists for this file — checkbox is
            # unreliable because the div is hidden (d-none) when AJAX finds no config.
            if datasource_config:
                # Use metadata-driven validation
                validation_result = upload_service.validate_with_datasource_config(
                    file_obj=uploaded_file,
                    file_name=file_name,
                    datasource_config=datasource_config
                )

                logger.warning(f"[GATE2] validation is_valid={validation_result.is_valid} row_count={validation_result.row_count} all_data={len(validation_result.all_data)} errors={validation_result.errors}")
                print(f"[GATE2] is_valid={validation_result.is_valid} row_count={validation_result.row_count} all_data={len(validation_result.all_data)}", flush=True)

                if validation_result.is_valid:
                    # Create upload record with datasource config
                    upload_data = {
                        'file_name': file_name,
                        'original_file_name': file_name,
                        'file_size': validation_result.file_size,
                        'file_type': validation_result.file_type,
                        'row_count': validation_result.row_count,
                        'column_count': validation_result.column_count,
                        'delimiter': validation_result.delimiter,
                        'has_header': validation_result.has_header,
                        'encoding': validation_result.encoding,
                        'description': description,
                        'schema': validation_result.columns,
                        'sample_data': validation_result.all_data or validation_result.sample_data,
                        'target_table_name': datasource_config.get('target_table', ''),
                    }

                    from .repositories.upload_kudu_repository import upload_kudu_repository
                    upload_id = upload_kudu_repository.create_upload(upload_data, user_info['username'])

                    logger.warning(f"[GATE3] upload_id={upload_id!r}")
                    print(f"[GATE3] upload_id={upload_id!r}", flush=True)

                    if upload_id:
                        # Store datasource_id for later use
                        upload_kudu_repository.update_upload(upload_id, {
                            'status': 'VALIDATED',
                            'description': f"{description}\n[Datasource: {datasource_config.get('source_id', '')}]"
                        }, user_info['username'])

                        # -------------------------------------------------------
                        # INSERT all rows into raw target table NOW (at upload
                        # time) while the file is still in memory. This avoids
                        # all cross-worker/cross-node file path problems.
                        # The ingest button will only run the ETL steps (Step 0
                        # standardize onward) — no file needed at ingest time.
                        # -------------------------------------------------------
                        from .repositories.upload_kudu_repository import upload_kudu_repository as _repo
                        from core.repositories.impala_connection import impala_manager as _imp
                        import re as _re
                        from datetime import datetime as _dt

                        # Determine processing_date: always read from MRA_PC_DATE.txt first.
                        # Fall back to description field, then today only as last resort.
                        from upload.repositories.datasource_repository import datasource_repository as _dsr_pd
                        _processing_date = _dsr_pd.get_processing_date_from_hdfs()
                        if not _processing_date:
                            _pd_match = _re.search(r'processing_date[=:\s]+(\d{8})', description or '')
                            _processing_date = _pd_match.group(1) if _pd_match else _dt.now().strftime('%Y%m%d')
                        logger.warning(f"[upload:direct] processing_date={_processing_date}")

                        # all_data is already fully parsed by validate_with_datasource_config.
                        # No file re-read. No service layer fallback chain. Direct INSERT.
                        _all_rows = list(validation_result.all_data)
                        _target_table = datasource_config.get('target_table', '')
                        _src_id = _target_table.lower().split('.')[-1]
                        logger.warning(f"[upload:direct] {len(_all_rows)} rows → {_target_table} "
                                       f"src_id={_src_id} processing_date={_processing_date}")
                        print(f"[upload:direct] {len(_all_rows)} rows → {_target_table} src_id={_src_id}", flush=True)

                        # --- Pre-insert: detect key columns from the data ---
                        _col_names = list(_all_rows[0].keys()) if _all_rows else []
                        _isin_col = next((c for c in ('isin_code', 'isin') if c in _col_names), None)
                        _port_col = next((c for c in ('portfolio', 'portfolio_name', 'account_name') if c in _col_names), None)
                        _basis_col = next((c for c in ('position_basis',) if c in _col_names), None)
                        _date_col  = next((c for c in ('reporting_date', 'position_date', 'price_date') if c in _col_names), None)
                        _key_cols = [c for c in (_port_col, _isin_col, _basis_col, _date_col) if c]

                        # --- Fix 2: Skip rows with null/empty key fields (warn, don't block) ---
                        if _key_cols:
                            _null_row_nums = [
                                i + 1 for i, r in enumerate(_all_rows)
                                if any(not str(r.get(c) or '').strip() for c in _key_cols)
                            ]
                            if _null_row_nums:
                                _null_msg = (
                                    f"Skipped {len(_null_row_nums)} row(s) with null/empty key fields "
                                    f"({', '.join(_key_cols)}): rows {_null_row_nums[:10]}"
                                    + (' …' if len(_null_row_nums) > 10 else '')
                                )
                                logger.warning(f"[upload:direct] {_null_msg}")
                                messages.warning(request, _null_msg)
                                _null_set = set(_null_row_nums)
                                _all_rows = [
                                    r for i, r in enumerate(_all_rows)
                                    if (i + 1) not in _null_set
                                ]

                        # --- Fix 1: Deduplicate before insert ---
                        _dedup_key_cols = _key_cols or _col_names
                        _seen_keys = set()
                        _unique_rows = []
                        _dup_count = 0
                        for _r in _all_rows:
                            _k = tuple(str(_r.get(c, '')).strip() for c in _dedup_key_cols)
                            if _k not in _seen_keys:
                                _seen_keys.add(_k)
                                _unique_rows.append(_r)
                            else:
                                _dup_count += 1
                        if _dup_count > 0:
                            logger.warning(f"[upload:direct] removed {_dup_count} duplicate rows, {len(_unique_rows)} unique remain")
                        _all_rows = _unique_rows

                        # Get target table column list from Impala.
                        # Exclude processing_date — it is the Hive partition key,
                        # not a regular column in the SELECT list.
                        from upload.repositories.datasource_repository import datasource_repository as _dsr
                        _tbl_info = _dsr.get_table_info(_target_table, 'gmp_cis')
                        _tbl_cols = [c['name'] for c in _tbl_info.get('columns', [])
                                     if c['name'].lower() != 'processing_date']
                        logger.warning(f"[upload:direct] tbl_cols={_tbl_cols}")
                        print(f"[upload:direct] tbl_cols={_tbl_cols}", flush=True)

                        POSITION_BASIS = {
                            'cis_user_sta_adhoc_position_1': 'TRADE_DATE',
                            'cis_user_sta_adhoc_position_2': 'TRADE_DATE',
                            'cis_user_sta_adhoc_position_3': 'TRADE_DATE',
                            'cis_user_sta_adhoc_position_4': 'SETTLE_DATE',
                            'cis_user_sta_adhoc_position_5': 'SETTLE_DATE',
                        }
                        # Fixed server-injected columns (NOT including processing_date —
                        # that goes in PARTITION clause, not in the SELECT list)
                        _fixed = {
                            'src_id': _src_id,
                            'src_system': 'USER_UPLOAD',
                            'sub_system': 'user',
                            'data_cat': 'sta',
                            'data_frq': 'adhoc',
                            'position_basis': POSITION_BASIS.get(_src_id, 'TRADE_DATE'),
                        }

                        # Build desc early (before thread so messages are correct)
                        _desc_parts = [
                            f"{description}",
                            f"[Datasource: {datasource_config.get('source_id', '')}]",
                            f"processing_date={_processing_date}",
                        ]
                        if _dup_count > 0:
                            _desc_parts.append(f"{_dup_count} duplicates removed")
                        _desc = '\n'.join(_desc_parts)

                        if not _all_rows or not _tbl_cols:
                            logger.error(f"[upload:direct] SKIP — all_rows={len(_all_rows)} tbl_cols={len(_tbl_cols)} — nothing to insert")
                            _repo.update_upload(upload_id, {
                                'status': 'VALIDATED',
                                'description': _desc,
                                'row_count': 0,
                            }, user_info['username'])
                            messages.warning(request, 'No rows to insert — check file format.')
                            return redirect('upload:detail', upload_id=upload_id)

                        # Mark INGESTING immediately — background thread does the work.
                        # This prevents the Gunicorn 30 s timeout on large files (800+ rows).
                        _repo.update_upload(upload_id, {
                            'status': UploadKuduRepository.STATUS_INGESTING,
                            'description': _desc,
                            'row_count': len(_all_rows),
                        }, user_info['username'])

                        # Capture everything the thread needs before the request ends
                        _t_upload_id    = upload_id
                        _t_rows         = _all_rows
                        _t_tbl_cols     = _tbl_cols
                        _t_non_part     = _tbl_cols
                        _t_fixed        = _fixed
                        _t_target       = _target_table
                        _t_pd           = _processing_date
                        _t_desc         = _desc
                        _t_username     = user_info['username']
                        _t_dup_count    = _dup_count

                        def _sql_escape(_v: str) -> str:
                            _v = _v.replace('\\', '\\\\')
                            _v = _v.replace("'", "\\'")
                            _v = _v.replace('\n', '\\n')
                            _v = _v.replace('\r', '\\r')
                            _v = _v.replace('\0', '')
                            return _v

                        def _build_direct_row_sql(_row, _cols, _fix, _tbl, _pd):
                            _col_exprs = []
                            for _col in _cols:
                                _cl = _col.lower()
                                if _cl in _fix:
                                    _v = str(_fix[_cl])
                                else:
                                    _v = str(_row.get(_col) or _row.get(_cl) or '')
                                _col_exprs.append(f"'{_sql_escape(_v)}' AS `{_col}`")
                            return (
                                f"INSERT INTO gmp_cis.{_tbl} "
                                f"PARTITION (processing_date='{_pd}') "
                                f"SELECT {', '.join(_col_exprs)}"
                            )

                        def _do_direct_insert():
                            from core.repositories.impala_connection import impala_manager as _imp2
                            from upload.repositories.upload_kudu_repository import upload_kudu_repository as _repo2

                            # Drop existing partition so re-runs don't double-insert
                            try:
                                _imp2.execute_write(
                                    f"ALTER TABLE gmp_cis.{_t_target} "
                                    f"DROP IF EXISTS PARTITION (processing_date='{_t_pd}')",
                                    database='gmp_cis'
                                )
                                logger.warning(f"[upload:direct:bg] dropped partition processing_date={_t_pd}")
                            except Exception as _dp_ex:
                                logger.warning(f"[upload:direct:bg] drop partition skipped: {_dp_ex}")

                            _ins = 0
                            _fail = 0
                            for _ri, _row in enumerate(_t_rows):
                                _sql = _build_direct_row_sql(_row, _t_non_part, _t_fixed, _t_target, _t_pd)
                                _ok = _imp2.execute_write(_sql, database='gmp_cis')
                                if _ok:
                                    _ins += 1
                                    if _ins % 100 == 0:
                                        logger.warning(f"[upload:direct:bg] {_ins}/{len(_t_rows)} inserted")
                                else:
                                    _fail += 1
                                    logger.error(f"[upload:direct:bg] row {_ri} FAILED. SQL={_sql[:200]}")
                                    if _fail > 10:
                                        logger.error(f"[upload:direct:bg] too many failures — aborting")
                                        break

                            if _ins > 0:
                                try:
                                    _imp2.execute_write(
                                        f"INVALIDATE METADATA gmp_cis.{_t_target}",
                                        database='gmp_cis'
                                    )
                                except Exception:
                                    pass
                                _final_desc = _t_desc + (f"\n{_ins} rows inserted" if _fail else '')
                                _repo2.update_upload(_t_upload_id, {
                                    'status': UploadKuduRepository.STATUS_COMPLETED,
                                    'description': _final_desc,
                                    'row_count': _ins,
                                }, _t_username)
                                logger.warning(f"[upload:direct:bg] DONE — {_ins} rows into {_t_target}")
                            else:
                                _repo2.update_upload(_t_upload_id, {
                                    'status': UploadKuduRepository.STATUS_FAILED,
                                    'description': f"{_t_desc}\nAll rows failed to insert",
                                }, _t_username)
                                logger.error(f"[upload:direct:bg] FAILED — 0 rows inserted into {_t_target}")

                        import threading as _threading
                        _t = _threading.Thread(
                            target=_do_direct_insert,
                            daemon=True,
                            name=f"direct-{upload_id[:8]}"
                        )
                        _t.start()
                        logger.warning(f"[upload:direct] background insert started for {upload_id} ({len(_all_rows)} rows)")

                        messages.success(request, (
                            f'File "{file_name}" uploading in background '
                            f'({len(_all_rows)} rows → {datasource_config.get("target_table", "")}). '
                            f'Refresh the page in a moment to see the result.'
                        ))
                        return redirect('upload:detail', upload_id=upload_id)
                    else:
                        # Table doesn't exist - use session fallback
                        import uuid
                        import tempfile
                        upload_id = f"TEMP-{uuid.uuid4().hex[:12].upper()}"

                        # Save file to temp directory for later HDFS upload
                        temp_dir = os.path.join(settings.BASE_DIR, 'temp_uploads')
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_file_path = os.path.join(temp_dir, f"{upload_id}_{file_name}")

                        # Save the file content
                        uploaded_file.seek(0)
                        with open(temp_file_path, 'wb') as f:
                            for chunk in uploaded_file.chunks():
                                f.write(chunk)

                        # Store in session with datasource config info
                        # Use all_data (full rows) for ingest; sample_data is preview-only
                        _all_data = getattr(validation_result, 'all_data', None) or validation_result.sample_data
                        request.session[f'upload_{upload_id}'] = {
                            'upload_id': upload_id,
                            'file_name': file_name,
                            'file_size': validation_result.file_size,
                            'file_type': validation_result.file_type,
                            'row_count': validation_result.row_count,
                            'column_count': validation_result.column_count,
                            'delimiter': validation_result.delimiter,
                            'has_header': validation_result.has_header,
                            'encoding': validation_result.encoding,
                            'description': description,
                            'schema_json': validation_result.columns,
                            'sample_data_json': _all_data,  # full rows for ingest
                            'status': 'VALIDATED',
                            'created_by': user_info['username'],
                            'target_table_name': datasource_config.get('target_table', ''),
                            'datasource_config': datasource_config,  # Store for preview
                            'temp_file_path': temp_file_path,  # Path to saved file
                        }

                        messages.warning(request, 'Upload table not available. Data stored temporarily in session.')
                        messages.success(request, f'File "{file_name}" validated using datasource config. Target: {datasource_config.get("target_table", "")}')
                        return redirect('upload:preview', upload_id=upload_id)
                else:
                    for error in validation_result.errors:
                        messages.error(request, error)
            else:
                # Standard upload - auto-detect schema
                upload_id, validation_result = upload_service.validate_and_create_upload(
                    file_obj=uploaded_file,
                    file_name=file_name,
                    description=description,
                    created_by=user_info['username']
                )

                # If table doesn't exist, store in session as fallback
                if not upload_id and validation_result.is_valid:
                    # Generate temporary ID
                    import uuid
                    upload_id = f"TEMP-{uuid.uuid4().hex[:12].upper()}"

                    # Save file to temp directory for later HDFS upload
                    temp_dir = os.path.join(settings.BASE_DIR, 'temp_uploads')
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_file_path = os.path.join(temp_dir, f"{upload_id}_{file_name}")

                    # Save the file content
                    uploaded_file.seek(0)
                    with open(temp_file_path, 'wb') as f:
                        for chunk in uploaded_file.chunks():
                            f.write(chunk)

                    # Store in session — use all_data (full rows) for ingest
                    _all_data = getattr(validation_result, 'all_data', None) or validation_result.sample_data
                    request.session[f'upload_{upload_id}'] = {
                        'upload_id': upload_id,
                        'file_name': file_name,
                        'file_size': validation_result.file_size,
                        'file_type': validation_result.file_type,
                        'row_count': validation_result.row_count,
                        'column_count': validation_result.column_count,
                        'delimiter': validation_result.delimiter,
                        'has_header': validation_result.has_header,
                        'encoding': validation_result.encoding,
                        'description': description,
                        'schema_json': validation_result.columns,
                        'sample_data_json': _all_data,  # full rows for ingest
                        'status': 'VALIDATED',
                        'created_by': user_info['username'],
                        'temp_file_path': temp_file_path,  # Path to saved file
                    }

                    messages.warning(request, 'Upload table not available. Data stored temporarily in session.')
                    messages.success(request, f'File "{file_name}" validated successfully!')
                    return redirect('upload:preview', upload_id=upload_id)

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

                    # Check if datasource config exists (but wasn't used)
                    if datasource_config:
                        messages.info(request, f'Datasource configuration found for "{file_name}". You can use metadata-driven ingestion.')

                    messages.success(request, f'File "{file_name}" uploaded and validated successfully!')
                    return redirect('upload:preview', upload_id=upload_id)
                else:
                    # Validation failed
                    for error in validation_result.errors:
                        messages.error(request, error)
                    for warning in validation_result.warnings:
                        messages.warning(request, warning)

        except Exception as e:
            logger.error(f"[UPLOAD_CREATE] unhandled exception: {e}", exc_info=True)
            print(f"[UPLOAD_CREATE] unhandled exception: {e}", flush=True)
            messages.error(request, f'Upload error: {str(e)}')

    # Get available datasource configs for dropdown
    datasource_configs = upload_service.get_all_datasource_configs()

    context = {
        'supported_formats': ', '.join(FileValidationService.SUPPORTED_EXTENSIONS.keys()),
        'max_file_size': FileValidationService.MAX_FILE_SIZE,
        'max_file_size_mb': FileValidationService.MAX_FILE_SIZE // (1024 * 1024),
        'datasource_configs': datasource_configs,
    }

    return render(request, 'upload/upload_form.html', context)


# =============================================================================
# UPLOAD PREVIEW & SCHEMA EDITING
# =============================================================================

def upload_preview(request, upload_id: str):
    """
    Preview uploaded file and edit schema before ingestion.
    """
    # First try to get from database
    upload = upload_service.get_upload_by_id(upload_id)

    # If not found, check session (for temporary storage when table doesn't exist)
    is_session_upload = False
    if not upload:
        session_key = f'upload_{upload_id}'
        upload = request.session.get(session_key)
        is_session_upload = True

    if not upload:
        raise Http404("Upload not found")

    # Parse JSON fields
    schema = []
    sample_data = []

    try:
        schema_json = upload.get('schema_json', '[]')
        if schema_json:
            schema = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
    except (json.JSONDecodeError, TypeError):
        # If it's already a list (from session), use it directly
        if isinstance(upload.get('schema_json'), list):
            schema = upload.get('schema_json')

    try:
        sample_json = upload.get('sample_data_json', '[]')
        if sample_json:
            sample_data = json.loads(sample_json) if isinstance(sample_json, str) else sample_json
    except (json.JSONDecodeError, TypeError):
        # If it's already a list (from session), use it directly
        if isinstance(upload.get('sample_data_json'), list):
            sample_data = upload.get('sample_data_json')

    # Check for datasource configuration
    # First check if stored in session (from metadata-driven upload)
    datasource_config = upload.get('datasource_config') if is_session_upload else None

    # If not in session, look up by filename
    if not datasource_config:
        file_name = upload.get('file_name', '')
        datasource_config = upload_service.get_datasource_config(file_name)

    # Get processing date from HDFS
    processing_date = None
    if datasource_config:
        from .repositories.datasource_repository import datasource_repository
        processing_date = datasource_repository.get_processing_date()

    # Available Hive types for schema editing
    hive_types = [
        'STRING', 'BIGINT', 'INT', 'SMALLINT', 'TINYINT',
        'DOUBLE', 'FLOAT', 'DECIMAL(20,6)', 'BOOLEAN',
        'DATE', 'TIMESTAMP'
    ]

    # Determine if ingestion is allowed
    upload_status = upload.get('status', '')
    can_ingest = upload_status in [
        'VALIDATED',
        'PENDING',  # Allow pending for metadata-driven uploads
        UploadKuduRepository.STATUS_VALIDATED,
        UploadKuduRepository.STATUS_PENDING,  # Allow pending
        UploadKuduRepository.STATUS_VALIDATION_FAILED,  # Allow retry
        'VALIDATION_FAILED',
    ]

    # For metadata-driven uploads with datasource config, always allow ingestion
    if datasource_config and not can_ingest:
        can_ingest = True
        logger.info(f"Allowing ingestion for metadata-driven upload: {upload_id}")

    # Ensure all columns have STRING type for metadata-driven uploads
    if datasource_config:
        for col in schema:
            col['type'] = 'STRING'

    context = {
        'upload': upload,
        'schema': schema,
        'schema_json': json.dumps(schema),  # For JavaScript
        'sample_data': sample_data[:20],  # Limit preview rows
        'hive_types': hive_types,
        'datasource_config': datasource_config,
        'processing_date': processing_date,
        'can_ingest': can_ingest,
        'is_session_upload': is_session_upload,
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

    Supports two modes:
    1. Standard ingestion - create new external table
    2. Metadata-driven ingestion - use cis_datasource_mng config to insert
       into existing target table with additional columns (src_id, src_system,
       data_cat, data_frq, processing_date)
    """
    user_info = get_user_info(request)

    # First try to get from database
    upload = upload_service.get_upload_by_id(upload_id)

    # If not found, check session (for temporary storage when table doesn't exist)
    is_session_upload = False
    if not upload:
        session_key = f'upload_{upload_id}'
        upload = request.session.get(session_key)
        is_session_upload = True

    if not upload:
        messages.error(request, 'Upload not found')
        return redirect('upload:list')

    try:
        # Check if metadata-driven ingestion is requested
        use_datasource_ingestion = request.POST.get('use_datasource_ingestion', '') == 'true'
        file_name = upload.get('file_name', '')

        if use_datasource_ingestion:
            # Metadata-driven ingestion using cis_datasource_mng
            # Check stored datasource_config first (for session uploads)
            datasource_config = upload.get('datasource_config') if is_session_upload else None
            if not datasource_config:
                datasource_config = upload_service.get_datasource_config(file_name)

            if not datasource_config:
                messages.error(request, f'No datasource configuration found for "{file_name}"')
                return redirect('upload:preview', upload_id=upload_id)

            # Get optional processing date override
            processing_date = request.POST.get('processing_date', '').strip()

            # Get ingestion mode (overwrite or append)
            ingestion_mode = request.POST.get('ingestion_mode', 'overwrite').strip()

            # ------------------------------------------------------------------
            # POSITION UPLOAD SHORT-CIRCUIT
            # Rows were already inserted into the raw target table at upload
            # time (upload_create). The Ingest button here only needs to confirm
            # data is present — no file access needed.
            # If the raw table already has rows for this partition, mark COMPLETED
            # and skip the file-based ingest path entirely.
            # ------------------------------------------------------------------
            if not is_session_upload and upload_service.is_position_upload(upload):
                import re as _re
                from core.repositories.impala_connection import impala_manager
                _target = datasource_config.get('target_table', '')
                _src_id = _target.lower().split('.')[-1]
                # Resolve processing_date from POST → description → today
                if not processing_date:
                    _desc = upload.get('description', '') or ''
                    _dm = _re.search(r'processing_date[=:\s]+(\d{8})', _desc)
                    processing_date = _dm.group(1) if _dm else ''
                if not processing_date:
                    from datetime import datetime as _dt2
                    processing_date = _dt2.now().strftime('%Y%m%d')
                logger.info(f"[ingest:view] Position upload short-circuit: checking {_target} src_id={_src_id} date={processing_date}")
                try:
                    _cnt_rows = impala_manager.execute_query(
                        f"SELECT COUNT(*) AS cnt FROM gmp_cis.{_target} "
                        f"WHERE src_id='{_src_id}' AND processing_date='{processing_date}'",
                        database='gmp_cis'
                    )
                    _raw_count = int(_cnt_rows[0].get('cnt', 0)) if _cnt_rows else 0
                except Exception as _ce:
                    logger.warning(f"[ingest:view] Could not count raw rows: {_ce}")
                    _raw_count = 0
                logger.warning(f"[ingest:view] Raw table row count = {_raw_count}")
                if _raw_count > 0:
                    # Data already in raw table — mark COMPLETED and skip file ingest
                    upload_service.repository.update_upload(
                        upload_id,
                        {'status': 'COMPLETED', 'row_count': _raw_count},
                        user_info['username']
                    )
                    messages.success(request, (
                        f"Raw data ingested: {_raw_count} rows in {_target} "
                        f"(processing_date={processing_date}). Click 'Run ETL' to proceed."
                    ))
                    return redirect('upload:detail', upload_id=upload_id)
                else:
                    # Raw table empty — file is gone (request ended).
                    # Block the 20-row fallback: tell user to re-upload.
                    messages.error(request, (
                        f"No data found in {_target} for processing_date={processing_date}. "
                        f"The file was not ingested at upload time. Please delete this record and re-upload the file."
                    ))
                    return redirect('upload:detail', upload_id=upload_id)

            # ------------------------------------------------------------------
            # Standard file-based ingest (non-position uploads, or session uploads)
            # ------------------------------------------------------------------
            logger.info(f"[ingest:view] ===== FILE INGEST upload_id={upload_id} is_session={is_session_upload} =====")
            logger.info(f"[ingest:view] upload.file_path={upload.get('file_path')!r}")
            logger.info(f"[ingest:view] upload.hdfs_path={upload.get('hdfs_path')!r}")
            logger.info(f"[ingest:view] upload.file_name={upload.get('file_name')!r}")
            logger.info(f"[ingest:view] upload.row_count={upload.get('row_count')!r}")
            if is_session_upload:
                temp_file_path = upload.get('temp_file_path')
                logger.info(f"[ingest:view] session upload temp_file_path={temp_file_path!r}")
            else:
                # Priority 1: file_path persisted in the DB record at upload time
                temp_file_path = upload.get('file_path', '').strip() or None
                logger.info(f"[ingest:view] P1 DB file_path={temp_file_path!r} exists={os.path.exists(temp_file_path) if temp_file_path else False}")
                if temp_file_path and os.path.exists(temp_file_path):
                    logger.info(f"[ingest:view] P1 RESOLVED — local file: {temp_file_path}")
                else:
                    # Priority 2: session key (same-worker fast-path)
                    temp_file_path = request.session.get(f'temp_path_{upload_id}')
                    logger.info(f"[ingest:view] P2 session key={temp_file_path!r} exists={os.path.exists(temp_file_path) if temp_file_path else False}")
                    if not temp_file_path or not os.path.exists(temp_file_path):
                        # Priority 3: reconstruct from naming convention
                        _temp_dir = os.path.join(settings.BASE_DIR, 'temp_uploads')
                        _file_name = upload.get('file_name', '') or upload.get('original_file_name', '')
                        _reconstructed = os.path.join(_temp_dir, f"{upload_id}_{_file_name}")
                        logger.info(f"[ingest:view] P3 reconstructed={_reconstructed!r} exists={os.path.exists(_reconstructed)}")
                        if os.path.exists(_reconstructed):
                            temp_file_path = _reconstructed
                            logger.info(f"[ingest:view] P3 RESOLVED — reconstructed: {temp_file_path}")
                        else:
                            temp_file_path = None
                            logger.warning(f"[ingest:view] P1/P2/P3 all FAILED — no local file available")
                logger.info(f"[ingest:view] final temp_file_path={temp_file_path!r}")
            sample_data = None
            if is_session_upload:
                sample_data_json = upload.get('sample_data_json', [])
                sample_data = sample_data_json if isinstance(sample_data_json, list) else json.loads(sample_data_json)
            elif not temp_file_path:
                # DB upload but local file is gone (cross-node). Pass DB sample_data_json
                # so the service's P4 fallback fires rather than returning "no file".
                sample_data_json = upload.get('sample_data_json', [])
                if sample_data_json:
                    sample_data = sample_data_json if isinstance(sample_data_json, list) else json.loads(sample_data_json)
                    logger.warning(f"[ingest:view] cross-node fallback — using DB sample_data_json ({len(sample_data)} rows)")

            # Mark INGESTING immediately so the UI shows progress — the actual
            # work runs in a background thread so the HTTP response returns at
            # once and Gunicorn never times out on large files.
            if not is_session_upload:
                upload_service.repository.update_upload(
                    upload_id, {'status': UploadKuduRepository.STATUS_INGESTING},
                    user_info['username']
                )

            # Capture everything the thread needs (no request/session access inside thread)
            _username   = user_info['username']
            _user_id    = user_info['user_id']
            _user_email = user_info['user_email']
            _proc_date  = processing_date if processing_date else None
            _is_session = is_session_upload
            _file_name  = file_name
            _req_path   = request.path
            _ip         = request.META.get('REMOTE_ADDR')
            _ua         = request.META.get('HTTP_USER_AGENT', '')
            _ds_cfg     = datasource_config
            _tfp        = temp_file_path
            _sd         = sample_data
            _mode       = ingestion_mode

            def _do_ingest():
                try:
                    ok, msg = upload_service.ingest_to_target_table(
                        upload_id=upload_id,
                        datasource_config=_ds_cfg,
                        updated_by=_username,
                        processing_date=_proc_date,
                        temp_file_path=_tfp,
                        sample_data=_sd,
                        ingestion_mode=_mode,
                    )
                    if ok:
                        audit_log_kudu_repository.log_action(
                            user_id=_user_id, username=_username,
                            user_email=_user_email, action_type='INGEST',
                            entity_type='FILE_UPLOAD', entity_id=upload_id,
                            entity_name=_file_name, action_description=msg,
                            request_method='POST', request_path=_req_path,
                            ip_address=_ip, user_agent=_ua, status='SUCCESS'
                        )
                        logger.info(f"[ingest:bg] DONE upload_id={upload_id}: {msg}")
                    else:
                        logger.error(f"[ingest:bg] FAILED upload_id={upload_id}: {msg}")
                        if not _is_session:
                            upload_service.repository.update_upload(
                                upload_id, {'status': UploadKuduRepository.STATUS_FAILED,
                                            'description': msg[:500]}, _username
                            )
                except Exception as _ex:
                    logger.error(f"[ingest:bg] EXCEPTION upload_id={upload_id}: {_ex}", exc_info=True)
                    if not _is_session:
                        upload_service.repository.update_upload(
                            upload_id,
                            {'status': UploadKuduRepository.STATUS_FAILED,
                             'description': str(_ex)[:500]},
                            _username
                        )

            import threading as _threading
            _t = _threading.Thread(target=_do_ingest, daemon=True, name=f"ingest-{upload_id[:8]}")
            _t.start()
            messages.info(request, (
                f'Ingestion started for {_file_name}. '
                f'Refresh this page in a moment to see the result.'
            ))
            return redirect('upload:detail', upload_id=upload_id)

        else:
            # Standard ingestion - create new external table
            table_name = request.POST.get('table_name', '').strip()

            # Parse schema from form
            schema_json = upload.get('schema_json', '[]')
            columns = json.loads(schema_json) if isinstance(schema_json, str) else schema_json

            # Get HDFS path (in production, file would be copied to HDFS)
            hdfs_path = upload.get('hdfs_path', '')

            # Perform standard ingestion
            success, message = upload_service.ingest_to_hive(
                upload_id=upload_id,
                table_name=table_name if table_name else None,
                columns=columns,
                file_path=hdfs_path,
                updated_by=user_info['username']
            )
            if success:
                messages.success(request, message)
            else:
                messages.error(request, message)

    except Exception as e:
        logger.error(f"[ingest:view] EXCEPTION: {e}", exc_info=True)
        messages.error(request, f'Ingestion error: {str(e)}')

    return redirect('upload:detail', upload_id=upload_id)


# =============================================================================
# UPLOAD DETAIL
# =============================================================================

def upload_detail(request, upload_id: str):
    """View upload details."""
    upload = upload_service.get_upload_by_id(upload_id)

    is_session_upload = False
    if not upload:
        session_key = f'upload_{upload_id}'
        upload = request.session.get(session_key)
        is_session_upload = True

    if not upload:
        raise Http404("Upload not found")

    logger.warning(f"[upload_detail] upload_id={upload_id} is_session={is_session_upload} status={upload.get('status')} target={upload.get('target_table_name')}")

    # Normalise session-upload dicts: fill in fields the template expects
    # that are only present on DB-persisted rows.
    if is_session_upload:
        from datetime import datetime as _dt
        _now = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
        upload.setdefault('created_at', _now)
        upload.setdefault('updated_at', _now)
        upload.setdefault('updated_by', upload.get('created_by', ''))
        upload.setdefault('hdfs_path', '')
        upload.setdefault('mime_type', '')
        upload.setdefault('original_file_name', upload.get('file_name', ''))
        upload.setdefault('validation_errors_json', '[]')
        upload.setdefault('target_database', 'gmp_cis')

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
        parsed = json.loads(errors_json) if isinstance(errors_json, str) else errors_json
        # Must be a list — if it's a string (truncated JSON), wrap it
        validation_errors = parsed if isinstance(parsed, list) else [str(parsed)]
    except Exception:
        # Truncated/invalid JSON stored in Kudu (old row before the write-cap fix).
        # Try to recover complete string entries from the partial JSON array,
        # then append a warning so the user knows the list may be incomplete.
        raw = upload.get('validation_errors_json', '') or ''
        recovered = []
        try:
            import re as _re
            # Pull out all fully-quoted strings from the partial array
            recovered = _re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
            recovered = [s.replace('\\"', '"') for s in recovered]
        except Exception:
            pass
        if recovered:
            recovered.append('[Validation errors list was truncated — only partial results shown]')
            validation_errors = recovered
        else:
            validation_errors = [str(raw)[:500]] if raw else []

    # Get table preview and reconciliation data if completed
    table_preview = []
    recon_data = None
    if upload.get('status') == UploadKuduRepository.STATUS_COMPLETED:
        table_name = upload.get('target_table_name')
        if table_name:
            from .repositories.upload_kudu_repository import upload_kudu_repository
            table_preview = upload_kudu_repository.get_table_preview(table_name, limit=10)

            # Get reconciliation data
            # Try to extract processing_date from description or use None
            processing_date = None
            description = upload.get('description', '')
            if description:
                # Look for processing_date pattern in description
                import re
                date_match = re.search(r'processing_date[=:\s]+(\d{8})', description)
                if date_match:
                    processing_date = date_match.group(1)

            recon_data = upload_kudu_repository.get_reconciliation_data(
                table_name=table_name,
                processing_date=processing_date
            )

            # Determine match status based on source row count vs table count
            source_row_count = upload.get('row_count', 0)
            table_count = recon_data.get('table_count', 0)
            if source_row_count and table_count:
                if source_row_count == table_count:
                    recon_data['match_status'] = 'MATCH'
                else:
                    recon_data['match_status'] = 'MISMATCH'
            elif table_count > 0:
                recon_data['match_status'] = 'MATCH'  # Data exists
            else:
                recon_data['match_status'] = 'UNKNOWN'

    is_position_upload = upload_service.is_position_upload(upload)
    upload_status = upload.get('status', '')

    # For position uploads: query the actual Hive partition count so the
    # detail page shows the real row count regardless of what Kudu stores.
    hive_row_count = None
    _pd2 = None
    if is_position_upload:
        try:
            import re as _re2
            from core.repositories.impala_connection import impala_manager as _imp2
            _tgt = upload.get('target_table_name', '').split('.')[-1]
            _desc2 = upload.get('description', '') or ''
            _dm2 = _re2.search(r'processing_date[=:\s]+(\d{8})', _desc2)
            _pd2 = _dm2.group(1) if _dm2 else None
            if _tgt and _pd2:
                _cnt = _imp2.execute_query(
                    f"SELECT COUNT(*) AS cnt FROM gmp_cis.{_tgt} "
                    f"WHERE processing_date='{_pd2}'",
                    database='gmp_cis'
                )
                hive_row_count = int(_cnt[0].get('cnt', 0)) if _cnt else None
                logger.info(f"[detail] hive_row_count={hive_row_count} for {_tgt} pd={_pd2}")
        except Exception as _hce:
            logger.warning(f"[detail] Could not count Hive rows: {_hce}")

    context = {
        'upload': upload,
        'schema': schema,
        'sample_data': sample_data[:10],
        'hive_row_count': hive_row_count,
        'validation_errors': validation_errors,
        'table_preview': table_preview,
        'recon_data': recon_data,
        'etl_processing_date': _pd2 or '',
        'can_edit': upload_status in [
            UploadKuduRepository.STATUS_PENDING,
            UploadKuduRepository.STATUS_VALIDATED,
            UploadKuduRepository.STATUS_VALIDATION_FAILED
        ],
        # Ingest button only for non-position VALIDATED uploads
        'can_ingest': (not is_position_upload) and upload_status == UploadKuduRepository.STATUS_VALIDATED,
        'can_delete': upload_status not in [
            UploadKuduRepository.STATUS_INGESTING
        ],
        'is_position_upload': is_position_upload,
        # Run Position ETL: show whenever raw data is in the table (COMPLETED, FAILED,
        # INGESTING — bg thread still running) or VALIDATED (data inserted at upload time).
        'can_run_position': is_position_upload and upload_status in [
            UploadKuduRepository.STATUS_VALIDATED,
            UploadKuduRepository.STATUS_INGESTING,
            UploadKuduRepository.STATUS_COMPLETED,
            UploadKuduRepository.STATUS_FAILED,
        ],
        # Show a "still processing" banner when INGESTING
        'is_ingesting': upload_status == UploadKuduRepository.STATUS_INGESTING,
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
        file_name = uploaded_file.name

        # Check for datasource configuration
        datasource_config = upload_service.get_datasource_config(file_name)

        # If datasource config found, use it for validation
        if datasource_config:
            result = upload_service.validate_with_datasource_config(
                file_obj=uploaded_file,
                file_name=file_name,
                datasource_config=datasource_config
            )
            # Include datasource config info in response
            ds_info = {
                'source_id': datasource_config.get('source_id', ''),
                'source_name': datasource_config.get('source_name', ''),
                'target_table': datasource_config.get('target_table', ''),
                'separator': datasource_config.get('separator', ','),
            }
        else:
            result = validation_service.validate_file(uploaded_file, file_name)
            ds_info = None

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
            'datasource_config': ds_info,
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


# =============================================================================
# POSITION UPLOAD — Run ETL & Download Report
# =============================================================================

@require_http_methods(["POST"])
def run_position_etl(request, upload_id: str):
    """
    POST: Trigger the position upload transform pipeline for a completed upload.

    Reads src_id (target_table_name) and processing_date from the upload record,
    then runs the 7-step AVP validation + cis_position upsert + report write.
    """
    user_info = get_user_info(request)
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        upload = request.session.get(f'upload_{upload_id}')

    if not upload:
        messages.error(request, 'Upload not found')
        return redirect('upload:list')

    if not upload_service.is_position_upload(upload):
        messages.error(request, 'This upload is not a position file — ETL not applicable')
        return redirect('upload:detail', upload_id=upload_id)

    # Derive src_id and processing_date
    src_id = (upload.get('target_table_name') or '').lower().split('.')[-1]
    processing_date = request.POST.get('processing_date', '').strip()

    if not processing_date:
        # Try to read from description
        import re
        date_match = re.search(r'processing_date[=:\s]+(\d{8})', upload.get('description', ''))
        if date_match:
            processing_date = date_match.group(1)

    if not processing_date:
        # Fall back to today
        from datetime import datetime
        processing_date = datetime.now().strftime('%Y%m%d')

    # Mark INGESTING so the UI shows "processing" banner while ETL runs
    upload_service.repository.update_upload(
        upload_id, {'status': UploadKuduRepository.STATUS_INGESTING},
        user_info['username']
    )

    # Capture request-bound data before handing off to the thread
    _username   = user_info['username']
    _user_id    = user_info['user_id']
    _user_email = user_info['user_email']
    _file_name  = upload.get('file_name', '')
    _req_path   = request.path
    _ip         = request.META.get('REMOTE_ADDR')
    _ua         = request.META.get('HTTP_USER_AGENT', '')
    _src_id     = src_id
    _proc_date  = processing_date

    def _do_etl():
        try:
            ok, msg, result = upload_service.run_position_etl(
                upload_id=upload_id,
                src_id=_src_id,
                processing_date=_proc_date,
                updated_by=_username,
            )
            if ok:
                # Persist completed status + ETL identifiers so download report can find the partition
                _etl_desc = (
                    f"Position ETL complete\n"
                    f"src_id={_src_id}\n"
                    f"processing_date={_proc_date}\n"
                    f"total={result.get('total', 0)} pass={result.get('passed', 0)} fail={result.get('failed', 0)}"
                )
                upload_service.repository.update_upload(
                    upload_id,
                    {'status': UploadKuduRepository.STATUS_COMPLETED,
                     'description': _etl_desc},
                    _username
                )
                audit_log_kudu_repository.log_action(
                    user_id=_user_id, username=_username,
                    user_email=_user_email, action_type='POSITION_ETL',
                    entity_type='FILE_UPLOAD', entity_id=upload_id,
                    entity_name=_file_name, action_description=msg,
                    new_value=json.dumps(result),
                    request_method='POST', request_path=_req_path,
                    ip_address=_ip, user_agent=_ua, status='SUCCESS'
                )
                logger.info(f"[etl:bg] DONE upload_id={upload_id}: {msg}")
            else:
                logger.error(f"[etl:bg] FAILED upload_id={upload_id}: {msg}")
                upload_service.repository.update_upload(
                    upload_id,
                    {'status': UploadKuduRepository.STATUS_FAILED,
                     'description': msg[:500]},
                    _username
                )
        except Exception as _ex:
            logger.error(f"[etl:bg] EXCEPTION upload_id={upload_id}: {_ex}", exc_info=True)
            upload_service.repository.update_upload(
                upload_id,
                {'status': UploadKuduRepository.STATUS_FAILED,
                 'description': str(_ex)[:500]},
                _username
            )

    import threading as _threading
    _t = _threading.Thread(target=_do_etl, daemon=True, name=f"etl-{upload_id[:8]}")
    _t.start()

    messages.info(request, (
        f'Position ETL started for {_file_name} '
        f'(src_id={_src_id}, date={_proc_date}). '
        f'Refresh this page in a moment to see the result.'
    ))
    return redirect('upload:detail', upload_id=upload_id)


@require_http_methods(["GET"])
def download_position_report(request, upload_id: str):
    """
    GET: Stream position_upload_report as a CSV file for download.

    Query params:
        processing_date (optional): override partition date (YYYYMMDD)
    """
    upload = upload_service.get_upload_by_id(upload_id)
    if not upload:
        upload = request.session.get(f'upload_{upload_id}')
    if not upload:
        raise Http404("Upload not found")

    if not upload_service.is_position_upload(upload):
        messages.error(request, 'This upload is not a position file')
        return redirect('upload:detail', upload_id=upload_id)

    src_id = (
        upload.get('etl_src_id')
        or (upload.get('target_table_name') or '').lower().split('.')[-1]
    )
    processing_date = request.GET.get('processing_date', '').strip()

    if not processing_date:
        processing_date = upload.get('etl_processing_date', '').strip()

    if not processing_date:
        import re
        date_match = re.search(r'processing_date[=:\s]+(\d{8})', upload.get('description', ''))
        if date_match:
            processing_date = date_match.group(1)

    if not processing_date:
        from datetime import datetime
        processing_date = datetime.now().strftime('%Y%m%d')

    success, message, csv_content = upload_service.build_position_report_csv(
        src_id=src_id,
        processing_date=processing_date
    )

    if not success:
        messages.error(request, message)
        return redirect('upload:detail', upload_id=upload_id)

    file_name = upload.get('file_name', 'position_report').rsplit('.', 1)[0]
    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="position_report_{file_name}_{processing_date}.csv"'
    )
    return response


@require_http_methods(["GET"])
def api_reconciliation(request, upload_id: str):
    """
    API: Get reconciliation data for completed upload.
    Used for refresh button in UI.
    """
    upload = upload_service.get_upload_by_id(upload_id)

    if not upload:
        return JsonResponse({'error': 'Upload not found'}, status=404)

    if upload.get('status') != UploadKuduRepository.STATUS_COMPLETED:
        return JsonResponse({'error': 'Upload not yet completed'}, status=400)

    table_name = upload.get('target_table_name')
    if not table_name:
        return JsonResponse({'error': 'No target table'}, status=400)

    # Get processing_date from request or description
    processing_date = request.GET.get('processing_date', '').strip()
    if not processing_date:
        description = upload.get('description', '')
        if description:
            import re
            date_match = re.search(r'processing_date[=:\s]+(\d{8})', description)
            if date_match:
                processing_date = date_match.group(1)

    from .repositories.upload_kudu_repository import upload_kudu_repository
    recon_data = upload_kudu_repository.get_reconciliation_data(
        table_name=table_name,
        processing_date=processing_date if processing_date else None
    )

    # Determine match status
    source_row_count = upload.get('row_count', 0)
    table_count = recon_data.get('table_count', 0)
    if source_row_count and table_count:
        if source_row_count == table_count:
            recon_data['match_status'] = 'MATCH'
        else:
            recon_data['match_status'] = 'MISMATCH'
    elif table_count > 0:
        recon_data['match_status'] = 'MATCH'
    else:
        recon_data['match_status'] = 'UNKNOWN'

    # Add source row count for comparison
    recon_data['source_row_count'] = source_row_count

    return JsonResponse(recon_data)
