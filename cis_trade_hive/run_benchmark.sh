#!/bin/bash
#
# CisTrade Benchmark Execution Script
# ====================================
#
# Runs various load testing scenarios against the CisTrade application
#
# Usage:
#   ./run_benchmark.sh [scenario] [users] [duration]
#
# Examples:
#   ./run_benchmark.sh quick 50 2m
#   ./run_benchmark.sh standard 500 10m
#   ./run_benchmark.sh stress 1000 5m
#   ./run_benchmark.sh soak 200 2h
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SCENARIO="${1:-standard}"
USERS="${2:-500}"
DURATION="${3:-10m}"
HOST="${LOCUST_HOST:-http://localhost:8000}"
SPAWN_RATE=10

# Create results directory
RESULTS_DIR="benchmark_results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="${RESULTS_DIR}/${SCENARIO}_${USERS}users_${TIMESTAMP}"

mkdir -p "${REPORT_DIR}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CisTrade Load Testing${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Scenario: ${GREEN}${SCENARIO}${NC}"
echo -e "Users: ${GREEN}${USERS}${NC}"
echo -e "Duration: ${GREEN}${DURATION}${NC}"
echo -e "Host: ${GREEN}${HOST}${NC}"
echo -e "Results: ${GREEN}${REPORT_DIR}${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Activate virtual environment
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source venv/bin/activate
fi

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}Locust not found. Installing...${NC}"
    pip install -r requirements-dev.txt
fi

# Pre-flight checks
echo -e "${YELLOW}Running pre-flight checks...${NC}"

# Check if Django server is running
if ! curl -s "${HOST}" > /dev/null 2>&1; then
    echo -e "${RED}⚠️  WARNING: Django server not responding at ${HOST}${NC}"
    echo -e "${YELLOW}Please start the server with: python manage.py runserver${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Server is running${NC}"

# Check database connectivity
echo -e "${YELLOW}Checking database connectivity...${NC}"
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Database OK')" || {
    echo -e "${RED}⚠️  Database connection failed${NC}"
    exit 1
}

echo -e "${GREEN}✓ Database is connected${NC}\n"

# Run appropriate scenario
case "${SCENARIO}" in
    quick)
        echo -e "${YELLOW}Running QUICK benchmark (small user count, short duration)${NC}"
        USERS=50
        DURATION=2m
        SPAWN_RATE=5
        ;;
    standard)
        echo -e "${YELLOW}Running STANDARD benchmark (500 users, 10 minutes)${NC}"
        USERS=500
        DURATION=10m
        SPAWN_RATE=10
        ;;
    stress)
        echo -e "${YELLOW}Running STRESS test (high user count, rapid spawn)${NC}"
        USERS=1000
        DURATION=5m
        SPAWN_RATE=50
        ;;
    soak)
        echo -e "${YELLOW}Running SOAK test (sustained load over time)${NC}"
        USERS=200
        DURATION=2h
        SPAWN_RATE=5
        ;;
    portfolio)
        echo -e "${YELLOW}Running PORTFOLIO-focused test${NC}"
        USER_CLASS="PortfolioUser"
        ;;
    refdata)
        echo -e "${YELLOW}Running REFERENCE DATA-focused test${NC}"
        USER_CLASS="ReferenceDataUser"
        ;;
    *)
        echo -e "${RED}Unknown scenario: ${SCENARIO}${NC}"
        echo "Available scenarios: quick, standard, stress, soak, portfolio, refdata"
        exit 1
        ;;
esac

# Start system monitoring (optional)
if command -v vmstat &> /dev/null; then
    echo -e "${YELLOW}Starting system monitoring...${NC}"
    vmstat 5 > "${REPORT_DIR}/system_stats.log" &
    VMSTAT_PID=$!
fi

# Run Locust
echo -e "\n${GREEN}Starting Locust load test...${NC}\n"

if [ -n "${USER_CLASS}" ]; then
    # Run specific user class
    locust \
        --host="${HOST}" \
        --users="${USERS}" \
        --spawn-rate="${SPAWN_RATE}" \
        --run-time="${DURATION}" \
        --headless \
        --html="${REPORT_DIR}/report.html" \
        --csv="${REPORT_DIR}/stats" \
        --logfile="${REPORT_DIR}/locust.log" \
        --loglevel=INFO \
        ${USER_CLASS}
else
    # Run all user classes with weights
    locust \
        --host="${HOST}" \
        --users="${USERS}" \
        --spawn-rate="${SPAWN_RATE}" \
        --run-time="${DURATION}" \
        --headless \
        --html="${REPORT_DIR}/report.html" \
        --csv="${REPORT_DIR}/stats" \
        --logfile="${REPORT_DIR}/locust.log" \
        --loglevel=INFO
fi

LOCUST_EXIT_CODE=$?

# Stop system monitoring
if [ -n "${VMSTAT_PID}" ]; then
    kill ${VMSTAT_PID} 2>/dev/null || true
fi

# Generate summary report
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Benchmark Complete${NC}"
echo -e "${BLUE}========================================${NC}"

if [ ${LOCUST_EXIT_CODE} -eq 0 ]; then
    echo -e "${GREEN}✓ Benchmark completed successfully${NC}\n"

    # Extract key metrics from CSV
    if [ -f "${REPORT_DIR}/stats_stats.csv" ]; then
        echo -e "${YELLOW}Key Metrics:${NC}"
        echo "----------------------------------------"

        # Parse stats CSV for summary
        tail -n +2 "${REPORT_DIR}/stats_stats.csv" | while IFS=, read -r type name request_count failure_count median_response average_response min_response max_response avg_content requests_per_sec failures_per_sec percentile_50 percentile_60 percentile_70 percentile_80 percentile_90 percentile_95 percentile_99 percentile_100; do
            if [ "$type" == "Aggregated" ]; then
                echo -e "Total Requests: ${GREEN}${request_count}${NC}"
                echo -e "Failed Requests: ${RED}${failure_count}${NC}"
                echo -e "Median Response Time: ${GREEN}${median_response} ms${NC}"
                echo -e "Average Response Time: ${GREEN}${average_response} ms${NC}"
                echo -e "95th Percentile: ${YELLOW}${percentile_95} ms${NC}"
                echo -e "Requests/sec: ${GREEN}${requests_per_sec}${NC}"
            fi
        done
    fi

    echo "----------------------------------------"
    echo -e "📊 HTML Report: ${GREEN}${REPORT_DIR}/report.html${NC}"
    echo -e "📈 CSV Stats: ${GREEN}${REPORT_DIR}/stats_stats.csv${NC}"
    echo -e "📝 Log File: ${GREEN}${REPORT_DIR}/locust.log${NC}"

    # Offer to open HTML report
    if [[ "$OSTYPE" == "darwin"* ]]; then
        read -p "Open HTML report in browser? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            open "${REPORT_DIR}/report.html"
        fi
    fi
else
    echo -e "${RED}✗ Benchmark failed with exit code ${LOCUST_EXIT_CODE}${NC}"
    echo -e "Check logs: ${REPORT_DIR}/locust.log"
fi

echo -e "\n${BLUE}========================================${NC}\n"

exit ${LOCUST_EXIT_CODE}
