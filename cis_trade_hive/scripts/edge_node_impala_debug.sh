#!/bin/bash
#===============================================================================
# Edge Node Impala/Kerberos/SASL Debug
#===============================================================================
# Consolidates every diagnostic check used while debugging
#   "Could not start SASL: None of the mechanisms listed meet all
#    required properties"
# when running edge_jobs_py36/*.py against a GSSAPI-secured Impala cluster
# (SIT/UAT/PROD/DR) from a Kerberized edge node.
#
# Run this from inside the activated venv, from the edge_jobs_py36/
# directory (or pass a different one via EDGE_JOBS_DIR):
#
#   source /app/CISGW/cis_etl_env3.6/bin/activate
#   cd edge_jobs_py36
#   ../scripts/edge_node_impala_debug.sh 2>&1 | tee /tmp/edge_impala_debug_$(date +%Y%m%d_%H%M%S).log
#
# Each section prints what it found -- read top to bottom, the first
# non-OK result is almost always the actual root cause; later sections
# often fail as a downstream consequence of an earlier one.
#
# Author: CIS Trade Hive Team
# Version: 1.0
# Date: 2026-08-11
#===============================================================================

EDGE_JOBS_DIR="${EDGE_JOBS_DIR:-$(pwd)}"

section() {
    echo ""
    echo "==============================================================="
    echo "  $1"
    echo "==============================================================="
}

#-------------------------------------------------------------------------------
section "0. Which Python will this script actually use?"
#-------------------------------------------------------------------------------
# A hardcoded 'python3.6' default here previously caused every downstream
# check to silently run against the SYSTEM /usr/bin/python3.6 instead of
# the activated venv, whenever the venv doesn't provide a binary literally
# named python3.6 (e.g. a venv built from a python3.8 base, as this one
# turned out to be) -- 'which python3.6' falls straight through PATH to
# the system copy in that case, with no error to signal it happened.
# Prefer $VIRTUAL_ENV/bin/python explicitly when a venv is active, since
# that's unambiguous regardless of what's named what.

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PY="${VIRTUAL_ENV}/bin/python"
    echo "VIRTUAL_ENV is active: ${VIRTUAL_ENV}"
    echo "Using PY = ${PY}  (explicit \$VIRTUAL_ENV/bin/python)"
else
    PY="${PY:-python}"
    echo "WARNING: VIRTUAL_ENV is not set -- no venv appears to be activated"
    echo "  in this shell. If you meant to test inside one, activate it first:"
    echo "    source /app/CISGW/cis_etl_env3.6/bin/activate"
    echo "Using PY = ${PY}  (resolved via PATH: $(command -v "${PY}" 2>&1))"
fi

"${PY}" -c "import sys; print('Actual interpreter in use: sys.executable =', sys.executable); print('Version:', sys.version)"

echo ""
echo "If sys.executable above does NOT point inside the venv you expect"
echo "(e.g. it says /usr/bin/python3.x instead of something under"
echo "/app/CISGW/.../bin/), every section below will report false failures"
echo "-- fix the venv activation before trusting anything past this point."

#-------------------------------------------------------------------------------
section "1. CIS_ENV / IMPALA_* environment variables"
#-------------------------------------------------------------------------------
# environments.py's LOCAL fallback branch hardcodes KERBEROS_SERVICE_NAME=None
# and USE_SSL=False -- if CIS_ENV isn't exactly SIT/UAT/PROD/DR, GSSAPI auth
# is broken regardless of what else is set. Confirmed NOT the issue in this
# specific investigation (CIS_ENV=SIT was already verified in the app log),
# but check first every time -- it's the cheapest possible check.

echo "CIS_ENV            = ${CIS_ENV:-<unset>}"
echo "IMPALA_HOST         = ${IMPALA_HOST:-<unset>}"
echo "IMPALA_PORT         = ${IMPALA_PORT:-<unset>}"
echo "IMPALA_AUTH         = ${IMPALA_AUTH:-<unset>}"
echo "IMPALA_USE_SSL      = ${IMPALA_USE_SSL:-<unset>}"
echo "IMPALA_KRB_SERVICE_NAME = ${IMPALA_KRB_SERVICE_NAME:-<unset>}"
echo "KRB_SERVICE_NAME    = ${KRB_SERVICE_NAME:-<unset>}"
echo "KRB5CCNAME          = ${KRB5CCNAME:-<unset, defaults to /tmp/krb5cc_\$UID>}"

if [[ -z "${CIS_ENV}" ]]; then
    echo "  WARNING: CIS_ENV is not set -- will fall through to the LOCAL"
    echo "  config branch (no Kerberos), even if IMPALA_AUTH=GSSAPI."
fi

#-------------------------------------------------------------------------------
section "2. Kerberos ticket (klist)"
#-------------------------------------------------------------------------------
# "Could not start SASL: None of the mechanisms listed meet all required
# properties" is the classic symptom of no valid TGT in the ccache at
# connect time. Check the ticket is present AND not expired AND its cache
# path matches KRB5CCNAME if that's set.

klist 2>&1

#-------------------------------------------------------------------------------
section "3. Python / venv identity"
#-------------------------------------------------------------------------------
# Confirms which interpreter is actually active -- venvs can be misleadingly
# named (e.g. a venv called cis_etl_env3.6 that actually contains Python 3.8).

which "${PY}"
"${PY}" --version 2>&1
"${PY}" -c "import sys; print('sys.executable =', sys.executable)"

#-------------------------------------------------------------------------------
section "4. SASL Python packages"
#-------------------------------------------------------------------------------
# import succeeding here only proves the Python wrapper loaded and linked
# against libsasl2.so -- it does NOT prove the GSSAPI plugin for that
# library is installed at the OS level (see section 5).

"${PY}" -c "import sasl; print('sasl: importable, version =', getattr(sasl, '__version__', 'unknown'))" 2>&1
"${PY}" -c "import puresasl; print('puresasl: importable')" 2>&1
"${PY}" -m pip show thrift-sasl 2>&1
"${PY}" -m pip show pure-sasl 2>&1
"${PY}" -m pip show impyla 2>&1

echo ""
echo "-- Which backend will thrift_sasl actually use? --"
"${PY}" -c "
try:
    import sasl
    print('thrift_sasl will use: sasl (C extension) -- needs the OS-level')
    print('  cyrus-sasl-gssapi package for GSSAPI specifically (see section 5)')
except ImportError:
    import puresasl
    print('thrift_sasl will use: puresasl -- needs python kerberos/gssapi bindings')
"

#-------------------------------------------------------------------------------
section "5. System-level Cyrus SASL GSSAPI plugin"
#-------------------------------------------------------------------------------
# The actual, most likely root cause given sections 2-4 all check out:
# Cyrus SASL loads mechanism plugins (GSSAPI, PLAIN, etc.) as separate
# shared objects at RUNTIME from this directory, independent of whether
# the Python 'sasl' package imported successfully.

echo "-- /usr/lib64/sasl2/ contents --"
ls -la /usr/lib64/sasl2/ 2>&1

echo ""
echo "-- Looking specifically for a GSSAPI plugin --"
ls /usr/lib64/sasl2/ 2>/dev/null | grep -i gssapi || echo "  NOT FOUND -- no libgssapiv2.so or similar in /usr/lib64/sasl2/"

echo ""
echo "-- Installed cyrus-sasl RPMs --"
rpm -qa 2>/dev/null | grep -i cyrus-sasl || echo "  No cyrus-sasl* packages found via rpm -qa"

echo ""
echo "If 'cyrus-sasl-gssapi' is missing from the list above, that is almost"
echo "certainly the fix: yum install cyrus-sasl-gssapi (needs root/sudo --"
echo "loop in infra/sysadmin if this account doesn't have it)."

#-------------------------------------------------------------------------------
section "6. Live Impala connection test (via edge_jobs_py36/lib)"
#-------------------------------------------------------------------------------
# Exercises the exact same code path the failing job uses -- lib/config.py's
# settings resolution + lib/impala_connection.py's connect logic -- so this
# reproduces (or resolves) the original error directly, isolated from the
# rest of the ETL script's business logic.

if [[ ! -d "${EDGE_JOBS_DIR}/lib" ]]; then
    echo "  SKIPPED -- lib/ not found under ${EDGE_JOBS_DIR}"
    echo "  Set EDGE_JOBS_DIR to the edge_jobs_py36 directory, or cd into it first."
else
    "${PY}" - <<PYEOF
import sys, os
sys.path.insert(0, "${EDGE_JOBS_DIR}")
from lib.config import settings
print("Resolved IMPALA_CONFIG:", settings.IMPALA_CONFIG)

from lib.impala_connection import impala_manager
print("Attempting test_connection() ...")
ok = impala_manager.test_connection()
print("RESULT:", "CONNECTED OK" if ok else "FAILED -- see [ERROR] lines above from impala_connection's own logging")
PYEOF
fi

echo ""
echo "==============================================================="
echo "  Debug run complete. Share the full output (or the tee'd log"
echo "  file) -- the first non-OK/WARNING/missing item from the top"
echo "  is almost always the actual root cause."
echo "==============================================================="
