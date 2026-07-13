#!/bin/bash
# =============================================================================
# CIS EOD Control-M Job Script — PROD Environment
# =============================================================================
# Environment : SIT
# Host        : lxmrwpsgv0w1
# Impala      : lxmrwpsgv0w1:21050
# Queue       : EOD_Queue
# Keytab      : /app/prodlib/<PROD_KEYTAB>.keytab        ← PLACEHOLDER
# Principal   : <PROD_PRINCIPAL>@SG.UOBNET.COM           ← PLACEHOLDER
#
# Jobs (in order):
#   1. equity_price_copy   — impala-shell, reads gmpcisalldates.txt
#   2. corporate_actions   — spark, source_id=cis_corporate_actions
#   3. cash_flow           — spark, source_id=cis_cash_flow
#   4. eod                 — spark, source_id=cis_eod
#   5. sod                 — spark, source_id=cis_sod (next contextual date)
#   6. correction          — spark, source_id=cis_correction (first week of month only)
#
# Re-run behaviour:
#   Set START_FROM=<step_number> to resume from a failed step.
#   e.g.  START_FROM=3 ./cis_eod_sit.sh
#   Default START_FROM=1 (run all steps)
#
# Usage:
#   ./cis_eod_sit.sh
#   START_FROM=3 ./cis_eod_sit.sh
#   ./cis_eod_sit.sh -d 20260713        (override processing_date)
# =============================================================================

set -uo pipefail

# -----------------------------------------------------------------------------
# Environment config
# -----------------------------------------------------------------------------
REGION="PROD"
IMPALA_DAEMON="lxmrwpsgv0w1"
IMPALA_PORT="21050"
KEYTAB="/app/prodlib/<PROD_KEYTAB>.keytab"           # PLACEHOLDER
PRINCIPAL="<PROD_PRINCIPAL>@SG.UOBNET.COM"           # PLACEHOLDER
QUEUE="EOD_Queue"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_FILE="${BASE_DIR}/cis_db_init"
DATABASE_PATH="${BASE_DIR}"
DATABASE_NAME="gmp_cis"
HDFS_PATH="/cis/datalake/"
GMP_ALLDATES_FILE="/sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt"

PYSPARK_BIN="/app/HRMS8/py/amua/bin/python"
SPARK_SUBMIT="/usr/bin/spark3-submit"

LOG_DIR="${BASE_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/cis_eod_${REGION}_$(date +%Y%m%d_%H%M%S).log"

# Step resume — set externally or default to 1
START_FROM="${START_FROM:-1}"

# State file — tracks last completed step for re-run
STATE_FILE="${LOG_DIR}/cis_eod_${REGION}_state.txt"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$REGION] $*" | tee -a "${LOG_FILE}"
}

log_step() {
    echo "" | tee -a "${LOG_FILE}"
    echo "==============================================================================" | tee -a "${LOG_FILE}"
    log "STEP $1: $2"
    echo "==============================================================================" | tee -a "${LOG_FILE}"
}

error_exit() {
    log "ERROR: $1"
    log "FAILED at STEP ${CURRENT_STEP}. To re-run from this step: START_FROM=${CURRENT_STEP} $0 $*"
    echo "${CURRENT_STEP}" > "${STATE_FILE}"
    exit 1
}

should_run() {
    local step=$1
    if [[ $step -ge $START_FROM ]]; then
        return 0
    else
        log "SKIP STEP ${step} (START_FROM=${START_FROM})"
        return 1
    fi
}

mark_done() {
    local step=$1
    echo "$((step + 1))" > "${STATE_FILE}"
    log "STEP ${step} completed successfully."
}

# -----------------------------------------------------------------------------
# Parse args
# -----------------------------------------------------------------------------
processing_date=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--date) processing_date="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# -----------------------------------------------------------------------------
# Kerberos init
# -----------------------------------------------------------------------------
log "Initialising Kerberos ticket: kinit -kt ${KEYTAB} ${PRINCIPAL}"
/usr/bin/kinit -kt "${KEYTAB}" "${PRINCIPAL}"
if [[ $? -ne 0 ]]; then
    log "ERROR: kinit failed. Check keytab and principal."
    exit 1
fi
log "Kerberos ticket obtained."

# -----------------------------------------------------------------------------
# Resolve processing_date from gmpcisalldates.txt
# File format (| separated, no schema header):
#   Line 1: Header  — skip
#   Line 2: trade_date|settle_date|report_date|  ← body, report_date = processing_date
#   Last  : Trailer — skip
# -----------------------------------------------------------------------------
if [[ -z "${processing_date}" ]]; then
    if [[ -f "${GMP_ALLDATES_FILE}" ]]; then
        body_line=$(sed -n '2p' "${GMP_ALLDATES_FILE}")
        processing_date=$(echo "${body_line}" | cut -d'|' -f3)
        log "gmpcisalldates.txt body line : [${body_line}]"
        log "processing_date (report_date): ${processing_date}"
    else
        log "WARNING: ${GMP_ALLDATES_FILE} not found — falling back to today"
        processing_date=$(date +%Y%m%d)
    fi
else
    log "processing_date from -d param  : ${processing_date}"
fi

if [[ -z "${processing_date}" ]]; then
    log "ERROR: Could not determine processing_date."
    exit 1
fi

# SOD date — PLACEHOLDER: replace field index when alldates schema confirmed
# Currently same as processing_date; update cut -f<N> when field is known
sod_date=$(sed -n '2p' "${GMP_ALLDATES_FILE}" | cut -d'|' -f2)    # PLACEHOLDER — confirm field
log "sod_date (next contextual date) : ${sod_date}  ← PLACEHOLDER field index"

# Correction job runs first week of month only (day 1–7)
day_of_month=$(date -d "${processing_date}" +%d 2>/dev/null || date +%d)
run_correction=false
if [[ $day_of_month -ge 1 && $day_of_month -le 7 ]]; then
    run_correction=true
    log "Correction job ENABLED (day_of_month=${day_of_month})"
else
    log "Correction job SKIPPED (day_of_month=${day_of_month}, only runs days 1-7)"
fi

log "Starting CIS EOD — region=${REGION} processing_date=${processing_date}"
log "Log file: ${LOG_FILE}"
log "Resume from step: ${START_FROM}"

# -----------------------------------------------------------------------------
# Helper: submit spark job
# -----------------------------------------------------------------------------
submit_spark_job() {
    local source_id=$1
    local proc_date=$2
    local extra_args=${3:-""}

    log "spark-submit: source_id=${source_id} processing_date=${proc_date}"
    ${SPARK_SUBMIT} \
        --master yarn \
        --deploy-mode cluster \
        --queue ${QUEUE} \
        --conf spark.app.name="${source_id}_${proc_date}" \
        --conf spark.sql.crossJoin.enabled=true \
        --conf spark.sql.legacy.timeParserPolicy=LEGACY \
        --conf spark.rpc.askTimeout=300s \
        --conf spark.network.timeout=60 \
        --conf spark.pyspark.driver.python=${PYSPARK_BIN} \
        --conf spark.pyspark.python=${PYSPARK_BIN} \
        ${PYTHON_FILE}/cis_ingestion.py \
        ${source_id} ${proc_date} ${DATABASE_NAME} ${extra_args} \
        2>&1 | tee -a "${LOG_FILE}"

    return ${PIPESTATUS[0]}
}

# =============================================================================
# STEP 1 — Equity Price Copy (impala-shell)
# =============================================================================
CURRENT_STEP=1
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Equity Price Copy → hive_cis_equity_price"
    SQL_FILE="${DATABASE_PATH}/sql/etl/equity_price_hive_copy_job.sql"
    if [[ ! -f "${SQL_FILE}" ]]; then
        error_exit "SQL file not found: ${SQL_FILE}"
    fi
    impala-shell -i "${IMPALA_DAEMON}:${IMPALA_PORT}" \
        --var=processing_date="${processing_date}" \
        -f "${SQL_FILE}" \
        2>&1 | tee -a "${LOG_FILE}"
    [[ ${PIPESTATUS[0]} -ne 0 ]] && error_exit "equity_price_copy failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 2 — Corporate Actions
# =============================================================================
CURRENT_STEP=2
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Corporate Actions (cis_corporate_actions)"
    submit_spark_job "cis_corporate_actions" "${processing_date}"
    [[ $? -ne 0 ]] && error_exit "corporate_actions spark job failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 3 — Cash Flow
# =============================================================================
CURRENT_STEP=3
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Cash Flow (cis_cash_flow)"
    submit_spark_job "cis_cash_flow" "${processing_date}"
    [[ $? -ne 0 ]] && error_exit "cash_flow spark job failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 4 — EOD
# =============================================================================
CURRENT_STEP=4
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "EOD (cis_eod)"
    submit_spark_job "cis_eod" "${processing_date}"
    [[ $? -ne 0 ]] && error_exit "eod spark job failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 5 — SOD (next contextual date)
# =============================================================================
CURRENT_STEP=5
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "SOD (cis_sod) — next contextual date: ${sod_date}"
    submit_spark_job "cis_sod" "${sod_date}"
    [[ $? -ne 0 ]] && error_exit "sod spark job failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 6 — Correction (first week of month only)
# =============================================================================
CURRENT_STEP=6
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Correction (cis_correction) — run=${run_correction}"
    if [[ "${run_correction}" == "true" ]]; then
        submit_spark_job "cis_correction" "${processing_date}"
        [[ $? -ne 0 ]] && error_exit "correction spark job failed"
    else
        log "Correction skipped — not first week of month"
    fi
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# ALL STEPS DONE
# =============================================================================
rm -f "${STATE_FILE}"
log ""
log "########## CIS EOD ${REGION} completed successfully for processing_date=${processing_date} ##########"
