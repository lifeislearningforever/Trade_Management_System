#!/usr/bin/env python3
"""
Hive Connection Test using Beeline (subprocess)

Since JDBC via JayDeBeApi has JPype issues, this uses beeline directly
via subprocess - the same tool that works in your terminal.

Run: python test_hive_beeline.py
"""
import os
import sys
import subprocess
import shlex

print("=" * 70)
print("HIVE BEELINE CONNECTION TEST")
print("=" * 70)

# Check Kerberos
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("ERROR: No Kerberos ticket. Run kinit first!")
    sys.exit(1)
print("Kerberos ticket: OK\n")

# JDBC URL (from working beeline)
JDBC_URL = (
    "jdbc:hive2://lxmrwtsgv0m1.sg.uobnet.com:2181,"
    "lxmrwtsgv0m2.sg.uobnet.com:2181,"
    "lxmrwtsgv0w1.sg.uobnet.com:2181/default;"
    "principal=hive/_HOST@TST.UOBNET.COM;"
    "serviceDiscoveryMode=zooKeeper;"
    "zookeeperNamespace=hiveserver2;"
    "ssl=true;"
    "sslTrustStore=/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks;"
    "trustStoreType=jks"
)

print(f"JDBC URL: {JDBC_URL[:80]}...\n")

def run_beeline_query(query, timeout=60):
    """Run a query via beeline and return results."""
    cmd = [
        "beeline",
        "-u", JDBC_URL,
        "-e", query,
        "--silent=true",
        "--outputformat=csv2"
    ]

    print(f"Running: {query}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Query timed out"
    except Exception as e:
        return False, str(e)

# Test 1: Simple SELECT
print("-" * 70)
print("[1] Test: SELECT 1")
print("-" * 70)
success, output = run_beeline_query("SELECT 1")
if success:
    print(f"SUCCESS!\n{output}")
else:
    print(f"FAILED: {output}")

# Test 2: Show databases
print("\n" + "-" * 70)
print("[2] Test: SHOW DATABASES")
print("-" * 70)
success, output = run_beeline_query("SHOW DATABASES")
if success:
    print(f"SUCCESS!\n{output[:500]}")
else:
    print(f"FAILED: {output}")

# Test 3: Use mrw_ima database
print("\n" + "-" * 70)
print("[3] Test: USE mrw_ima; SHOW TABLES")
print("-" * 70)
success, output = run_beeline_query("USE mrw_ima; SHOW TABLES")
if success:
    print(f"SUCCESS!\n{output[:500]}")
else:
    print(f"FAILED: {output}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)

print("""
If beeline works, we can use it in Python via subprocess for Hive writes.
This avoids JDBC/JVM complexities while still using the same connection method.

Next: We'll create a HiveBeelineExecutor class to wrap this.
""")
