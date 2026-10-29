#!/bin/bash
# ============================================================================
# Hive POC - Start Local Hive Environment
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Hive POC - Starting Local Environment"
echo "=========================================="

# Start Docker containers
echo "Starting Docker containers..."
docker-compose up -d

# Wait for services to be healthy
echo "Waiting for services to start..."
sleep 10

# Check if metastore is ready
echo "Waiting for Hive Metastore..."
for i in {1..30}; do
    if docker exec hive-metastore bash -c "cat < /dev/null > /dev/tcp/localhost/9083" 2>/dev/null; then
        echo "Hive Metastore is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 5
done

# Check if HiveServer2 is ready
echo "Waiting for HiveServer2..."
for i in {1..30}; do
    if docker exec hiveserver2 bash -c "cat < /dev/null > /dev/tcp/localhost/10000" 2>/dev/null; then
        echo "HiveServer2 is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 5
done

echo ""
echo "=========================================="
echo "Hive Environment Started!"
echo "=========================================="
echo ""
echo "HiveServer2:  localhost:10000"
echo "Web UI:       http://localhost:10002"
echo "Metastore:    localhost:9083"
echo ""
echo "To connect via beeline:"
echo "  docker exec -it hiveserver2 beeline -u jdbc:hive2://localhost:10000"
echo ""
echo "To initialize database and tables:"
echo "  ./init-hive-db.sh"
echo ""
