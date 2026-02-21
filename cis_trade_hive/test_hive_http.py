#!/usr/bin/env python3
"""
Hive HTTP Transport Test for CML

DataViz might be using HTTP transport mode instead of Binary.
This tests HTTP transport with impyla.

Run: python test_hive_http.py
"""
import os
import sys

# Force work environment
os.environ['CIS_ENV'] = 'work'

HIVE_HOST = 'lxmrwtsgv0m2.sg.uobnet.com'
HIVE_PORT = 10000
HIVE_HTTP_PORT = 10001  # Common HTTP port for HiveServer2
DATABASE = 'mrw_ima'
KERBEROS_SERVICE = 'hive'

print("=" * 70)
print("HIVE HTTP TRANSPORT TEST")
print("=" * 70)

# Check Kerberos
import subprocess
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("ERROR: No Kerberos ticket. Run kinit first!")
    sys.exit(1)
print("Kerberos ticket: OK")

# Test 1: HTTP transport on port 10001
print("\n" + "-" * 70)
print("[1] Test HTTP transport on port 10001")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_HTTP_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name=KERBEROS_SERVICE,
        use_ssl=False,
        use_http_transport=True,
        http_path='cliservice',
        timeout=60,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: HTTP transport on port 10000
print("\n" + "-" * 70)
print("[2] Test HTTP transport on port 10000")
print("-" * 70)
try:
    from impala.dbapi import connect as impyla_connect

    conn = impyla_connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth_mechanism='GSSAPI',
        kerberos_service_name=KERBEROS_SERVICE,
        use_ssl=False,
        use_http_transport=True,
        http_path='cliservice',
        timeout=60,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 3: Try pyhive with HTTP mode
print("\n" + "-" * 70)
print("[3] Test pyhive with HTTP transport")
print("-" * 70)
try:
    from pyhive import hive

    # Check if thrift_transport parameter exists
    import inspect
    sig = inspect.signature(hive.Connection)
    print(f"pyhive.Connection parameters: {list(sig.parameters.keys())}")

    # Try with thrift_transport='http' if supported
    conn = hive.Connection(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=DATABASE,
        auth='KERBEROS',
        kerberos_service_name=KERBEROS_SERVICE,
        thrift_transport='http',
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print(f"SUCCESS! Result: {result}")
except TypeError as e:
    if 'thrift_transport' in str(e):
        print("thrift_transport not supported in this pyhive version")
    else:
        print(f"FAILED: {e}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 4: Check what ports are open on the Hive server
print("\n" + "-" * 70)
print("[4] Check connectivity to common Hive ports")
print("-" * 70)
import socket

ports_to_check = [10000, 10001, 10500, 10002, 21050]
for port in ports_to_check:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((HIVE_HOST, port))
        sock.close()
        status = "OPEN" if result == 0 else f"CLOSED (err={result})"
        print(f"  {HIVE_HOST}:{port} -> {status}")
    except Exception as e:
        print(f"  {HIVE_HOST}:{port} -> ERROR: {e}")

# Test 5: Try using JayDeBeApi (JDBC wrapper) if available
print("\n" + "-" * 70)
print("[5] Check for JDBC libraries")
print("-" * 70)
try:
    import jaydebeapi
    print("jaydebeapi is available - could use JDBC driver")
    print("To install: pip install JayDeBeApi")
except ImportError:
    print("jaydebeapi not installed")
    print("This could be an option: pip install JayDeBeApi")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("""
NEXT STEPS:
1. If HTTP transport works, we need to configure impyla to use HTTP mode
2. If no Python library works, we can use JayDeBeApi with Hive JDBC driver
3. Check with your Cloudera admin what transport mode HiveServer2 uses:
   - Binary (default, port 10000)
   - HTTP (port 10001 or configured)

To check HiveServer2 transport mode on server:
   hive.server2.transport.mode = binary|http
""")
