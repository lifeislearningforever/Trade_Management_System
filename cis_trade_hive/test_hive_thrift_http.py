#!/usr/bin/env python3
"""
Test Hive using Thrift HTTP Transport directly

This bypasses PyHive/Impyla and uses Thrift directly with HTTP.

Run: python test_hive_thrift_http.py
"""
import os
import sys
import subprocess

os.environ['CIS_ENV'] = 'work'

print("=" * 70)
print("HIVE THRIFT HTTP DIRECT TEST")
print("=" * 70)

# Check what we have
print("\n[1] Checking installed packages...")

packages_status = {}
for pkg in ['thrift', 'requests', 'requests_kerberos', 'pyhive', 'impyla']:
    try:
        mod = __import__(pkg.replace('-', '_').replace('_kerberos', '_kerberos'))
        ver = getattr(mod, '__version__', 'unknown')
        packages_status[pkg] = ver
        print(f"  {pkg}: {ver}")
    except ImportError:
        packages_status[pkg] = None
        print(f"  {pkg}: NOT INSTALLED")

# Test 2: Try using requests with SPNEGO directly to HS2
print("\n" + "-" * 70)
print("[2] Test direct HTTP to HiveServer2 with SPNEGO")
print("-" * 70)

HIVE_HOSTS = [
    ("lxmrwtsgv0m2.sg.uobnet.com", 10000),
    ("lxmrwtsgv0m1.sg.uobnet.com", 10000),
    ("lxmrwtsgv0m2.sg.uobnet.com", 10001),
    ("lxmrwtsgv0m1.sg.uobnet.com", 10001),
]

if packages_status.get('requests_kerberos'):
    import requests
    from requests_kerberos import HTTPKerberosAuth, OPTIONAL

    for host, port in HIVE_HOSTS:
        for path in ['/cliservice', '/', '']:
            url = f"http://{host}:{port}{path}"
            try:
                print(f"\nTrying: {url}")
                auth = HTTPKerberosAuth(mutual_authentication=OPTIONAL)
                resp = requests.post(
                    url,
                    auth=auth,
                    headers={'Content-Type': 'application/x-thrift'},
                    timeout=10
                )
                print(f"  Status: {resp.status_code}")
                if resp.status_code == 200:
                    print(f"  Response: {resp.content[:100]}")
            except Exception as e:
                print(f"  Error: {str(e)[:60]}")

# Test 3: Check Hive version and exact config needed
print("\n" + "-" * 70)
print("[3] Check environment variables")
print("-" * 70)

env_vars = ['KRB5CCNAME', 'KRB5_CONFIG', 'JAVA_HOME', 'HADOOP_HOME', 'HIVE_HOME']
for var in env_vars:
    print(f"  {var}: {os.environ.get(var, 'not set')}")

# Test 4: Check if we can use impala-shell or beeline
print("\n" + "-" * 70)
print("[4] Check available CLI tools")
print("-" * 70)

for tool in ['beeline', 'impala-shell', 'hive']:
    result = subprocess.run(['which', tool], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  {tool}: {result.stdout.strip()}")
    else:
        print(f"  {tool}: not found")

# Test 5: Try simplest possible connection
print("\n" + "-" * 70)
print("[5] Simple TCP test to Hive ports")
print("-" * 70)

import socket

for host, port in HIVE_HOSTS[:2]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))

        # Try sending a simple message
        sock.send(b'\x00\x00\x00\x00')  # Empty thrift message

        try:
            data = sock.recv(1024)
            print(f"  {host}:{port} - Received {len(data)} bytes")
        except socket.timeout:
            print(f"  {host}:{port} - Connected but no response (expected)")

        sock.close()
    except Exception as e:
        print(f"  {host}:{port} - {e}")

print("\n" + "=" * 70)
print("ANALYSIS")
print("=" * 70)
print("""
SITUATION:
- Ports are OPEN (10000, 10001)
- Kerberos ticket is valid
- But Python libraries can't complete SASL handshake

ROOT CAUSE:
- HiveServer2 requires SASL with GSSAPI
- Python's pure-sasl doesn't implement GSSAPI properly
- Native sasl library needs glibc 2.38 (CML has older)
- HTTP transport still needs Thrift SASL wrapper

POSSIBLE SOLUTIONS:

1. USE IMPALA FOR BOTH READS AND WRITES (if Impala works)
   - Impala supports INSERT/UPDATE on Kudu tables
   - If your tables are in Kudu, use Impala

2. USE SPARK/PYSPARK IN CML
   - CML has Spark integration
   - Spark can write to Hive tables directly
   - spark.sql("INSERT INTO table VALUES (...)")

3. USE CLOUDERA DATA ENGINEERING (CDE)
   - Submit Spark jobs via REST API
   - Jobs can write to Hive

4. CREATE REST PROXY ON EDGE NODE
   - Small Flask app on edge node
   - Accepts REST calls, executes beeline
   - No SSH needed, just HTTP

Which approach would you like to try?
""")
