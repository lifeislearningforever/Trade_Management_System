#!/bin/bash
#
# Kudu Direct Database Benchmark Runner
# =====================================
#
# Tests actual Kudu/Impala INSERT, UPDATE, DELETE performance
# directly against the database - matching real user experience.
#
# Usage:
#   ./run_kudu_benchmark.sh quick     # 10 ops, single user
#   ./run_kudu_benchmark.sh standard  # 100 ops, single user
#   ./run_kudu_benchmark.sh load      # 100 ops, 10 concurrent users
#   ./run_kudu_benchmark.sh stress    # 500 ops, 50 concurrent users
#
# Prerequisites:
#   docker-compose up -d
#   # Wait ~60 seconds for Impala to start

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_SCRIPT="$SCRIPT_DIR/scripts/kudu_benchmark.py"

# Check if benchmark script exists
if [ ! -f "$BENCHMARK_SCRIPT" ]; then
    echo -e "${RED}ERROR: Benchmark script not found: $BENCHMARK_SCRIPT${NC}"
    exit 1
fi

# Parse arguments
SCENARIO="${1:-standard}"

case "$SCENARIO" in
    quick)
        OPS=10
        USERS=1
        DESC="Quick smoke test"
        ;;
    standard)
        OPS=100
        USERS=1
        DESC="Standard benchmark (single user)"
        ;;
    load)
        OPS=100
        USERS=10
        DESC="Load test (10 concurrent users)"
        ;;
    stress)
        OPS=500
        USERS=50
        DESC="Stress test (50 concurrent users)"
        ;;
    custom)
        OPS="${2:-100}"
        USERS="${3:-1}"
        DESC="Custom benchmark"
        ;;
    *)
        echo -e "${YELLOW}Usage: $0 {quick|standard|load|stress|custom [ops] [users]}${NC}"
        echo ""
        echo "Scenarios:"
        echo "  quick     - 10 ops, 1 user (sanity check)"
        echo "  standard  - 100 ops, 1 user (baseline)"
        echo "  load      - 100 ops, 10 users (realistic load)"
        echo "  stress    - 500 ops, 50 users (find limits)"
        echo "  custom    - custom ops and users count"
        echo ""
        echo "Example:"
        echo "  $0 custom 200 20  # 200 ops, 20 users"
        exit 1
        ;;
esac

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}KUDU DIRECT DATABASE BENCHMARK${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Scenario: ${GREEN}$SCENARIO${NC} - $DESC"
echo -e "Operations: ${GREEN}$OPS${NC} per type"
echo -e "Concurrent users: ${GREEN}$USERS${NC}"
echo ""

# Check Docker containers
echo -e "${YELLOW}Checking Docker containers...${NC}"
if ! docker ps | grep -q kudu-impala; then
    echo -e "${RED}ERROR: Kudu/Impala container not running${NC}"
    echo "Start with: docker-compose up -d"
    echo "Then wait ~60 seconds for Impala to initialize"
    exit 1
fi

# Test Impala connection
echo -e "${YELLOW}Testing Impala connection...${NC}"
if docker exec kudu-impala-new impala-shell -q "SELECT 1" >/dev/null 2>&1; then
    echo -e "${GREEN}Impala connection OK${NC}"
else
    echo -e "${RED}ERROR: Cannot connect to Impala${NC}"
    echo "Wait for container to fully start, then retry"
    exit 1
fi

echo ""
echo -e "${YELLOW}Starting benchmark...${NC}"
echo ""

# Create results directory
RESULTS_DIR="$SCRIPT_DIR/benchmark_results/kudu_${SCENARIO}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Activate virtual environment if exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Run benchmark
cd "$SCRIPT_DIR"
python scripts/kudu_benchmark.py \
    --operations "$OPS" \
    --users "$USERS" \
    --tables portfolio trade security fx_rate equity_price \
    2>&1 | tee "$RESULTS_DIR/output.txt"

echo ""
echo -e "${GREEN}Results saved to: $RESULTS_DIR/output.txt${NC}"
echo ""

# Summary
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}BENCHMARK COMPLETE${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "To compare with previous results:"
echo "  diff $RESULTS_DIR/output.txt benchmark_results/baseline/output.txt"
echo ""
