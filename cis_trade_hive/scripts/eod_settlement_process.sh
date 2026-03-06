#!/bin/bash
# =============================================================================
# EOD Settlement Processing Script
# =============================================================================
# Description: End-of-Day settlement processing for AVP position calculation.
#              Processes pending settlements from cis_settlement_queue and
#              creates positions in cis_trade_position table.
#
# Usage:
#   ./scripts/eod_settlement_process.sh [OPTIONS]
#
# Options:
#   -d, --date DATE       Settlement date to process (YYYY-MM-DD), default: today
#   -e, --env ENV         Environment: local, dev, prod (default: local)
#   -u, --user USER       User running the job (default: SYSTEM)
#   -n, --dry-run         Show what would be processed without executing
#   -v, --verbose         Enable verbose output
#   -h, --help            Show this help message
#
# Examples:
#   ./scripts/eod_settlement_process.sh                    # Process today's settlements
#   ./scripts/eod_settlement_process.sh -d 2026-03-06      # Process specific date
#   ./scripts/eod_settlement_process.sh -e prod            # Run in production
#   ./scripts/eod_settlement_process.sh -n                 # Dry run
#
# Schedule with cron for automated EOD:
#   0 18 * * 1-5 /path/to/scripts/eod_settlement_process.sh -e prod >> /var/log/eod_settlement.log 2>&1
#
# Created: 2026-03-06
# Version: 1.0
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SQL_DIR="$PROJECT_DIR/sql/jobs"
LOG_DIR="/tmp/cis_eod_logs"

# Default values
SETTLE_DATE=$(date '+%Y-%m-%d')
PROCESSING_DATE=$(date '+%Y%m%d')
ENVIRONMENT="local"
RUN_BY="SYSTEM"
DRY_RUN=false
VERBOSE=false

# Impala connection settings per environment
declare -A IMPALA_HOSTS=(
    ["local"]="localhost:21050"
    ["dev"]="dev-impala.example.com:21050"
    ["prod"]="prod-impala.example.com:21050"
)

declare -A IMPALA_AUTH=(
    ["local"]="NOSASL"
    ["dev"]="GSSAPI"
    ["prod"]="GSSAPI"
)

# Database
DATABASE="gmp_cis"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() { echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_debug() { [[ "$VERBOSE" == "true" ]] && echo -e "${BLUE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_section() { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

show_help() {
    head -40 "$0" | tail -35 | sed 's/^# //' | sed 's/^#//'
}

generate_batch_id() {
    # Generate unique batch ID: timestamp in milliseconds
    echo $(date +%s%3N)
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--date)
            SETTLE_DATE="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -u|--user)
            RUN_BY="$2"
            shift 2
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! -v "IMPALA_HOSTS[$ENVIRONMENT]" ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Must be: local, dev, or prod"
    exit 1
fi

# Get Impala connection settings
IMPALA_HOST="${IMPALA_HOSTS[$ENVIRONMENT]}"
AUTH_METHOD="${IMPALA_AUTH[$ENVIRONMENT]}"

# Generate batch ID
BATCH_ID=$(generate_batch_id)

# =============================================================================
# Pre-flight Checks
# =============================================================================

preflight_checks() {
    log_section "Pre-flight Checks"

    # Check impala-shell is available
    if ! command -v impala-shell &> /dev/null; then
        log_error "impala-shell not found in PATH"
        exit 1
    fi
    log_info "impala-shell: OK"

    # Check SQL file exists
    if [[ ! -f "$SQL_DIR/eod_settlement_process.sql" ]]; then
        log_error "SQL file not found: $SQL_DIR/eod_settlement_process.sql"
        exit 1
    fi
    log_info "SQL file: OK"

    # Create log directory
    mkdir -p "$LOG_DIR"
    log_info "Log directory: $LOG_DIR"

    # Test Impala connection
    log_info "Testing Impala connection to $IMPALA_HOST..."
    local test_query="SELECT 1"
    local auth_args=""

    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    if ! impala-shell -i "$IMPALA_HOST" $auth_args -q "$test_query" &> /dev/null; then
        log_error "Cannot connect to Impala at $IMPALA_HOST"
        exit 1
    fi
    log_info "Impala connection: OK"
}

# =============================================================================
# Get Pending Settlements Count
# =============================================================================

get_pending_count() {
    local auth_args=""
    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    local query="SELECT COUNT(*) FROM $DATABASE.cis_settlement_queue WHERE settle_date <= '$SETTLE_DATE' AND status = 'PENDING'"

    local count=$(impala-shell -i "$IMPALA_HOST" $auth_args -d "$DATABASE" -q "$query" --quiet 2>/dev/null | grep -E '^[0-9]+$' | head -1)

    echo "${count:-0}"
}

# =============================================================================
# Show Pending Settlements
# =============================================================================

show_pending_settlements() {
    local auth_args=""
    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    local query="
    SELECT
        queue_id,
        trade_id,
        portfolio_id,
        security_id,
        trade_type,
        CAST(quantity AS STRING) as quantity,
        CAST(price AS STRING) as price,
        settle_date
    FROM $DATABASE.cis_settlement_queue
    WHERE settle_date <= '$SETTLE_DATE'
      AND status = 'PENDING'
    ORDER BY settle_date, queued_at
    LIMIT 20
    "

    log_info "Pending settlements (showing first 20):"
    impala-shell -i "$IMPALA_HOST" $auth_args -d "$DATABASE" -q "$query" --delimited --output_delimiter='|' 2>/dev/null | \
        awk -F'|' 'NR>1 {printf "  Trade %s: %s %s %s @ %s (settle: %s)\n", $2, $5, $6, $4, $7, $8}'
}

# =============================================================================
# Run EOD Settlement Process
# =============================================================================

run_eod_settlement() {
    log_section "EOD Settlement Processing"

    log_info "Configuration:"
    log_info "  Environment:     $ENVIRONMENT"
    log_info "  Impala Host:     $IMPALA_HOST"
    log_info "  Settlement Date: $SETTLE_DATE"
    log_info "  Processing Date: $PROCESSING_DATE"
    log_info "  Batch ID:        $BATCH_ID"
    log_info "  Run By:          $RUN_BY"

    # Get pending count
    local pending_count=$(get_pending_count)
    log_info "  Pending Records: $pending_count"

    if [[ "$pending_count" -eq 0 ]]; then
        log_warn "No pending settlements to process for $SETTLE_DATE"
        return 0
    fi

    # Show pending settlements
    if [[ "$VERBOSE" == "true" ]]; then
        show_pending_settlements
    fi

    # Dry run check
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY RUN - No changes will be made"
        show_pending_settlements
        return 0
    fi

    # Prepare auth arguments
    local auth_args=""
    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    # Log file for this run
    local log_file="$LOG_DIR/eod_settlement_${PROCESSING_DATE}_${BATCH_ID}.log"

    log_section "Executing Settlement Processing"
    log_info "Log file: $log_file"
    log_info "Processing $pending_count settlements..."

    # Execute the SQL script with variables
    local start_time=$(date +%s)

    if impala-shell -i "$IMPALA_HOST" $auth_args -d "$DATABASE" \
        --var=SETTLE_DATE="$SETTLE_DATE" \
        --var=BATCH_ID="$BATCH_ID" \
        --var=RUN_BY="$RUN_BY" \
        --var=PROCESSING_DATE="$PROCESSING_DATE" \
        -f "$SQL_DIR/eod_settlement_process.sql" \
        > "$log_file" 2>&1; then

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        log_info "Settlement processing completed successfully"
        log_info "Duration: ${duration} seconds"

        # Show summary
        show_batch_summary

        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))

        log_error "Settlement processing failed after ${duration} seconds"
        log_error "Check log file: $log_file"

        # Show last 20 lines of log
        log_error "Last 20 lines of log:"
        tail -20 "$log_file"

        return 1
    fi
}

# =============================================================================
# Show Batch Summary
# =============================================================================

show_batch_summary() {
    local auth_args=""
    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    log_section "Batch Summary"

    local query="
    SELECT
        batch_id,
        batch_date,
        status,
        total_pending,
        processed_count,
        failed_count,
        started_at,
        completed_at
    FROM $DATABASE.cis_eod_settlement_batch
    WHERE batch_id = $BATCH_ID
    "

    impala-shell -i "$IMPALA_HOST" $auth_args -d "$DATABASE" -q "$query" 2>/dev/null
}

# =============================================================================
# Show Position Results
# =============================================================================

show_position_results() {
    local auth_args=""
    if [[ "$AUTH_METHOD" == "NOSASL" ]]; then
        auth_args="-a NOSASL"
    fi

    log_section "Position Results"

    local query="
    SELECT
        portfolio_short_name,
        security_label,
        CAST(quantity AS STRING) as quantity,
        CAST(average_cost AS STRING) as avg_cost,
        CAST(total_cost AS STRING) as total_cost,
        CAST(realized_pnl AS STRING) as realized_pnl,
        status,
        position_date
    FROM $DATABASE.cis_trade_position
    WHERE created_by = '$RUN_BY'
      AND created_at >= '$SETTLE_DATE'
    ORDER BY version_id DESC
    LIMIT 20
    "

    impala-shell -i "$IMPALA_HOST" $auth_args -d "$DATABASE" -q "$query" 2>/dev/null
}

# =============================================================================
# Main
# =============================================================================

main() {
    log_section "CIS Trade Hive - EOD Settlement Processing"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Run pre-flight checks
    preflight_checks

    # Run EOD settlement
    if run_eod_settlement; then
        log_section "EOD Settlement Completed Successfully"

        # Show position results if verbose
        if [[ "$VERBOSE" == "true" ]]; then
            show_position_results
        fi

        exit 0
    else
        log_section "EOD Settlement Failed"
        exit 1
    fi
}

# Run main
main
