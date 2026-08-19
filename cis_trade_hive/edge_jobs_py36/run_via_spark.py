"""
Generic spark-submit entrypoint for the edge_jobs_py36 scripts.

None of these jobs use Spark's distributed engine (no SparkContext RDDs/
DataFrames, no executor tasks) -- they're pure Python + Impala via impyla,
same as the rest of this package. This wrapper exists only so ops can
launch them as real YARN applications through spark3-submit (queue
accounting, `yarn logs` retrieval, cluster-wide job visibility in the
ResourceManager UI) instead of a bare `python3.6 <script>.py` process.

It creates a minimal SparkSession purely to register the YARN application,
then runs the target script's own `if __name__ == '__main__':` block
unchanged via runpy -- no business logic here, no duplication of any
job's add_arguments()/handle().

Usage:
    spark3-submit --master yarn --deploy-mode client \\
        run_via_spark.py sync_gmp_corporate_actions.py

    spark3-submit --master yarn --deploy-mode client \\
        run_via_spark.py process_approved_cashflows.py --run-type EOD

    spark3-submit --master yarn --deploy-mode client \\
        run_via_spark.py refresh_positions.py --run-type EOD
"""
import runpy
import sys


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('Usage: run_via_spark.py <script.py> [job-args...]\n')
        sys.exit(1)

    target = sys.argv[1]
    job_args = sys.argv[2:]

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName('cis_edge_job:{}'.format(target)).getOrCreate()

    # Target scripts parse sys.argv themselves (argparse via lib.management_base
    # or their own argparse setup) -- swap it so they only see their own args.
    sys.argv = [target] + job_args
    try:
        runpy.run_path(target, run_name='__main__')
    except SystemExit as e:
        if e.code not in (None, 0):
            raise
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
