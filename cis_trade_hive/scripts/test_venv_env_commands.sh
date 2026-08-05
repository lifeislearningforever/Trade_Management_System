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

ENV_DIR="/app/CISGW/cis_etl_env_11"
VENV_TAR="${ENV_DIR}/cis_etl_env_tar.gz"
CIS_UTIL_ZIP="${ENV_DIR}/cis_util.zip"
TEST_SCRIPT="test_venv_env.py"   # path to the script from this repo's scripts/ dir, copied onto the edge node

# Bare `spark-submit` on this edge node's PATH resolves to Spark 2 (deprecated
# warning seen on first test run) -- the real wrapper script explicitly uses
# /usr/bin/spark3-submit for exactly this reason. Override if that path is
# different on your node (e.g. `which spark3-submit`).
SPARK_SUBMIT_BIN="/usr/bin/spark3-submit"

# Absolute, edge-node-local path to the venv's python3.11 -- NOT the same as
# the relative ./myenv/bin/python3.11 used below for spark.pyspark.python.
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
# In client mode the driver runs LOCALLY on this edge node, not inside a
# YARN container -- --archives only auto-unpacks into container working
# directories, so the relative ./myenv/... path Spark resolves for
# executors doesn't exist for the driver process. driver.python must be
# the real local filesystem path instead; only spark.pyspark.python
# (the executors) uses the relative in-container path.
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
# Driver ALSO runs inside a YARN container in this mode, so it DOES see the
# relative ./myenv/... path correctly -- both driver.python and
# spark.pyspark.python use the same relative path here, unlike client mode.
# Nothing prints to this terminal either way -- capture the appId
# spark-submit reports, then pull logs with step2c.
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
        "${TEST_SCRIPT}"
}

# ---------------------------------------------------------------------------
# Step 2c: Fetch cluster-mode logs and filter to the lines that matter.
# Usage: step2c_fetch_logs application_1234567890_0001
# ---------------------------------------------------------------------------
step2c_fetch_logs() {
    local app_id="$1"
    yarn logs -applicationId "${app_id}" | grep -E "PYTHON_EXECUTABLE|PYTHON_VERSION|CIS_UTIL_IMPORT"
}

# Uncomment the step(s) you want to run, or call this script with the
# function name as $1, e.g.:  ./test_venv_env_commands.sh step2a_test_client_mode
if [[ -n "$1" ]]; then
    "$1"
fi
