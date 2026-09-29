#!/bin/bash
# =============================================================================
# Trade Data Ingestion Script
# =============================================================================
# Purpose: Run PySpark job to ingest trade data from Hive to Kudu
#
# Usage:
#   ./run_trade_ingestion.sh                    # Full load
#   ./run_trade_ingestion.sh --limit 1000       # Test with 1000 records
#   ./run_trade_ingestion.sh --incremental      # Incremental load
#
# =============================================================================

set -e

# Configuration
SOURCE_DB="${SOURCE_DB:-gmp_cis}"
SOURCE_TABLE="${SOURCE_TABLE:-cis_trade_hive}"
TARGET_DB="${TARGET_DB:-gmp_cis}"
TARGET_TABLE="${TARGET_TABLE:-cis_trade}"
BATCH_SIZE="${BATCH_SIZE:-10000}"

# Spark configuration
SPARK_MASTER="${SPARK_MASTER:-yarn}"
DEPLOY_MODE="${DEPLOY_MODE:-cluster}"
EXECUTOR_MEMORY="${EXECUTOR_MEMORY:-4g}"
DRIVER_MEMORY="${DRIVER_MEMORY:-2g}"
NUM_EXECUTORS="${NUM_EXECUTORS:-4}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
LIMIT=""
INCREMENTAL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="--limit $2"
            shift 2
            ;;
        --incremental)
            INCREMENTAL="--incremental-column created_at"
            shift
            ;;
        --source-db)
            SOURCE_DB="$2"
            shift 2
            ;;
        --source-table)
            SOURCE_TABLE="$2"
            shift 2
            ;;
        --target-db)
            TARGET_DB="$2"
            shift 2
            ;;
        --target-table)
            TARGET_TABLE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "Trade Data Ingestion"
echo "=============================================="
echo "Source: ${SOURCE_DB}.${SOURCE_TABLE}"
echo "Target: ${TARGET_DB}.${TARGET_TABLE}"
echo "Batch Size: ${BATCH_SIZE}"
echo "Spark Master: ${SPARK_MASTER}"
echo "=============================================="

# Run Spark job
spark-submit \
    --master ${SPARK_MASTER} \
    --deploy-mode ${DEPLOY_MODE} \
    --executor-memory ${EXECUTOR_MEMORY} \
    --driver-memory ${DRIVER_MEMORY} \
    --num-executors ${NUM_EXECUTORS} \
    --conf spark.sql.shuffle.partitions=200 \
    --conf spark.default.parallelism=100 \
    --conf spark.dynamicAllocation.enabled=true \
    --conf spark.dynamicAllocation.minExecutors=2 \
    --conf spark.dynamicAllocation.maxExecutors=10 \
    "${SCRIPT_DIR}/ingest_trade_simple.py" \
    --source-db "${SOURCE_DB}" \
    --source-table "${SOURCE_TABLE}" \
    --target-db "${TARGET_DB}" \
    --target-table "${TARGET_TABLE}" \
    --batch-size "${BATCH_SIZE}" \
    ${LIMIT} ${INCREMENTAL}

echo "=============================================="
echo "Ingestion Complete!"
echo "=============================================="
