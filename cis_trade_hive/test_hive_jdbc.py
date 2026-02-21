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

# Cloudera CDH JAR directory
CDH_JAR_DIR = "/app/cloudera/parcels/CDH/jars"

import glob

# Find specific Hive JDBC driver
jdbc_pattern = os.path.join(CDH_JAR_DIR, "hive-jdbc-3.1.3000*.jar")
jdbc_matches = glob.glob(jdbc_pattern)

if jdbc_matches:
    # Use the standalone jar if available, otherwise regular
    standalone = [j for j in jdbc_matches if 'standalone' in j]
    jdbc_driver = standalone[0] if standalone else jdbc_matches[0]
    print(f"Found JDBC driver: {jdbc_driver}")
else:
    print(f"ERROR: Hive JDBC driver not found in {CDH_JAR_DIR}")
    sys.exit(1)

# Test with JayDeBeApi
print("\n" + "-" * 70)
print("Testing JDBC connection with JayDeBeApi...")
print("-" * 70)

try:
    import jaydebeapi
    import jpype

    # Get all required JARs from CDH directory
    all_jars = glob.glob(os.path.join(CDH_JAR_DIR, "*.jar"))
    print(f"Loading {len(all_jars)} JARs from {CDH_JAR_DIR}")

    # Start JVM if not already started
    if not jpype.isJVMStarted():
        # Auto-detect JAVA_HOME
        java_home = os.environ.get('JAVA_HOME')

        if not java_home:
            # Try to find from readlink
            result = subprocess.run(["readlink", "-f", "/usr/bin/java"],
                                   capture_output=True, text=True)
            if result.returncode == 0:
                java_bin = result.stdout.strip()  # e.g., /usr/lib/jvm/.../jre/bin/java
                # Go up from bin/java to get JAVA_HOME
                if '/jre/bin/java' in java_bin:
                    java_home = java_bin.replace('/jre/bin/java', '')
                elif '/bin/java' in java_bin:
                    java_home = java_bin.replace('/bin/java', '')

        if not java_home:
            # Fallback paths
            for path in [
                '/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.462.b08-2.el8.x86_64',
                '/usr/lib/jvm/java-11-openjdk',
                '/usr/lib/jvm/java-1.8.0-openjdk',
            ]:
                if os.path.exists(path):
                    java_home = path
                    break

        os.environ['JAVA_HOME'] = java_home
        print(f"JAVA_HOME: {java_home}")

        # Find libjvm.so
        jvm_path = None
        for pattern in [
            f"{java_home}/jre/lib/amd64/server/libjvm.so",
            f"{java_home}/lib/server/libjvm.so",
            f"{java_home}/jre/lib/server/libjvm.so",
        ]:
            if os.path.exists(pattern):
                jvm_path = pattern
                break

        if not jvm_path:
            jvm_path = jpype.getDefaultJVMPath()

        print(f"JVM path: {jvm_path}")
        jpype.startJVM(jvm_path, classpath=all_jars, convertStrings=True)

    print("JVM started successfully")

    # Connect using Kerberos (no username/password needed)
    print(f"\nConnecting to Hive...")
    conn = jaydebeapi.connect(
        "org.apache.hive.jdbc.HiveDriver",
        JDBC_URL,
        ["", ""],  # empty for Kerberos auth
        jdbc_driver
    )
    print("Connected!")

    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    print(f"SUCCESS! SELECT 1 = {result}")

    # Try to show databases
    print("\nListing databases...")
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()
    print(f"Databases: {[db[0] for db in databases[:10]]}")

    cursor.close()
    conn.close()
    print("\nConnection closed successfully")

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
