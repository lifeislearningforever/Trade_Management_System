#!/bin/bash
#===============================================================================
# Kudu Backup and Restore Wrapper Script
#===============================================================================
# This script provides a simple wrapper for Kudu backup/restore operations.
# Uses the official kudu-backup JAR for reliable backup operations.
#
# Usage:
#   ./kudu_backup.sh full-backup --table cis_trade
#   ./kudu_backup.sh incremental-backup --table cis_trade --hours-back 24
#   ./kudu_backup.sh full-restore --table cis_trade --backup-path <path>
#   ./kudu_backup.sh incremental-restore --table cis_trade --backup-path <path>
#   ./kudu_backup.sh list-backups --table cis_trade
#   ./kudu_backup.sh status
#
# Author: CIS Trade Hive Team
# Version: 1.0
# Date: 2026-04-01
#===============================================================================

set -e  # Exit on error

#-------------------------------------------------------------------------------
# Configuration - Modify these for your environment
#-------------------------------------------------------------------------------

# Kudu/Spark configuration
KUDU_MASTER="${KUDU_MASTER:-kudu-master:7051}"
SPARK_MASTER="${SPARK_MASTER:-yarn}"
DATABASE="${DATABASE:-gmp_cis}"

# Paths
BACKUP_PATH="${BACKUP_PATH:-hdfs:///backups/kudu}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAR_PATH="${JAR_PATH:-/jars/kudu}"

# JAR files (adjust versions as needed)
KUDU_SPARK_JAR="${KUDU_SPARK_JAR:-${JAR_PATH}/kudu-spark3_2.12-1.17.0.jar}"
KUDU_BACKUP_JAR="${KUDU_BACKUP_JAR:-${JAR_PATH}/kudu-backup3_2.12-1.17.0.jar}"

# Spark submit options
SPARK_DRIVER_MEMORY="${SPARK_DRIVER_MEMORY:-4g}"
SPARK_EXECUTOR_MEMORY="${SPARK_EXECUTOR_MEMORY:-4g}"
SPARK_EXECUTOR_CORES="${SPARK_EXECUTOR_CORES:-2}"
SPARK_NUM_EXECUTORS="${SPARK_NUM_EXECUTORS:-4}"

# Logging
LOG_DIR="${LOG_DIR:-/var/log/kudu-backup}"
LOG_FILE="${LOG_DIR}/kudu_backup_$(date +%Y%m%d).log"

#-------------------------------------------------------------------------------
# Helper Functions
#-------------------------------------------------------------------------------

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}" 2>/dev/null || echo "[${timestamp}] [${level}] ${message}"
}

info() { log "INFO" "$@"; }
warn() { log "WARN" "$@"; }
error() { log "ERROR" "$@"; }

check_prerequisites() {
    info "Checking prerequisites..."

    # Check spark-submit
    if ! command -v spark-submit &> /dev/null; then
        error "spark-submit not found. Please ensure Spark is installed and in PATH."
        exit 1
    fi

    # Check JAR files exist (for local testing)
    if [[ "${SPARK_MASTER}" == "local"* ]]; then
        if [[ ! -f "${KUDU_SPARK_JAR}" ]]; then
            warn "Kudu Spark JAR not found at ${KUDU_SPARK_JAR}"
        fi
        if [[ ! -f "${KUDU_BACKUP_JAR}" ]]; then
            warn "Kudu Backup JAR not found at ${KUDU_BACKUP_JAR}"
        fi
    fi

    info "Prerequisites check completed"
}

create_log_dir() {
    mkdir -p "${LOG_DIR}" 2>/dev/null || true
}

build_spark_submit_cmd() {
    local script="$1"
    shift
    local extra_args="$@"

    echo "spark-submit \
        --master ${SPARK_MASTER} \
        --deploy-mode client \
        --driver-memory ${SPARK_DRIVER_MEMORY} \
        --executor-memory ${SPARK_EXECUTOR_MEMORY} \
        --executor-cores ${SPARK_EXECUTOR_CORES} \
        --num-executors ${SPARK_NUM_EXECUTORS} \
        --jars ${KUDU_SPARK_JAR},${KUDU_BACKUP_JAR} \
        --conf spark.kudu.master=${KUDU_MASTER} \
        ${script} \
        --kudu-master ${KUDU_MASTER} \
        --database ${DATABASE} \
        --backup-path ${BACKUP_PATH} \
        ${extra_args}"
}

#-------------------------------------------------------------------------------
# Backup Commands
#-------------------------------------------------------------------------------

cmd_full_backup() {
    info "Starting full backup..."

    local table=""
    local all_tables=false
    local dry_run=false
    local compression="snappy"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -t|--table) table="$2"; shift 2 ;;
            -a|--all-tables) all_tables=true; shift ;;
            --dry-run) dry_run=true; shift ;;
            -c|--compression) compression="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    local extra_args="--compression ${compression}"

    if [[ "${all_tables}" == true ]]; then
        extra_args="${extra_args} --all-tables"
    elif [[ -n "${table}" ]]; then
        extra_args="${extra_args} --table ${table}"
    else
        error "Must specify --table or --all-tables"
        exit 1
    fi

    if [[ "${dry_run}" == true ]]; then
        extra_args="${extra_args} --dry-run"
    fi

    local cmd=$(build_spark_submit_cmd "${SCRIPT_DIR}/kudu_full_backup.py" "${extra_args}")
    info "Executing: ${cmd}"
    eval "${cmd}"

    local exit_code=$?
    if [[ ${exit_code} -eq 0 ]]; then
        info "Full backup completed successfully"
    else
        error "Full backup failed with exit code ${exit_code}"
    fi
    return ${exit_code}
}

cmd_incremental_backup() {
    info "Starting incremental backup..."

    local table=""
    local all_tables=false
    local hours_back=24
    local since=""
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -t|--table) table="$2"; shift 2 ;;
            -a|--all-tables) all_tables=true; shift ;;
            -H|--hours-back) hours_back="$2"; shift 2 ;;
            -s|--since) since="$2"; shift 2 ;;
            --dry-run) dry_run=true; shift ;;
            *) shift ;;
        esac
    done

    local extra_args="--hours-back ${hours_back}"

    if [[ -n "${since}" ]]; then
        extra_args="--since '${since}'"
    fi

    if [[ "${all_tables}" == true ]]; then
        extra_args="${extra_args} --all-tables"
    elif [[ -n "${table}" ]]; then
        extra_args="${extra_args} --table ${table}"
    else
        error "Must specify --table or --all-tables"
        exit 1
    fi

    if [[ "${dry_run}" == true ]]; then
        extra_args="${extra_args} --dry-run"
    fi

    local cmd=$(build_spark_submit_cmd "${SCRIPT_DIR}/kudu_incremental_backup.py" "${extra_args}")
    info "Executing: ${cmd}"
    eval "${cmd}"

    local exit_code=$?
    if [[ ${exit_code} -eq 0 ]]; then
        info "Incremental backup completed successfully"
    else
        error "Incremental backup failed with exit code ${exit_code}"
    fi
    return ${exit_code}
}

#-------------------------------------------------------------------------------
# Restore Commands
#-------------------------------------------------------------------------------

cmd_full_restore() {
    info "Starting full restore..."

    local table=""
    local backup_path_arg=""
    local mode="truncate_insert"
    local dry_run=false
    local validate=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -t|--table) table="$2"; shift 2 ;;
            -b|--backup-path) backup_path_arg="$2"; shift 2 ;;
            -M|--mode) mode="$2"; shift 2 ;;
            --dry-run) dry_run=true; shift ;;
            --validate) validate=true; shift ;;
            *) shift ;;
        esac
    done

    if [[ -z "${table}" ]]; then
        error "Must specify --table"
        exit 1
    fi

    if [[ -z "${backup_path_arg}" ]]; then
        error "Must specify --backup-path"
        exit 1
    fi

    local extra_args="--table ${table} --backup-path ${backup_path_arg} --mode ${mode}"

    if [[ "${dry_run}" == true ]]; then
        extra_args="${extra_args} --dry-run"
    fi

    if [[ "${validate}" == true ]]; then
        extra_args="${extra_args} --validate"
    fi

    local cmd=$(build_spark_submit_cmd "${SCRIPT_DIR}/kudu_full_restore.py" "${extra_args}")
    info "Executing: ${cmd}"
    eval "${cmd}"

    local exit_code=$?
    if [[ ${exit_code} -eq 0 ]]; then
        info "Full restore completed successfully"
    else
        error "Full restore failed with exit code ${exit_code}"
    fi
    return ${exit_code}
}

cmd_incremental_restore() {
    info "Starting incremental restore..."

    local table=""
    local backup_path_arg=""
    local backup_base=""
    local since=""
    local until=""
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -t|--table) table="$2"; shift 2 ;;
            -b|--backup-path) backup_path_arg="$2"; shift 2 ;;
            --backup-base) backup_base="$2"; shift 2 ;;
            --since) since="$2"; shift 2 ;;
            --until) until="$2"; shift 2 ;;
            --dry-run) dry_run=true; shift ;;
            *) shift ;;
        esac
    done

    if [[ -z "${table}" ]]; then
        error "Must specify --table"
        exit 1
    fi

    local extra_args="--table ${table}"

    if [[ -n "${backup_path_arg}" ]]; then
        extra_args="${extra_args} --backup-path ${backup_path_arg}"
    elif [[ -n "${backup_base}" ]]; then
        extra_args="${extra_args} --backup-base ${backup_base}"
        [[ -n "${since}" ]] && extra_args="${extra_args} --since ${since}"
        [[ -n "${until}" ]] && extra_args="${extra_args} --until ${until}"
    else
        error "Must specify --backup-path or --backup-base"
        exit 1
    fi

    if [[ "${dry_run}" == true ]]; then
        extra_args="${extra_args} --dry-run"
    fi

    local cmd=$(build_spark_submit_cmd "${SCRIPT_DIR}/kudu_incremental_restore.py" "${extra_args}")
    info "Executing: ${cmd}"
    eval "${cmd}"

    local exit_code=$?
    if [[ ${exit_code} -eq 0 ]]; then
        info "Incremental restore completed successfully"
    else
        error "Incremental restore failed with exit code ${exit_code}"
    fi
    return ${exit_code}
}

#-------------------------------------------------------------------------------
# Utility Commands
#-------------------------------------------------------------------------------

cmd_list_backups() {
    local table="$2"

    if [[ -z "${table}" ]]; then
        info "Listing all backups at ${BACKUP_PATH}/${DATABASE}/"
        hdfs dfs -ls -R "${BACKUP_PATH}/${DATABASE}/" 2>/dev/null | head -50 || \
            echo "Cannot list HDFS path. Ensure HDFS is accessible."
    else
        info "Listing backups for table: ${table}"
        echo ""
        echo "Full Backups:"
        hdfs dfs -ls "${BACKUP_PATH}/${DATABASE}/${table}/full/" 2>/dev/null || \
            echo "  No full backups found"
        echo ""
        echo "Incremental Backups:"
        hdfs dfs -ls "${BACKUP_PATH}/${DATABASE}/${table}/incremental/" 2>/dev/null | tail -20 || \
            echo "  No incremental backups found"
    fi
}

cmd_status() {
    echo "========================================================================"
    echo "  KUDU BACKUP STATUS"
    echo "========================================================================"
    echo ""
    echo "Configuration:"
    echo "  Kudu Master:     ${KUDU_MASTER}"
    echo "  Spark Master:    ${SPARK_MASTER}"
    echo "  Database:        ${DATABASE}"
    echo "  Backup Path:     ${BACKUP_PATH}"
    echo "  JAR Path:        ${JAR_PATH}"
    echo "  Log Directory:   ${LOG_DIR}"
    echo ""
    echo "Spark Resources:"
    echo "  Driver Memory:   ${SPARK_DRIVER_MEMORY}"
    echo "  Executor Memory: ${SPARK_EXECUTOR_MEMORY}"
    echo "  Executor Cores:  ${SPARK_EXECUTOR_CORES}"
    echo "  Num Executors:   ${SPARK_NUM_EXECUTORS}"
    echo ""

    # Check disk usage
    echo "Backup Storage:"
    hdfs dfs -du -h "${BACKUP_PATH}/${DATABASE}/" 2>/dev/null | head -20 || \
        echo "  Cannot access HDFS"

    echo ""
    echo "========================================================================"
}

cmd_cleanup() {
    local days="${2:-30}"

    info "Cleaning up backups older than ${days} days..."

    # Calculate cutoff date
    local cutoff_date=$(date -d "${days} days ago" +%Y-%m-%d 2>/dev/null || \
                        date -v-${days}d +%Y-%m-%d)

    info "Cutoff date: ${cutoff_date}"

    echo ""
    echo "The following backups would be deleted (older than ${cutoff_date}):"
    echo "(Add --execute to actually delete)"

    # This is a placeholder - actual implementation would iterate and delete
    hdfs dfs -ls "${BACKUP_PATH}/${DATABASE}/*/full/" 2>/dev/null | \
        awk -v cutoff="${cutoff_date}" '$6 < cutoff {print $8}' | head -20
}

show_help() {
    cat << EOF
Kudu Backup and Restore Utility
================================

Usage: $(basename "$0") <command> [options]

Commands:
  full-backup         Run full backup of Kudu tables
  incremental-backup  Run incremental backup (changes since last backup)
  full-restore        Restore from a full backup
  incremental-restore Apply incremental backup(s)
  list-backups        List available backups
  status              Show configuration and backup status
  cleanup             Clean up old backups
  help                Show this help message

Full Backup Options:
  -t, --table <name>       Single table to backup
  -a, --all-tables         Backup all tables
  -c, --compression <type> Compression: snappy, gzip, lz4, none (default: snappy)
  --dry-run                Validate without actual backup

Incremental Backup Options:
  -t, --table <name>       Single table to backup
  -a, --all-tables         Backup all tables
  -H, --hours-back <n>     Backup changes from last N hours (default: 24)
  -s, --since <timestamp>  Backup changes since timestamp (YYYY-MM-DD HH:MM:SS)
  --dry-run                Validate without actual backup

Full Restore Options:
  -t, --table <name>       Target table name
  -b, --backup-path <path> Path to backup directory
  -M, --mode <mode>        truncate_insert, upsert, insert_ignore, create_new
  --validate               Validate restore by counting rows
  --dry-run                Validate without actual restore

Incremental Restore Options:
  -t, --table <name>       Target table name
  -b, --backup-path <path> Path to single incremental backup
  --backup-base <path>     Base path for multiple incremental backups
  --since <timestamp>      Apply backups after this timestamp
  --until <timestamp>      Apply backups before this timestamp
  --dry-run                Validate without applying

Examples:
  # Full backup of single table
  $(basename "$0") full-backup --table cis_trade

  # Full backup of all tables
  $(basename "$0") full-backup --all-tables

  # Incremental backup (last 6 hours)
  $(basename "$0") incremental-backup --table cis_trade --hours-back 6

  # Full restore
  $(basename "$0") full-restore --table cis_trade \\
      --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/full/2026-04-01_000000

  # List backups for a table
  $(basename "$0") list-backups --table cis_trade

  # Show status
  $(basename "$0") status

Environment Variables:
  KUDU_MASTER          Kudu master address (default: kudu-master:7051)
  SPARK_MASTER         Spark master (default: yarn)
  DATABASE             Database name (default: gmp_cis)
  BACKUP_PATH          Backup storage path (default: hdfs:///backups/kudu)
  JAR_PATH             Path to Kudu JAR files (default: /jars/kudu)
  SPARK_DRIVER_MEMORY  Spark driver memory (default: 4g)
  SPARK_EXECUTOR_MEMORY Spark executor memory (default: 4g)

EOF
}

#-------------------------------------------------------------------------------
# Main Entry Point
#-------------------------------------------------------------------------------

main() {
    create_log_dir

    local command="${1:-help}"
    shift || true

    case "${command}" in
        full-backup|fullbackup|fb)
            check_prerequisites
            cmd_full_backup "$@"
            ;;
        incremental-backup|incbackup|ib)
            check_prerequisites
            cmd_incremental_backup "$@"
            ;;
        full-restore|fullrestore|fr)
            check_prerequisites
            cmd_full_restore "$@"
            ;;
        incremental-restore|increstore|ir)
            check_prerequisites
            cmd_incremental_restore "$@"
            ;;
        list-backups|list|ls)
            cmd_list_backups "$@"
            ;;
        status|st)
            cmd_status
            ;;
        cleanup)
            cmd_cleanup "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "Unknown command: ${command}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
