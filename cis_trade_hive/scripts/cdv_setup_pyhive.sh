#!/bin/bash
#
# CDV PyHive Setup Script
# =======================
#
# This script creates a new virtual environment with PyHive for testing
# Hive connections in Cloudera Data Visualization (CDV) environment.
#
# Based on CDV paths:
#   - CDV venv: /opt/vizapps/venv
#   - Site packages: /opt/vizapps/venv/lib64/python3.9/site-packages
#
# Usage:
#   chmod +x cdv_setup_pyhive.sh
#   ./cdv_setup_pyhive.sh
#

echo "=============================================="
echo "CDV PyHive Setup Script"
echo "=============================================="
echo ""

# Configuration
CDV_VENV="/opt/vizapps/venv"
NEW_VENV="$HOME/pyhive_venv"
PYTHON_VERSION="python3.9"

# Step 1: Check existing CDV environment
echo "[1/6] Checking CDV environment..."
if [ -d "$CDV_VENV" ]; then
    echo "  CDV venv found: $CDV_VENV"
    echo "  Python: $($CDV_VENV/bin/python --version 2>/dev/null || echo 'Not accessible')"
else
    echo "  CDV venv not found at $CDV_VENV"
fi

# Step 2: List available packages in CDV
echo ""
echo "[2/6] Listing CDV packages (for reference)..."
if [ -f "$CDV_VENV/bin/pip" ]; then
    echo "  Saving CDV package list to cdv_packages.txt..."
    $CDV_VENV/bin/pip freeze > cdv_packages.txt 2>/dev/null || echo "  Could not list packages"
    echo "  Done. Check cdv_packages.txt"
else
    echo "  pip not found in CDV venv"
fi

# Step 3: Create new virtual environment
echo ""
echo "[3/6] Creating new virtual environment at $NEW_VENV..."
if [ -d "$NEW_VENV" ]; then
    echo "  Removing existing venv..."
    rm -rf "$NEW_VENV"
fi

$PYTHON_VERSION -m venv "$NEW_VENV"
if [ $? -eq 0 ]; then
    echo "  Created: $NEW_VENV"
else
    echo "  ERROR: Failed to create venv. Trying python3..."
    python3 -m venv "$NEW_VENV"
fi

# Step 4: Activate and upgrade pip
echo ""
echo "[4/6] Activating venv and upgrading pip..."
source "$NEW_VENV/bin/activate"
pip install --upgrade pip

# Step 5: Install PyHive and dependencies
echo ""
echo "[5/6] Installing PyHive and dependencies..."

# Core packages for Hive connectivity
pip install \
    pyhive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    sasl==0.3.1 \
    pure-sasl==0.6.2

# Additional useful packages
pip install \
    requests \
    pandas

echo ""
echo "  Installed packages:"
pip list | grep -E "pyhive|thrift|sasl|pure"

# Step 6: Create test script
echo ""
echo "[6/6] Creating test script..."

cat > "$NEW_VENV/test_hive.py" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""
Quick Hive Connection Test
"""
import os
import sys

# CDV Settings
HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
HIVE_DATABASE = 'mrw_ima'

print("="*60)
print("HIVE CONNECTION TEST")
print("="*60)
print(f"Host: {HIVE_HOST}")
print(f"Port: {HIVE_PORT}")
print(f"Database: {HIVE_DATABASE}")
print()

try:
    from pyhive import hive
    print("[OK] PyHive imported successfully")

    print("\nConnecting with Kerberos...")
    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=HIVE_DATABASE,
        auth='KERBEROS',
        kerberos_service_name='hive'
    )
    print("[OK] Connected!")

    cursor = conn.cursor()

    # Test query
    print("\nRunning: SELECT 1")
    cursor.execute("SELECT 1 AS test")
    print(f"Result: {cursor.fetchone()}")

    # Show tables
    print(f"\nRunning: SHOW TABLES IN {HIVE_DATABASE}")
    cursor.execute(f"SHOW TABLES IN {HIVE_DATABASE}")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {tables[:10]}")

    cursor.close()
    conn.close()
    print("\n[SUCCESS] All tests passed!")

except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print("Install: pip install pyhive thrift thrift-sasl sasl")
except Exception as e:
    print(f"[ERROR] {e}")
PYTHON_SCRIPT

chmod +x "$NEW_VENV/test_hive.py"

# Print summary
echo ""
echo "=============================================="
echo "SETUP COMPLETE"
echo "=============================================="
echo ""
echo "Virtual environment: $NEW_VENV"
echo ""
echo "To use:"
echo "  1. Activate venv:"
echo "     source $NEW_VENV/bin/activate"
echo ""
echo "  2. Ensure Kerberos ticket:"
echo "     kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM"
echo ""
echo "  3. Run test:"
echo "     python $NEW_VENV/test_hive.py"
echo ""
echo "  Or run directly:"
echo "     $NEW_VENV/bin/python $NEW_VENV/test_hive.py"
echo ""
