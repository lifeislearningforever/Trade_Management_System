"""
Lookup Repositories

Exports lookup table repository for dynamic table management.
Uses backward-compatible impala_manager alias (maps to hive_manager).
"""

from .lookup_kudu_repository import lookup_kudu_repository, LookupKuduRepository

# Backward compatibility aliases
lookup_hive_repository = lookup_kudu_repository
LookupHiveRepository = LookupKuduRepository

__all__ = [
    'lookup_kudu_repository',
    'lookup_hive_repository',
    'LookupKuduRepository',
    'LookupHiveRepository',
]
