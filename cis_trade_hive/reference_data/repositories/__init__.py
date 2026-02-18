"""
Reference Data Repositories Package

Uses Hive managed tables (ORC + ACID) for all reference data.
"""

from .reference_data_hive_repository import (
    currency_hive_repository,
    country_hive_repository,
    counterparty_hive_repository,
)

# Backward compatibility - use Hive repositories with expected names
currency_repository = currency_hive_repository
country_repository = country_hive_repository
counterparty_repository = counterparty_hive_repository

# Calendar repository placeholder (not migrated yet)
# Use old repository for calendar until migration is complete
from .reference_data_repository import calendar_repository

__all__ = [
    'currency_repository',
    'country_repository',
    'calendar_repository',
    'counterparty_repository',
    # Explicit Hive repository names
    'currency_hive_repository',
    'country_hive_repository',
    'counterparty_hive_repository',
]
