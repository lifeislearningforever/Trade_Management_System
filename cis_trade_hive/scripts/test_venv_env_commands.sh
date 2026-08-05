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
# IMPORTANT: myenv/bin/python3.11 is a symlink to /usr/bin/python3.11 (confirmed
# via `ls -la myenv/bin/` on the edge node -- this is normal for any
# `python3.11 -m venv`, which never bundles the interpreter itself). That
# symlink is NOT relocatable: once the archive is shipped and unpacked inside
# a YARN container on a different machine, it still points at the fixed
# edge-node path /usr/bin/python3.11, which produced "error=20, Not a
# directory" in cluster mode. Fix: don't ship/use the venv's own bin/python3.11
# at all -- use the WORKER NODE's own /usr/bin/python3.11 (installed
# identically cluster-wide per the original ask) as PYSPARK_PYTHON, and only
# ship the venv's installed packages (lib/python3.11/site-packages) via
# --archives, added to PYTHONPATH so the system interpreter can import them.

ENV_DIR="/app/CISGW/cis_etl_env_11"
VENV_TAR="${ENV_DIR}/cis_etl_env_tar.gz"
CIS_UTIL_ZIP="${ENV_DIR}/cis_util.zip"
TEST_SCRIPT="test_venv_env.py"   # path to the script from this repo's scripts/ dir, copied onto the edge node

# Bare `spark-submit` on this edge node's PATH resolves to Spark 2 (deprecated
# warning seen on first test run) -- the real wrapper script explicitly uses
# /usr/bin/spark3-submit for exactly this reason. Override if that path is
# different on your node (e.g. `which spark3-submit`).
SPARK_SUBMIT_BIN="/usr/bin/spark3-submit"

# The interpreter every process uses now -- system python3.11, present at this
# same absolute path on every node (edge + all YARN workers), NOT the venv's
# own (non-relocatable) bin/python3.11 symlink.
SYSTEM_PYTHON="/usr/bin/python3.11"

# In-container relative path to the shipped venv's installed packages, once
# --archives unpacks cis_etl_env_tar.gz under the #myenv alias. Used for
# executors (both deploy modes) and the AM/driver in cluster mode -- the
# client-mode driver needs no equivalent since it runs locally and picks up
# myenv's site-packages automatically via myenv/bin/python3.11's own
# pyvenv.cfg.
SITE_PACKAGES_REL="./myenv/lib/python3.11/site-packages"

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
# Driver: runs LOCALLY on this edge node (client mode), so it uses the venv's
# real local python directly -- no relocation involved. Already confirmed
# working: invoking myenv/bin/python3.11 directly picks up myenv's
# site-packages automatically via the adjacent pyvenv.cfg, regardless of the
# interpreter itself being a symlink -- no explicit PYTHONPATH needed here.
# Executors: ALWAYS run inside YARN containers regardless of deploy mode, so
# they hit the same non-relocatable-symlink problem cluster mode did -- use
# system python3.11 + PYTHONPATH pointed at the shipped archive's
# site-packages instead of the archive's own (broken) bin/python3.11.
# ---------------------------------------------------------------------------
step2a_test_client_mode() {
    "${SPARK_SUBMIT_BIN}" \
        --master yarn \
        --deploy-mode client \
        --archives "${VENV_TAR}#myenv" \
        --py-files "${CIS_UTIL_ZIP}" \
        --conf spark.pyspark.driver.python="${ENV_DIR}/myenv/bin/python3.11" \
        --conf spark.executorEnv.PYSPARK_PYTHON="${SYSTEM_PYTHON}" \
        --conf spark.executorEnv.PYTHONPATH="${SITE_PACKAGES_REL}" \
        "${TEST_SCRIPT}"
}

# ---------------------------------------------------------------------------
# Step 2b: Smoke test in cluster mode -- matches how the real ETL job is
# submitted (see submitSparkNativeClientJob in cis_ingestion_wrapper.sh).
#
# Driver (AM) AND executors both run inside YARN containers here, so BOTH
# need system python3.11 + PYTHONPATH pointed at the shipped site-packages,
# via spark.yarn.appMasterEnv.* (driver/AM) and spark.executorEnv.* (executors)
# -- spark.pyspark.driver.python does not reliably control the AM container's
# environment (see comment history in git log for this file).
# ---------------------------------------------------------------------------
step2b_test_cluster_mode() {
    "${SPARK_SUBMIT_BIN}" \
        --master yarn \
        --deploy-mode cluster \
        --queue EOD_Queue \
        --archives "${VENV_TAR}#myenv" \
        --py-files "${CIS_UTIL_ZIP}" \
        --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON="${SYSTEM_PYTHON}" \
        --conf spark.yarn.appMasterEnv.PYTHONPATH="${SITE_PACKAGES_REL}" \
        --conf spark.executorEnv.PYSPARK_PYTHON="${SYSTEM_PYTHON}" \
        --conf spark.executorEnv.PYTHONPATH="${SITE_PACKAGES_REL}" \
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
