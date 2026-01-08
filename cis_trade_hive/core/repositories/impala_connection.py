"""
Impala/Kudu Connection Manager

Handles connections to Impala/Kudu database following the Repository pattern.
Implements connection pooling and error handling.
Uses Impala Python library for connectivity (supports Kudu writes).
"""

import logging
import threading
import time
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from queue import Queue, Empty
from django.conf import settings

logger = logging.getLogger('core')

# Import Impala DB-API conditionally to handle environments where it's not available
try:
    from impala.dbapi import connect as impala_connect
    IMPALA_AVAILABLE = True
except ImportError:
    IMPALA_AVAILABLE = False
    logger.warning("Impala Python library not available. Impala/Kudu features will be disabled.")


class ImpalaConnectionManager:
    """
    Connection pool manager for Impala/Kudu database (Production-ready).

    Features:
    - Connection pooling with configurable pool size
    - Connection validation before use
    - Thread-safe implementation
    - Automatic connection recycling
    - Graceful degradation
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
            # Get pool size from settings, default to 35 for production (4 workers x 4 threads + margin)
            from django.conf import settings
            max_pool_size = getattr(settings, 'IMPALA_POOL_SIZE', 35)

            self._pool = Queue(maxsize=max_pool_size)
            self._pool_lock = threading.Lock()
            self._connection_count = 0
            self._max_connections = max_pool_size
            self._connection_timeout = 3600  # 1 hour in seconds
            self._initialized = True
            logger.info(f"Impala connection pool initialized (max: {max_pool_size} connections)")

    def _create_connection(self, database: Optional[str] = None):
        """
        Create a new Impala connection.

        Args:
            database: Optional database name

        Returns:
            Connection object or None
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Impala connection requested but Impala library not available")
            return None

        try:
            config = settings.IMPALA_CONFIG
            db_name = database or config['DATABASE']
            auth_mode = config.get('AUTH', 'NOSASL')

            # Build connection parameters
            conn_params = {
                'host': config['HOST'],
                'port': config['PORT'],
                'database': db_name,
                'auth_mechanism': auth_mode,
            }

            # Add credentials for auth modes that require them
            if auth_mode in ['LDAP', 'CUSTOM']:
                conn_params['user'] = config.get('USERNAME', '')
                conn_params['password'] = config.get('PASSWORD', '')

            # Create connection
            connection = impala_connect(**conn_params)

            # Store creation time for recycling
            connection._created_at = time.time()
            connection._database = db_name

            logger.info(f"Created new Impala connection to database: {db_name}")
            return connection

        except Exception as e:
            logger.error(f"Failed to create Impala connection: {str(e)}")
            return None

    def _validate_connection(self, connection) -> bool:
        """
        Validate if connection is still alive and not expired.

        Args:
            connection: Connection to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if connection is too old (recycle after 1 hour)
            if hasattr(connection, '_created_at'):
                age = time.time() - connection._created_at
                if age > self._connection_timeout:
                    logger.debug("Connection expired (age: {:.0f}s), will recycle".format(age))
                    return False

            # Ping the connection
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True

        except Exception as e:
            logger.debug(f"Connection validation failed: {str(e)}")
            return False

    def get_connection(self, database: Optional[str] = None):
        """
        Get a connection from the pool.

        Args:
            database: Optional database name

        Returns:
            Connection object from pool
        """
        if not IMPALA_AVAILABLE:
            return None

        # Try to get connection from pool
        try:
            connection = self._pool.get(block=False)

            # Validate connection
            if self._validate_connection(connection):
                return connection
            else:
                # Connection is stale, close it
                try:
                    connection.close()
                except:
                    pass
                with self._pool_lock:
                    self._connection_count -= 1

        except Empty:
            pass  # Pool is empty, create new connection

        # Create new connection if under limit
        with self._pool_lock:
            if self._connection_count < self._max_connections:
                connection = self._create_connection(database)
                if connection:
                    self._connection_count += 1
                    logger.debug(f"Pool stats: {self._connection_count}/{self._max_connections} connections")
                return connection
            else:
                # Wait for connection from pool
                logger.warning("Connection pool exhausted, waiting for available connection")
                try:
                    connection = self._pool.get(timeout=30)
                    if self._validate_connection(connection):
                        return connection
                    else:
                        # Stale connection, create new one
                        try:
                            connection.close()
                        except:
                            pass
                        self._connection_count -= 1
                        return self._create_connection(database)
                except Empty:
                    logger.error("Timeout waiting for connection from pool")
                    return None

    def return_connection(self, connection):
        """
        Return a connection to the pool.

        Args:
            connection: Connection to return
        """
        if connection is None:
            return

        try:
            # Validate before returning to pool
            if self._validate_connection(connection):
                self._pool.put(connection, block=False)
            else:
                # Connection is bad, close it
                try:
                    connection.close()
                except:
                    pass
                with self._pool_lock:
                    self._connection_count -= 1

        except Exception as e:
            logger.debug(f"Failed to return connection to pool: {str(e)}")
            try:
                connection.close()
            except:
                pass
            with self._pool_lock:
                self._connection_count -= 1

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """
        Context manager for Impala cursor (with connection pooling).

        Usage:
            with impala_manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        connection = None
        cursor = None
        try:
            connection = self.get_connection(database)
            if connection:
                cursor = connection.cursor()
                yield cursor
            else:
                yield None
        except Exception as e:
            logger.error(f"Error in Impala cursor: {str(e)}")
            raise
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            # Return connection to pool instead of closing
            if connection:
                self.return_connection(connection)

    def execute_query(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as list of dictionaries.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            List of dictionaries with column names as keys
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute query: Impala library not available")
            return []

        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # Get column names
                columns = [desc[0] for desc in cursor.description]

                # Fetch all results
                rows = cursor.fetchall()

                # Convert to list of dictionaries
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to execute query: {str(e)}")
            logger.error(f"Query: {query}")
            return []

    def execute_write(self, query: str, params: Optional[List] = None,
                     database: Optional[str] = None) -> bool:
        """
        Execute a write query (INSERT, UPDATE, DELETE) with connection pooling.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            True if successful, False otherwise
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute write: Impala library not available")
            return False

        connection = None
        cursor = None
        try:
            connection = self.get_connection(database)
            if connection is None:
                return False

            cursor = connection.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Commit the transaction - critical for Kudu writes to persist
            connection.commit()

            logger.info("Write query executed and committed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            if connection:
                try:
                    connection.rollback()
                except:
                    pass
            return False
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            # Return connection to pool instead of closing
            if connection:
                self.return_connection(connection)

    def test_connection(self) -> bool:
        """Test if Impala connection is available"""
        if not IMPALA_AVAILABLE:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
            return False
        except Exception as e:
            logger.error(f"Impala connection test failed: {str(e)}")
            return False

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in the database"""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                return tables
        except Exception as e:
            logger.error(f"Failed to get tables: {str(e)}")
            return []

    def describe_table(self, table_name: str, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get table schema information"""
        try:
            with self.get_cursor(database) as cursor:
                if cursor is None:
                    return []

                cursor.execute(f"DESCRIBE {table_name}")
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to describe table {table_name}: {str(e)}")
            return []


# Global instance
impala_manager = ImpalaConnectionManager()
