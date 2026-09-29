#!/bin/bash
# ============================================================================
# Debug: ETL log analysis — extract step timings and errors from app log
# Run on CML terminal:  bash sql/transforms/debug_etl_logs.sh
# Optionally pass a date filter: bash debug_etl_logs.sh 2026-07-09
# ============================================================================

LOG_DIR="${CIS_LOG_DIR:-$HOME/CIS/logs}"
DATE_FILTER="${1:-}"

# Find all log files (current + rotated)
LOG_FILES=$(ls "$LOG_DIR"/cistrade.log* 2>/dev/null)

if [ -z "$LOG_FILES" ]; then
    echo "ERROR: No log files found in $LOG_DIR"
    echo "Try setting CIS_LOG_DIR to the correct path, e.g.:"
    echo "  CIS_LOG_DIR=/path/to/logs bash debug_etl_logs.sh"
    exit 1
fi

echo "============================================================"
echo "Log files found:"
ls -lh "$LOG_DIR"/cistrade.log* 2>/dev/null
echo "============================================================"

# ============================================================
# 1. ETL step timings — how long each step took
# ============================================================
echo ""
echo "=== ETL STEP TIMINGS ==="
grep -h "position_etl.*Step\|position_etl.*complete\|position_etl.*failed" \
    $LOG_FILES \
    | grep "${DATE_FILTER}" \
    | tail -100

# ============================================================
# 2. All ETL-related errors
# ============================================================
echo ""
echo "=== ETL ERRORS ==="
grep -h "position_etl\|AnalysisException\|Could not resolve\|incompatible\|Failed to execute" \
    $LOG_FILES \
    | grep -i "error\|exception\|failed\|incompatible\|could not" \
    | grep "${DATE_FILTER}" \
    | tail -100

# ============================================================
# 3. Upload status transitions (INGESTING → COMPLETED/FAILED)
# ============================================================
echo ""
echo "=== UPLOAD STATUS TRANSITIONS ==="
grep -h "upload_detail\|status=INGESTING\|status=COMPLETED\|status=FAILED\|status=VALIDATED" \
    $LOG_FILES \
    | grep "${DATE_FILTER}" \
    | tail -50

# ============================================================
# 4. Impala connection events — how many connections opened
# ============================================================
echo ""
echo "=== IMPALA CONNECTION EVENTS ==="
grep -h "Created new Impala connection\|Impala connection\|connection.*pool\|ssl_PROTOCOL" \
    $LOG_FILES \
    | grep "${DATE_FILTER}" \
    | tail -50

# ============================================================
# 5. All ERROR and WARNING lines (any module)
# ============================================================
echo ""
echo "=== ALL ERRORS AND WARNINGS ==="
grep -h "\[ERROR\]\|\[WARNING\]\|ERROR\|WARNING" \
    $LOG_FILES \
    | grep "${DATE_FILTER}" \
    | grep -v "ssl_PROTOCOL_TLS is deprecated" \
    | tail -100

# ============================================================
# 6. ETL run summary — total time per upload_id
# ============================================================
echo ""
echo "=== ETL RUN SUMMARY (total elapsed per run) ==="
grep -h "position_etl.*total\|ETL complete\|run_position_etl\|etl.*elapsed\|Step 7B complete" \
    $LOG_FILES \
    | grep "${DATE_FILTER}" \
    | tail -30

# ============================================================
# 7. Repository / audit errors
# ============================================================
echo ""
echo "=== REPOSITORY / AUDIT ERRORS ==="
grep -h "repository\|audit\|kudu_repository" \
    $LOG_FILES \
    | grep -i "error\|exception\|failed" \
    | grep "${DATE_FILTER}" \
    | tail -50

# ============================================================
# 8. Full log tail — last 200 lines (most recent activity)
# ============================================================
echo ""
echo "=== LAST 200 LOG LINES ==="
# Use the most recently modified log file
LATEST_LOG=$(ls -t "$LOG_DIR"/cistrade.log* 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    echo "Reading from: $LATEST_LOG"
    tail -200 "$LATEST_LOG"
fi

echo ""
echo "============================================================"
echo "Done. To filter by a specific date, run:"
echo "  bash debug_etl_logs.sh 2026-07-09"
echo "To filter by upload_id, run:"
echo "  grep 'UPL-<your-upload-id>' $LOG_DIR/cistrade.log*"
echo "============================================================"
