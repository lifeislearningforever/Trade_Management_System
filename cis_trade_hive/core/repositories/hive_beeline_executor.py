"""
Hive Beeline Executor for CML (Cloudera Machine Learning)

Uses beeline CLI via subprocess to execute Hive queries.
This approach works because:
1. Beeline uses JDBC with ZooKeeper service discovery
2. Handles Kerberos authentication properly
3. No Python JDBC/JVM dependencies needed

Configuration:
    Set these environment variables or use defaults:
    - HIVE_ZOOKEEPER_HOSTS: ZooKeeper hosts (comma-separated)
    - HIVE_PRINCIPAL: Kerberos principal for Hive
    - HIVE_TRUSTSTORE_PATH: Path to SSL truststore
    - HIVE_DATABASE: Default database

Usage:
    from core.repositories.hive_beeline_executor import hive_executor

    # Execute query
    success, results = hive_executor.execute_query("SELECT * FROM table LIMIT 10")

    # Execute write
    success = hive_executor.execute_write("INSERT INTO table VALUES (...)")
"""

import os
import subprocess
import logging
import tempfile
import csv
import io
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger('core')


class HiveBeelineExecutor:
    """
    Execute Hive queries using beeline CLI.

    This is the most reliable way to connect to HiveServer2 in Cloudera
    environments that use ZooKeeper for service discovery.
    """

    def __init__(self):
        # ZooKeeper hosts for HiveServer2 discovery
        self._zk_hosts = os.environ.get(
            'HIVE_ZOOKEEPER_HOSTS',
            'lxmrwtsgv0m1.sg.uobnet.com:2181,'
            'lxmrwtsgv0m2.sg.uobnet.com:2181,'
            'lxmrwtsgv0w1.sg.uobnet.com:2181'
        )

        # Kerberos principal
        self._principal = os.environ.get(
            'HIVE_PRINCIPAL',
            'hive/_HOST@TST.UOBNET.COM'
        )

        # ZooKeeper namespace
        self._zk_namespace = os.environ.get(
            'HIVE_ZK_NAMESPACE',
            'hiveserver2'
        )

        # Default database
        self._database = os.environ.get('HIVE_DATABASE', 'mrw_ima')

        # Find truststore path
        self._truststore_path = self._find_truststore()

        # Query timeout (seconds)
        self._timeout = int(os.environ.get('HIVE_QUERY_TIMEOUT', '300'))

        # Build JDBC URL
        self._jdbc_url = self._build_jdbc_url()

        logger.info(f"HiveBeelineExecutor initialized")
        logger.info(f"  ZooKeeper: {self._zk_hosts}")
        logger.info(f"  Database: {self._database}")
        logger.info(f"  Truststore: {self._truststore_path}")

    def _find_truststore(self) -> str:
        """Find the SSL truststore file."""
        # Check environment variable first
        env_path = os.environ.get('HIVE_TRUSTSTORE_PATH')
        if env_path and os.path.exists(env_path):
            return env_path

        # Common locations to check
        locations = [
            # Cloudera edge node default
            '/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks',
            # Project bundled (for CML)
            os.path.join(os.path.dirname(__file__), '../../config/certs/cm-auto-global_truststore.jks'),
            # CML project root
            '/home/cdsw/CIS/config/certs/cm-auto-global_truststore.jks',
            # Alternative CML path
            '/home/cdsw/config/certs/cm-auto-global_truststore.jks',
        ]

        for path in locations:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                return abs_path

        # If not found, return default (will fail at runtime if missing)
        logger.warning("Truststore not found in common locations")
        return '/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks'

    def _build_jdbc_url(self, database: Optional[str] = None) -> str:
        """Build the JDBC URL for beeline."""
        db = database or self._database

        url = (
            f"jdbc:hive2://{self._zk_hosts}/{db};"
            f"principal={self._principal};"
            f"serviceDiscoveryMode=zooKeeper;"
            f"zookeeperNamespace={self._zk_namespace};"
            f"ssl=true;"
            f"sslTrustStore={self._truststore_path};"
            f"trustStoreType=jks"
        )

        return url

    def execute_query(self, query: str, database: Optional[str] = None,
                     timeout: Optional[int] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL query to execute
            database: Database to use (optional, uses default)
            timeout: Query timeout in seconds (optional)

        Returns:
            Tuple of (success: bool, results: List[Dict])
        """
        jdbc_url = self._build_jdbc_url(database) if database else self._jdbc_url
        query_timeout = timeout or self._timeout

        cmd = [
            "beeline",
            "-u", jdbc_url,
            "-e", query,
            "--silent=true",
            "--outputformat=csv2",
            "--showHeader=true"
        ]

        try:
            logger.debug(f"Executing query: {query[:100]}...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=query_timeout
            )

            if result.returncode != 0:
                logger.error(f"Query failed: {result.stderr}")
                return False, []

            # Parse CSV output
            output = result.stdout.strip()
            if not output:
                return True, []

            # Use csv reader to parse
            reader = csv.DictReader(io.StringIO(output))
            results = [dict(row) for row in reader]

            logger.debug(f"Query returned {len(results)} rows")
            return True, results

        except subprocess.TimeoutExpired:
            logger.error(f"Query timed out after {query_timeout}s")
            return False, []
        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            return False, []

    def execute_write(self, query: str, database: Optional[str] = None,
                     timeout: Optional[int] = None) -> bool:
        """
        Execute a write query (INSERT, UPDATE, DELETE, CREATE, etc.).

        Args:
            query: SQL query to execute
            database: Database to use (optional)
            timeout: Query timeout in seconds (optional)

        Returns:
            True if successful, False otherwise
        """
        jdbc_url = self._build_jdbc_url(database) if database else self._jdbc_url
        query_timeout = timeout or self._timeout

        cmd = [
            "beeline",
            "-u", jdbc_url,
            "-e", query,
            "--silent=true"
        ]

        try:
            logger.debug(f"Executing write: {query[:100]}...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=query_timeout
            )

            if result.returncode != 0:
                logger.error(f"Write query failed: {result.stderr}")
                return False

            logger.debug("Write query executed successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Write query timed out after {query_timeout}s")
            return False
        except Exception as e:
            logger.error(f"Write execution error: {str(e)}")
            return False

    def execute_script(self, script_path: str, database: Optional[str] = None,
                      timeout: Optional[int] = None) -> bool:
        """
        Execute a SQL script file.

        Args:
            script_path: Path to SQL script file
            database: Database to use (optional)
            timeout: Script timeout in seconds (optional)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(script_path):
            logger.error(f"Script file not found: {script_path}")
            return False

        jdbc_url = self._build_jdbc_url(database) if database else self._jdbc_url
        script_timeout = timeout or self._timeout * 2  # Double timeout for scripts

        cmd = [
            "beeline",
            "-u", jdbc_url,
            "-f", script_path,
            "--silent=true"
        ]

        try:
            logger.info(f"Executing script: {script_path}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=script_timeout
            )

            if result.returncode != 0:
                logger.error(f"Script execution failed: {result.stderr}")
                return False

            logger.info("Script executed successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Script timed out after {script_timeout}s")
            return False
        except Exception as e:
            logger.error(f"Script execution error: {str(e)}")
            return False

    def test_connection(self) -> bool:
        """Test the Hive connection."""
        try:
            success, results = self.execute_query("SELECT 1", timeout=30)
            if success:
                logger.info("Hive connection test: SUCCESS")
                return True
            else:
                logger.error("Hive connection test: FAILED")
                return False
        except Exception as e:
            logger.error(f"Hive connection test error: {str(e)}")
            return False

    def get_tables(self, database: Optional[str] = None) -> List[str]:
        """Get list of tables in database."""
        db = database or self._database
        success, results = self.execute_query(f"SHOW TABLES IN {db}")
        if success:
            return [row.get('tab_name', row.get('tableName', '')) for row in results]
        return []

    def get_databases(self) -> List[str]:
        """Get list of databases."""
        success, results = self.execute_query("SHOW DATABASES")
        if success:
            return [row.get('database_name', row.get('databaseName', '')) for row in results]
        return []


# Global instance
hive_executor = HiveBeelineExecutor()
