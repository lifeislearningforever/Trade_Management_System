"""
Hive Configuration for POC (DEPRECATED)

This module is deprecated. Configuration is now managed in:
- config/settings.py (HIVE_CONFIG, IMPALA_CONFIG)
- core/repositories/hybrid_connection.py

Connection routing:
- Reads: Impala (fast)
- Writes: Hive (ACID)

For backward compatibility, this re-exports the HIVE_CONFIG from settings.
"""

import logging
from django.conf import settings

logger = logging.getLogger('hive_poc')
logger.warning("hive_poc.hive_config is deprecated. Use django.conf.settings.HIVE_CONFIG instead.")

# Re-export for backward compatibility
HIVE_POC_CONFIG = getattr(settings, 'HIVE_CONFIG', {
    'HOST': 'localhost',
    'PORT': 10000,
    'DATABASE': 'gmp_cis',
    'AUTH': 'NONE',
    'USERNAME': '',
    'PASSWORD': '',
    'TIMEOUT': 60,
})
