"""
test_venv_env.py -- smoke test for the shipped Python 3.11 venv archive
(cis_etl_env_tar.gz) and cis_util.zip on --py-files, before pointing
spark-submit at the real cis_ingestion.py.

Checks BOTH the driver process and an actual executor task (the executor
always runs inside a real YARN container, so it's the only reliable proof
the shipped venv -- not the edge node's own Python -- is what's in use).

Usage (run from the edge node, deploy-mode client for fastest iteration --
driver output prints straight to your terminal):

    spark-submit \\
        --master yarn \\
        --deploy-mode client \\
        --archives /app/CISGW/cis_etl_env_11/cis_etl_env_tar.gz#myenv \\
        --py-files /app/CISGW/cis_etl_env_11/cis_util.zip \\
        --conf spark.pyspark.python=./myenv/bin/python3.11 \\
        --conf spark.pyspark.driver.python=./myenv/bin/python3.11 \\
        test_venv_env.py

Once that passes, re-run with --deploy-mode cluster to match how the real
job is submitted -- in cluster mode the driver ALSO runs inside a YARN
container, so this print output won't reach your terminal; fetch it via:

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
