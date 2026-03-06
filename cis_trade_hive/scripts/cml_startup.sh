#!/bin/bash
# =============================================================================
# CML Application Startup Script
# =============================================================================
# Description: Startup script for CIS Trade Hive on Cloudera Machine Learning.
#              Starts Django server AND Position Queue Worker together.
#
# Usage in CML:
#   1. Upload this script to your CML project
#   2. In CML Application settings, set:
#      - Script: scripts/cml_startup.sh
#      - Or add to "Pre-start" commands
#
# Or run manually:
#   ./scripts/cml_startup.sh
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

# Log files
DJANGO_LOG="/tmp/cis_django.log"
WORKER_LOG="/tmp/cis_position_worker.log"
PID_DIR="/tmp"

# Server settings
DJANGO_HOST="${DJANGO_HOST:-0.0.0.0}"
DJANGO_PORT="${CDSW_APP_PORT:-8000}"  # CML sets CDSW_APP_PORT

# Worker settings
WORKER_POLL_INTERVAL="${WORKER_POLL_INTERVAL:-10}"
WORKER_BATCH_SIZE="${WORKER_BATCH_SIZE:-100}"

# =============================================================================
# Logging
# =============================================================================

log_info() { echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_warn() { echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $1"; }

# =============================================================================
# Startup Functions
# =============================================================================

start_django() {
    log_info "Starting Django server on ${DJANGO_HOST}:${DJANGO_PORT}..."

    cd "$PROJECT_DIR"

    # Use gunicorn for production
    if command -v gunicorn &> /dev/null; then
        nohup gunicorn config.wsgi:application \
            --bind "${DJANGO_HOST}:${DJANGO_PORT}" \
            --workers 4 \
            --threads 2 \
            --timeout 120 \
            --access-logfile "$DJANGO_LOG" \
            --error-logfile "$DJANGO_LOG" \
            >> "$DJANGO_LOG" 2>&1 &
        echo $! > "$PID_DIR/cis_django.pid"
        log_info "Django (gunicorn) started (PID: $!)"
    else
        # Fallback to runserver
        nohup python manage.py runserver "${DJANGO_HOST}:${DJANGO_PORT}" \
            >> "$DJANGO_LOG" 2>&1 &
        echo $! > "$PID_DIR/cis_django.pid"
        log_info "Django (runserver) started (PID: $!)"
    fi
}

start_worker() {
    log_info "Starting Position Queue Worker..."

    cd "$PROJECT_DIR"

    nohup python manage.py position_worker start \
        --poll-interval "$WORKER_POLL_INTERVAL" \
        --batch-size "$WORKER_BATCH_SIZE" \
        >> "$WORKER_LOG" 2>&1 &

    echo $! > "$PID_DIR/cis_position_worker.pid"
    log_info "Position Worker started (PID: $!)"
}

wait_for_django() {
    log_info "Waiting for Django to be ready..."

    local retries=30
    local count=0

    while [[ $count -lt $retries ]]; do
        if curl -s "http://localhost:${DJANGO_PORT}/health/" > /dev/null 2>&1 || \
           curl -s "http://localhost:${DJANGO_PORT}/" > /dev/null 2>&1; then
            log_info "Django is ready!"
            return 0
        fi

        sleep 1
        count=$((count + 1))
    done

    log_warn "Django may not be fully ready, continuing anyway..."
    return 0
}

health_monitor() {
    # Background health monitoring loop
    log_info "Starting health monitor..."

    while true; do
        sleep 60

        # Check Django
        if ! kill -0 $(cat "$PID_DIR/cis_django.pid" 2>/dev/null) 2>/dev/null; then
            log_error "Django process died! Restarting..."
            start_django
        fi

        # Check Worker
        if ! kill -0 $(cat "$PID_DIR/cis_position_worker.pid" 2>/dev/null) 2>/dev/null; then
            log_error "Position Worker died! Restarting..."
            start_worker
        fi

        # Log health status
        local worker_health=$(curl -s "http://localhost:${DJANGO_PORT}/trade/api/worker-health/" 2>/dev/null | head -c 100)
        log_info "Health: $worker_health"

    done
}

# =============================================================================
# Main
# =============================================================================

main() {
    log_info "============================================"
    log_info "CIS Trade Hive - CML Startup"
    log_info "============================================"
    log_info "Project: $PROJECT_DIR"
    log_info "Django: ${DJANGO_HOST}:${DJANGO_PORT}"
    log_info "Worker Poll: ${WORKER_POLL_INTERVAL}s"
    log_info "============================================"

    # Change to project directory
    cd "$PROJECT_DIR"

    # Activate virtual environment if exists
    if [[ -f ".venv/bin/activate" ]]; then
        source .venv/bin/activate
        log_info "Virtual environment activated"
    fi

    # Run migrations (optional, uncomment if needed)
    # log_info "Running migrations..."
    # python manage.py migrate --noinput

    # Collect static files (optional, uncomment if needed)
    # log_info "Collecting static files..."
    # python manage.py collectstatic --noinput

    # Start services
    start_django
    sleep 2
    start_worker
    sleep 2

    # Wait for Django to be ready
    wait_for_django

    # Show initial status
    log_info "Services started. Logs:"
    log_info "  Django: $DJANGO_LOG"
    log_info "  Worker: $WORKER_LOG"

    # Start health monitor (runs forever)
    health_monitor
}

# Run main
main
