#!/usr/bin/env python3
"""
Test Hive connection via ZooKeeper using impyla

In Cloudera, HiveServer2 registers with ZooKeeper.
We can query ZooKeeper to get the actual HiveServer2 host/port,
then connect directly.

Run: python test_hive_zookeeper.py
"""
import os
import sys
import subprocess

os.environ['CIS_ENV'] = 'work'

print("=" * 70)
print("HIVE ZOOKEEPER DISCOVERY TEST")
print("=" * 70)

# Check Kerberos
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("WARNING: No Kerberos ticket found")
else:
    print("Kerberos ticket: OK")

# ZooKeeper hosts
ZK_HOSTS = [
    "lxmrwtsgv0m1.sg.uobnet.com:2181",
    "lxmrwtsgv0m2.sg.uobnet.com:2181",
    "lxmrwtsgv0w1.sg.uobnet.com:2181",
]
ZK_NAMESPACE = "hiveserver2"

print(f"\nZooKeeper hosts: {ZK_HOSTS}")
print(f"Namespace: {ZK_NAMESPACE}")

# Test 1: Try kazoo to query ZooKeeper
print("\n" + "-" * 70)
print("[1] Query ZooKeeper for HiveServer2 instances")
print("-" * 70)

try:
    from kazoo.client import KazooClient

    zk = KazooClient(hosts=','.join(ZK_HOSTS))
    zk.start(timeout=10)

    # List children under hiveserver2 namespace
    path = f"/{ZK_NAMESPACE}"
    if zk.exists(path):
        children = zk.get_children(path)
        print(f"Found {len(children)} HiveServer2 instances:")
        for child in children:
            data, stat = zk.get(f"{path}/{child}")
            print(f"  - {child}")
            if data:
                print(f"    Data: {data.decode('utf-8')[:200]}")
    else:
        print(f"Path {path} does not exist")

    zk.stop()

except ImportError:
    print("kazoo not installed. Install with: pip install kazoo")
except Exception as e:
    print(f"ZooKeeper query failed: {e}")

# Test 2: Try direct connection to HiveServer2 hosts
print("\n" + "-" * 70)
print("[2] Test direct connection to potential HiveServer2 hosts")
print("-" * 70)

# These are the ZK hosts - HS2 might be on same or different hosts
POTENTIAL_HS2_HOSTS = [
    ("lxmrwtsgv0m1.sg.uobnet.com", 10000),
    ("lxmrwtsgv0m2.sg.uobnet.com", 10000),
    ("lxmrwtsgv0w1.sg.uobnet.com", 10000),
]

import socket

for host, port in POTENTIAL_HS2_HOSTS:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        status = "OPEN" if result == 0 else f"CLOSED"
        print(f"  {host}:{port} -> {status}")
    except Exception as e:
        print(f"  {host}:{port} -> ERROR: {e}")

# Test 3: Try impyla with each potential host
print("\n" + "-" * 70)
print("[3] Test impyla connection to each host")
print("-" * 70)

try:
    from impala.dbapi import connect as impyla_connect

    for host, port in POTENTIAL_HS2_HOSTS:
        try:
            print(f"\nTrying {host}:{port}...")
            conn = impyla_connect(
                host=host,
                port=port,
                database='default',
                auth_mechanism='GSSAPI',
                kerberos_service_name='hive',
                use_ssl=False,
                timeout=30,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            print(f"  SUCCESS! Result: {result}")
            print(f"\n*** WORKING HOST FOUND: {host}:{port} ***")
            break
        except Exception as e:
            print(f"  Failed: {str(e)[:100]}")

except ImportError:
    print("impyla not installed")

# Test 4: Check if we can use pyhive with HTTP transport
print("\n" + "-" * 70)
print("[4] Test pyhive with different configurations")
print("-" * 70)

try:
    from pyhive import hive

    configs = [
        {"auth": "KERBEROS", "kerberos_service_name": "hive"},
        {"auth": "NONE"},
    ]

    for host, port in POTENTIAL_HS2_HOSTS[:1]:  # Just test first host
        for config in configs:
            try:
                print(f"\nTrying {host}:{port} with {config}...")
                conn = hive.Connection(
                    host=host,
                    port=port,
                    database='default',
                    **config
                )
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                print(f"  SUCCESS! Result: {result}")
                break
            except Exception as e:
                print(f"  Failed: {str(e)[:100]}")

except ImportError:
    print("pyhive not installed")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("""
NEXT STEPS:
1. If ZooKeeper query works, we can discover HS2 dynamically
2. If direct connection works, we can skip ZooKeeper
3. Install kazoo for ZooKeeper: pip install kazoo
""")
