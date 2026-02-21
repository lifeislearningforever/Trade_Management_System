#!/usr/bin/env python3
"""
Test Hybrid Connection Manager (Impala + Hive via Beeline)

Run: python test_hybrid_connection.py

This tests:
1. Impala connection (reads via impyla)
2. Hive connection (writes via beeline)
"""
import os
import sys

# Set environment
os.environ['CIS_ENV'] = 'work'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Setup Django
import django
django.setup()

from django.conf import settings
from core.repositories.hybrid_connection import hybrid_manager

print("=" * 70)
print("HYBRID CONNECTION TEST (Impala + Hive Beeline)")
print("=" * 70)

print(f"\nEnvironment: {settings.CIS_ENV}")
print(f"\nImpala Config:")
print(f"  Host: {settings.IMPALA_CONFIG['HOST']}")
print(f"  Port: {settings.IMPALA_CONFIG['PORT']}")
print(f"  Auth: {settings.IMPALA_CONFIG['AUTH_MECHANISM']}")

print(f"\nHive Config (using beeline with ZooKeeper):")
print(f"  Database: {settings.HIVE_CONFIG['DATABASE']}")

# Test connections
print("\n" + "-" * 70)
print("Testing Connections...")
print("-" * 70)

results = hybrid_manager.test_connection()

print(f"\nResults:")
print(f"  Impala: {'OK' if results['impala'] else 'FAILED'}")
print(f"  Hive:   {'OK' if results['hive'] else 'FAILED'} (via {results.get('hive_method', 'unknown')})")

# Pool stats
print("\n" + "-" * 70)
print("Pool Statistics")
print("-" * 70)
stats = hybrid_manager.get_pool_stats()
print(f"  Impala: {stats['impala']}")
print(f"  Hive:   {stats['hive']}")

# Test read query
print("\n" + "-" * 70)
print("Test Read Query (via Impala)")
print("-" * 70)
try:
    results = hybrid_manager.execute_query("SELECT 1 AS test_value")
    print(f"  Result: {results}")
except Exception as e:
    print(f"  Error: {e}")

# Test write query (just a SELECT via Hive to verify connection)
print("\n" + "-" * 70)
print("Test Hive Query (via Beeline)")
print("-" * 70)
try:
    from core.repositories.hive_beeline_executor import hive_executor
    success, results = hive_executor.execute_query("SELECT 1 AS hive_test")
    print(f"  Success: {success}")
    print(f"  Result: {results}")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
