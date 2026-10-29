"""
Database Router for dual database support.

Routes queries between:
- Primary DB (SQLite/MySQL): Django models (if needed)
- Hive: Reference data and analytics accessed via services

Following Open/Closed Principle - easily extendable for new routing rules.
"""

import logging

logger = logging.getLogger('core')


class DatabaseRouter:
    """
    Database router to control database operations on models.

    All Django ORM operations go to the 'default' database (SQLite/MySQL).
    Hive access is handled through services, not Django ORM.
    """

    def db_for_read(self, model, **hints):
        """
        Suggest the database for read operations.
        All reads go to 'default' database.
        """
        return 'default'

    def db_for_write(self, model, **hints):
        """
        Suggest the database for write operations.
        All writes go to 'default' database.
        """
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between objects in the same database.
        """
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure that all apps' models get migrated to the 'default' database.
        """
        return db == 'default'
