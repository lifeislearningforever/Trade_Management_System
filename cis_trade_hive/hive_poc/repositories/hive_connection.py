"""
Hive Connection Manager for POC

Manages connections to HiveServer2 for ACID transactions on ORC tables.
Separate from Impala connection - specifically for Hive managed tables.
"""

import logging
import threading
import time
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from queue import Queue, Empty

from ..hive_config import HIVE_POC_CONFIG

logger = logging.getLogger('hive_poc')

# Import PyHive for Hive connectivity
try:
    from pyhive import hive
    HIVE_AVAILABLE = True
except ImportError:
    HIVE_AVAILABLE = False
    logger.warning("PyHive not available. Hive POC features will be disabled.")


class HiveConnectionManager:
    """
    Connection pool manager for HiveServer2.

    Features:
    - Connection pooling for HiveServer2
    - ACID transaction support for ORC tables
    - Thread-safe implementation
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._pool = Queue(maxsize=10)
            self._pool_lock = threading.Lock()
            self._connection_count = 0
            self._max_connections = 10
            self._connection_timeout = 3600  # 1 hour
            self._initialized = True
            self._config = HIVE_POC_CONFIG
            logger.info(f"Hive POC connection manager initialized (host: {self._config['HOST']}:{self._config['PORT']})")

    def _create_connection(self, database: Optional[str] = None):
        """Create a new Hive connection."""
        if not HIVE_AVAILABLE:
            logger.warning("Hive connection requested but PyHive not available")
            return None

        try:
            db_name = database or self._config['DATABASE']

            conn = hive.Connection(
                host=self._config['HOST'],
                port=self._config['PORT'],
                database=db_name,
                auth=self._config['AUTH'],
                username=self._config['USERNAME'] or None,
                password=self._config['PASSWORD'] or None,
            )

            conn._created_at = time.time()
            conn._database = db_name
            logger.info(f"Created new Hive connection to {db_name}")
            return conn

        except Exception as e:
            logger.error(f"Failed to create Hive connection: {str(e)}")
            return None

    def _validate_connection(self, connection) -> bool:
        """Validate if connection is still alive."""
        try:
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    return False

            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """Context manager for Hive cursor."""
        connection = None
        cursor = None
        try:
            connection = self._create_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                yield None
        except Exception as e:
            logger.error(f"Error in Hive cursor: {str(e)}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if connection:
                try:
                    connection.close()
                except:
                    pass

    def execute_query(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dictionaries."""
        if not HIVE_AVAILABLE:
            logger.warning("Cannot execute query: PyHive not available")
            return []

        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if cursor.description:
                    # Strip table prefix from column names (e.g., "table.column" -> "column")
                    columns = [desc[0].split('.')[-1] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                return []

        except Exception as e:
            logger.error(f"Failed to execute query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> bool:
        """Execute a write query (INSERT, UPDATE, DELETE)."""
        if not HIVE_AVAILABLE:
            logger.warning("Cannot execute write: PyHive not available")
            return False

        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return False

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                logger.info("Hive write query executed successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            return False

    def test_connection(self) -> bool:
        """Test if Hive connection is available."""
        if not HIVE_AVAILABLE:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
            return False
        except Exception as e:
            logger.error(f"Hive connection test failed: {str(e)}")
            return False

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in the database."""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []
                cursor.execute("SHOW TABLES")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tables: {str(e)}")
            return []


# Global instance
hive_manager = HiveConnectionManager()
