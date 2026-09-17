#!/bin/bash
# ============================================================================
# Hive POC - Stop Local Hive Environment
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping Hive POC containers..."
docker-compose down

echo "Done!"
