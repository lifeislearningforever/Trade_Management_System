#!/bin/bash
# ============================================================================
# Position Master ETL Runner Script
# ============================================================================
# Usage:
#   ./run_etl.sh <processing_date> [mode] [engine]
#
# Arguments:
#   processing_date : Date in DDMMYYYY format (required)
#   mode           : 'append' or 'overwrite' (default: append)
#   engine         : 'pyspark' or 'hive' (default: pyspark)
#
# Examples:
#   ./run_etl.sh 03032026
#   ./run_etl.sh 03032026 overwrite
#   ./run_etl.sh 03032026 append hive
# ============================================================================

set -e

# Default values
PROCESSING_DATE="${1:-}"
MODE="${2:-append}"
ENGINE="${3:-pyspark}"
BATCH_ID="batch_$(date +%Y%m%d_%H%M%S)"

# Hive connection settings
HIVE_HOST="${HIVE_HOST:-localhost}"
HIVE_PORT="${HIVE_PORT:-10000}"
HIVE_USER="${HIVE_USER:-prakashhosalli}"
HIVE_PASSWORD="${HIVE_PASSWORD:-}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate arguments
if [ -z "$PROCESSING_DATE" ]; then
    print_error "Processing date is required!"
    echo "Usage: $0 <processing_date> [mode] [engine]"
    echo "  processing_date: Date in DDMMYYYY format"
    echo "  mode: 'append' or 'overwrite' (default: append)"
    echo "  engine: 'pyspark' or 'hive' (default: pyspark)"
    exit 1
fi

# Validate date format (DDMMYYYY)
if ! [[ "$PROCESSING_DATE" =~ ^[0-9]{8}$ ]]; then
    print_error "Invalid date format. Expected DDMMYYYY, got: $PROCESSING_DATE"
    exit 1
fi

# Validate mode
if [[ "$MODE" != "append" && "$MODE" != "overwrite" ]]; then
    print_error "Invalid mode. Expected 'append' or 'overwrite', got: $MODE"
    exit 1
fi

# Validate engine
if [[ "$ENGINE" != "pyspark" && "$ENGINE" != "hive" ]]; then
    print_error "Invalid engine. Expected 'pyspark' or 'hive', got: $ENGINE"
    exit 1
fi

echo "============================================================================"
echo "Position Master ETL Job"
echo "============================================================================"
print_info "Processing Date: $PROCESSING_DATE"
print_info "Mode: $MODE"
print_info "Engine: $ENGINE"
print_info "Batch ID: $BATCH_ID"
print_info "Script Directory: $SCRIPT_DIR"
echo "============================================================================"

# Run ETL based on engine choice
if [ "$ENGINE" == "pyspark" ]; then
    print_info "Running PySpark ETL..."

    # Check if spark-submit is available
    if ! command -v spark-submit &> /dev/null; then
        print_error "spark-submit not found. Please ensure Spark is installed and in PATH."
        exit 1
    fi

    # Run PySpark ETL
    spark-submit \
        --master yarn \
        --deploy-mode client \
        --name "PositionMasterETL_${PROCESSING_DATE}" \
        --conf "spark.sql.sources.partitionOverwriteMode=dynamic" \
        --conf "spark.sql.parquet.compression.codec=snappy" \
        --conf "spark.dynamicAllocation.enabled=true" \
        --conf "spark.dynamicAllocation.minExecutors=2" \
        --conf "spark.dynamicAllocation.maxExecutors=10" \
        "${SCRIPT_DIR}/position_master_etl.py" \
        --processing-date "$PROCESSING_DATE" \
        --mode "$MODE" \
        --batch-id "$BATCH_ID"

    ETL_EXIT_CODE=$?

elif [ "$ENGINE" == "hive" ]; then
    print_info "Running Hive SQL ETL..."

    # Check if beeline is available
    if ! command -v beeline &> /dev/null; then
        print_error "beeline not found. Please ensure Hive is installed and in PATH."
        exit 1
    fi

    # Build connection URL
    JDBC_URL="jdbc:hive2://${HIVE_HOST}:${HIVE_PORT}"

    # Build beeline command
    BEELINE_CMD="beeline -u \"${JDBC_URL}\" -n \"${HIVE_USER}\""
    if [ -n "$HIVE_PASSWORD" ]; then
        BEELINE_CMD="${BEELINE_CMD} -p \"${HIVE_PASSWORD}\""
    fi

    # Run Hive SQL ETL
    print_info "Connecting to: $JDBC_URL"

    beeline -u "${JDBC_URL}" \
        -n "${HIVE_USER}" \
        ${HIVE_PASSWORD:+-p "${HIVE_PASSWORD}"} \
        --hivevar processing_date="${PROCESSING_DATE}" \
        --hivevar batch_id="${BATCH_ID}" \
        -f "${SCRIPT_DIR}/04_position_master_etl_hive.sql"

    ETL_EXIT_CODE=$?
fi

# Check exit code
if [ $ETL_EXIT_CODE -eq 0 ]; then
    echo "============================================================================"
    print_info "ETL Job completed successfully!"
    print_info "Processing Date: $PROCESSING_DATE"
    print_info "Batch ID: $BATCH_ID"
    echo "============================================================================"
else
    echo "============================================================================"
    print_error "ETL Job failed with exit code: $ETL_EXIT_CODE"
    echo "============================================================================"
    exit $ETL_EXIT_CODE
fi
