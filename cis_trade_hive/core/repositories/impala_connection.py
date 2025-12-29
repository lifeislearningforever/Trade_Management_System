"""
Impala/Kudu Connection Manager

Handles connections to Impala/Kudu database following the Repository pattern.
Implements connection pooling and error handling.
Uses Impala Python library for connectivity (supports Kudu writes).
"""

import logging
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
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
    Singleton connection manager for Impala/Kudu database.
    Follows Single Responsibility Principle.
    Uses PyHive to connect to Impala.
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
            logger.warning("Impala connection requested but Impala library not available")
            return None

        try:
            config = settings.IMPALA_CONFIG
            db_name = database or config['DATABASE']
            auth_mode = config.get('AUTH', 'NOSASL')

            # Build connection parameters for Impala
            conn_params = {
                'host': config['HOST'],
                'port': config['PORT'],
                'database': db_name,
                'auth_mechanism': auth_mode,
            }

            # Only add username/password for auth modes that require them
            if auth_mode in ['LDAP', 'CUSTOM']:
                conn_params['user'] = config.get('USERNAME', '')
                conn_params['password'] = config.get('PASSWORD', '')

            # Create new connection using Impala
            connection = impala_connect(**conn_params)

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
        Execute a write query (INSERT, UPDATE, DELETE).

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
            if connection:
                try:
                    connection.close()
                except:
                    pass

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
