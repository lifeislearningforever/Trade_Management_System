#!/usr/bin/env python3
"""
Test Impala/Hive Connection Script

Usage:
    # In CML terminal
    python manage.py shell < test_connection.py

    # Or directly
    python test_connection.py
"""

import os
import sys

# Setup Django if running directly
if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

from config.environments import (
    CIS_ENV,
    IMPALA_CONFIG,
    HIVE_CONFIG,
    print_environment_info,
    CURRENT_ENV,
    CURRENT_CONFIG,
)


def test_environment():
    """Print current environment configuration."""
    print("=" * 70)
    print("  ENVIRONMENT CHECK")
    print("=" * 70)
    print(f"  CIS_ENV:       {CIS_ENV}")
    print(f"  CURRENT_ENV:   {CURRENT_ENV}")
    print("")
    print_environment_info()


def test_impala_connection():
    """Test Impala connection."""
    print("\n" + "=" * 70)
    print("  IMPALA CONNECTION TEST")
    print("=" * 70)

    try:
        from impala.dbapi import connect
    except ImportError:
        print("  ERROR: impala library not installed")
        print("  Run: pip install impyla")
        return False

    print(f"  Host:     {IMPALA_CONFIG['HOST']}")
    print(f"  Port:     {IMPALA_CONFIG['PORT']}")
    print(f"  Database: {IMPALA_CONFIG['DATABASE']}")
    print(f"  Auth:     {IMPALA_CONFIG['AUTH_MECHANISM']}")
    print(f"  SSL:      {IMPALA_CONFIG['USE_SSL']}")
    print(f"  Kerberos: {IMPALA_CONFIG.get('KERBEROS_SERVICE_NAME')}")
    print("-" * 70)

    try:
        # Build connection params
        conn_params = {
            'host': IMPALA_CONFIG['HOST'],
            'port': IMPALA_CONFIG['PORT'],
            'database': IMPALA_CONFIG['DATABASE'],
            'auth_mechanism': IMPALA_CONFIG['AUTH_MECHANISM'],
        }

        # Add SSL if enabled
        if IMPALA_CONFIG.get('USE_SSL'):
            conn_params['use_ssl'] = True

        # Add Kerberos service name if using GSSAPI
        if IMPALA_CONFIG['AUTH_MECHANISM'] == 'GSSAPI':
            conn_params['kerberos_service_name'] = IMPALA_CONFIG.get('KERBEROS_SERVICE_NAME', 'impala')

        print(f"  Connecting with params: {conn_params}")
        print("-" * 70)

        conn = connect(**conn_params)
        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print(f"  SELECT 1 result: {result}")

        # Show databases
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        print(f"  Available databases: {[db[0] for db in databases[:5]]}...")

        cursor.close()
        conn.close()

        print("  " + "-" * 68)
        print("  IMPALA CONNECTION: SUCCESS")
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        print("  " + "-" * 68)
        print("  IMPALA CONNECTION: FAILED")
        return False


def test_hive_connection():
    """Test Hive connection."""
    print("\n" + "=" * 70)
    print("  HIVE CONNECTION TEST")
    print("=" * 70)

    try:
        from pyhive import hive
    except ImportError:
        print("  ERROR: pyhive library not installed")
        print("  Run: pip install pyhive")
        return False

    print(f"  Host:     {HIVE_CONFIG['HOST']}")
    print(f"  Port:     {HIVE_CONFIG['PORT']}")
    print(f"  Database: {HIVE_CONFIG['DATABASE']}")
    print(f"  Auth:     {HIVE_CONFIG['AUTH']}")
    print(f"  SSL:      {HIVE_CONFIG['USE_SSL']}")
    print(f"  Kerberos: {HIVE_CONFIG.get('KERBEROS_SERVICE_NAME')}")
    print("-" * 70)

    try:
        # Build connection params
        # Note: pyhive uses 'KERBEROS' not 'GSSAPI' for auth
        auth_mode = HIVE_CONFIG['AUTH']
        if auth_mode == 'GSSAPI':
            auth_mode = 'KERBEROS'  # pyhive uses 'KERBEROS' not 'GSSAPI'

        conn_params = {
            'host': HIVE_CONFIG['HOST'],
            'port': HIVE_CONFIG['PORT'],
            'database': HIVE_CONFIG['DATABASE'],
            'auth': auth_mode,
        }

        # Add Kerberos service name if using KERBEROS auth
        if auth_mode == 'KERBEROS':
            conn_params['kerberos_service_name'] = HIVE_CONFIG.get('KERBEROS_SERVICE_NAME', 'hive')

        print(f"  Connecting with params: {conn_params}")
        print("-" * 70)

        conn = hive.connect(**conn_params)
        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print(f"  SELECT 1 result: {result}")

        cursor.close()
        conn.close()

        print("  " + "-" * 68)
        print("  HIVE CONNECTION: SUCCESS")
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        print("  " + "-" * 68)
        print("  HIVE CONNECTION: FAILED")
        return False


def check_kerberos():
    """Check Kerberos ticket status."""
    print("\n" + "=" * 70)
    print("  KERBEROS TICKET CHECK")
    print("=" * 70)

    import subprocess
    try:
        result = subprocess.run(['klist'], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
            print("  KERBEROS: Valid ticket found")
            return True
        else:
            print(f"  ERROR: {result.stderr}")
            print("  KERBEROS: No valid ticket")
            print("\n  To fix, run:")
            print("    kinit -kt /path/to/keytab principal@REALM")
            return False
    except FileNotFoundError:
        print("  ERROR: klist command not found")
        print("  KERBEROS: Cannot check (klist not available)")
        return False


def test_impala_manager():
    """Test ImpalaConnectionManager."""
    print("\n" + "=" * 70)
    print("  IMPALA CONNECTION MANAGER TEST")
    print("=" * 70)

    try:
        from core.repositories.impala_connection import ImpalaConnectionManager, IMPALA_AVAILABLE
        from django.conf import settings

        if not IMPALA_AVAILABLE:
            print("  ERROR: Impala library not available")
            return False

        # Print what settings the manager will use
        print(f"  settings.IMPALA_CONFIG:")
        print(f"    HOST:          {settings.IMPALA_CONFIG.get('HOST')}")
        print(f"    PORT:          {settings.IMPALA_CONFIG.get('PORT')}")
        print(f"    DATABASE:      {settings.IMPALA_CONFIG.get('DATABASE')}")
        print(f"    AUTH_MECHANISM:{settings.IMPALA_CONFIG.get('AUTH_MECHANISM')}")
        print(f"    USE_SSL:       {settings.IMPALA_CONFIG.get('USE_SSL')}")
        print(f"    KERBEROS:      {settings.IMPALA_CONFIG.get('KERBEROS_SERVICE_NAME')}")
        print("-" * 70)

        # Reset singleton to pick up fresh config
        if hasattr(ImpalaConnectionManager, '_instance') and ImpalaConnectionManager._instance is not None:
            # Clear the instance's initialized flag too
            if hasattr(ImpalaConnectionManager._instance, '_initialized'):
                del ImpalaConnectionManager._instance._initialized
        ImpalaConnectionManager._instance = None

        manager = ImpalaConnectionManager()

        print("  Testing connection via manager...")

        # Try to get a connection and run a query
        try:
            with manager.get_cursor() as cursor:
                if cursor is None:
                    print("  ERROR: Could not get cursor")
                    return False

                cursor.execute("SELECT 1 as test_col")
                result = cursor.fetchone()
                print(f"  SELECT 1 result: {result}")

            print("  CONNECTION MANAGER: SUCCESS")
            return True

        except Exception as conn_error:
            print(f"  Connection error: {conn_error}")
            print("  CONNECTION MANAGER: FAILED")
            return False

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all connection tests."""
    print("\n")
    print("*" * 70)
    print("*  CIS TRADE HIVE - CONNECTION TEST SUITE")
    print("*" * 70)

    # Check environment
    test_environment()

    # Check Kerberos if not LOCAL
    if CIS_ENV != 'local' and CIS_ENV != 'LOCAL':
        check_kerberos()

    # Test Impala
    impala_ok = test_impala_connection()

    # Test Hive
    hive_ok = test_hive_connection()

    # Test Connection Manager
    manager_ok = test_impala_manager()

    # Summary
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)
    print(f"  Impala Direct:      {'PASS' if impala_ok else 'FAIL'}")
    print(f"  Hive Direct:        {'PASS' if hive_ok else 'FAIL'}")
    print(f"  Connection Manager: {'PASS' if manager_ok else 'FAIL'}")
    print("=" * 70)

    return impala_ok and manager_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
