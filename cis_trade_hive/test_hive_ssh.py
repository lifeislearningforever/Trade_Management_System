#!/usr/bin/env python3
"""
Test Hive SSH Executor for CML

Since CML doesn't have beeline and pure-sasl doesn't support GSSAPI,
we use SSH to execute beeline on an edge node.

Prerequisites:
1. SSH key-based auth to edge node, OR
2. Set HIVE_SSH_HOST, HIVE_SSH_USER environment variables

Run: python test_hive_ssh.py
"""
import os
import sys

os.environ['CIS_ENV'] = 'work'

# Configure SSH - update these for your environment
os.environ.setdefault('HIVE_SSH_HOST', 'lxmrwtsgv0w1.sg.uobnet.com')
# os.environ.setdefault('HIVE_SSH_USER', 'your_username')  # Defaults to current user
# os.environ.setdefault('HIVE_SSH_KEY', '/path/to/private/key')  # Optional

print("=" * 70)
print("HIVE SSH EXECUTOR TEST")
print("=" * 70)

print(f"\nSSH Host: {os.environ.get('HIVE_SSH_HOST')}")
print(f"SSH User: {os.environ.get('HIVE_SSH_USER', '(current user)')}")

# Test 1: SSH connection
print("\n" + "-" * 70)
print("[1] Test SSH Connection")
print("-" * 70)

import subprocess
import getpass

ssh_host = os.environ.get('HIVE_SSH_HOST', 'lxmrwtsgv0w1.sg.uobnet.com')
ssh_user = os.environ.get('HIVE_SSH_USER', getpass.getuser())

cmd = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    f"{ssh_user}@{ssh_host}",
    "whoami && hostname"
]

print(f"Testing: ssh {ssh_user}@{ssh_host}")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

if result.returncode == 0:
    print(f"SSH OK: {result.stdout.strip()}")
else:
    print(f"SSH FAILED: {result.stderr}")
    print("\nTo fix SSH access:")
    print("1. Ensure SSH keys are set up (ssh-keygen, ssh-copy-id)")
    print("2. Or set HIVE_SSH_KEY to your private key path")
    print("3. Verify you can SSH manually: ssh {ssh_user}@{ssh_host}")
    sys.exit(1)

# Test 2: Beeline via SSH
print("\n" + "-" * 70)
print("[2] Test Beeline via SSH")
print("-" * 70)

try:
    from core.repositories.hive_ssh_executor import hive_ssh_executor

    print("Testing Hive connection via SSH...")
    success = hive_ssh_executor.test_connection()

    if success:
        print("\nHive SSH Executor: WORKING!")

        # Test query
        print("\n" + "-" * 70)
        print("[3] Test Query")
        print("-" * 70)

        success, results = hive_ssh_executor.execute_query("SHOW DATABASES")
        if success:
            print(f"Databases: {[r.get('database_name', r) for r in results[:10]]}")
        else:
            print("Query failed")

    else:
        print("\nHive SSH Executor: FAILED")
        print("Check that beeline works on the edge node")

except ImportError as e:
    print(f"Import error: {e}")
    print("\nRunning without Django...")

    # Manual test without Django
    jdbc_url = (
        "jdbc:hive2://lxmrwtsgv0m1.sg.uobnet.com:2181,"
        "lxmrwtsgv0m2.sg.uobnet.com:2181,"
        "lxmrwtsgv0w1.sg.uobnet.com:2181/mrw_ima;"
        "principal=hive/_HOST@TST.UOBNET.COM;"
        "serviceDiscoveryMode=zooKeeper;"
        "zookeeperNamespace=hiveserver2;"
        "ssl=true;"
        "sslTrustStore=/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks;"
        "trustStoreType=jks"
    )

    beeline_cmd = f'beeline -u "{jdbc_url}" -e "SELECT 1" --silent=true'

    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        f"{ssh_user}@{ssh_host}",
        beeline_cmd
    ]

    print(f"\nRunning beeline via SSH...")
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120)

    if result.returncode == 0:
        print(f"SUCCESS! Output: {result.stdout[:200]}")
    else:
        print(f"FAILED: {result.stderr[:200]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
