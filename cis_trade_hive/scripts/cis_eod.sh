#!/bin/bash
# =============================================================================
# CIS EOD Control-M Job Script
# =============================================================================
# Single script for all environments — pass --env to select.
#
# Environments:
#   SIT   lxmrwtsgv0w1   keytab: <SIT_KEYTAB>.keytab    principal: <SIT_PRINCIPAL>
#   UAT   lxmrwusgv0w1   keytab: <UAT_KEYTAB>.keytab    principal: <UAT_PRINCIPAL>
#   PROD  lxmrwpsgv0w1   keytab: <PROD_KEYTAB>.keytab   principal: <PROD_PRINCIPAL>
#   DR    lxmrwrsgv0w1   keytab: <DR_KEYTAB>.keytab     principal: <DR_PRINCIPAL>
#
# EOD Steps (in order):
#   1. equity_price_copy     impala-shell → equity_price_hive_copy_job.sql
#   2. corporate_actions     manage.py process_corporate_actions --run-type EOD
#   3. cash_flow             manage.py process_approved_cashflows --run-type EOD
#   4. eod                   manage.py process_settlements
#   5. sod                   manage.py create_sod_snapshot  (uses sod_date from alldates)
#   6. correction            manage.py process_corporate_actions --run-type CORR
#                            manage.py process_approved_cashflows --run-type CORR
#                            (first week of month only: days 1-7)
#
# Processing date source:
#   /sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt
#   Line 2 (body): trade_date|settle_date|report_date|
#   processing_date = field 3 (report_date)
#   sod_date        = field 2 (settle_date) ← PLACEHOLDER: confirm field index
#
# date format passed to manage.py: YYYY-MM-DD
# date format from alldates:       YYYYMMDD → converted internally
#
# Usage:
#   ./cis_eod.sh --env SIT
#   ./cis_eod.sh --env UAT  --date 20260713
#   ./cis_eod.sh --env PROD --date 20260713 --start-from 3
#   START_FROM=3 ./cis_eod.sh --env DR
#
# Re-run from failed step:
#   ./cis_eod.sh --env SIT --start-from 3
#   START_FROM=3 ./cis_eod.sh --env SIT
# =============================================================================

set -uo pipefail

# =============================================================================
# Parse arguments
# =============================================================================
ENV=""
processing_date_raw=""      # YYYYMMDD — from alldates or -d arg
START_FROM="${START_FROM:-1}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --env|-e)           ENV="${2^^}";             shift 2 ;;
        --date|-d)          processing_date_raw="$2"; shift 2 ;;
        --start-from|-s)    START_FROM="$2";          shift 2 ;;
        *) echo "Unknown argument: $1"; shift ;;
    esac
done

if [[ -z "${ENV}" ]]; then
    echo "ERROR: --env is required. Use: SIT | UAT | PROD | DR"
    echo "Usage: $0 --env SIT [--date 20260713] [--start-from 3]"
    exit 1
fi

# =============================================================================
# Environment config
# =============================================================================
case "${ENV}" in
    SIT)
        IMPALA_DAEMON="lxmrwtsgv0w1"
        KEYTAB="/app/prodlib/<SIT_KEYTAB>.keytab"       # PLACEHOLDER
        PRINCIPAL="<SIT_PRINCIPAL>@SG.UOBNET.COM"       # PLACEHOLDER
        ;;
    UAT)
        IMPALA_DAEMON="lxmrwusgv0w1"
        KEYTAB="/app/prodlib/<UAT_KEYTAB>.keytab"       # PLACEHOLDER
        PRINCIPAL="<UAT_PRINCIPAL>@SG.UOBNET.COM"       # PLACEHOLDER
        ;;
    PROD)
        IMPALA_DAEMON="lxmrwpsgv0w1"
        KEYTAB="/app/prodlib/<PROD_KEYTAB>.keytab"      # PLACEHOLDER
        PRINCIPAL="<PROD_PRINCIPAL>@SG.UOBNET.COM"      # PLACEHOLDER
        ;;
    DR)
        IMPALA_DAEMON="lxmrwrsgv0w1"
        KEYTAB="/app/prodlib/<DR_KEYTAB>.keytab"        # PLACEHOLDER
        PRINCIPAL="<DR_PRINCIPAL>@SG.UOBNET.COM"        # PLACEHOLDER
        ;;
    *)
        echo "ERROR: Unknown environment '${ENV}'. Use: SIT | UAT | PROD | DR"
        exit 1
        ;;
esac

IMPALA_PORT="21050"
QUEUE="EOD_Queue"

# =============================================================================
# Paths
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANAGE_PY="${BASE_DIR}/manage.py"
DATABASE_PATH="${BASE_DIR}"
GMP_ALLDATES_FILE="/sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt"

LOG_DIR="${BASE_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/cis_eod_${ENV}_$(date +%Y%m%d_%H%M%S).log"
STATE_FILE="${LOG_DIR}/cis_eod_${ENV}_state.txt"

# =============================================================================
# Logging helpers
# =============================================================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${ENV}] $*" | tee -a "${LOG_FILE}"
}

log_step() {
    local step=$1; shift
    echo "" | tee -a "${LOG_FILE}"
    echo "==============================================================================" | tee -a "${LOG_FILE}"
    log "STEP ${step}: $*"
    echo "==============================================================================" | tee -a "${LOG_FILE}"
}

log_ok() {
    log "  [OK] $*"
}

log_err() {
    log "  [ERROR] $*"
}

error_exit() {
    local msg=$1
    log_err "${msg}"
    log ""
    log ">>> FAILED at STEP ${CURRENT_STEP} <<<"
    log ">>> To re-run from this step:"
    log ">>>   $0 --env ${ENV} --start-from ${CURRENT_STEP}"
    log ">>> Or with explicit date:"
    log ">>>   $0 --env ${ENV} --date ${processing_date_raw} --start-from ${CURRENT_STEP}"
    echo "${CURRENT_STEP}" > "${STATE_FILE}"
    exit 1
}

should_run() {
    local step=$1
    if [[ ${step} -ge ${START_FROM} ]]; then
        return 0
    else
        log "SKIP STEP ${step} (resuming from step ${START_FROM})"
        return 1
    fi
}

mark_done() {
    local step=$1
    log_ok "STEP ${step} completed."
    echo "$((step + 1))" > "${STATE_FILE}"
}

run_manage() {
    # run_manage <step> <command> [args...]
    # Runs: python manage.py <command> [args...] and logs all output
    local step=$1; shift
    log "Running: python ${MANAGE_PY} $*"
    python "${MANAGE_PY}" "$@" 2>&1 | tee -a "${LOG_FILE}"
    local rc=${PIPESTATUS[0]}
    if [[ ${rc} -ne 0 ]]; then
        error_exit "manage.py $1 exited with code ${rc}"
    fi
    log_ok "manage.py $1 done (exit 0)"
}

# =============================================================================
# Kerberos
# =============================================================================
log "============================================================"
log "CIS EOD starting — env=${ENV} log=${LOG_FILE}"
log "============================================================"
log "Kerberos: kinit -kt ${KEYTAB} ${PRINCIPAL}"
/usr/bin/kinit -kt "${KEYTAB}" "${PRINCIPAL}" 2>&1 | tee -a "${LOG_FILE}"
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    log_err "kinit failed — check keytab and principal"
    exit 1
fi
log_ok "Kerberos ticket obtained"

# =============================================================================
# Resolve processing_date from gmpcisalldates.txt
#
# File: /sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt
# Format (| separated, no header schema):
#   Line 1: Header  — skip
#   Line 2: 20260713|20260715|20260713|   ← body
#            field1   field2   field3
#            trade    settle   report_date ← processing_date
#   Last  : Trailer — skip
# =============================================================================
if [[ -z "${processing_date_raw}" ]]; then
    log "No --date supplied — reading from ${GMP_ALLDATES_FILE}"
    if [[ ! -f "${GMP_ALLDATES_FILE}" ]]; then
        log_err "alldates file not found: ${GMP_ALLDATES_FILE}"
        exit 1
    fi
    body_line=$(sed -n '2p' "${GMP_ALLDATES_FILE}")
    if [[ -z "${body_line}" ]]; then
        log_err "alldates file has no body line (line 2 is empty): ${GMP_ALLDATES_FILE}"
        exit 1
    fi
    processing_date_raw=$(echo "${body_line}" | cut -d'|' -f3)
    sod_date_raw=$(echo "${body_line}"         | cut -d'|' -f2)   # PLACEHOLDER — confirm field
    log "alldates body line    : [${body_line}]"
    log "processing_date (f3)  : ${processing_date_raw}"
    log "sod_date (f2)         : ${sod_date_raw}  ← PLACEHOLDER field index"
else
    log "--date supplied        : ${processing_date_raw}"
    # Still read sod_date from file even when date is overridden
    if [[ -f "${GMP_ALLDATES_FILE}" ]]; then
        body_line=$(sed -n '2p' "${GMP_ALLDATES_FILE}")
        sod_date_raw=$(echo "${body_line}" | cut -d'|' -f2)       # PLACEHOLDER
    else
        sod_date_raw="${processing_date_raw}"                      # fallback: same date
    fi
fi

# Validate YYYYMMDD format
if [[ ! "${processing_date_raw}" =~ ^[0-9]{8}$ ]]; then
    log_err "processing_date '${processing_date_raw}' is not YYYYMMDD format"
    exit 1
fi

# Convert YYYYMMDD → YYYY-MM-DD for manage.py commands
processing_date="${processing_date_raw:0:4}-${processing_date_raw:4:2}-${processing_date_raw:6:2}"
sod_date="${sod_date_raw:0:4}-${sod_date_raw:4:2}-${sod_date_raw:6:2}"

# Correction job: only on days 1-7 of month
day_of_month=$(date -d "${processing_date}" +%d 2>/dev/null || echo "$(date +%d)")
day_of_month=$((10#${day_of_month}))   # strip leading zero
if [[ ${day_of_month} -ge 1 && ${day_of_month} -le 7 ]]; then
    run_correction=true
else
    run_correction=false
fi

log "processing_date (fmt)  : ${processing_date}"
log "sod_date (fmt)         : ${sod_date}"
log "day_of_month           : ${day_of_month}"
log "correction enabled     : ${run_correction}"
log "resuming from step     : ${START_FROM}"

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
    log "impala-shell -i ${IMPALA_DAEMON}:${IMPALA_PORT} --var=processing_date=${processing_date_raw}"
    impala-shell \
        -i "${IMPALA_DAEMON}:${IMPALA_PORT}" \
        --var=processing_date="${processing_date_raw}" \
        -f "${SQL_FILE}" \
        2>&1 | tee -a "${LOG_FILE}"
    [[ ${PIPESTATUS[0]} -ne 0 ]] && error_exit "impala-shell equity_price_copy failed"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 2 — Corporate Actions (EOD run)
# =============================================================================
CURRENT_STEP=2
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Corporate Actions — process_corporate_actions --run-type EOD"
    run_manage ${CURRENT_STEP} \
        process_corporate_actions \
        --date "${processing_date}" \
        --run-type EOD \
        --user SYSTEM
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 3 — Cash Flow (EOD run)
# =============================================================================
CURRENT_STEP=3
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Cash Flow — process_approved_cashflows --run-type EOD"
    run_manage ${CURRENT_STEP} \
        process_approved_cashflows \
        --run-type EOD \
        --position-date "${processing_date}"
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 4 — EOD Settlements
# =============================================================================
CURRENT_STEP=4
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "EOD Settlements — process_settlements"
    run_manage ${CURRENT_STEP} \
        process_settlements \
        --date "${processing_date}" \
        --user SYSTEM
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 5 — SOD Snapshot (next contextual date from alldates)
# =============================================================================
CURRENT_STEP=5
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "SOD Snapshot — create_sod_snapshot (sod_date=${sod_date})"
    log "NOTE: sod_date field index is PLACEHOLDER — confirm against alldates schema"
    run_manage ${CURRENT_STEP} \
        create_sod_snapshot
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# STEP 6 — Correction (first week of month only)
#   Runs both CA correction and Cash Flow correction
# =============================================================================
CURRENT_STEP=6
if should_run ${CURRENT_STEP}; then
    log_step ${CURRENT_STEP} "Correction — run_correction=${run_correction} (day_of_month=${day_of_month})"
    if [[ "${run_correction}" == "true" ]]; then
        log "Running CA correction..."
        run_manage ${CURRENT_STEP} \
            process_corporate_actions \
            --date "${processing_date}" \
            --run-type CORR \
            --user SYSTEM

        log "Running Cash Flow correction..."
        run_manage ${CURRENT_STEP} \
            process_approved_cashflows \
            --run-type CORR \
            --position-date "${processing_date}"
    else
        log "Correction skipped — day ${day_of_month} is not in first week (1-7)"
    fi
    mark_done ${CURRENT_STEP}
fi

# =============================================================================
# All steps done
# =============================================================================
rm -f "${STATE_FILE}"
log ""
log "============================================================"
log "CIS EOD COMPLETED — env=${ENV} processing_date=${processing_date}"
log "============================================================"
