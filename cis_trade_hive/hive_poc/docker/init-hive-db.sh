#!/bin/bash
# ============================================================================
# Hive POC - Initialize Database and Tables
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Hive POC - Initializing Database"
echo "=========================================="

# Copy SQL file to container
echo "Copying SQL script to container..."
docker cp "$SCRIPT_DIR/init-db.sql" hiveserver2:/tmp/init-db.sql

# Run initialization
echo "Running initialization script..."
docker exec hiveserver2 beeline -u "jdbc:hive2://localhost:10000" -f /tmp/init-db.sql

echo ""
echo "=========================================="
echo "Database initialized successfully!"
echo "=========================================="
echo ""
echo "Tables created:"
echo "  - gmp_cis.portfolio_hive"
echo "  - gmp_cis.trade_hive"
echo ""
echo "Sample data loaded (3 portfolios, 3 trades)"
echo ""
