#!/usr/bin/env python3
"""
Quick CML Connection Test - Run this in CML terminal:
    export CIS_ENV=work && python test_cml_quick.py

Or just:
    python test_cml_quick.py  (auto-detects CML)
"""
import os

# Force work environment for CML
os.environ['CIS_ENV'] = 'work'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from core.repositories.hybrid_connection import hybrid_manager

print("=" * 60)
print("CML QUICK CONNECTION TEST")
print("=" * 60)
print(f"\nEnvironment: {settings.CIS_ENV}")
print(f"\nImpala: {settings.IMPALA_CONFIG['HOST']}:{settings.IMPALA_CONFIG['PORT']}")
print(f"        Auth: {settings.IMPALA_CONFIG['AUTH_MECHANISM']}")
print(f"\nHive:   {settings.HIVE_CONFIG['HOST']}:{settings.HIVE_CONFIG['PORT']}")
print(f"        Auth: {settings.HIVE_CONFIG['AUTH']}")

print("\n" + "-" * 60)
print("Testing connections...")
results = hybrid_manager.test_connection()
print(f"\nImpala: {'OK' if results['impala'] else 'FAILED'}")
print(f"Hive:   {'OK' if results['hive'] else 'FAILED'}")
print("=" * 60)
