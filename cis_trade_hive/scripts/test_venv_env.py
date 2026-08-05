"""
test_venv_env.py -- smoke test for the shipped Python 3.11 venv archive
(cis_etl_env_tar.gz) and cis_util.zip on --py-files, before pointing
spark-submit at the real cis_ingestion.py.

Checks BOTH the driver process and an actual executor task (the executor
always runs inside a real YARN container, so it's the only reliable proof
the shipped venv -- not the edge node's own Python -- is what's in use).

Usage: see test_venv_env_commands.sh (step2a_test_client_mode /
step2b_test_cluster_mode) for the actual spark-submit invocation -- it now
points PYSPARK_PYTHON at the cluster's system python3.11 rather than the
venv's own (non-relocatable symlink) bin/python3.11, and adds the shipped
archive's site-packages to PYTHONPATH instead.

In cluster mode the driver ALSO runs inside a YARN container, so this print
output won't reach your terminal; fetch it via:

    yarn application -list -appStates RUNNING   # find the appId
    yarn logs -applicationId <appId>            # after it finishes
"""
import sys
import platform


def report(where):
    lines = [
        f"[{where}] PYTHON_EXECUTABLE={sys.executable}",
        f"[{where}] PYTHON_VERSION={platform.python_version()}",
    ]
    try:
        import cis_util
        lines.append(f"[{where}] CIS_UTIL_IMPORT=OK file={getattr(cis_util, '__file__', '?')}")
    except ImportError as e:
        lines.append(f"[{where}] CIS_UTIL_IMPORT=FAILED {e}")
    # ruamel.yaml is installed in the venv's site-packages (confirmed via the
    # tar listing) but is NOT part of the Python 3.11 stdlib and is NOT
    # shipped via --py-files -- so this only succeeds if PYTHONPATH is
    # correctly pointing at the shipped archive's site-packages, actually
    # validating the fix rather than just re-checking --py-files.
    try:
        import ruamel.yaml
        lines.append(f"[{where}] RUAMEL_YAML_IMPORT=OK file={getattr(ruamel.yaml, '__file__', '?')}")
    except ImportError as e:
        lines.append(f"[{where}] RUAMEL_YAML_IMPORT=FAILED {e}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Driver-side check (this process itself -- in client mode this is the
    # edge node's shell process using whatever spark.pyspark.driver.python
    # resolved to; in cluster mode it's a YARN container, same as executors).
    print(report("DRIVER"))

    # Executor-side check -- runs as a distributed task inside real YARN
    # containers on worker nodes, the only unambiguous proof the shipped
    # archive (not some pre-existing node-local Python) is what's running.
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName("venv_smoke_test").getOrCreate()
    sc = spark.sparkContext
    results = sc.parallelize(range(4), 4).map(lambda _: report("EXECUTOR")).collect()
    for r in results:
        print(r)
    spark.stop()
