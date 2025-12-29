"""
Hive Connection Manager

Handles connections to Hive database following the Repository pattern.
Implements connection pooling and error handling.
"""

import logging
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from django.conf import settings

logger = logging.getLogger('core')

# Import PyHive conditionally to handle environments where it's not available
try:
    from pyhive import hive
    from thrift.transport import TSocket
    from thrift.transport import TTransport
    from thrift.protocol import TBinaryProtocol
    HIVE_AVAILABLE = True
except ImportError:
    HIVE_AVAILABLE = False
    logger.warning("PyHive not available. Hive features will be disabled.")


class HiveConnectionManager:
    """
    Singleton connection manager for Hive database.
    Follows Single Responsibility Principle.
    """
    _instance = None
    _connection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self, database: Optional[str] = None):
        """
        Get or create Hive connection.

        Args:
            database: Optional database name, defaults to HIVE_CONFIG['DATABASE']

        Returns:
            Connection object or None if not available
        """
        if not HIVE_AVAILABLE:
            logger.warning("Hive connection requested but PyHive not available")
            return None

        try:
            config = settings.HIVE_CONFIG
            db_name = database or config['DATABASE']
            auth_mode = config.get('AUTH', 'NOSASL')

            # Build connection parameters based on auth mode
            conn_params = {
                'host': config['HOST'],
                'port': config['PORT'],
                'database': db_name,
                'auth': auth_mode,
            }

            # Only add username/password for auth modes that require them
            if auth_mode in ['LDAP', 'CUSTOM']:
                conn_params['username'] = config.get('USERNAME', '')
                conn_params['password'] = config.get('PASSWORD', '')

            # Create new connection
            connection = hive.Connection(**conn_params)

            logger.info(f"Successfully connected to Hive database: {db_name}")
            return connection

        except Exception as e:
            logger.error(f"Failed to connect to Hive: {str(e)}")
            return None

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """
        Context manager for Hive cursor.

        Usage:
            with hive_manager.get_cursor() as cursor:
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
        """
        Execute a query and return results as list of dictionaries.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            List of dictionaries with column names as keys
        """
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
        Execute a write query (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query to execute
            params: Optional query parameters
            database: Optional database name

        Returns:
            True if successful, False otherwise
        """
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

                logger.info("Write query executed successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to execute write query: {str(e)}")
            logger.error(f"Query: {query}")
            return False

    def test_connection(self) -> bool:
        """Test if Hive connection is available"""
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
hive_manager = HiveConnectionManager()
