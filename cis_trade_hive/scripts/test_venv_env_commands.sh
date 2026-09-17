#!/bin/bash
# test_venv_env_commands.sh
#
# Reference commands for packaging the Python 3.11 venv + testing it via
# spark-submit, before wiring the real cis_ingestion_wrapper.sh to use it.
# Not meant to be run unattended top-to-bottom -- copy/paste the section
# you need, or run this whole file one step at a time.
#
# Layout assumed:
#   /app/CISGW/cis_etl_env_11/myenv            <- python3.11 venv (pip installs live here)
#   /app/CISGW/cis_etl_env_11/cis_etl_env_tar.gz  <- packaged venv, built by step 1
#   /app/CISGW/cis_etl_env_11/cis_util.zip      <- shared project code, shipped via --py-files
#   /app/CISGW/cis_etl_env_11/python_libs.tgz   <- TBD role, not yet wired in below
#
# IMPORTANT: myenv must be created with `python3.11 -m venv --copies myenv`,
# NOT the default (symlink) mode. A default venv's bin/python3.11 is a
# symlink to /usr/bin/python3.11 -- not relocatable once shipped and unpacked
# inside a YARN container on a different machine (confirmed: produced
# "error=20, Not a directory" in cluster mode). --copies makes bin/python3.11
# a real, self-contained binary, so the whole venv travels correctly via
# --archives and we can use ./myenv/bin/python3.11 directly everywhere --
# no PYTHONPATH injection, no risk of the venv's packages shadowing the
# cluster's own pyspark/py4j.

# Bump this filename (or set VENV_TAR_NAME in the environment before calling
# this script) whenever the archive's CONTENTS change but you suspect YARN's
# NodeManager local cache isn't picking up the new file under the old name --
# identical byte-for-byte errors persisting across otherwise-substantive
# venv rebuilds is the tell. YARN keys its cache off the resource's
# name/size/timestamp; reusing a filename across many iterations is the
# single most common cause of "my fix didn't change anything" with --archives.
VENV_TAR_NAME="${VENV_TAR_NAME:-cis_etl_env_tar.gz}"

ENV_DIR="/app/CISGW/cis_etl_env_11"
VENV_TAR="${ENV_DIR}/${VENV_TAR_NAME}"
CIS_UTIL_ZIP="${ENV_DIR}/cis_util.zip"
TEST_SCRIPT="test_venv_env.py"   # path to the script from this repo's scripts/ dir, copied onto the edge node

# Bare `spark-submit` on this edge node's PATH resolves to Spark 2 (deprecated
# warning seen on first test run) -- the real wrapper script explicitly uses
# /usr/bin/spark3-submit for exactly this reason. Override if that path is
# different on your node (e.g. `which spark3-submit`).
SPARK_SUBMIT_BIN="/usr/bin/spark3-submit"

# Absolute, edge-node-local path to the venv's python3.11 -- used only for
# the client-mode driver, which runs locally and never goes through
# --archives unpacking at all.
DRIVER_PYTHON_LOCAL="${ENV_DIR}/myenv/bin/python3.11"

# ---------------------------------------------------------------------------
# Step 1: Package the venv into a tarball (run once, and again whenever the
# venv's installed packages change). Tar from INSIDE myenv/ -- not the
# myenv folder itself -- so there's no double-nesting once Spark's
# --archives unpacks it under the #myenv alias.
# ---------------------------------------------------------------------------
step1_package_venv() {
    cd "${ENV_DIR}/myenv" || exit 1
    tar -czf "${VENV_TAR}" .
    echo "Wrote ${VENV_TAR}"
}

# ---------------------------------------------------------------------------
# Step 2a: Smoke test in client mode -- fastest iteration, driver output
# prints straight to this terminal.
#
# Driver: runs LOCALLY on this edge node, uses the venv's real local path.
# Executors: run inside YARN containers -- now safe to use the relative
# ./myenv/... path since the --copies venv is self-contained/relocatable.
# ---------------------------------------------------------------------------
step2a_test_client_mode() {
    "${SPARK_SUBMIT_BIN}" \
        --master yarn \
        --deploy-mode client \
        --archives "${VENV_TAR}#myenv" \
        --py-files "${CIS_UTIL_ZIP}" \
        --conf spark.pyspark.python=./myenv/bin/python3.11 \
        --conf spark.pyspark.driver.python="${DRIVER_PYTHON_LOCAL}" \
        "${TEST_SCRIPT}"
}

# ---------------------------------------------------------------------------
# Step 2b: Smoke test in cluster mode -- matches how the real ETL job is
# submitted (see submitSparkNativeClientJob in cis_ingestion_wrapper.sh).
#
# Driver (AM) AND executors both run inside YARN containers here. Set both
# spark.pyspark.python/driver.python (works on some Spark versions) AND the
# spark.yarn.appMasterEnv.*/spark.executorEnv.* equivalents (the reliable
# mechanism for the AM container specifically) -- all pointing at the same
# relative in-archive path, now safe since the venv is self-contained.
# ---------------------------------------------------------------------------
step2b_test_cluster_mode() {
    "${SPARK_SUBMIT_BIN}" \
        --master yarn \
        --deploy-mode cluster \
        --queue EOD_Queue \
        --archives "${VENV_TAR}#myenv" \
        --py-files "${CIS_UTIL_ZIP}" \
        --conf spark.pyspark.python=./myenv/bin/python3.11 \
        --conf spark.pyspark.driver.python=./myenv/bin/python3.11 \
        --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./myenv/bin/python3.11 \
        --conf spark.executorEnv.PYSPARK_PYTHON=./myenv/bin/python3.11 \
        "${TEST_SCRIPT}"
}

# ---------------------------------------------------------------------------
# Step 2c: Fetch cluster-mode logs and filter to the lines that matter.
# Usage: step2c_fetch_logs application_1234567890_0001
# ---------------------------------------------------------------------------
step2c_fetch_logs() {
    local app_id="$1"
    yarn logs -applicationId "${app_id}" | grep -E "PYTHON_EXECUTABLE|PYTHON_VERSION|CIS_UTIL_IMPORT|RUAMEL_YAML_IMPORT"
}

# Uncomment the step(s) you want to run, or call this script with the
# function name as $1, e.g.:  ./test_venv_env_commands.sh step2a_test_client_mode
if [[ -n "$1" ]]; then
    "$1"
fi
