"""
Hive Connection for POC

Uses the HybridConnectionManager from core.repositories for:
- Impala: Fast reads (SELECT queries)
- Hive: ACID writes (INSERT, UPDATE, DELETE)

This module re-exports the hybrid_manager as hive_manager for backward compatibility.
"""

import logging

logger = logging.getLogger('hive_poc')

# Import hybrid connection manager from core
try:
    from core.repositories.hybrid_connection import hybrid_manager as hive_manager
    logger.info("hive_poc: Using HybridConnectionManager from core.repositories")
except ImportError:
    # Fallback to core.repositories.hive_connection
    try:
        from core.repositories.hive_connection import hive_manager
        logger.info("hive_poc: Using HiveConnectionManager from core.repositories")
    except ImportError:
        hive_manager = None
        logger.error("hive_poc: No connection manager available!")

# Re-export for backward compatibility
__all__ = ['hive_manager', 'HiveConnectionManager']


# Backward compatibility class alias
class HiveConnectionManager:
    """
    Backward compatibility wrapper.

    Returns the singleton hybrid_manager instance.
    New code should import directly from core.repositories.hybrid_connection.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = hive_manager
        return cls._instance
