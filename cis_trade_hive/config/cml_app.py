#!/usr/bin/env python3
"""
CML (Cloudera Machine Learning) Application Entry Point

This script serves as the entry point for deploying the CIS Trade Hive
Django application as a CML Project Application.

Features:
- Kerberos authentication with automatic ticket renewal
- Hybrid connection: Impala (reads) + Hive (writes)
- Gunicorn WSGI server with configurable workers/threads

CML Application Configuration:
- Script: config/cml_app.py
- Subdomain: cis-trade-hive

Environment Variables (set in CML Project Settings):
- CIS_ENV: Set to 'work' for CML/Cloudera environment
- KRB5_KTNAME: Kerberos keytab path
- KRB5_PRINCIPAL: Kerberos principal
- KRB5CCNAME: Kerberos credential cache

Impala/Hive are configured via IMPALA_CONFIG and HIVE_CONFIG in settings.py
"""

import os
import sys
import subprocess
import threading
import time

# === CML Application Launcher ===
WORKDIR = os.environ.get("WORKDIR", "/home/cdsw/CIS/")
DJANGO_SETTINGS = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")
COLLECT_STATIC = os.environ.get("DJANGO_COLLECT_STATIC", "0") in ("1", "true", "True")
print(os.environ.get("USER_OWNER"))
print(os.environ.get("CDSW_USERNAME"))


def run(cmd, env=None, check=True):
    """Run a command and optionally check return code."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def kinit_with_keytab(keytab, principal, cache=None):
    """Initialize Kerberos ticket using keytab."""
    env = os.environ.copy()
    if cache:
        env["KRB5CCNAME"] = cache
    print(f"==> kinit -kt {keytab} {principal}")
    rc = subprocess.run(["kinit", "-kt", keytab, principal], env=env).returncode
    if rc != 0:
        print("ERROR: kinit failed. Verify keytab, principal, and krb5.conf.")
        sys.exit(rc)
    subprocess.run(["klist"], env=env)
    return rc


def start_kerberos_renewal_loop(keytab, principal, interval_sec=3600, cache=None):
    """Start a background thread to renew Kerberos ticket periodically."""
    def _renew():
        env = os.environ.copy()
        if cache:
            env["KRB5CCNAME"] = cache
        while True:
            r = subprocess.run(["kinit", "-R"], env=env)
            if r.returncode != 0:
                print("Renewal failed; re-acquiring ticket via keytab...")
                subprocess.run(["kinit", "-kt", keytab, principal], env=env)
            time.sleep(interval_sec)

    t = threading.Thread(target=_renew, daemon=True)
    t.start()


def main():
    """Main entry point for CML application deployment."""
    if WORKDIR:
        os.chdir(WORKDIR)

    # Set Django environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS)
    os.environ.setdefault("DJANGO_DEBUG", "True")
    os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "*")

    # Set CIS_ENV to 'work' for CML/Cloudera configuration
    os.environ.setdefault("CIS_ENV", "work")

    # ==================== REST Proxy Configuration ====================
    # Enable REST proxy mode for Hive operations (bypasses direct Hive connections)
    # This is required in CML where glibc/SASL issues prevent direct connections
    os.environ.setdefault("USE_REST_PROXY", "true")

    # REST Proxy URL - Flask app running on edge node
    # Change this to your edge node IP/hostname where app_v2.py is running
    os.environ.setdefault("HIVE_PROXY_URL", "http://172.29.22.185:5000")

    # Database name for Hive operations
    os.environ.setdefault("HIVE_DATABASE", "mrw_ima")

    # Optional: API key for proxy authentication (if configured on proxy)
    # os.environ.setdefault("HIVE_PROXY_API_KEY", "your-api-key")

    # Timeout for proxy requests (seconds)
    os.environ.setdefault("HIVE_TIMEOUT", "300")

    # Kerberos config (from env)
    keytab = os.environ.get("KRB5_KTNAME") or "/home/cdsw/CIS/secrets/qwntmwsg.keytab"
    principal = os.environ.get("KRB5_PRINCIPAL") or "qwntmwsg@TST.UOBNET.COM"
    cache = os.environ.get("KRB5CCNAME") or "FILE:/home/cdsw/CIS/krb5/krb5cc"

    # Obtain Kerberos TGT up-front (before commands that hit Impala/Hive)
    kinit_with_keytab(keytab, principal, cache=cache)
    start_kerberos_renewal_loop(keytab, principal, interval_sec=3600, cache=cache)

    python_exec = sys.executable

    # Run Django management commands
    run([python_exec, "manage.py", "migrate"])
    try:
        run([python_exec, "manage.py", "setup_roles"], check=False)
    except Exception:
        print("setup_roles command not found; continuing...")

    try:
        run([python_exec, "manage.py", "create_hive_tables"], check=False)
    except Exception:
        print("create_hive_tables failed or not available; continuing...")

    if COLLECT_STATIC:
        os.environ.setdefault("DJANGO_COLLECTSTATIC", "1")
        run([python_exec, "manage.py", "collectstatic", "--noinput"], check=True)

    # Gunicorn configuration
    port = os.environ.get("CDSW_APP_PORT") or os.environ.get("PORT", "8080")
    bind = f"127.0.0.1:{os.environ.get('CDSW_APP_PORT', port)}"
    workers = os.environ.get("WORKERS") or str(8)
    timeout = os.environ.get("TIMEOUT", "120")
    worker_class = os.environ.get("WORKER_CLASS", "gthread")
    threads = os.environ.get("THREADS", "8")
    keepalive = os.environ.get("KEEPALIVE", "5")

    print("=== Runtime Configuration ===")
    print(f"DJANGO_SETTINGS_MODULE = {os.environ['DJANGO_SETTINGS_MODULE']}")
    print(f"DJANGO_DEBUG           = {os.environ.get('DJANGO_DEBUG')}")
    print(f"DJANGO_ALLOWED_HOSTS   = {os.environ.get('DJANGO_ALLOWED_HOSTS')}")
    print(f"CIS_ENV                = {os.environ.get('CIS_ENV')}")
    print(f"Collect_static         = {COLLECT_STATIC}")
    print(f"Gunicorn bind          = {bind}")
    print(f"Workers                = {workers}")
    print(f"Timeout                = {timeout}")
    print(f"KRB5_KTNAME            = {keytab}")
    print(f"KRB5_PRINCIPAL         = {principal}")
    print(f"KRB5CCNAME             = {cache}")
    print(f"Worker class           = {worker_class}")
    print(f"Threads                = {threads}")
    print(f"Keep-alive             = {keepalive}")
    print("--- REST Proxy Configuration ---")
    print(f"USE_REST_PROXY         = {os.environ.get('USE_REST_PROXY')}")
    print(f"HIVE_PROXY_URL         = {os.environ.get('HIVE_PROXY_URL')}")
    print(f"HIVE_DATABASE          = {os.environ.get('HIVE_DATABASE')}")
    print(f"HIVE_TIMEOUT           = {os.environ.get('HIVE_TIMEOUT')}")

    run([
        "gunicorn",
        "--bind", bind,
        "--workers", workers,
        "--worker-class", worker_class,
        "--threads", threads,
        "--keep-alive", keepalive,
        "--timeout", timeout,
        f"{DJANGO_SETTINGS.rsplit('.', 1)[0]}.wsgi:application",
    ])


if __name__ == "__main__":
    main()
