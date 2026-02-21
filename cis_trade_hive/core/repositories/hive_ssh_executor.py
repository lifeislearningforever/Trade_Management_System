"""
Hive SSH Executor for CML (Cloudera Machine Learning)

Executes Hive queries via SSH to an edge node where beeline is available.
This is a workaround for CML environments where:
1. beeline is not installed in the Docker container
2. pure-sasl doesn't support GSSAPI properly
3. Direct JDBC connection requires native SASL libraries

Configuration:
    Set these environment variables:
    - HIVE_SSH_HOST: Edge node hostname (e.g., lxmrwtsgv0w1.sg.uobnet.com)
    - HIVE_SSH_USER: SSH username (defaults to current user)
    - HIVE_SSH_KEY: Path to SSH private key (optional)
    - HIVE_SSH_PORT: SSH port (default 22)

Usage:
    from core.repositories.hive_ssh_executor import hive_ssh_executor

    # Execute query
    success, results = hive_ssh_executor.execute_query("SELECT * FROM table LIMIT 10")

    # Execute write
    success = hive_ssh_executor.execute_write("INSERT INTO table VALUES (...)")
"""

import os
import subprocess
import logging
import csv
import io
import getpass
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger('core')


class HiveSSHExecutor:
    """
    Execute Hive queries via SSH to edge node using beeline.

    This bypasses CML's limitations by running beeline on a proper
    Cloudera edge node that has all required dependencies.
    """

    def __init__(self):
        # SSH configuration
        self._ssh_host = os.environ.get('HIVE_SSH_HOST', 'lxmrwtsgv0w1.sg.uobnet.com')
        self._ssh_user = os.environ.get('HIVE_SSH_USER', getpass.getuser())
        self._ssh_port = int(os.environ.get('HIVE_SSH_PORT', '22'))
        self._ssh_key = os.environ.get('HIVE_SSH_KEY', '')

        # Hive/Beeline configuration
        self._zk_hosts = os.environ.get(
            'HIVE_ZOOKEEPER_HOSTS',
            'lxmrwtsgv0m1.sg.uobnet.com:2181,'
            'lxmrwtsgv0m2.sg.uobnet.com:2181,'
            'lxmrwtsgv0w1.sg.uobnet.com:2181'
        )
        self._principal = os.environ.get('HIVE_PRINCIPAL', 'hive/_HOST@TST.UOBNET.COM')
        self._zk_namespace = os.environ.get('HIVE_ZK_NAMESPACE', 'hiveserver2')
        self._database = os.environ.get('HIVE_DATABASE', 'mrw_ima')
        self._truststore = os.environ.get(
            'HIVE_TRUSTSTORE_PATH',
            '/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks'
        )

        # Query timeout
        self._timeout = int(os.environ.get('HIVE_QUERY_TIMEOUT', '300'))

        # Build JDBC URL
        self._jdbc_url = self._build_jdbc_url()

        logger.info(f"HiveSSHExecutor initialized")
        logger.info(f"  SSH: {self._ssh_user}@{self._ssh_host}:{self._ssh_port}")
        logger.info(f"  Database: {self._database}")

    def _build_jdbc_url(self, database: Optional[str] = None) -> str:
        """Build the JDBC URL for beeline."""
        db = database or self._database

        url = (
            f"jdbc:hive2://{self._zk_hosts}/{db};"
            f"principal={self._principal};"
            f"serviceDiscoveryMode=zooKeeper;"
            f"zookeeperNamespace={self._zk_namespace};"
            f"ssl=true;"
            f"sslTrustStore={self._truststore};"
            f"trustStoreType=jks"
        )

        return url

    def _build_ssh_command(self) -> List[str]:
        """Build the SSH command prefix."""
        cmd = ["ssh"]

        # Add SSH key if specified
        if self._ssh_key and os.path.exists(self._ssh_key):
            cmd.extend(["-i", self._ssh_key])

        # Add port if not default
        if self._ssh_port != 22:
            cmd.extend(["-p", str(self._ssh_port)])

        # Add common SSH options
        cmd.extend([
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            f"{self._ssh_user}@{self._ssh_host}"
        ])

        return cmd

    def _run_beeline_via_ssh(self, query: str, database: Optional[str] = None,
                             output_format: str = "csv2") -> Tuple[bool, str]:
        """Run beeline command via SSH."""
        jdbc_url = self._build_jdbc_url(database) if database else self._jdbc_url

        # Build beeline command
        beeline_cmd = (
            f'beeline -u "{jdbc_url}" '
            f'-e "{query}" '
            f'--silent=true '
            f'--outputformat={output_format}'
        )

        # Full SSH command
        ssh_cmd = self._build_ssh_command()
        ssh_cmd.append(beeline_cmd)

        try:
            logger.debug(f"Executing via SSH: {query[:100]}...")

            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout
            )

            if result.returncode != 0:
                logger.error(f"SSH beeline failed: {result.stderr}")
                return False, result.stderr

            return True, result.stdout

        except subprocess.TimeoutExpired:
            logger.error(f"SSH beeline timed out after {self._timeout}s")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"SSH beeline error: {str(e)}")
            return False, str(e)

    def execute_query(self, query: str, database: Optional[str] = None,
                     timeout: Optional[int] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL query to execute
            database: Database to use (optional)
            timeout: Query timeout in seconds (optional)

        Returns:
            Tuple of (success: bool, results: List[Dict])
        """
        if timeout:
            old_timeout = self._timeout
            self._timeout = timeout

        try:
            success, output = self._run_beeline_via_ssh(query, database, "csv2")

            if not success:
                return False, []

            # Parse CSV output
            output = output.strip()
            if not output:
                return True, []

            reader = csv.DictReader(io.StringIO(output))
            results = [dict(row) for row in reader]

            logger.debug(f"Query returned {len(results)} rows")
            return True, results

        finally:
            if timeout:
                self._timeout = old_timeout

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
        if timeout:
            old_timeout = self._timeout
            self._timeout = timeout

        try:
            success, output = self._run_beeline_via_ssh(query, database, "table")
            return success

        finally:
            if timeout:
                self._timeout = old_timeout

    def test_connection(self) -> bool:
        """Test SSH and Hive connection."""
        # First test SSH
        try:
            ssh_cmd = self._build_ssh_command()
            ssh_cmd.append("echo 'SSH OK'")

            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"SSH connection failed: {result.stderr}")
                return False

            logger.info("SSH connection: OK")

        except Exception as e:
            logger.error(f"SSH test failed: {str(e)}")
            return False

        # Then test Hive via beeline
        try:
            success, results = self.execute_query("SELECT 1", timeout=60)
            if success:
                logger.info("Hive connection (via SSH beeline): OK")
                return True
            else:
                logger.error("Hive connection test failed")
                return False
        except Exception as e:
            logger.error(f"Hive test failed: {str(e)}")
            return False

    def test_ssh_only(self) -> bool:
        """Test just the SSH connection."""
        try:
            ssh_cmd = self._build_ssh_command()
            ssh_cmd.append("whoami")

            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"SSH OK - user: {result.stdout.strip()}")
                return True
            else:
                logger.error(f"SSH failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"SSH error: {str(e)}")
            return False


# Global instance
hive_ssh_executor = HiveSSHExecutor()
