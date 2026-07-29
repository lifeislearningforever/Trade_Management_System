#!/bin/bash
#
# SIT to UAT Database Migration - DDL Extraction Script
#
# This script extracts DDL from SIT Impala/Kudu database and generates
# migration files for UAT deployment.
#
# Supports two connection modes:
# 1. impala-shell (recommended for Kerberos/CML environments)
# 2. PyHive (for local Docker development)
#
# Usage:
#   # Using impala-shell with Kerberos (CML/Production)
#   ./run_extraction.sh --use-impala-shell --host sit-impala-host --kerberos
#
#   # Using impala-shell with Kerberos and custom principal
#   ./run_extraction.sh --use-impala-shell --host sit-impala-host --kerberos --principal impala/host@REALM
#
#   # Using PyHive (local Docker)
#   ./run_extraction.sh --host localhost --port 21050
#
#   # Extract DDL and data
#   ./run_extraction.sh --use-impala-shell --host sit-impala-host --kerberos --include-data
#
#   # Extract specific tables
#   ./run_extraction.sh --use-impala-shell --host sit-impala-host --tables cis_trade,cis_portfolio
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Default values
SIT_HOST="${SIT_IMPALA_HOST:-localhost}"
SIT_PORT="${SIT_IMPALA_PORT:-21050}"
USE_IMPALA_SHELL=false
USE_KERBEROS=false
USE_SSL=false
PRINCIPAL=""
CA_CERT=""
INCLUDE_DATA=false
TABLES=""
DATA_LIMIT=""
SOURCE_DATABASE=""
TARGET_DATABASE=""
DROP_EXISTING=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Connection Modes:"
    echo "  --use-impala-shell  Use impala-shell command (recommended for Kerberos)"
    echo "                      Without this flag, PyHive library is used"
    echo ""
    echo "Connection Options:"
    echo "  --host HOST         SIT Impala host (default: localhost)"
    echo "  --port PORT         SIT Impala port (default: 21050)"
    echo ""
    echo "Authentication (for impala-shell):"
    echo "  --kerberos, -k      Use Kerberos authentication"
    echo "  --principal PRINC   Kerberos principal (e.g., impala/host@REALM)"
    echo "  --ssl               Use SSL connection"
    echo "  --ca-cert FILE      CA certificate for SSL"
    echo ""
    echo "Extraction Options:"
    echo "  --tables TABLES     Comma-separated list of tables (default: all)"
    echo "  --include-data      Extract table data as well"
    echo "  --data-limit N      Limit rows per table when extracting data"
    echo ""
    echo "Database Naming:"
    echo "  --source-database DB   Database to read DDL/data from (default: gmp_cis)"
    echo "  --target-database DB   Database name to generate DDL/data for"
    echo "                         (default: same as --source-database)"
    echo "  --drop-existing        Emit DROP TABLE IF EXISTS before each CREATE TABLE"
    echo "                         (destructive; default is safe CREATE TABLE IF NOT EXISTS)"
    echo ""
    echo "Other:"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  SIT_IMPALA_HOST     SIT Impala host"
    echo "  SIT_IMPALA_PORT     SIT Impala port"
    echo "  KRB5_CONFIG         Kerberos config file path"
    echo "  KRB5CCNAME          Kerberos credential cache path"
    echo ""
    echo "Examples:"
    echo "  # CML with Kerberos (most common)"
    echo "  $0 --use-impala-shell --host impala-host.company.com --kerberos"
    echo ""
    echo "  # CML with Kerberos and custom principal"
    echo "  $0 --use-impala-shell --host impala-host.company.com --kerberos --principal impala/_HOST@REALM"
    echo ""
    echo "  # Local Docker (no Kerberos)"
    echo "  $0 --host localhost --port 21050"
    echo ""
    echo "  # Extract with data"
    echo "  $0 --use-impala-shell --host impala-host --kerberos --include-data"
    echo ""
    echo "  # Copy into a differently-named SIT database"
    echo "  $0 --use-impala-shell --host impala-host --kerberos --include-data \\"
    echo "      --source-database gmp_cis --target-database gmp_cis_dev"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --use-impala-shell)
            USE_IMPALA_SHELL=true
            shift
            ;;
        --host)
            SIT_HOST="$2"
            shift 2
            ;;
        --port)
            SIT_PORT="$2"
            shift 2
            ;;
        --kerberos|-k)
            USE_KERBEROS=true
            shift
            ;;
        --principal)
            PRINCIPAL="$2"
            shift 2
            ;;
        --ssl)
            USE_SSL=true
            shift
            ;;
        --ca-cert)
            CA_CERT="$2"
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
        --source-database)
            SOURCE_DATABASE="$2"
            shift 2
            ;;
        --target-database)
            TARGET_DATABASE="$2"
            shift 2
            ;;
        --drop-existing)
            DROP_EXISTING=true
            shift
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "SIT to UAT Database Migration"
echo "============================================"
echo ""
echo -e "Connection Mode: ${GREEN}$([ "$USE_IMPALA_SHELL" = true ] && echo "impala-shell" || echo "PyHive")${NC}"
echo -e "SIT Host: ${GREEN}$SIT_HOST${NC}"
echo -e "SIT Port: ${GREEN}$SIT_PORT${NC}"

if [ "$USE_IMPALA_SHELL" = true ]; then
    echo -e "Kerberos: ${GREEN}$USE_KERBEROS${NC}"
    if [ -n "$PRINCIPAL" ]; then
        echo -e "Principal: ${GREEN}$PRINCIPAL${NC}"
    fi
    echo -e "SSL: ${GREEN}$USE_SSL${NC}"
fi

echo -e "Include Data: ${GREEN}$INCLUDE_DATA${NC}"
if [ -n "$TABLES" ]; then
    echo -e "Tables: ${GREEN}$TABLES${NC}"
else
    echo -e "Tables: ${GREEN}ALL${NC}"
fi
if [ -n "$SOURCE_DATABASE" ]; then
    echo -e "Source Database: ${GREEN}$SOURCE_DATABASE${NC}"
fi
if [ -n "$TARGET_DATABASE" ]; then
    echo -e "Target Database: ${GREEN}$TARGET_DATABASE${NC}"
fi
echo -e "Drop Existing: ${GREEN}$DROP_EXISTING${NC}"
echo ""

# Check Kerberos ticket if using Kerberos
if [ "$USE_KERBEROS" = true ]; then
    echo -e "${BLUE}Checking Kerberos ticket...${NC}"
    if ! klist -s 2>/dev/null; then
        echo -e "${RED}ERROR: No valid Kerberos ticket found.${NC}"
        echo ""
        echo "Please obtain a Kerberos ticket first:"
        echo "  kinit <username>@<REALM>"
        echo ""
        echo "Or if using a keytab:"
        echo "  kinit -kt /path/to/keytab <principal>"
        echo ""
        exit 1
    fi
    echo -e "${GREEN}Kerberos ticket found:${NC}"
    klist
    echo ""
fi

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Build command
CMD="python $SCRIPT_DIR/extract_sit_ddl.py"
CMD="$CMD --host $SIT_HOST"
CMD="$CMD --port $SIT_PORT"

if [ "$USE_IMPALA_SHELL" = true ]; then
    CMD="$CMD --use-impala-shell"
fi

if [ "$USE_KERBEROS" = true ]; then
    CMD="$CMD --kerberos"
fi

if [ -n "$PRINCIPAL" ]; then
    CMD="$CMD --principal $PRINCIPAL"
fi

if [ "$USE_SSL" = true ]; then
    CMD="$CMD --ssl"
fi

if [ -n "$CA_CERT" ]; then
    CMD="$CMD --ca-cert $CA_CERT"
fi

if [ -n "$TABLES" ]; then
    CMD="$CMD --tables $TABLES"
fi

if [ "$INCLUDE_DATA" = true ]; then
    CMD="$CMD --include-data"
fi

if [ -n "$DATA_LIMIT" ]; then
    CMD="$CMD --data-limit $DATA_LIMIT"
fi

if [ -n "$SOURCE_DATABASE" ]; then
    CMD="$CMD --source-database $SOURCE_DATABASE"
fi

if [ -n "$TARGET_DATABASE" ]; then
    CMD="$CMD --target-database $TARGET_DATABASE"
fi

if [ "$DROP_EXISTING" = true ]; then
    CMD="$CMD --drop-existing"
fi

# Run extraction
echo "Running extraction..."
echo -e "${BLUE}Command: $CMD${NC}"
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
    if [ "$USE_KERBEROS" = true ]; then
        echo "  2. Run: ./deploy_to_uat.sh --host <uat-host> --kerberos"
    else
        echo "  2. Run: ./deploy_to_uat.sh --host <uat-host> --port 21050"
    fi
    echo ""
else
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}Extraction Failed!${NC}"
    echo -e "${RED}============================================${NC}"
    exit $EXIT_CODE
fi
