-- Debug: get ground truth for a position upload whose stored description
-- disagrees with its live stat panel (Step 7B overwriting Step 6's locked-in
-- counts bug, fixed in upload_service.py commit 5254d81). Use this to decide
-- what the corrected description/status should say for an already-run upload.
-- Replace src_id / processing_date with the actual values from the upload
-- record (target_table_name lowercased, and the processing_date embedded in
-- the description, e.g. "processing_date=20260303").
-- ---------------------------------------------------------------------------

-- ── 1. What position_upload_report actually contains right now ──────────────
SELECT row_status, fail_reason, COUNT(*) AS cnt
FROM gmp_cis.position_upload_report
WHERE src_id = 'cis_user_sta_adhoc_position_1'
  AND processing_date = '20260303'
GROUP BY row_status, fail_reason
ORDER BY cnt DESC;

-- ── 2. Total row count in the report for this partition ─────────────────────
SELECT COUNT(*) AS total_report_rows
FROM gmp_cis.position_upload_report
WHERE src_id = 'cis_user_sta_adhoc_position_1'
  AND processing_date = '20260303';

-- ── 3. How many rows actually landed in cis_position for this source/date ───
-- (source_table on cis_position should match the upload's src_id/table name)
SELECT COUNT(*) AS cis_position_rows
FROM gmp_cis.cis_position
WHERE source_table = 'cis_user_sta_adhoc_position_1'
  AND processing_date = '20260303'
  AND is_latest = true;

-- ── 4. The current upload record itself (status + stored description) ───────
SELECT upload_id, status, description, updated_at
FROM gmp_cis.cis_file_upload
WHERE upload_id = 'UPL-20260717151534-A93AE15D';
