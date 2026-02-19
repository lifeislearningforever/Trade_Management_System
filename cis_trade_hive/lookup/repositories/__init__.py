"""
Lookup Repositories

Exports lookup table repository for dynamic table management.
Uses HiveConnectionManager for Hive Managed Tables with ACID support.
"""

from .lookup_hive_repository import lookup_hive_repository, LookupHiveRepository

# Backward compatibility aliases
lookup_kudu_repository = lookup_hive_repository
LookupKuduRepository = LookupHiveRepository

__all__ = [
    'lookup_hive_repository',
    'lookup_kudu_repository',
    'LookupHiveRepository',
    'LookupKuduRepository',
]
