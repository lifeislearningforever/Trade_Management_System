#!/usr/bin/env python3
"""
Locust Load Testing - CML Application Entry Point

This script runs Locust load tests in Cloudera CML environment.

CML Application Configuration:
- Script: locust_cml_app.py
- Subdomain: cis-locust

Usage in CML:
1. Create a new CML Application
2. Set script to: locust_cml_app.py
3. Access via CML application URL

Or run headless in terminal:
    python locust_cml_app.py --headless --users 100 --spawn-rate 10 --run-time 5m
"""

import os
import sys
import subprocess

# CML environment variables
CDSW_APP_PORT = os.environ.get("CDSW_APP_PORT", "8089")
CIS_ENV = os.environ.get("CIS_ENV", "SIT")

# Target host - adjust based on environment
TARGET_HOSTS = {
    "LOCAL": "http://localhost:8000",
    "SIT": "http://localhost:8000",  # Assuming Django runs locally in CML
    "UAT": "http://localhost:8000",
    "PROD": "http://localhost:8000",
}

TARGET_HOST = os.environ.get("LOCUST_TARGET_HOST", TARGET_HOSTS.get(CIS_ENV, "http://localhost:8000"))


def run_locust_web():
    """Run Locust with Web UI for CML Application mode."""
    print("=" * 60)
    print(f"  Locust Load Testing - CML Application")
    print("=" * 60)
    print(f"  Environment: {CIS_ENV}")
    print(f"  Target Host: {TARGET_HOST}")
    print(f"  Web Port: {CDSW_APP_PORT}")
    print("=" * 60)

    cmd = [
        "locust",
        f"--host={TARGET_HOST}",
        "--web-host=0.0.0.0",
        f"--web-port={CDSW_APP_PORT}",
        "-f", "locustfile.py",
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd)


def run_locust_headless(users=100, spawn_rate=10, run_time="5m", user_class=None):
    """Run Locust in headless mode for automated testing."""
    print("=" * 60)
    print(f"  Locust Load Testing - Headless Mode")
    print("=" * 60)
    print(f"  Environment: {CIS_ENV}")
    print(f"  Target Host: {TARGET_HOST}")
    print(f"  Users: {users}")
    print(f"  Spawn Rate: {spawn_rate}")
    print(f"  Run Time: {run_time}")
    if user_class:
        print(f"  User Class: {user_class}")
    print("=" * 60)

    cmd = [
        "locust",
        f"--host={TARGET_HOST}",
        f"--users={users}",
        f"--spawn-rate={spawn_rate}",
        f"--run-time={run_time}",
        "--headless",
        "--csv=load_test_results",
        "--html=load_test_report.html",
        "-f", "locustfile.py",
    ]

    if user_class:
        cmd.append(user_class)

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    print("\n" + "=" * 60)
    print("  Load Test Complete!")
    print("=" * 60)
    print("  Reports generated:")
    print("    - load_test_results_stats.csv")
    print("    - load_test_results_failures.csv")
    print("    - load_test_results_stats_history.csv")
    print("    - load_test_report.html")
    print("=" * 60)

    return result.returncode


def print_usage():
    """Print usage instructions."""
    print("""
Locust CML Load Testing
========================

Usage:
    # Web UI mode (CML Application)
    python locust_cml_app.py

    # Headless mode
    python locust_cml_app.py --headless --users 100 --spawn-rate 10 --run-time 5m

    # Specific user class
    python locust_cml_app.py --headless --users 50 PositionAVPUser
    python locust_cml_app.py --headless --users 200 ConnectionPoolStressUser

Available User Classes:
    - TradeUser              (25%) - Trade operations
    - SecurityUser           (15%) - Security master
    - PortfolioUser          (15%) - Portfolio management
    - PositionAVPUser        (10%) - Position/AVP testing
    - EquityPriceUser        (10%) - Equity price management
    - FXRateUser             (10%) - FX rate management
    - CounterpartyUser       (10%) - Counterparty management
    - ReferenceDataUser       (5%) - Reference data
    - UDFUser                 (5%) - UDF management
    - DashboardUser           (5%) - Dashboard monitoring
    - MixedUser                    - Mixed workflow
    - StressTestUser               - Rapid-fire stress
    - SoakTestUser                 - Long-running soak test
    - ConnectionPoolStressUser     - Connection pool stress
    - CRUDTestUser                 - CRUD operations

Environment Variables:
    CIS_ENV             - Environment (SIT, UAT, PROD)
    LOCUST_TARGET_HOST  - Override target host URL
    CDSW_APP_PORT       - CML application port (auto-set by CML)
""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print_usage()
        sys.exit(0)

    if "--headless" in args:
        # Parse headless arguments
        users = 100
        spawn_rate = 10
        run_time = "5m"
        user_class = None

        i = 0
        while i < len(args):
            if args[i] == "--users" and i + 1 < len(args):
                users = int(args[i + 1])
                i += 2
            elif args[i] == "--spawn-rate" and i + 1 < len(args):
                spawn_rate = int(args[i + 1])
                i += 2
            elif args[i] == "--run-time" and i + 1 < len(args):
                run_time = args[i + 1]
                i += 2
            elif args[i] == "--headless":
                i += 1
            elif not args[i].startswith("--"):
                user_class = args[i]
                i += 1
            else:
                i += 1

        sys.exit(run_locust_headless(users, spawn_rate, run_time, user_class))
    else:
        # Web UI mode
        run_locust_web()
