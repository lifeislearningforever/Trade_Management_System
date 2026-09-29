#!/bin/bash
# =============================================================================
# Position Worker Daemon Script for CML Deployment
# =============================================================================
# Description: Manages the position queue worker as a background daemon.
#              Includes health checks, auto-restart, and monitoring.
#
# Usage:
#   ./scripts/position_worker_daemon.sh start    # Start worker daemon
#   ./scripts/position_worker_daemon.sh stop     # Stop worker daemon
#   ./scripts/position_worker_daemon.sh restart  # Restart worker
#   ./scripts/position_worker_daemon.sh status   # Check if running
#   ./scripts/position_worker_daemon.sh health   # Health check with queue stats
#   ./scripts/position_worker_daemon.sh logs     # Tail worker logs
#
# CML Deployment:
#   Add to CML Application startup script or run as separate CML Job
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
VENV_DIR="$PROJECT_DIR/.venv"

# PID and Log files
PID_FILE="/tmp/cis_position_worker.pid"
LOG_FILE="/tmp/cis_position_worker.log"
HEALTH_FILE="/tmp/cis_position_worker.health"

# Worker settings
POLL_INTERVAL=10
BATCH_SIZE=100

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# =============================================================================
# Helper Functions
# =============================================================================

log_info() { echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"; }

get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

is_running() {
    local pid=$(get_pid)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

activate_venv() {
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        source "$VENV_DIR/bin/activate"
    elif [[ -n "${VIRTUAL_ENV:-}" ]]; then
        # Already in a venv
        :
    else
        log_warn "Virtual environment not found, using system Python"
    fi
}

# =============================================================================
# Commands
# =============================================================================

cmd_start() {
    log_info "Starting Position Queue Worker..."

    if is_running; then
        local pid=$(get_pid)
        log_warn "Worker is already running (PID: $pid)"
        return 0
    fi

    # Activate virtual environment
    activate_venv

    # Change to project directory
    cd "$PROJECT_DIR"

    # Start worker in background
    nohup python manage.py position_worker start \
        --poll-interval "$POLL_INTERVAL" \
        --batch-size "$BATCH_SIZE" \
        >> "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Wait a moment and verify it started
    sleep 2

    if is_running; then
        log_info "Worker started successfully (PID: $pid)"
        log_info "Log file: $LOG_FILE"

        # Write initial health status
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Worker started (PID: $pid)" > "$HEALTH_FILE"
        return 0
    else
        log_error "Worker failed to start. Check logs: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

cmd_stop() {
    log_info "Stopping Position Queue Worker..."

    if ! is_running; then
        log_warn "Worker is not running"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid=$(get_pid)

    # Send SIGTERM for graceful shutdown
    kill -TERM "$pid" 2>/dev/null

    # Wait for process to stop (max 30 seconds)
    local count=0
    while kill -0 "$pid" 2>/dev/null && [[ $count -lt 30 ]]; do
        sleep 1
        count=$((count + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        log_warn "Worker not responding, sending SIGKILL..."
        kill -KILL "$pid" 2>/dev/null
        sleep 1
    fi

    rm -f "$PID_FILE"
    log_info "Worker stopped"

    # Update health file
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Worker stopped" > "$HEALTH_FILE"
}

cmd_restart() {
    log_info "Restarting Position Queue Worker..."
    cmd_stop
    sleep 2
    cmd_start
}

cmd_status() {
    if is_running; then
        local pid=$(get_pid)
        log_info "Worker is RUNNING (PID: $pid)"

        # Show process info
        ps -p "$pid" -o pid,ppid,user,%cpu,%mem,etime,command 2>/dev/null | head -2

        return 0
    else
        log_warn "Worker is NOT RUNNING"

        # Check if PID file exists but process is dead
        if [[ -f "$PID_FILE" ]]; then
            log_warn "Stale PID file found, removing..."
            rm -f "$PID_FILE"
        fi

        return 1
    fi
}

cmd_health() {
    echo "============================================================"
    echo "  Position Queue Worker Health Check"
    echo "============================================================"
    echo ""

    # Check if worker is running
    if is_running; then
        local pid=$(get_pid)
        echo -e "Worker Status: ${GREEN}RUNNING${NC} (PID: $pid)"

        # Show uptime
        local uptime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
        echo "Uptime: $uptime"
    else
        echo -e "Worker Status: ${RED}NOT RUNNING${NC}"
    fi

    echo ""

    # Get queue statistics using Django
    activate_venv
    cd "$PROJECT_DIR"

    echo "Queue Statistics:"
    python manage.py position_worker status 2>/dev/null | grep -E "^(Total|Pending|Processing|Completed|Failed|Dead)" || echo "  Unable to fetch queue stats"

    echo ""

    # Show recent log entries
    echo "Recent Log Entries:"
    if [[ -f "$LOG_FILE" ]]; then
        tail -5 "$LOG_FILE" | sed 's/^/  /'
    else
        echo "  No log file found"
    fi

    echo ""

    # Update health file
    if is_running; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Health check: OK" >> "$HEALTH_FILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Health check: WORKER DOWN" >> "$HEALTH_FILE"
    fi
}

cmd_logs() {
    if [[ -f "$LOG_FILE" ]]; then
        log_info "Tailing log file: $LOG_FILE"
        tail -f "$LOG_FILE"
    else
        log_error "Log file not found: $LOG_FILE"
        return 1
    fi
}

cmd_ensure() {
    # Ensure worker is running - used by health check/cron
    if is_running; then
        return 0
    else
        log_warn "Worker is not running, starting..."
        cmd_start
    fi
}

# =============================================================================
# Main
# =============================================================================

show_usage() {
    echo "Usage: $0 {start|stop|restart|status|health|logs|ensure}"
    echo ""
    echo "Commands:"
    echo "  start    Start the position worker daemon"
    echo "  stop     Stop the position worker daemon"
    echo "  restart  Restart the worker"
    echo "  status   Check if worker is running"
    echo "  health   Full health check with queue stats"
    echo "  logs     Tail the worker log file"
    echo "  ensure   Start worker if not running (for cron)"
}

COMMAND=${1:-help}

case $COMMAND in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    health)  cmd_health ;;
    logs)    cmd_logs ;;
    ensure)  cmd_ensure ;;
    *)
        show_usage
        exit 1
        ;;
esac
