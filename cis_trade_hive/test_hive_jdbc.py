#!/usr/bin/env python3
"""
Hive JDBC Connection Test for CML

Uses JayDeBeApi to connect via JDBC - same method as beeline/DataViz.
This uses ZooKeeper for service discovery.

Prerequisites:
    pip install JayDeBeApi JPype1

Run: python test_hive_jdbc.py
"""
import os
import sys
import subprocess

print("=" * 70)
print("HIVE JDBC CONNECTION TEST (via ZooKeeper)")
print("=" * 70)

# Check Kerberos
result = subprocess.run(["klist"], capture_output=True, text=True)
if result.returncode != 0:
    print("ERROR: No Kerberos ticket. Run kinit first!")
    sys.exit(1)
print("Kerberos ticket: OK\n")

# JDBC Connection parameters (from working beeline)
ZOOKEEPER_HOSTS = "lxmrwtsgv0m1.sg.uobnet.com:2181,lxmrwtsgv0m2.sg.uobnet.com:2181,lxmrwtsgv0w1.sg.uobnet.com:2181"
DATABASE = "default"
PRINCIPAL = "hive/_HOST@TST.UOBNET.COM"
ZOOKEEPER_NAMESPACE = "hiveserver2"
TRUSTSTORE_PATH = "/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks"

# Build JDBC URL (matching beeline)
JDBC_URL = (
    f"jdbc:hive2://{ZOOKEEPER_HOSTS}/{DATABASE};"
    f"principal={PRINCIPAL};"
    f"serviceDiscoveryMode=zooKeeper;"
    f"zookeeperNamespace={ZOOKEEPER_NAMESPACE};"
    f"ssl=true;"
    f"sslTrustStore={TRUSTSTORE_PATH};"
    f"trustStoreType=jks"
)

print(f"JDBC URL:\n{JDBC_URL}\n")

# Find Hive JDBC driver
HIVE_JDBC_PATHS = [
    "/opt/cloudera/parcels/CDH/jars/hive-jdbc-*.jar",
    "/opt/cloudera/parcels/CDH/lib/hive/lib/hive-jdbc-*.jar",
    "/app/cloudera/parcels/CDH/jars/hive-jdbc-*.jar",
    "/usr/lib/hive/lib/hive-jdbc-*.jar",
]

import glob
jdbc_driver = None
for pattern in HIVE_JDBC_PATHS:
    matches = glob.glob(pattern)
    if matches:
        jdbc_driver = matches[0]
        break

if not jdbc_driver:
    print("Searching for Hive JDBC driver...")
    result = subprocess.run(
        ["find", "/opt", "/app", "/usr", "-name", "hive-jdbc-*.jar", "-type", "f"],
        capture_output=True, text=True, timeout=30
    )
    if result.stdout.strip():
        jdbc_driver = result.stdout.strip().split('\n')[0]

if jdbc_driver:
    print(f"Found JDBC driver: {jdbc_driver}")
else:
    print("ERROR: Hive JDBC driver not found!")
    print("Looking for any hive jars...")
    result = subprocess.run(
        ["find", "/opt", "/app", "-name", "hive*.jar", "-type", "f"],
        capture_output=True, text=True, timeout=30
    )
    print(result.stdout[:2000] if result.stdout else "No jars found")
    sys.exit(1)

# Test with JayDeBeApi
print("\n" + "-" * 70)
print("Testing JDBC connection with JayDeBeApi...")
print("-" * 70)

try:
    import jaydebeapi
    import jpype

    # Get all required JARs
    jar_dir = os.path.dirname(jdbc_driver)
    required_jars = glob.glob(os.path.join(jar_dir, "*.jar"))

    # Start JVM if not already started
    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=required_jars)

    # Connect
    conn = jaydebeapi.connect(
        "org.apache.hive.jdbc.HiveDriver",
        JDBC_URL,
        ["", ""],  # username, password (empty for Kerberos)
        jdbc_driver
    )

    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    print(f"SUCCESS! Result: {result}")

    # Try to show databases
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()
    print(f"\nDatabases: {[db[0] for db in databases[:10]]}")

    cursor.close()
    conn.close()

except ImportError as e:
    print(f"JayDeBeApi not installed: {e}")
    print("\nTo install:")
    print("  pip install JayDeBeApi JPype1")

except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
