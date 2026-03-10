#!/bin/bash
#
# SIT to UAT Database Migration - DDL Extraction Script
#
# This script extracts DDL from SIT Impala/Kudu database and generates
# migration files for UAT deployment.
#
# Usage:
#   # Extract DDL only (local Docker)
#   ./run_extraction.sh
#
#   # Extract DDL from specific SIT host
#   ./run_extraction.sh --host sit-impala-host.company.com --port 21050
#
#   # Extract DDL and data
#   ./run_extraction.sh --host sit-impala-host --include-data
#
#   # Extract specific tables
#   ./run_extraction.sh --tables cis_trade,cis_portfolio,cis_trade_position
#
#   # CML environment with Kerberos
#   ./run_extraction.sh --host sit-impala-host --auth GSSAPI
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default values
SIT_HOST="${SIT_IMPALA_HOST:-localhost}"
SIT_PORT="${SIT_IMPALA_PORT:-21050}"
SIT_AUTH="${SIT_IMPALA_AUTH:-NOSASL}"
INCLUDE_DATA=false
TABLES=""
DATA_LIMIT=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            SIT_HOST="$2"
            shift 2
            ;;
        --port)
            SIT_PORT="$2"
            shift 2
            ;;
        --auth)
            SIT_AUTH="$2"
            shift 2
            ;;
        --tables)
            TABLES="$2"
            shift 2
            ;;
        --include-data)
            INCLUDE_DATA=true
            shift
            ;;
        --data-limit)
            DATA_LIMIT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --host HOST       SIT Impala host (default: localhost)"
            echo "  --port PORT       SIT Impala port (default: 21050)"
            echo "  --auth AUTH       Authentication: NOSASL, GSSAPI, LDAP (default: NOSASL)"
            echo "  --tables TABLES   Comma-separated list of tables (default: all)"
            echo "  --include-data    Extract table data as well"
            echo "  --data-limit N    Limit rows per table when extracting data"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  SIT_IMPALA_HOST     SIT Impala host"
            echo "  SIT_IMPALA_PORT     SIT Impala port"
            echo "  SIT_IMPALA_AUTH     Authentication method"
            echo "  SIT_IMPALA_USER     Username (for LDAP)"
            echo "  SIT_IMPALA_PASSWORD Password (for LDAP)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "SIT to UAT Database Migration"
echo "============================================"
echo ""
echo -e "SIT Host: ${GREEN}$SIT_HOST${NC}"
echo -e "SIT Port: ${GREEN}$SIT_PORT${NC}"
echo -e "Auth: ${GREEN}$SIT_AUTH${NC}"
echo -e "Include Data: ${GREEN}$INCLUDE_DATA${NC}"
if [ -n "$TABLES" ]; then
    echo -e "Tables: ${GREEN}$TABLES${NC}"
else
    echo -e "Tables: ${GREEN}ALL${NC}"
fi
echo ""

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Build command
CMD="python $SCRIPT_DIR/extract_sit_ddl.py"
CMD="$CMD --host $SIT_HOST"
CMD="$CMD --port $SIT_PORT"
CMD="$CMD --auth $SIT_AUTH"

if [ -n "$TABLES" ]; then
    CMD="$CMD --tables $TABLES"
fi

if [ "$INCLUDE_DATA" = true ]; then
    CMD="$CMD --include-data"
fi

if [ -n "$DATA_LIMIT" ]; then
    CMD="$CMD --data-limit $DATA_LIMIT"
fi

# Run extraction
echo "Running extraction..."
echo "Command: $CMD"
echo ""

$CMD

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}Extraction Successful!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "Output files are in: $SCRIPT_DIR/output/"
    echo ""
    echo "To deploy to UAT:"
    echo "  1. Copy the output directory to UAT environment"
    echo "  2. Run: ./deploy_to_uat.sh --host <uat-host> --port 21050"
    echo ""
else
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}Extraction Failed!${NC}"
    echo -e "${RED}============================================${NC}"
    exit $EXIT_CODE
fi
