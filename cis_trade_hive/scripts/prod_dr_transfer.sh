#!/bin/bash
#===============================================================================
# PROD -> DR Backup Transfer
#===============================================================================
# Copies a kudu_full_backup.py backup (data + manifest) from PROD's HDFS to
# a path DR's kudu_full_restore_from_manifest.py can read, using
# `hadoop distcp` (a distributed, MapReduce/YARN-based copy -- the standard
# tool for cross-cluster HDFS transfers at scale, not a plain `hdfs dfs -cp`).
#
# WHY THIS SCRIPT EXISTS AT ALL: PROD and DR were confirmed to be on
# different hostnames with UNTESTED cross-cluster reachability at the time
# this was written (see docs/CONTROL_M_DR_SYNC_JOB.md). If it turns out
# DR can already read PROD's backup path directly (shared HDFS namespace,
# viewfs mount, etc.), this whole step can be skipped -- run
# `./prod_dr_transfer.sh test-connectivity` first to find out, before
# wiring this into the daily Control-M chain.
#
# Usage:
#   ./prod_dr_transfer.sh test-connectivity
#   ./prod_dr_transfer.sh transfer-latest
#   ./prod_dr_transfer.sh transfer --manifest manifest_20260807_020000.json
#
# Author: CIS Trade Hive Team
# Version: 1.0
# Date: 2026-08-07
#===============================================================================

set -euo pipefail

#-------------------------------------------------------------------------------
# Configuration -- fill in real values before use. Fully-qualified
# hdfs://host:port/path URIs are required for cross-cluster distcp; a bare
# /path is only ever interpreted against the CURRENT cluster's default
# filesystem, which is exactly the ambiguity that makes cross-cluster
# copies silently target the wrong cluster if you're not careful here.
#-------------------------------------------------------------------------------

PROD_NAMENODE="${PROD_NAMENODE:-hdfs://<PROD_NAMENODE_HOST>:8020}"
DR_NAMENODE="${DR_NAMENODE:-hdfs://<DR_NAMENODE_HOST>:8020}"

DATABASE="${DATABASE:-gmp_cis}"
BACKUP_ROOT="${BACKUP_ROOT:-/backups/gmp_cis}"   # path only, no scheme/host -- combined with the namenode vars above

PROD_BACKUP_PATH="${PROD_NAMENODE}${BACKUP_ROOT}"
DR_BACKUP_PATH="${DR_NAMENODE}${BACKUP_ROOT}"

LOG_DIR="${LOG_DIR:-/var/log/kudu-backup}"
LOG_FILE="${LOG_DIR}/prod_dr_transfer_$(date +%Y%m%d).log"

#-------------------------------------------------------------------------------
# Helpers
#-------------------------------------------------------------------------------

log() {
    local level="$1"; shift
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${ts}] [${level}] $*" | tee -a "${LOG_FILE}" 2>/dev/null || echo "[${ts}] [${level}] $*"
}
info() { log "INFO" "$@"; }
warn() { log "WARN" "$@"; }
error() { log "ERROR" "$@"; }

create_log_dir() { mkdir -p "${LOG_DIR}" 2>/dev/null || true; }

#-------------------------------------------------------------------------------
# test-connectivity: run this FIRST. Confirms (a) this node can list both
# PROD's and DR's backup paths, and (b) whether they're actually the SAME
# reachable filesystem already (in which case distcp is unnecessary).
#-------------------------------------------------------------------------------

cmd_test_connectivity() {
    info "Testing connectivity to PROD backup path: ${PROD_BACKUP_PATH}"
    if hdfs dfs -ls "${PROD_BACKUP_PATH}" >/dev/null 2>&1; then
        info "  OK -- can list PROD backup path"
    else
        error "  FAILED -- cannot list PROD backup path from this node"
    fi

    info "Testing connectivity to DR backup path: ${DR_BACKUP_PATH}"
    if hdfs dfs -ls "${DR_BACKUP_PATH}" >/dev/null 2>&1; then
        info "  OK -- can list DR backup path"
    else
        info "  Cannot list (may not exist yet -- that's fine for a first run). Checking parent..."
        if hdfs dfs -ls "${DR_NAMENODE}$(dirname "${BACKUP_ROOT}")" >/dev/null 2>&1; then
            info "  OK -- DR namenode reachable, parent directory exists"
        else
            error "  FAILED -- cannot reach DR namenode at all from this node"
        fi
    fi

    echo ""
    echo "If BOTH checks above are OK, and PROD_NAMENODE / DR_NAMENODE actually"
    echo "resolve to the SAME underlying storage (e.g. federated HDFS, shared"
    echo "object store), you may not need this transfer script at all --"
    echo "kudu_full_restore_from_manifest.py could read PROD_BACKUP_PATH"
    echo "directly from a DR-side spark-submit. Confirm before assuming distcp"
    echo "is required."
}

#-------------------------------------------------------------------------------
# transfer-latest: find the most recent manifest on PROD, distcp its
# manifest directory AND every table directory it references.
#-------------------------------------------------------------------------------

cmd_transfer_latest() {
    info "Finding latest manifest under ${PROD_BACKUP_PATH}/manifests/"
    local latest
    latest=$(hdfs dfs -ls "${PROD_BACKUP_PATH}/manifests/" 2>/dev/null \
        | awk '{print $8}' | grep 'manifest_.*\.json$' | sort | tail -1)

    if [[ -z "${latest}" ]]; then
        error "No manifest found under ${PROD_BACKUP_PATH}/manifests/"
        exit 1
    fi

    local manifest_name
    manifest_name=$(basename "${latest}")
    info "Latest manifest: ${manifest_name}"
    cmd_transfer --manifest "${manifest_name}"
}

#-------------------------------------------------------------------------------
# transfer: distcp one manifest + the table directories it lists.
#-------------------------------------------------------------------------------

cmd_transfer() {
    local manifest_name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --manifest) manifest_name="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    if [[ -z "${manifest_name}" ]]; then
        error "Must specify --manifest <manifest_<ts>.json>"
        exit 1
    fi

    local backup_id="${manifest_name#manifest_}"
    backup_id="${backup_id%.json}"
    info "Backup id: ${backup_id}"

    info "Transferring manifest directory..."
    hadoop distcp -update \
        "${PROD_BACKUP_PATH}/manifests/${manifest_name}" \
        "${DR_BACKUP_PATH}/manifests/${manifest_name}"

    info "Reading manifest to find table list..."
    local manifest_json
    manifest_json=$(hdfs dfs -cat "${PROD_BACKUP_PATH}/manifests/${manifest_name}/part-*" 2>/dev/null)

    if [[ -z "${manifest_json}" ]]; then
        error "Could not read manifest content -- aborting transfer"
        exit 1
    fi

    # Extract table names via python (avoids depending on jq being installed
    # on the edge node -- python3 is already a hard requirement everywhere
    # else in this project).
    local tables
    tables=$(python3 -c "
import json, sys
m = json.loads(sys.argv[1])
for t in m.get('tables', []):
    if t.get('status') == 'SUCCESS':
        print(t.get('table'))
" "${manifest_json}")

    local count
    count=$(echo "${tables}" | grep -c . || true)
    info "Transferring ${count} table director(ies)..."

    while IFS= read -r table; do
        [[ -z "${table}" ]] && continue
        info "  ${table}"
        hadoop distcp -update \
            "${PROD_BACKUP_PATH}/${DATABASE}/${table}/full/${backup_id}" \
            "${DR_BACKUP_PATH}/${DATABASE}/${table}/full/${backup_id}"
    done <<< "${tables}"

    info "Transfer complete for backup ${backup_id}"
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

show_help() {
    cat << EOF
PROD -> DR Backup Transfer
===========================

Usage: $(basename "$0") <command> [options]

Commands:
  test-connectivity          Check whether this node can reach both
                              PROD and DR backup paths (RUN THIS FIRST)
  transfer-latest             distcp the most recent PROD manifest + its tables to DR
  transfer --manifest <name>  distcp a specific manifest + its tables to DR
  help                        Show this help message

Environment Variables:
  PROD_NAMENODE   Fully-qualified PROD HDFS URI, e.g. hdfs://prod-nn:8020
  DR_NAMENODE     Fully-qualified DR HDFS URI, e.g. hdfs://dr-nn:8020
  DATABASE        Database name (default: gmp_cis)
  BACKUP_ROOT     Backup path, no scheme/host (default: /backups/gmp_cis)
  LOG_DIR         Log directory (default: /var/log/kudu-backup)

Example (Control-M DR_SYNC_TRANSFER job -- see docs/CONTROL_M_DR_SYNC_JOB.md):
  PROD_NAMENODE=hdfs://lxmrwpsgv0w1:8020 \\
  DR_NAMENODE=hdfs://lxmrwrsgv0w1:8020 \\
  $(basename "$0") transfer-latest
EOF
}

create_log_dir
COMMAND="${1:-help}"
shift || true

case "${COMMAND}" in
    test-connectivity|test|tc) cmd_test_connectivity ;;
    transfer-latest|tl)        cmd_transfer_latest ;;
    transfer|t)                cmd_transfer "$@" ;;
    help|--help|-h)            show_help ;;
    *)
        error "Unknown command: ${COMMAND}"
        show_help
        exit 1
        ;;
esac
