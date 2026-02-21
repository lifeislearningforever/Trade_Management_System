#!/usr/bin/env python3
"""
Test script for Hive/Impala connections in CML.

Run this in CML Session terminal:
    python test_hive_connection.py

Or in Django shell:
    python manage.py shell < test_hive_connection.py

IMPORTANT: This script automatically sets CIS_ENV='work' for CML testing.
"""

import os
import sys
import socket

# =============================================================================
# CRITICAL: Set CIS_ENV BEFORE importing Django settings
# This MUST be set before any Django imports to use work configuration
# =============================================================================
os.environ['CIS_ENV'] = 'work'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

print("=" * 60)
print("HIVE/IMPALA CONNECTION TEST")
print("=" * 60)
print(f"\nEnvironment: CIS_ENV = {os.environ.get('CIS_ENV')}")

# Configuration
IMPALA_HOST = os.environ.get('IMPALA_HOST', 'lxmrwsgv0d1.sg.uobnet.com')
IMPALA_PORT = int(os.environ.get('IMPALA_PORT', '21050'))
HIVE_HOST = os.environ.get('HIVE_HOST', 'lxmrwtsgv0m2.sg.uobnet.com')
HIVE_PORT = int(os.environ.get('HIVE_PORT', '10000'))
DATABASE = os.environ.get('HIVE_DB', 'mrw_ima')

print(f"\nConfiguration:")
print(f"  Impala: {IMPALA_HOST}:{IMPALA_PORT}")
print(f"  Hive:   {HIVE_HOST}:{HIVE_PORT}")
print(f"  Database: {DATABASE}")

# ==================== TEST 1: DNS Resolution ====================
print("\n" + "=" * 60)
print("[TEST 1] DNS Resolution")
print("=" * 60)

for name, host in [("Impala", IMPALA_HOST), ("Hive", HIVE_HOST)]:
    try:
        ip = socket.gethostbyname(host)
        print(f"  {name}: {host} -> {ip} [OK]")
    except socket.gaierror as e:
        print(f"  {name}: {host} -> FAILED: {e}")

# ==================== TEST 2: TCP Connection ====================
print("\n" + "=" * 60)
print("[TEST 2] TCP Port Connectivity")
print("=" * 60)

for name, host, port in [("Impala", IMPALA_HOST, IMPALA_PORT), ("Hive", HIVE_HOST, HIVE_PORT)]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"  {name}: {host}:{port} -> OPEN [OK]")
        else:
            print(f"  {name}: {host}:{port} -> CLOSED (error {result})")
    except Exception as e:
        print(f"  {name}: {host}:{port} -> FAILED: {e}")

# ==================== TEST 3: Kerberos Ticket ====================
print("\n" + "=" * 60)
print("[TEST 3] Kerberos Ticket")
print("=" * 60)

import subprocess
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode == 0:
    print("  Kerberos ticket: VALID [OK]")
    # Show principal
    for line in result.stdout.split('\n'):
        if 'Default principal' in line or 'Principal' in line:
            print(f"    {line.strip()}")
else:
    print("  Kerberos ticket: NOT FOUND or EXPIRED")
    print("  Run: kinit -kt <keytab> <principal>")

# ==================== TEST 4: Impala Connection (impyla) ====================
print("\n" + "=" * 60)
print("[TEST 4] Impala Connection (impyla)")
print("=" * 60)

try:
    from impala.dbapi import connect as impala_connect

    conn = impala_connect(
        host=IMPALA_HOST,
        port=IMPALA_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name='impala',
        use_ssl=True,
        timeout=30
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"  Impala connection: SUCCESS [OK]")
    print(f"    SELECT 1 = {result}")
except ImportError:
    print("  Impala: impyla not installed")
    print("  Run: pip install impyla pure-sasl")
except Exception as e:
    print(f"  Impala connection: FAILED")
    print(f"    Error: {e}")

# ==================== TEST 5: Hive Connection (pyhive) ====================
print("\n" + "=" * 60)
print("[TEST 5] Hive Connection (pyhive)")
print("=" * 60)

try:
    from pyhive import hive

    print(f"  Attempting connection to {HIVE_HOST}:{HIVE_PORT}...")
    print(f"  Auth: KERBEROS, Service: hive")

    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth='KERBEROS',
        kerberos_service_name='hive'
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"  Hive connection: SUCCESS [OK]")
    print(f"    SELECT 1 = {result}")
except ImportError:
    print("  Hive: pyhive not installed")
    print("  Run: pip install pyhive pure-sasl thrift-sasl")
except Exception as e:
    print(f"  Hive connection: FAILED")
    print(f"    Error: {e}")
    print(f"    Error type: {type(e).__name__}")

    # Additional diagnostics
    print("\n  Troubleshooting:")
    print("  1. Check if Hive service is running on the server")
    print("  2. Verify Kerberos principal has access to Hive")
    print("  3. Try connecting via beeline:")
    print(f"     beeline -u \"jdbc:hive2://{HIVE_HOST}:{HIVE_PORT}/{DATABASE};principal=hive/_HOST@REALM\"")

# ==================== TEST 6: Hybrid Manager ====================
print("\n" + "=" * 60)
print("[TEST 6] Django Hybrid Connection Manager")
print("=" * 60)

try:
    # NOTE: Django settings module and CIS_ENV already set at top of script
    import django
    django.setup()

    # Verify settings loaded correctly
    from django.conf import settings
    print(f"\n  Django Settings Loaded:")
    print(f"    CIS_ENV: {settings.CIS_ENV}")
    print(f"    Impala Host: {settings.IMPALA_CONFIG.get('HOST')}")
    print(f"    Impala Auth: {settings.IMPALA_CONFIG.get('AUTH_MECHANISM')}")
    print(f"    Hive Host: {settings.HIVE_CONFIG.get('HOST')}")
    print(f"    Hive Auth: {settings.HIVE_CONFIG.get('AUTH')}")

    from core.repositories.hybrid_connection import hybrid_manager

    results = hybrid_manager.test_connection()
    print(f"\n  Connection Tests:")
    print(f"    Impala: {'SUCCESS [OK]' if results.get('impala') else 'FAILED'}")
    print(f"    Hive:   {'SUCCESS [OK]' if results.get('hive') else 'FAILED'}")

    stats = hybrid_manager.get_pool_stats()
    print(f"\n  Pool Stats:")
    print(f"    Impala: {stats['impala']}")
    print(f"    Hive:   {stats['hive']}")

except Exception as e:
    import traceback
    print(f"  Hybrid manager test: FAILED")
    print(f"    Error: {e}")
    traceback.print_exc()

# ==================== SUMMARY ====================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("""
If Impala works but Hive fails with "TSocket read 0 bytes":

1. Check Hive service name (might be 'hiveserver2' instead of 'hive'):
   Try: kerberos_service_name='hiveserver2'

2. Check Hive port (might be different):
   Common ports: 10000, 10001, 10500

3. Check Hive authentication mode on server:
   - binary mode vs HTTP mode
   - For HTTP mode, use: auth='KERBEROS', thrift_transport='http'

4. Try connecting via beeline first to verify server is accessible:
   beeline -u "jdbc:hive2://{HIVE_HOST}:10000/;principal=hive/_HOST@REALM"

5. Check if SSL is required for Hive:
   Add: use_ssl=True to connection
""".format(HIVE_HOST=HIVE_HOST))
