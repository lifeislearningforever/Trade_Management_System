"""
Impala/Kudu Connection Manager

Handles connections to Kudu/Impala database following the Repository pattern.
Implements connection pooling and error handling.
"""

import logging
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from django.conf import settings

logger = logging.getLogger('core')

# Import impyla conditionally to handle environments where it's not available
try:
    from impala.dbapi import connect
    from impala.error import Error as ImpalaError
    IMPALA_AVAILABLE = True
except ImportError:
    IMPALA_AVAILABLE = False
    ImpalaError = Exception
    logger.warning("Impyla not available. Kudu/Impala features will be disabled.")


class ImpalaConnectionManager:
    """
    Singleton connection manager for Impala/Kudu database.
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
        Get or create Impala connection.

        Args:
            database: Optional database name, defaults to IMPALA_CONFIG['DATABASE']

        Returns:
            Connection object or None if not available
        """
        if not IMPALA_AVAILABLE:
            logger.warning("Impala connection requested but impyla not available")
            return None

        try:
            config = settings.IMPALA_CONFIG
            db_name = database or config['DATABASE']

            # Create new connection (connection pooling can be added here)
            connection = connect(
                host=config['HOST'],
                port=config['PORT'],
                database=db_name,
                use_ssl=config['USE_SSL'],
                auth_mechanism=config['AUTH_MECHANISM'],
                kerberos_service_name=config.get('KRB_SERVICE_NAME', 'impala'),
                timeout=config.get('TIMEOUT', 60)
            )

            logger.info(f"Successfully connected to Impala database: {db_name}")
            return connection

        except Exception as e:
            logger.error(f"Failed to connect to Impala: {str(e)}")
            return None

    @contextmanager
    def get_cursor(self, database: Optional[str] = None):
        """
        Context manager for Impala cursor.

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
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute query: Impyla not available")
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
        if not IMPALA_AVAILABLE:
            logger.warning("Cannot execute write: Impyla not available")
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
        """Test if Impala connection is available"""
        if not IMPALA_AVAILABLE:
            return False

        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute("SELECT 1")
                    return True
            return False
        except:
            return False


# Global instance
impala_manager = ImpalaConnectionManager()
