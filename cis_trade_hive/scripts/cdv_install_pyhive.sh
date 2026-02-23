#!/bin/bash
#
# Install PyHive in CDV Virtual Environment
# ==========================================
#
# This script installs PyHive into a user-writable location
# that can be added to PYTHONPATH in CDV.
#
# CDV venv is read-only, so we install to user site-packages.
#
# Usage:
#   chmod +x cdv_install_pyhive.sh
#   ./cdv_install_pyhive.sh
#

echo "=============================================="
echo "Install PyHive for CDV"
echo "=============================================="

# Configuration
CDV_PYTHON="/opt/vizapps/venv/bin/python"
USER_PACKAGES="$HOME/.local/lib/python3.9/site-packages"
INSTALL_DIR="$HOME/pyhive_packages"

# Check CDV Python
echo ""
echo "[1/5] Checking CDV Python..."
if [ -f "$CDV_PYTHON" ]; then
    echo "  CDV Python: $($CDV_PYTHON --version)"
else
    echo "  CDV Python not found at $CDV_PYTHON"
    echo "  Using system Python..."
    CDV_PYTHON="python3"
fi

# Create install directory
echo ""
echo "[2/5] Creating install directory..."
mkdir -p "$INSTALL_DIR"
echo "  Directory: $INSTALL_DIR"

# Install PyHive to custom location
echo ""
echo "[3/5] Installing PyHive and dependencies..."
$CDV_PYTHON -m pip install \
    --target="$INSTALL_DIR" \
    --upgrade \
    pyhive==0.7.0 \
    thrift==0.16.0 \
    thrift-sasl==0.4.3 \
    sasl==0.3.1 \
    pure-sasl==0.6.2 \
    2>&1 | tee pyhive_install.log

echo ""
echo "[4/5] Verifying installation..."
ls -la "$INSTALL_DIR" | head -20

# Create test script
echo ""
echo "[5/5] Creating test script..."

cat > "$HOME/test_pyhive_cdv.py" << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""
Test PyHive in CDV Environment
"""
import sys
import os

# Add custom packages to path
PYHIVE_PATH = os.path.expanduser("~/pyhive_packages")
if PYHIVE_PATH not in sys.path:
    sys.path.insert(0, PYHIVE_PATH)
    print(f"Added to path: {PYHIVE_PATH}")

# CDV Settings
HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
HIVE_DATABASE = 'mrw_ima'

print("="*60)
print("PyHive Test in CDV Environment")
print("="*60)
print(f"Python: {sys.version}")
print(f"Host: {HIVE_HOST}")
print(f"Port: {HIVE_PORT}")
print()

try:
    from pyhive import hive
    print("[OK] PyHive imported successfully")
    print(f"     PyHive location: {hive.__file__}")

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

    # Test 1: Simple query
    print("\n[Test 1] SELECT 1")
    cursor.execute("SELECT 1 AS test")
    print(f"Result: {cursor.fetchone()}")

    # Test 2: Show databases
    print("\n[Test 2] SHOW DATABASES")
    cursor.execute("SHOW DATABASES")
    dbs = [row[0] for row in cursor.fetchall()]
    print(f"Databases: {dbs[:5]}...")

    # Test 3: Show tables
    print(f"\n[Test 3] SHOW TABLES IN {HIVE_DATABASE}")
    cursor.execute(f"SHOW TABLES IN {HIVE_DATABASE}")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {tables[:10]}...")

    # Test 4: Describe a table
    print(f"\n[Test 4] DESCRIBE cis_trade")
    cursor.execute(f"DESCRIBE {HIVE_DATABASE}.cis_trade")
    columns = cursor.fetchall()
    print(f"Columns ({len(columns)} total):")
    for col in columns[:10]:
        print(f"  {col[0]}: {col[1]}")
    if len(columns) > 10:
        print(f"  ... and {len(columns)-10} more")

    cursor.close()
    conn.close()

    print("\n" + "="*60)
    print("[SUCCESS] All tests passed!")
    print("="*60)

except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print("\nMake sure PyHive is installed:")
    print("  Run: ./cdv_install_pyhive.sh")
    print(f"\nOr add to PYTHONPATH:")
    print(f"  export PYTHONPATH={PYHIVE_PATH}:$PYTHONPATH")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
PYTHON_SCRIPT

chmod +x "$HOME/test_pyhive_cdv.py"

# Print instructions
echo ""
echo "=============================================="
echo "INSTALLATION COMPLETE"
echo "=============================================="
echo ""
echo "PyHive installed to: $INSTALL_DIR"
echo ""
echo "To use in Python:"
echo "  import sys"
echo "  sys.path.insert(0, '$INSTALL_DIR')"
echo "  from pyhive import hive"
echo ""
echo "Or set PYTHONPATH:"
echo "  export PYTHONPATH=$INSTALL_DIR:\$PYTHONPATH"
echo ""
echo "Test script created: $HOME/test_pyhive_cdv.py"
echo ""
echo "To test:"
echo "  1. Get Kerberos ticket:"
echo "     kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM"
echo ""
echo "  2. Run test:"
echo "     $CDV_PYTHON $HOME/test_pyhive_cdv.py"
echo ""
