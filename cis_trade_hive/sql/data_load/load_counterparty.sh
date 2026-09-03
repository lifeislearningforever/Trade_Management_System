#!/bin/bash
# ============================================================================
# Load Counterparty Data to Kudu
# ============================================================================
# Purpose: Create table and load counterparty data into Kudu
# Author: Claude Code
# Date: 2025-01-07
# ============================================================================

set -e  # Exit on error

echo "============================================================================"
echo "Counterparty Data Load to Kudu"
echo "============================================================================"
echo ""

# Configuration
IMPALA_HOST="${IMPALA_HOST:-localhost}"
IMPALA_PORT="${IMPALA_PORT:-21050}"
DDL_FILE="sql/ddl/cis_counterparty_kudu.sql"
DATA_FILE="sql/data_load/insert_counterparty_data.sql"

echo "Configuration:"
echo "  Impala Host: $IMPALA_HOST"
echo "  Impala Port: $IMPALA_PORT"
echo "  DDL File: $DDL_FILE"
echo "  Data File: $DATA_FILE"
echo ""

# Check if files exist
if [ ! -f "$DDL_FILE" ]; then
    echo "ERROR: DDL file not found: $DDL_FILE"
    exit 1
fi

if [ ! -f "$DATA_FILE" ]; then
    echo "ERROR: Data file not found: $DATA_FILE"
    exit 1
fi

# Step 1: Create Kudu table
echo "Step 1: Creating Kudu table..."
echo "Executing: $DDL_FILE"
impala-shell -i "$IMPALA_HOST:$IMPALA_PORT" -k --ssl -f "$DDL_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Table created successfully"
else
    echo "❌ Failed to create table"
    exit 1
fi

echo ""

# Step 2: Load data
echo "Step 2: Loading counterparty data..."
echo "Executing: $DATA_FILE"
echo "(This may take several minutes for 6535 records...)"

impala-shell -i "$IMPALA_HOST:$IMPALA_PORT" -k --ssl -f "$DATA_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Data loaded successfully"
else
    echo "❌ Failed to load data"
    exit 1
fi

echo ""

# Step 3: Verify data
echo "Step 3: Verifying data load..."
QUERY="USE gmp_cis; SELECT COUNT(*) as total_count FROM cis_counterparty_kudu;"

echo "Running: $QUERY"
impala-shell -i "$IMPALA_HOST:$IMPALA_PORT" -k --ssl -q "$QUERY"

echo ""

# Step 4: Show sample data
echo "Step 4: Sample data (first 10 records)..."
SAMPLE_QUERY="USE gmp_cis; SELECT counterparty_short_name, m_label, country, is_bank, is_issuer FROM cis_counterparty_kudu LIMIT 10;"

echo "Running: $SAMPLE_QUERY"
impala-shell -i "$IMPALA_HOST:$IMPALA_PORT" -k --ssl -q "$SAMPLE_QUERY"

echo ""
echo "============================================================================"
echo "✅ Counterparty data load completed successfully!"
echo "============================================================================"
echo ""
echo "Next steps:"
echo "1. Update Django repository to use cis_counterparty_kudu table"
echo "2. Update reference_data/repositories/reference_data_repository.py"
echo "3. Change TABLE_NAME from 'gmp_cis_sta_dly_counterparty' to 'cis_counterparty_kudu'"
echo "4. Test the application"
echo ""
