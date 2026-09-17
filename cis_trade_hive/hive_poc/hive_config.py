"""
Hive Configuration for POC

Separate configuration for Hive managed tables with ORC format.
Connects to local HiveServer2 for ACID transactions.
"""

import os

# Hive POC Configuration - Local HiveServer2
HIVE_POC_CONFIG = {
    'HOST': os.environ.get('HIVE_POC_HOST', 'localhost'),
    'PORT': int(os.environ.get('HIVE_POC_PORT', '10000')),
    'DATABASE': os.environ.get('HIVE_POC_DB', 'gmp_cis'),
    'AUTH': os.environ.get('HIVE_POC_AUTH', 'NONE'),
    'USERNAME': os.environ.get('HIVE_POC_USERNAME', ''),
    'PASSWORD': os.environ.get('HIVE_POC_PASSWORD', ''),
    'TIMEOUT': int(os.environ.get('HIVE_POC_TIMEOUT', '60')),
}

# Connection string for reference
# jdbc:hive2://localhost:10000/gmp_cis
