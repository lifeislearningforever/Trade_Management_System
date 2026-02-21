#!/usr/bin/env python3
"""
Test Hive HTTP Transport Mode

HiveServer2 config shows: hive.server2.transport.mode=all
This means HTTP transport is supported alongside binary.

HTTP transport uses:
- Port: Usually 10001 (or 10000 with http path)
- Path: /cliservice
- No native SASL libraries needed for HTTP mode

Run: python test_hive_http_transport.py
"""
import os
import sys
import subprocess
import requests

os.environ['CIS_ENV'] = 'work'

print("=" * 70)
print("HIVE HTTP TRANSPORT TEST")
print("=" * 70)

# Hosts from ZooKeeper discovery
HIVE_HOSTS = [
    "lxmrwtsgv0m2.sg.uobnet.com",
    "lxmrwtsgv0m1.sg.uobnet.com",
]

# Common HTTP ports for HiveServer2
HTTP_PORTS = [10001, 10000]

# Check Kerberos
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("WARNING: No Kerberos ticket")
else:
    print("Kerberos ticket: OK")
    for line in result.stdout.split('\n'):
        if 'Default principal' in line:
            print(f"  {line.strip()}")

# Test 1: Check HTTP connectivity
print("\n" + "-" * 70)
print("[1] Check HTTP Connectivity to HiveServer2")
print("-" * 70)

import socket

for host in HIVE_HOSTS:
    for port in HTTP_PORTS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            status = "OPEN" if result == 0 else "CLOSED"
            print(f"  {host}:{port} -> {status}")
        except Exception as e:
            print(f"  {host}:{port} -> ERROR: {e}")

# Test 2: Try requests-kerberos for HTTP auth
print("\n" + "-" * 70)
print("[2] Test HTTP with Kerberos (requests-kerberos)")
print("-" * 70)

try:
    from requests_kerberos import HTTPKerberosAuth, REQUIRED

    for host in HIVE_HOSTS:
        for port in HTTP_PORTS:
            try:
                url = f"http://{host}:{port}/cliservice"
                print(f"\nTrying: {url}")

                auth = HTTPKerberosAuth(mutual_authentication=REQUIRED)
                response = requests.get(url, auth=auth, timeout=10)
                print(f"  Status: {response.status_code}")
                print(f"  Response: {response.text[:200]}")

            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

except ImportError:
    print("requests-kerberos not installed")
    print("Install: pip install requests-kerberos")

# Test 3: Try PyHive with HTTP transport
print("\n" + "-" * 70)
print("[3] Test PyHive with HTTP Transport")
print("-" * 70)

try:
    from pyhive import hive

    for host in HIVE_HOSTS:
        for port in HTTP_PORTS:
            try:
                print(f"\nTrying PyHive HTTP: {host}:{port}")

                conn = hive.Connection(
                    host=host,
                    port=port,
                    username='owntmrwsg',
                    database='default',
                    auth='KERBEROS',
                    kerberos_service_name='hive',
                    thrift_transport='http',
                    http_path='cliservice',
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                print(f"  SUCCESS! Result: {result}")
                sys.exit(0)

            except TypeError as e:
                if 'thrift_transport' in str(e):
                    print(f"  thrift_transport not supported in this PyHive version")
                else:
                    print(f"  Failed: {str(e)[:80]}")
            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

except ImportError:
    print("PyHive not installed")

# Test 4: Try impyla with HTTP transport
print("\n" + "-" * 70)
print("[4] Test Impyla with HTTP Transport")
print("-" * 70)

try:
    from impala.dbapi import connect as impyla_connect

    for host in HIVE_HOSTS:
        for port in HTTP_PORTS:
            try:
                print(f"\nTrying Impyla HTTP: {host}:{port}")

                conn = impyla_connect(
                    host=host,
                    port=port,
                    database='default',
                    auth_mechanism='GSSAPI',
                    kerberos_service_name='hive',
                    use_http_transport=True,
                    http_path='cliservice',
                    use_ssl=False,
                    timeout=30,
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                print(f"  SUCCESS! Result: {result}")
                sys.exit(0)

            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

except ImportError:
    print("Impyla not installed")

# Test 5: Check thrift HTTP client
print("\n" + "-" * 70)
print("[5] Available Python packages")
print("-" * 70)

packages = [
    'pyhive', 'impyla', 'thrift', 'thrift_sasl', 'pure-sasl',
    'puresasl', 'requests_kerberos', 'gssapi', 'kerberos'
]

for pkg in packages:
    try:
        __import__(pkg.replace('-', '_'))
        print(f"  {pkg}: installed")
    except ImportError:
        print(f"  {pkg}: NOT installed")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("""
RECOMMENDATIONS:
1. If HTTP transport works, use PyHive or Impyla with use_http_transport=True
2. Install: pip install requests-kerberos pyhive impyla
3. HTTP mode avoids SASL/glibc issues completely
""")
