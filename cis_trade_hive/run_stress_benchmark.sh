#!/bin/bash
#
# Kudu Stress Benchmark Runner
# ============================
#
# Easy-to-use wrapper for kudu_stress_benchmark.py
# Similar to JMeter test plan execution
#
# Usage:
#   ./run_stress_benchmark.sh quick      # Smoke test (10 users, 1 min)
#   ./run_stress_benchmark.sh standard   # Regular load (50 users, 5 min)
#   ./run_stress_benchmark.sh stress     # Stress test (100 users, 10 min)
#   ./run_stress_benchmark.sh spike      # Spike test (200 users, 2 min)
#   ./run_stress_benchmark.sh soak       # Endurance (30 users, 30 min)
#   ./run_stress_benchmark.sh custom 100 300 30  # Custom: 100 users, 300s, 30s ramp-up
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_SCRIPT="${SCRIPT_DIR}/scripts/kudu_stress_benchmark.py"
RESULTS_DIR="${SCRIPT_DIR}/stress_results"

# Banner
print_banner() {
    echo ""
    echo -e "${BLUE}=====================================================================${NC}"
    echo -e "${BLUE}  KUDU STRESS BENCHMARK - JMeter Style Load Testing${NC}"
    echo -e "${BLUE}=====================================================================${NC}"
    echo ""
}

# Usage
print_usage() {
    echo "Usage: $0 <scenario> [options]"
    echo ""
    echo "Predefined Scenarios:"
    echo "  quick     - Smoke test: 10 users, 1 minute, 10s ramp-up"
    echo "  standard  - Regular load: 50 users, 5 minutes, 30s ramp-up"
    echo "  stress    - Stress test: 100 users, 10 minutes, 60s ramp-up"
    echo "  spike     - Spike test: 200 users, 2 minutes, 10s ramp-up"
    echo "  soak      - Endurance: 30 users, 30 minutes, 60s ramp-up"
    echo ""
    echo "Custom Scenario:"
    echo "  custom <users> <duration_sec> <ramp_up_sec>"
    echo "  Example: $0 custom 100 300 30"
    echo ""
    echo "Options:"
    echo "  --tables <t1> <t2> ...  Tables to test (trade, portfolio, security, fx_rate)"
    echo "  --output <dir>          Output directory (default: stress_results)"
    echo "  --help                  Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 quick                      # Quick smoke test"
    echo "  $0 standard                   # Standard load test"
    echo "  $0 stress --tables trade      # Stress test on trade table only"
    echo "  $0 custom 200 600 60          # 200 users, 10 min, 60s ramp-up"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check Python
    if ! command -v python &> /dev/null; then
        echo -e "${RED}ERROR: Python not found${NC}"
        exit 1
    fi
    echo "  ✓ Python: $(python --version 2>&1)"

    # Check benchmark script
    if [ ! -f "$BENCHMARK_SCRIPT" ]; then
        echo -e "${RED}ERROR: Benchmark script not found: $BENCHMARK_SCRIPT${NC}"
        exit 1
    fi
    echo "  ✓ Benchmark script found"

    # Check Django setup
    if ! python -c "import django" 2>/dev/null; then
        echo -e "${YELLOW}  ⚠ Django not in path, will activate venv...${NC}"
        if [ -f "${SCRIPT_DIR}/.venv/bin/activate" ]; then
            source "${SCRIPT_DIR}/.venv/bin/activate"
            echo "  ✓ Virtual environment activated"
        fi
    fi

    # Create results directory
    mkdir -p "$RESULTS_DIR"
    echo "  ✓ Results directory: $RESULTS_DIR"

    echo ""
}

# Run benchmark
run_benchmark() {
    local scenario=$1
    shift
    local extra_args="$@"

    echo -e "${GREEN}Starting benchmark: ${scenario}${NC}"
    echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Activate virtual environment if exists
    if [ -f "${SCRIPT_DIR}/.venv/bin/activate" ]; then
        source "${SCRIPT_DIR}/.venv/bin/activate"
    fi

    # Run the benchmark
    cd "$SCRIPT_DIR"
    python "$BENCHMARK_SCRIPT" --scenario "$scenario" --output-dir "$RESULTS_DIR" $extra_args

    local exit_code=$?

    echo ""
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}=====================================================================${NC}"
        echo -e "${GREEN}  BENCHMARK COMPLETED SUCCESSFULLY${NC}"
        echo -e "${GREEN}=====================================================================${NC}"
    else
        echo -e "${RED}=====================================================================${NC}"
        echo -e "${RED}  BENCHMARK FAILED (exit code: $exit_code)${NC}"
        echo -e "${RED}=====================================================================${NC}"
    fi

    # Show results location
    echo ""
    echo "Results saved to: $RESULTS_DIR"
    echo "Latest reports:"
    ls -lt "$RESULTS_DIR"/*.json 2>/dev/null | head -3 || echo "  No reports found"
    echo ""

    return $exit_code
}

# Run custom benchmark
run_custom() {
    local users=$1
    local duration=$2
    local ramp_up=$3
    shift 3
    local extra_args="$@"

    if [ -z "$users" ] || [ -z "$duration" ] || [ -z "$ramp_up" ]; then
        echo -e "${RED}ERROR: Custom scenario requires: users, duration, ramp_up${NC}"
        echo "Example: $0 custom 100 300 30"
        exit 1
    fi

    echo -e "${GREEN}Starting custom benchmark${NC}"
    echo "  Users: $users"
    echo "  Duration: ${duration}s"
    echo "  Ramp-up: ${ramp_up}s"
    echo ""

    # Activate virtual environment if exists
    if [ -f "${SCRIPT_DIR}/.venv/bin/activate" ]; then
        source "${SCRIPT_DIR}/.venv/bin/activate"
    fi

    cd "$SCRIPT_DIR"
    python "$BENCHMARK_SCRIPT" \
        --users "$users" \
        --duration "$duration" \
        --ramp-up "$ramp_up" \
        --output-dir "$RESULTS_DIR" \
        $extra_args

    return $?
}

# Compare results
compare_results() {
    echo -e "${BLUE}Recent Benchmark Results:${NC}"
    echo ""

    if [ ! -d "$RESULTS_DIR" ]; then
        echo "No results directory found"
        return
    fi

    # Find recent JSON files
    local json_files=$(ls -t "$RESULTS_DIR"/*.json 2>/dev/null | head -5)

    if [ -z "$json_files" ]; then
        echo "No benchmark results found"
        return
    fi

    echo "| Test Name | Scenario | Users | Ops | Success% | Throughput | P95(ms) |"
    echo "|-----------|----------|-------|-----|----------|------------|---------|"

    for file in $json_files; do
        if [ -f "$file" ]; then
            python3 -c "
import json
with open('$file') as f:
    d = json.load(f)
    print(f\"| {d.get('test_name', 'N/A')[:20]} | {d.get('scenario', 'N/A')} | {d.get('total_users', 0)} | {d.get('total_operations', 0)} | {d.get('success_rate_pct', 0):.1f}% | {d.get('throughput_ops_per_sec', 0):.1f}/s | {d.get('latency_p95_ms', 0):.1f} |\")" 2>/dev/null || echo "| Error reading $file |"
        fi
    done

    echo ""
}

# Main
main() {
    print_banner

    # Parse arguments
    case "$1" in
        quick|standard|stress|spike|soak)
            check_prerequisites
            run_benchmark "$@"
            ;;
        custom)
            shift
            check_prerequisites
            run_custom "$@"
            ;;
        compare|results)
            compare_results
            ;;
        --help|-h|help)
            print_usage
            ;;
        "")
            echo -e "${YELLOW}No scenario specified. Running quick test...${NC}"
            echo ""
            check_prerequisites
            run_benchmark "quick"
            ;;
        *)
            echo -e "${RED}Unknown scenario: $1${NC}"
            echo ""
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
