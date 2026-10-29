#!/bin/bash
# =============================================================================
# Check Settlement Queue Status
# =============================================================================
# Quick script to check pending settlements and position status.
#
# Usage:
#   ./scripts/check_settlement_queue.sh [DATE]
#
# Examples:
#   ./scripts/check_settlement_queue.sh           # Check today's status
#   ./scripts/check_settlement_queue.sh 2026-03-06 # Check specific date
#
# Created: 2026-03-06
# =============================================================================

set -euo pipefail

# Default to today
CHECK_DATE=${1:-$(date '+%Y-%m-%d')}

# Impala connection (adjust for your environment)
IMPALA_HOST="localhost:21050"
AUTH_ARGS="-a NOSASL"
DATABASE="gmp_cis"

echo "============================================================"
echo "  CIS Trade Hive - Settlement Queue Status"
echo "============================================================"
echo "Date: $CHECK_DATE"
echo ""

echo "--- Pending Settlements ---"
impala-shell -i "$IMPALA_HOST" $AUTH_ARGS -d "$DATABASE" -q "
SELECT
    queue_id,
    trade_id,
    portfolio_id,
    security_id,
    trade_type,
    CAST(quantity AS STRING) as quantity,
    CAST(price AS STRING) as price,
    settle_date,
    status,
    queued_at
FROM cis_settlement_queue
WHERE settle_date <= '$CHECK_DATE'
ORDER BY settle_date, queued_at
LIMIT 50;
" 2>/dev/null

echo ""
echo "--- Settlement Queue Summary ---"
impala-shell -i "$IMPALA_HOST" $AUTH_ARGS -d "$DATABASE" -q "
SELECT
    settle_date,
    status,
    COUNT(*) as count
FROM cis_settlement_queue
GROUP BY settle_date, status
ORDER BY settle_date DESC, status
LIMIT 20;
" 2>/dev/null

echo ""
echo "--- Recent Positions ---"
impala-shell -i "$IMPALA_HOST" $AUTH_ARGS -d "$DATABASE" -q "
SELECT
    portfolio_short_name,
    security_label,
    CAST(quantity AS STRING) as quantity,
    CAST(average_cost AS STRING) as avg_cost,
    CAST(realized_pnl AS STRING) as realized_pnl,
    status,
    position_date,
    trade_type as last_trade
FROM cis_trade_position
ORDER BY version_id DESC
LIMIT 10;
" 2>/dev/null

echo ""
echo "Done."
