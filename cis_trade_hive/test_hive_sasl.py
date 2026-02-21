#!/usr/bin/env python3
"""
Test Hive connection with correct SASL configuration

Based on ZooKeeper discovery:
- hive.server2.authentication=KERBEROS
- hive.server2.thrift.sasl.qop=auth
- hive.server2.transport.mode=all

Run: python test_hive_sasl.py
"""
import os
import sys
import subprocess

os.environ['CIS_ENV'] = 'work'

print("=" * 70)
print("HIVE SASL CONNECTION TEST")
print("=" * 70)

# Working hosts from ZooKeeper
HIVE_HOSTS = [
    ("lxmrwtsgv0m2.sg.uobnet.com", 10000),
    ("lxmrwtsgv0m1.sg.uobnet.com", 10000),
]

# Check Kerberos
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("ERROR: No Kerberos ticket. Run kinit first!")
    sys.exit(1)
print("Kerberos ticket: OK")

# Show principal
for line in result.stdout.split('\n'):
    if 'Default principal' in line or 'Principal' in line:
        print(f"  {line.strip()}")

# Test 1: impyla with different SASL configurations
print("\n" + "-" * 70)
print("[1] Test impyla with SASL QOP configurations")
print("-" * 70)

try:
    from impala.dbapi import connect as impyla_connect
    import inspect

    # Check available parameters
    sig = inspect.signature(impyla_connect)
    print(f"impyla.connect parameters: {list(sig.parameters.keys())[:15]}...")

    configs = [
        # Config 1: Standard GSSAPI
        {
            'auth_mechanism': 'GSSAPI',
            'kerberos_service_name': 'hive',
            'use_ssl': False,
        },
        # Config 2: With LDAP (if service account available)
        {
            'auth_mechanism': 'PLAIN',
            'user': os.environ.get('HIVE_USER', ''),
            'password': os.environ.get('HIVE_PASSWORD', ''),
            'use_ssl': False,
        },
        # Config 3: NOSASL (if allowed)
        {
            'auth_mechanism': 'NOSASL',
            'use_ssl': False,
        },
    ]

    for host, port in HIVE_HOSTS:
        for i, config in enumerate(configs):
            if config.get('auth_mechanism') == 'PLAIN' and not config.get('user'):
                continue  # Skip PLAIN if no credentials

            try:
                print(f"\nTrying {host}:{port} with config {i+1}: {config.get('auth_mechanism')}")
                conn = impyla_connect(
                    host=host,
                    port=port,
                    database='default',
                    timeout=30,
                    **config
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                print(f"  SUCCESS! Result: {result}")
                print(f"\n*** WORKING CONFIG FOUND ***")
                print(f"  Host: {host}:{port}")
                print(f"  Config: {config}")
                sys.exit(0)
            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

except ImportError:
    print("impyla not installed")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Try HTTP transport mode
print("\n" + "-" * 70)
print("[2] Test impyla with HTTP transport")
print("-" * 70)

try:
    from impala.dbapi import connect as impyla_connect

    for host, port in HIVE_HOSTS:
        # Try HTTP on standard port
        for http_port in [10000, 10001]:
            try:
                print(f"\nTrying HTTP transport on {host}:{http_port}...")
                conn = impyla_connect(
                    host=host,
                    port=http_port,
                    database='default',
                    auth_mechanism='GSSAPI',
                    kerberos_service_name='hive',
                    use_ssl=False,
                    use_http_transport=True,
                    http_path='cliservice',
                    timeout=30,
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                print(f"  SUCCESS! Result: {result}")
                print(f"\n*** HTTP TRANSPORT WORKS ***")
                sys.exit(0)
            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

except Exception as e:
    print(f"Error: {e}")

# Test 3: Try thrift_sasl directly
print("\n" + "-" * 70)
print("[3] Check thrift_sasl and pure-sasl versions")
print("-" * 70)

try:
    import thrift_sasl
    print(f"thrift_sasl version: {getattr(thrift_sasl, '__version__', 'unknown')}")
except ImportError:
    print("thrift_sasl not installed")

try:
    import puresasl
    print(f"pure-sasl version: {getattr(puresasl, '__version__', 'unknown')}")
except ImportError:
    print("pure-sasl not installed")

try:
    import sasl
    print(f"sasl (native) is installed - this might cause conflicts")
except ImportError:
    print("sasl (native) not installed - good, using pure-sasl")

# Test 4: Check environment
print("\n" + "-" * 70)
print("[4] Environment check")
print("-" * 70)

print(f"KRB5CCNAME: {os.environ.get('KRB5CCNAME', 'not set')}")
print(f"KRB5_CONFIG: {os.environ.get('KRB5_CONFIG', 'not set')}")

# Check if we can import gssapi
try:
    import gssapi
    print(f"gssapi available: yes")
    # Try to get credentials
    try:
        creds = gssapi.Credentials(usage='initiate')
        print(f"  Default credentials: {creds.name}")
    except Exception as e:
        print(f"  Credentials error: {e}")
except ImportError:
    print("gssapi not installed - pip install gssapi")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
