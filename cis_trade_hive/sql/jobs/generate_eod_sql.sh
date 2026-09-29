#!/bin/bash
# ============================================================================
# Generate EOD Settlement SQL with Variable Substitution
# ============================================================================
# Description: Generates a ready-to-run SQL file with date variables replaced.
#
# Usage:
#   ./generate_eod_sql.sh                           # Use today's date
#   ./generate_eod_sql.sh 2026-03-12                # Use specific date
#   ./generate_eod_sql.sh 2026-03-12 MY_USER        # With custom user
#
# Output:
#   Creates eod_settlement_run_YYYYMMDD.sql in current directory
#
# Example:
#   ./generate_eod_sql.sh 2026-03-12
#   impala-shell -i localhost:21050 -d gmp_cis -f eod_settlement_run_20260312.sql
#
# Created: 2026-03-12
# ============================================================================

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="$SCRIPT_DIR/eod_settlement_standalone.sql"

# Parse arguments
SETTLE_DATE="${1:-$(date '+%Y-%m-%d')}"
RUN_BY="${2:-EOD_SYSTEM}"

# Generate derived values
PROCESSING_DATE=$(echo "$SETTLE_DATE" | tr -d '-')
BATCH_ID=$(date +%s%3N)

# Output file
OUTPUT_FILE="eod_settlement_run_${PROCESSING_DATE}.sql"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  EOD Settlement SQL Generator${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Configuration:"
echo "  Settle Date:     $SETTLE_DATE"
echo "  Processing Date: $PROCESSING_DATE"
echo "  Batch ID:        $BATCH_ID"
echo "  Run By:          $RUN_BY"
echo "  Template:        $TEMPLATE_FILE"
echo "  Output:          $OUTPUT_FILE"
echo ""

# Check template exists
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "ERROR: Template file not found: $TEMPLATE_FILE"
    exit 1
fi

# Generate SQL with substitutions
echo "Generating SQL file..."

sed -e "s/'2026-03-12'/'${SETTLE_DATE}'/g" \
    -e "s/1741788000000/${BATCH_ID}/g" \
    -e "s/'20260312'/'${PROCESSING_DATE}'/g" \
    -e "s/'EOD_SYSTEM'/'${RUN_BY}'/g" \
    "$TEMPLATE_FILE" > "$OUTPUT_FILE"

# Verify no template values remain
if grep -q "2026-03-12\|1741788000000\|20260312" "$OUTPUT_FILE"; then
    echo "WARNING: Some template values may not have been replaced correctly"
fi

echo -e "${GREEN}SUCCESS: Generated $OUTPUT_FILE${NC}"
echo ""
echo "To run:"
echo "  impala-shell -i <host>:21050 -d gmp_cis -f $OUTPUT_FILE"
echo ""
echo "Or for local Docker:"
echo "  impala-shell -i localhost:21050 -a NOSASL -d gmp_cis -f $OUTPUT_FILE"
echo ""
