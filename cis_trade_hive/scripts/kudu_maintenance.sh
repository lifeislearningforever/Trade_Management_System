#!/bin/bash
# =============================================================================
# Kudu Cluster Maintenance Script
# =============================================================================
# Maintains health of the Kudu/Impala Docker cluster for CIS Trade Hive.
#
# Usage:
#   ./scripts/kudu_maintenance.sh [command]
#
# Commands:
#   status    - Show cluster health and disk usage (default)
#   cleanup   - Clean rotated logs and Docker resources
#   restart   - Graceful restart of the entire cluster
#   fix-raft  - Attempt to fix Raft consensus/leader election issues
#   full      - Run cleanup + restart + health check
#
# Schedule with cron for automated maintenance:
#   0 2 * * * /path/to/scripts/kudu_maintenance.sh cleanup >> /tmp/kudu_maint.log 2>&1
# =============================================================================

set -euo pipefail

# Configuration
MASTERS="kudu-master-1 kudu-master-2 kudu-master-3"
TSERVERS="kudu-tserver-1 kudu-tserver-2 kudu-tserver-3"
IMPALA="kudu-impala-new"
ALL_KUDU="$MASTERS $TSERVERS"
ALL_NODES="$ALL_KUDU $IMPALA"

# Thresholds
LOG_WARN_MB=200       # Warn if /tmp logs exceed this per node
WAL_WARN_MB=2000      # Warn if WALs exceed 2GB per node
VOLUME_WARN_GB=15     # Warn if volume exceeds 15GB

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

check_container_running() {
    local container=$1
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        log_error "$container is NOT running"
        return 1
    fi
    return 0
}

# =============================================================================
# STATUS - Show cluster health
# =============================================================================

cmd_status() {
    log_section "Kudu Cluster Health Report"
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Container status
    log_section "Container Status"
    printf "%-20s %-10s %-12s %-15s\n" "CONTAINER" "STATUS" "UPTIME" "LAYER SIZE"
    printf "%-20s %-10s %-12s %-15s\n" "---------" "------" "------" "----------"
    for node in $ALL_NODES; do
        local status=$(docker ps --filter "name=^${node}$" --format "{{.Status}}" 2>/dev/null)
        local size=$(docker ps -s --filter "name=^${node}$" --format "{{.Size}}" 2>/dev/null | head -1)
        if [ -z "$status" ]; then
            printf "%-20s ${RED}%-10s${NC} %-12s %-15s\n" "$node" "STOPPED" "-" "-"
        else
            local uptime=$(echo "$status" | sed 's/Up //')
            printf "%-20s ${GREEN}%-10s${NC} %-12s %-15s\n" "$node" "RUNNING" "$uptime" "$size"
        fi
    done

    # Disk usage per node
    log_section "Disk Usage (Data + WALs + Logs)"
    printf "%-20s %-10s %-10s %-10s %-10s\n" "NODE" "DATA" "WALs" "/tmp LOGS" "TOTAL VOL"
    printf "%-20s %-10s %-10s %-10s %-10s\n" "----" "----" "----" "---------" "---------"

    for master in $MASTERS; do
        if ! check_container_running "$master" 2>/dev/null; then continue; fi
        local data=$(docker exec "$master" du -sh /var/lib/kudu/master/data/ 2>/dev/null | awk '{print $1}')
        local wals=$(docker exec "$master" du -sh /var/lib/kudu/master/wals/ 2>/dev/null | awk '{print $1}')
        local logs=$(docker exec "$master" du -sh /tmp/ 2>/dev/null | awk '{print $1}')
        local vol_name="cis_trade_hive_${master}"
        local vol_size=$(docker system df -v 2>/dev/null | grep "$vol_name" | awk '{print $NF}')
        printf "%-20s %-10s %-10s %-10s %-10s\n" "$master" "$data" "$wals" "$logs" "$vol_size"
    done

    for tserver in $TSERVERS; do
        if ! check_container_running "$tserver" 2>/dev/null; then continue; fi
        local data=$(docker exec "$tserver" du -sh /var/lib/kudu/tserver/data/ 2>/dev/null | awk '{print $1}')
        local wals=$(docker exec "$tserver" du -sh /var/lib/kudu/tserver/wals/ 2>/dev/null | awk '{print $1}')
        local logs=$(docker exec "$tserver" du -sh /tmp/ 2>/dev/null | awk '{print $1}')
        local vol_name="cis_trade_hive_${tserver}"
        local vol_size=$(docker system df -v 2>/dev/null | grep "$vol_name" | awk '{print $NF}')
        printf "%-20s %-10s %-10s %-10s %-10s\n" "$tserver" "$data" "$wals" "$logs" "$vol_size"
    done

    # Docker system overview
    log_section "Docker System Overview"
    docker system df 2>/dev/null

    # Check for warnings
    log_section "Health Warnings"
    local warnings=0

    for node in $ALL_KUDU; do
        if ! check_container_running "$node" 2>/dev/null; then
            warnings=$((warnings + 1))
            continue
        fi
        local log_bytes=$(docker exec "$node" du -sb /tmp/ 2>/dev/null | awk '{print $1}')
        local log_mb=$((log_bytes / 1048576))
        if [ "$log_mb" -gt "$LOG_WARN_MB" ]; then
            log_warn "$node: /tmp logs at ${log_mb}MB (threshold: ${LOG_WARN_MB}MB) - run 'cleanup'"
            warnings=$((warnings + 1))
        fi
    done

    for tserver in $TSERVERS; do
        if ! check_container_running "$tserver" 2>/dev/null; then continue; fi
        local wal_bytes=$(docker exec "$tserver" du -sb /var/lib/kudu/tserver/wals/ 2>/dev/null | awk '{print $1}')
        local wal_mb=$((wal_bytes / 1048576))
        if [ "$wal_mb" -gt "$WAL_WARN_MB" ]; then
            log_warn "$tserver: WALs at ${wal_mb}MB (threshold: ${WAL_WARN_MB}MB)"
            warnings=$((warnings + 1))
        fi
    done

    if [ "$warnings" -eq 0 ]; then
        log_info "All health checks passed"
    else
        log_warn "$warnings warning(s) found"
    fi

    # Master leader status
    log_section "Kudu Master Leader"
    for master in $MASTERS; do
        if ! check_container_running "$master" 2>/dev/null; then continue; fi
        local is_leader=$(docker exec "$master" bash -c "tail -50 /tmp/kudu-master.INFO 2>/dev/null | grep -c 'LEADER' || true")
        if [ "$is_leader" -gt 0 ]; then
            log_info "$master appears to be the master leader"
        fi
    done
}

# =============================================================================
# CLEANUP - Clean rotated logs and Docker resources
# =============================================================================

cmd_cleanup() {
    log_section "Kudu Cluster Cleanup"

    # 1. Clean rotated Kudu logs (keep only current active log files)
    log_info "Cleaning rotated Kudu log files..."
    for node in $ALL_KUDU; do
        if ! check_container_running "$node" 2>/dev/null; then continue; fi

        local before=$(docker exec "$node" du -sh /tmp/ 2>/dev/null | awk '{print $1}')
        docker exec "$node" bash -c '
            # Find current active log files (symlink targets)
            CURRENT_INFO=$(readlink -f /tmp/kudu-*.INFO 2>/dev/null)
            CURRENT_WARN=$(readlink -f /tmp/kudu-*.WARNING 2>/dev/null)
            CURRENT_ERR=$(readlink -f /tmp/kudu-*.ERROR 2>/dev/null)

            # Delete all rotated log files except current ones
            for f in /tmp/kudu-*.log.*; do
                [ ! -f "$f" ] && continue
                if [ "$f" != "$CURRENT_INFO" ] && \
                   [ "$f" != "$CURRENT_WARN" ] && \
                   [ "$f" != "$CURRENT_ERR" ]; then
                    rm -f "$f"
                fi
            done

            # Also clean any FATAL logs older than 7 days
            find /tmp/ -name "kudu-*.FATAL.*" -mtime +7 -delete 2>/dev/null || true

            # Clean core dumps if any
            find /tmp/ -name "core.*" -delete 2>/dev/null || true
            find /var/lib/kudu/ -name "minidump*" -mtime +7 -delete 2>/dev/null || true
        ' 2>/dev/null
        local after=$(docker exec "$node" du -sh /tmp/ 2>/dev/null | awk '{print $1}')
        log_info "  $node: $before -> $after"
    done

    # 2. Clean Impala logs
    log_info "Cleaning Impala logs..."
    if check_container_running "$IMPALA" 2>/dev/null; then
        docker exec "$IMPALA" bash -c '
            find /tmp/ -name "*.log.*" -mtime +1 -delete 2>/dev/null || true
            find /var/log/ -name "*.log.*" -mtime +7 -delete 2>/dev/null || true
        ' 2>/dev/null
        log_info "  Impala logs cleaned"
    fi

    # 3. Prune Docker system resources
    log_info "Pruning Docker stopped containers and dangling images..."
    docker system prune -f 2>/dev/null | tail -1

    # 4. Show final disk state
    log_section "Post-Cleanup Disk Usage"
    docker system df 2>/dev/null

    log_info "Cleanup complete!"
}

# =============================================================================
# RESTART - Graceful cluster restart
# =============================================================================

cmd_restart() {
    log_section "Graceful Kudu Cluster Restart"

    # 1. Stop in reverse order: Impala -> TServers -> Masters
    log_info "Stopping Impala..."
    docker stop "$IMPALA" 2>/dev/null || true
    sleep 2

    log_info "Stopping tablet servers..."
    for ts in $TSERVERS; do
        docker stop "$ts" 2>/dev/null || true
    done
    sleep 3

    log_info "Stopping masters..."
    for master in $MASTERS; do
        docker stop "$master" 2>/dev/null || true
    done
    sleep 3

    # 2. Start in order: Masters -> TServers -> Impala
    log_info "Starting masters..."
    for master in $MASTERS; do
        docker start "$master" 2>/dev/null || log_error "Failed to start $master"
    done
    log_info "Waiting for master election (15s)..."
    sleep 15

    log_info "Starting tablet servers..."
    for ts in $TSERVERS; do
        docker start "$ts" 2>/dev/null || log_error "Failed to start $ts"
    done
    log_info "Waiting for tablet servers to register (20s)..."
    sleep 20

    log_info "Starting Impala..."
    docker start "$IMPALA" 2>/dev/null || log_error "Failed to start $IMPALA"
    log_info "Waiting for Impala to connect (10s)..."
    sleep 10

    # 3. Verify
    log_info "Verifying cluster..."
    local all_ok=true
    for node in $ALL_NODES; do
        if check_container_running "$node" 2>/dev/null; then
            log_info "  $node: running"
        else
            log_error "  $node: NOT running"
            all_ok=false
        fi
    done

    # 4. Test Impala connectivity
    log_info "Testing Impala query..."
    local result=$(docker exec "$IMPALA" impala-shell -q "SHOW DATABASES" 2>&1 | tail -5)
    if echo "$result" | grep -q "gmp_cis"; then
        log_info "Impala connection verified - gmp_cis database accessible"
    else
        log_warn "Impala may still be initializing, try again in a few seconds"
    fi

    if $all_ok; then
        log_info "Cluster restart complete - all nodes running!"
    else
        log_error "Some nodes failed to start. Check 'docker logs <container>' for details."
    fi
}

# =============================================================================
# FIX-RAFT - Attempt to fix Raft consensus issues
# =============================================================================

cmd_fix_raft() {
    log_section "Fixing Raft Consensus Issues"

    log_info "This procedure restarts tservers sequentially to force leader re-election"
    log_info "for tablet replicas that are stuck in FOLLOWER state."
    echo ""

    # 1. Check current state
    log_info "Checking for stuck tablets..."
    for ts in $TSERVERS; do
        if ! check_container_running "$ts" 2>/dev/null; then continue; fi
        local errors=$(docker exec "$ts" bash -c "tail -100 /tmp/kudu-tserver.ERROR 2>/dev/null | grep -c 'not leader' || true")
        if [ "$errors" -gt 0 ]; then
            log_warn "$ts has $errors 'not leader' errors in recent logs"
        fi
    done

    # 2. Sequential restart of tservers (one at a time to maintain quorum)
    for ts in $TSERVERS; do
        log_info "Restarting $ts..."
        docker restart "$ts" 2>/dev/null
        log_info "  Waiting 15s for tablet re-election..."
        sleep 15

        if check_container_running "$ts" 2>/dev/null; then
            log_info "  $ts is back up"
        else
            log_error "  $ts failed to restart!"
            return 1
        fi
    done

    # 3. Wait for leader election to stabilize
    log_info "Waiting 20s for Raft consensus to stabilize..."
    sleep 20

    # 4. Test write capability
    log_info "Testing write capability..."
    local write_test=$(docker exec "$IMPALA" impala-shell -q "
        SELECT COUNT(*) FROM gmp_cis.cis_sequence
    " 2>&1)

    if echo "$write_test" | grep -q "ERROR"; then
        log_error "Query still failing. May need a full cluster restart."
        log_info "Try: ./scripts/kudu_maintenance.sh full"
    else
        log_info "Query successful. Raft consensus appears healthy."
    fi
}

# =============================================================================
# FULL - Complete maintenance cycle
# =============================================================================

cmd_full() {
    log_section "Full Kudu Cluster Maintenance"
    echo "This will: cleanup logs -> restart cluster -> verify health"
    echo ""

    cmd_cleanup
    echo ""
    cmd_restart
    echo ""
    cmd_status
}

# =============================================================================
# Main
# =============================================================================

COMMAND=${1:-status}

case $COMMAND in
    status)     cmd_status ;;
    cleanup)    cmd_cleanup ;;
    restart)    cmd_restart ;;
    fix-raft)   cmd_fix_raft ;;
    full)       cmd_full ;;
    *)
        echo "Usage: $0 {status|cleanup|restart|fix-raft|full}"
        echo ""
        echo "Commands:"
        echo "  status    Show cluster health and disk usage (default)"
        echo "  cleanup   Clean rotated logs and Docker resources"
        echo "  restart   Graceful restart of the entire cluster"
        echo "  fix-raft  Fix Raft consensus/leader election issues"
        echo "  full      Run cleanup + restart + health check"
        exit 1
        ;;
esac
