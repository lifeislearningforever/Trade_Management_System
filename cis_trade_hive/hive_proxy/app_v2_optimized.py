#!/usr/bin/env python3
"""
Hive REST Proxy v2.1 - Optimized with Beeline Session Pooling

PERFORMANCE OPTIMIZATION:
- Previous issue: Each request spawned new beeline process (~30-40s overhead)
- Solution: Persistent beeline sessions with stdin/stdout communication
- Result: First request ~10s (session creation), subsequent requests ~1-3s

Features:
- Persistent beeline session pool (reuses JVM/connections)
- Session health monitoring and auto-recovery
- Batch query support for multiple operations
- Schema caching for performance
- Audit logging to mrw_ima.hive_proxy_audit
- Corner case handling (SQL injection, NULL, special chars, timestamps)
- Rate limiting and connection pooling

Deployment:
    gunicorn -b 0.0.0.0:5000 -w 1 --timeout 300 app_v2_optimized:app
    NOTE: Use workers=1 to share session pool across requests

Version: 2.1.0
"""

import os
import subprocess
import csv
import io
import json
import time
import re
import hashlib
import logging
import atexit
import signal
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional, Union
from functools import wraps
from threading import Lock, Semaphore, Thread
from collections import OrderedDict
from queue import Queue, Empty

from flask import Flask, request, jsonify, g

# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hive_proxy')

app = Flask(__name__)

# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Application configuration from environment variables."""

    # ZooKeeper hosts for HiveServer2 discovery
    ZOOKEEPER_HOSTS = os.environ.get(
        'HIVE_ZOOKEEPER_HOSTS',
        'lxmrwtsgv0m1.sg.uobnet.com:2181,'
        'lxmrwtsgv0m2.sg.uobnet.com:2181,'
        'lxmrwtsgv0w1.sg.uobnet.com:2181'
    )

    # Kerberos principal
    HIVE_PRINCIPAL = os.environ.get('HIVE_PRINCIPAL', 'hive/_HOST@TST.UOBNET.COM')

    # ZooKeeper namespace
    ZK_NAMESPACE = os.environ.get('HIVE_ZK_NAMESPACE', 'hiveserver2')

    # Default database
    DEFAULT_DATABASE = os.environ.get('HIVE_DATABASE', 'mrw_ima')

    # Audit database (where audit logs are stored)
    AUDIT_DATABASE = os.environ.get('HIVE_AUDIT_DATABASE', 'mrw_ima')

    # Audit table name
    AUDIT_TABLE = os.environ.get('HIVE_AUDIT_TABLE', 'hive_proxy_audit')

    # SSL truststore
    TRUSTSTORE_PATH = os.environ.get(
        'HIVE_TRUSTSTORE_PATH',
        '/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks'
    )

    # Query timeout (seconds)
    QUERY_TIMEOUT = int(os.environ.get('HIVE_QUERY_TIMEOUT', '300'))

    # Max concurrent queries
    MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT_QUERIES', '20'))

    # Java home for beeline
    JAVA_HOME = os.environ.get(
        'JAVA_HOME',
        '/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.462.b08-2.el8.x86_64/jre'
    )

    # API Key for authentication
    API_KEY = os.environ.get('HIVE_PROXY_API_KEY', '')

    # Schema cache TTL (seconds)
    SCHEMA_CACHE_TTL = int(os.environ.get('SCHEMA_CACHE_TTL', '3600'))

    # Enable audit logging
    AUDIT_ENABLED = os.environ.get('AUDIT_ENABLED', 'true').lower() == 'true'

    # YARN Queue for resource allocation (use EOD_Queue for less resources)
    YARN_QUEUE = os.environ.get('HIVE_YARN_QUEUE', 'EOD_Queue')

    # Session pool settings
    SESSION_POOL_SIZE = int(os.environ.get('SESSION_POOL_SIZE', '3'))
    SESSION_MAX_AGE = int(os.environ.get('SESSION_MAX_AGE', '1800'))  # 30 minutes
    SESSION_HEALTH_CHECK_INTERVAL = int(os.environ.get('SESSION_HEALTH_CHECK_INTERVAL', '60'))


config = Config()

# =============================================================================
# Thread-safe counters and locks
# =============================================================================

query_semaphore = Semaphore(config.MAX_CONCURRENT)
query_lock = Lock()
schema_cache_lock = Lock()

query_stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'select': 0,
    'insert': 0,
    'update': 0,
    'delete': 0,
    'session_reused': 0,
    'session_created': 0
}

# =============================================================================
# Beeline Session Pool - PERFORMANCE OPTIMIZATION
# =============================================================================

class BeelineSession:
    """
    Persistent beeline session using subprocess with stdin/stdout.

    Instead of spawning a new beeline process for each query,
    this keeps a session alive and sends queries via stdin.
    """

    # Marker to identify end of query output
    END_MARKER = "<<<HIVE_PROXY_END_MARKER>>>"

    def __init__(self, session_id: int, database: str = None):
        self.session_id = session_id
        self.database = database or config.DEFAULT_DATABASE
        self.process: Optional[subprocess.Popen] = None
        self.created_at = time.time()
        self.last_used = time.time()
        self.query_count = 0
        self.lock = Lock()
        self.healthy = False

    def start(self) -> bool:
        """Start the beeline session."""
        try:
            jdbc_url = self._build_jdbc_url()

            # Build beeline command for interactive mode
            env = os.environ.copy()
            env['JAVA_HOME'] = config.JAVA_HOME
            env['PATH'] = f"{config.JAVA_HOME}/bin:{env.get('PATH', '')}"

            cmd = [
                'beeline',
                '-u', jdbc_url,
                '--silent=true',
                '--color=false',
                '--outputformat=csv2',
                '--showHeader=true',
                '--fastConnect=true',  # Skip schema fetch on connect
                '--incremental=true',  # Stream results
            ]

            logger.info(f"Session {self.session_id}: Starting beeline session...")

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env=env
            )

            # Wait for connection and test with simple query
            time.sleep(2)  # Give beeline time to connect

            # Set queue and test connection
            init_sql = f"""
SET mapreduce.job.queuename={config.YARN_QUEUE};
SET tez.queue.name={config.YARN_QUEUE};
SELECT 1 AS connection_test;
SELECT '{self.END_MARKER}' AS marker;
"""
            self.process.stdin.write(init_sql)
            self.process.stdin.flush()

            # Read until marker
            output = self._read_until_marker(timeout=60)

            if 'connection_test' in output.lower() or '1' in output:
                self.healthy = True
                logger.info(f"Session {self.session_id}: Beeline session started successfully")
                return True
            else:
                logger.error(f"Session {self.session_id}: Failed to initialize: {output[:200]}")
                self.stop()
                return False

        except Exception as e:
            logger.exception(f"Session {self.session_id}: Failed to start: {e}")
            self.stop()
            return False

    def _build_jdbc_url(self) -> str:
        """Build JDBC URL for beeline."""
        return (
            f"jdbc:hive2://{config.ZOOKEEPER_HOSTS}/{self.database};"
            f"principal={config.HIVE_PRINCIPAL};"
            f"serviceDiscoveryMode=zooKeeper;"
            f"zookeeperNamespace={config.ZK_NAMESPACE};"
            f"ssl=true;"
            f"sslTrustStore={config.TRUSTSTORE_PATH};"
            f"trustStoreType=jks"
        )

    def _read_until_marker(self, timeout: int = 300) -> str:
        """Read stdout until END_MARKER is found or timeout."""
        output_lines = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.process is None or self.process.poll() is not None:
                # Process terminated
                break

            try:
                # Use select or non-blocking read
                import select
                ready, _, _ = select.select([self.process.stdout], [], [], 0.5)

                if ready:
                    line = self.process.stdout.readline()
                    if line:
                        output_lines.append(line.rstrip('\n'))
                        # Check for marker
                        if self.END_MARKER in line:
                            break

            except Exception as e:
                logger.warning(f"Session {self.session_id}: Read error: {e}")
                break

        return '\n'.join(output_lines)

    def execute(self, sql: str, timeout: int = None) -> Tuple[bool, Dict]:
        """Execute SQL query on this session."""
        timeout = timeout or config.QUERY_TIMEOUT

        with self.lock:
            if not self.healthy or self.process is None or self.process.poll() is not None:
                logger.warning(f"Session {self.session_id}: Session not healthy, cannot execute")
                return False, {'error': 'Session not healthy'}

            self.last_used = time.time()
            self.query_count += 1

            start_time = time.time()

            try:
                # Send query followed by marker query
                query_with_marker = f"{sql};\nSELECT '{self.END_MARKER}' AS marker;\n"
                self.process.stdin.write(query_with_marker)
                self.process.stdin.flush()

                # Read response
                output = self._read_until_marker(timeout)
                elapsed_ms = int((time.time() - start_time) * 1000)

                # Parse output
                return self._parse_output(output, elapsed_ms)

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.exception(f"Session {self.session_id}: Execution error: {e}")
                self.healthy = False
                return False, {'error': str(e), 'elapsed_ms': elapsed_ms}

    def _parse_output(self, output: str, elapsed_ms: int) -> Tuple[bool, Dict]:
        """Parse beeline output."""
        # Remove marker lines
        lines = [l for l in output.split('\n')
                 if self.END_MARKER not in l
                 and not l.startswith('INFO')
                 and not l.startswith('WARNING')]

        clean_output = '\n'.join(lines).strip()

        # Check for errors
        if any(err in clean_output.lower() for err in ['error', 'exception', 'failed']):
            if 'error' in clean_output.lower() and 'no error' not in clean_output.lower():
                return False, {'error': clean_output[:500], 'elapsed_ms': elapsed_ms}

        # Parse CSV output
        if not clean_output:
            return True, {'data': [], 'rows': 0, 'elapsed_ms': elapsed_ms}

        try:
            reader = csv.DictReader(io.StringIO(clean_output))
            data = []
            for row in reader:
                clean_row = {}
                for key, value in row.items():
                    if key and '.' in key:
                        clean_key = key.split('.')[-1]
                    else:
                        clean_key = key
                    clean_row[clean_key] = value
                data.append(clean_row)

            return True, {'data': data, 'rows': len(data), 'elapsed_ms': elapsed_ms}

        except Exception as e:
            return True, {'data': clean_output, 'elapsed_ms': elapsed_ms}

    def health_check(self) -> bool:
        """Check if session is healthy."""
        if not self.healthy or self.process is None or self.process.poll() is not None:
            self.healthy = False
            return False

        # Check age
        if time.time() - self.created_at > config.SESSION_MAX_AGE:
            logger.info(f"Session {self.session_id}: Expired (age > {config.SESSION_MAX_AGE}s)")
            self.healthy = False
            return False

        return True

    def stop(self):
        """Stop the beeline session."""
        if self.process:
            try:
                self.process.stdin.write("!quit\n")
                self.process.stdin.flush()
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.process = None
        self.healthy = False
        logger.info(f"Session {self.session_id}: Stopped")


class BeelineSessionPool:
    """
    Pool of persistent beeline sessions for connection reuse.

    Performance benefit:
    - First query: ~10s (creates session)
    - Subsequent queries: ~1-3s (reuses session)
    """

    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.sessions: List[BeelineSession] = []
        self.available_sessions: Queue = Queue()
        self.lock = Lock()
        self.session_counter = 0
        self._shutdown = False

        # Start health checker thread
        self.health_thread = Thread(target=self._health_checker, daemon=True)
        self.health_thread.start()

        logger.info(f"Session pool initialized (size={pool_size})")

    def _health_checker(self):
        """Background thread to check session health."""
        while not self._shutdown:
            time.sleep(config.SESSION_HEALTH_CHECK_INTERVAL)
            self._check_all_sessions()

    def _check_all_sessions(self):
        """Check health of all sessions."""
        with self.lock:
            unhealthy = []
            for session in self.sessions:
                if not session.health_check():
                    unhealthy.append(session)

            for session in unhealthy:
                logger.info(f"Removing unhealthy session {session.session_id}")
                session.stop()
                self.sessions.remove(session)

    def _create_session(self) -> Optional[BeelineSession]:
        """Create a new beeline session."""
        with self.lock:
            self.session_counter += 1
            session_id = self.session_counter

            with query_lock:
                query_stats['session_created'] += 1

        session = BeelineSession(session_id)
        if session.start():
            with self.lock:
                self.sessions.append(session)
            return session
        return None

    def acquire(self, timeout: int = 30) -> Optional[BeelineSession]:
        """Acquire a session from the pool."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Try to get from available queue
            try:
                session = self.available_sessions.get_nowait()
                if session.health_check():
                    with query_lock:
                        query_stats['session_reused'] += 1
                    return session
                else:
                    # Session unhealthy, remove it
                    session.stop()
                    with self.lock:
                        if session in self.sessions:
                            self.sessions.remove(session)
            except Empty:
                pass

            # Check if we can create a new session
            with self.lock:
                if len(self.sessions) < self.pool_size:
                    # Create new session
                    session = self._create_session()
                    if session:
                        return session

            # Wait a bit before retrying
            time.sleep(0.5)

        return None

    def release(self, session: BeelineSession):
        """Release a session back to the pool."""
        if session and session.healthy:
            self.available_sessions.put(session)
        elif session:
            session.stop()
            with self.lock:
                if session in self.sessions:
                    self.sessions.remove(session)

    def shutdown(self):
        """Shutdown all sessions."""
        self._shutdown = True
        with self.lock:
            for session in self.sessions:
                session.stop()
            self.sessions.clear()
        logger.info("Session pool shutdown complete")

    def stats(self) -> Dict:
        """Get pool statistics."""
        with self.lock:
            return {
                'pool_size': self.pool_size,
                'active_sessions': len(self.sessions),
                'available': self.available_sessions.qsize(),
                'total_created': self.session_counter
            }


# Initialize session pool
session_pool = BeelineSessionPool(pool_size=config.SESSION_POOL_SIZE)

# Cleanup on exit
def cleanup():
    session_pool.shutdown()

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda s, f: cleanup())

# =============================================================================
# Schema Cache
# =============================================================================

class SchemaCache:
    """Cache for table schemas to avoid repeated DESCRIBE queries."""

    def __init__(self, ttl: int = 3600):
        self.cache: Dict[str, Dict] = {}
        self.ttl = ttl
        self.lock = Lock()

    def _get_key(self, database: str, table: str) -> str:
        return f"{database}.{table}"

    def get(self, database: str, table: str) -> Optional[Dict]:
        """Get cached schema if not expired."""
        key = self._get_key(database, table)
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                cached_at = entry.get('cached_at')
                if cached_at is not None and (time.time() - cached_at) < self.ttl:
                    return entry
                else:
                    del self.cache[key]
        return None

    def set(self, database: str, table: str, schema: Dict) -> None:
        """Cache a schema."""
        key = self._get_key(database, table)
        with self.lock:
            self.cache[key] = {
                **schema,
                'cached_at': time.time()
            }

    def invalidate(self, database: str = None, table: str = None) -> None:
        """Invalidate cache entries."""
        with self.lock:
            if database and table:
                key = self._get_key(database, table)
                self.cache.pop(key, None)
            elif database:
                keys_to_delete = [k for k in self.cache if k.startswith(f"{database}.")]
                for k in keys_to_delete:
                    del self.cache[k]
            else:
                self.cache.clear()

    def stats(self) -> Dict:
        """Get cache statistics."""
        with self.lock:
            return {
                'entries': len(self.cache),
                'tables': list(self.cache.keys())
            }


schema_cache = SchemaCache(ttl=config.SCHEMA_CACHE_TTL)

# =============================================================================
# Type Mapping and Value Formatting
# =============================================================================

HIVE_TYPE_MAP = {
    'string': str,
    'varchar': str,
    'char': str,
    'int': int,
    'integer': int,
    'bigint': int,
    'smallint': int,
    'tinyint': int,
    'float': float,
    'double': float,
    'decimal': Decimal,
    'boolean': bool,
    'timestamp': datetime,
    'date': date,
    'binary': bytes,
}


def parse_hive_type(type_str: str) -> str:
    """Extract base type from Hive type string."""
    type_str = type_str.lower().strip()
    match = re.match(r'^(\w+)', type_str)
    return match.group(1) if match else 'string'


def format_value_for_hive(value: Any, hive_type: str) -> str:
    """Format a Python value for Hive SQL based on column type."""
    if value is None:
        return 'NULL'

    if value == '':
        return "NULL" if hive_type in ('timestamp', 'date', 'int', 'bigint', 'float', 'double', 'decimal', 'boolean') else "''"

    base_type = parse_hive_type(hive_type)

    if base_type in ('string', 'varchar', 'char'):
        escaped = str(value).replace("'", "''").replace("\\", "\\\\")
        return f"'{escaped}'"

    if base_type in ('int', 'integer', 'bigint', 'smallint', 'tinyint'):
        try:
            return str(int(value))
        except (ValueError, TypeError):
            return 'NULL'

    if base_type in ('float', 'double'):
        try:
            return str(float(value))
        except (ValueError, TypeError):
            return 'NULL'

    if base_type == 'decimal':
        try:
            return str(Decimal(str(value)))
        except:
            return 'NULL'

    if base_type == 'boolean':
        if isinstance(value, bool):
            return 'TRUE' if value else 'FALSE'
        if isinstance(value, str):
            return 'TRUE' if value.lower() in ('true', '1', 'yes') else 'FALSE'
        return 'TRUE' if value else 'FALSE'

    if base_type == 'timestamp':
        if isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ('now', 'current_timestamp', 'current'):
                return 'CURRENT_TIMESTAMP'
            for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(value, fmt)
                    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
                except ValueError:
                    continue
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        return 'CURRENT_TIMESTAMP'

    if base_type == 'date':
        if isinstance(value, (datetime, date)):
            return f"'{value.strftime('%Y-%m-%d')}'"
        if isinstance(value, str):
            return f"'{value[:10]}'"
        return 'NULL'

    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sanitize_identifier(name: str) -> str:
    """Sanitize SQL identifier to prevent injection."""
    if not name:
        raise ValueError("Identifier cannot be empty")

    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)

    if not sanitized:
        raise ValueError(f"Invalid identifier: {name}")

    if sanitized[0].isdigit():
        sanitized = '_' + sanitized

    return sanitized


def validate_table_name(full_table_name: str) -> Tuple[str, str]:
    """Validate and parse a fully qualified table name."""
    if '.' in full_table_name:
        parts = full_table_name.split('.', 1)
        database = sanitize_identifier(parts[0])
        table = sanitize_identifier(parts[1])
    else:
        database = config.DEFAULT_DATABASE
        table = sanitize_identifier(full_table_name)

    return database, table


def find_original_column_name(column_map_original: Dict, col_name_lower: str, default: str) -> str:
    """Find original column name using case-insensitive lookup."""
    if not column_map_original:
        return default
    for k in column_map_original.keys():
        if k is not None:
            try:
                if str(k).lower() == col_name_lower:
                    return k
            except (TypeError, AttributeError):
                continue
    return default


# =============================================================================
# Optimized Beeline Execution (using session pool)
# =============================================================================

def execute_beeline_pooled(sql: str, database: str = None, timeout: int = None) -> Tuple[bool, Dict]:
    """
    Execute SQL using a pooled beeline session.

    This is the OPTIMIZED version that reuses sessions.
    """
    session = session_pool.acquire(timeout=30)

    if not session:
        logger.error("Failed to acquire session from pool")
        return False, {'error': 'No session available'}

    try:
        return session.execute(sql, timeout)
    finally:
        session_pool.release(session)


def execute_beeline_subprocess(sql: str, database: str = None,
                              timeout: int = None, output_format: str = 'csv2') -> Tuple[bool, Dict]:
    """
    Execute SQL via subprocess (FALLBACK - creates new process each time).

    Use this for schema operations or when session pool is unavailable.
    """
    db = database or config.DEFAULT_DATABASE

    jdbc_url = (
        f"jdbc:hive2://{config.ZOOKEEPER_HOSTS}/{db};"
        f"principal={config.HIVE_PRINCIPAL};"
        f"serviceDiscoveryMode=zooKeeper;"
        f"zookeeperNamespace={config.ZK_NAMESPACE};"
        f"ssl=true;"
        f"sslTrustStore={config.TRUSTSTORE_PATH};"
        f"trustStoreType=jks"
    )

    query_timeout = timeout or config.QUERY_TIMEOUT
    sql_escaped = sql.replace('"', '\\"')

    if config.YARN_QUEUE:
        queue_setting = f"SET mapreduce.job.queuename={config.YARN_QUEUE}; SET tez.queue.name={config.YARN_QUEUE}; "
        sql_with_queue = queue_setting + sql_escaped
    else:
        sql_with_queue = sql_escaped

    cmd = (
        f'export JAVA_HOME="{config.JAVA_HOME}" && '
        f'export PATH="$JAVA_HOME/bin:$PATH" && '
        f'beeline -u "{jdbc_url}" '
        f'-e "{sql_with_queue}" '
        f'--silent=true '
        f'--outputformat={output_format} '
        f'--showHeader=true '
        f'--color=false'
    )

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=query_timeout
        )

        elapsed = time.time() - start_time
        elapsed_ms = int(elapsed * 1000)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
            return False, {'error': error_msg, 'elapsed_ms': elapsed_ms, 'returncode': result.returncode}

        output = result.stdout.strip()
        lines = [l for l in output.split('\n') if not l.startswith('INFO') and not l.startswith('WARNING')]
        output = '\n'.join(lines).strip()

        if not output:
            return True, {'data': [], 'rows': 0, 'elapsed_ms': elapsed_ms}

        if output_format == 'csv2':
            try:
                reader = csv.DictReader(io.StringIO(output))
                data = []
                for row in reader:
                    clean_row = {}
                    for key, value in row.items():
                        if key and '.' in key:
                            clean_key = key.split('.')[-1]
                        else:
                            clean_key = key
                        clean_row[clean_key] = value
                    data.append(clean_row)
                return True, {'data': data, 'rows': len(data), 'elapsed_ms': elapsed_ms}
            except Exception:
                return True, {'data': output, 'elapsed_ms': elapsed_ms}
        else:
            return True, {'data': output, 'elapsed_ms': elapsed_ms}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return False, {'error': f'Query timeout after {query_timeout}s', 'elapsed_ms': int(elapsed * 1000)}

    except Exception as e:
        elapsed = time.time() - start_time
        return False, {'error': str(e), 'elapsed_ms': int(elapsed * 1000)}


# Use pooled execution by default for write operations
def execute_beeline(sql: str, database: str = None, timeout: int = None,
                   output_format: str = 'csv2', use_pool: bool = True) -> Tuple[bool, Dict]:
    """
    Main execution function - uses pool for writes, subprocess for schema ops.
    """
    sql_upper = sql.upper().strip()

    # Use subprocess for schema operations (they're infrequent)
    if sql_upper.startswith('DESCRIBE') or sql_upper.startswith('SHOW'):
        return execute_beeline_subprocess(sql, database, timeout, output_format)

    # Use pool for data operations (INSERT, UPDATE, DELETE, SELECT)
    if use_pool:
        return execute_beeline_pooled(sql, database, timeout)

    return execute_beeline_subprocess(sql, database, timeout, output_format)


# =============================================================================
# Schema Operations
# =============================================================================

def get_table_schema(database: str, table: str, force_refresh: bool = False) -> Optional[Dict]:
    """Get table schema with caching."""
    if not force_refresh:
        cached = schema_cache.get(database, table)
        if cached:
            return cached

    sql = f"DESCRIBE {database}.{table}"
    success, result = execute_beeline(sql, database, timeout=120, use_pool=False)

    if not success:
        logger.error(f"Failed to get schema for {database}.{table}: {result.get('error')}")
        return None

    columns = []
    column_map = {}
    column_map_original = {}

    data = result.get('data', [])

    # Parse based on data type
    if isinstance(data, str):
        lines = data.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('+') or line.startswith('|-'):
                continue
            if set(line.replace(' ', '')) <= {'+', '-', '|'}:
                continue
            if '|' in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2:
                    col_name = parts[0].strip()
                    data_type = parts[1].strip()
                    if col_name.lower() in ('col_name', 'name', 'column_name', 'field'):
                        continue
                    if not col_name or col_name.startswith('-') or col_name.startswith('+'):
                        continue
                    columns.append({'name': col_name, 'type': data_type or 'string'})
                    column_map[col_name.lower()] = data_type or 'string'
                    column_map_original[col_name] = data_type or 'string'

    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                col_name = None
                data_type = None

                # Try to find column name and type from dict
                for key, value in row.items():
                    if key is None:
                        continue
                    key_lower = str(key).lower()
                    if any(k in key_lower for k in ['col_name', 'name', 'field', 'column']):
                        col_name = str(value).strip() if value else None
                    elif any(k in key_lower for k in ['data_type', 'type']):
                        data_type = str(value).strip() if value else None

                # Fallback to positional
                if not col_name:
                    values = list(row.values())
                    if values:
                        col_name = str(values[0]).strip() if values[0] else None
                    if len(values) > 1:
                        data_type = str(values[1]).strip() if values[1] else None

                if col_name and col_name.lower() not in ('col_name', 'name', 'column_name', ''):
                    columns.append({'name': col_name, 'type': data_type or 'string'})
                    column_map[col_name.lower()] = data_type or 'string'
                    column_map_original[col_name] = data_type or 'string'

    if not columns:
        logger.error(f"No columns found for {database}.{table}")
        return None

    schema = {
        'columns': columns,
        'column_map': column_map,
        'column_map_original': column_map_original,
        'primary_key': columns[0]['name'] if columns else None
    }

    schema_cache.set(database, table, schema)
    return schema


# =============================================================================
# Audit Logging
# =============================================================================

def log_audit(operation: str, database: str, table: str, record_id: str = None,
              old_values: Dict = None, new_values: Dict = None, user: str = None,
              ip_address: str = None, success: bool = True, error_message: str = None,
              elapsed_ms: int = 0) -> bool:
    """Log an audit record to the audit table."""
    if not config.AUDIT_ENABLED:
        return True

    try:
        audit_id = hashlib.md5(f"{time.time()}{operation}{table}".encode()).hexdigest()[:16]
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        old_json = json.dumps(old_values) if old_values else None
        new_json = json.dumps(new_values) if new_values else None

        old_escaped = old_json.replace("'", "''") if old_json else 'NULL'
        new_escaped = new_json.replace("'", "''") if new_json else 'NULL'
        error_escaped = error_message.replace("'", "''") if error_message else 'NULL'

        sql = f"""
        INSERT INTO {config.AUDIT_DATABASE}.{config.AUDIT_TABLE}
        (audit_id, operation, database_name, table_name, record_id, old_values, new_values,
         performed_by, ip_address, performed_at, success, error_message, elapsed_ms)
        VALUES
        ('{audit_id}', '{operation}', '{database}', '{table}',
         {f"'{record_id}'" if record_id else 'NULL'},
         {f"'{old_escaped}'" if old_json else 'NULL'},
         {f"'{new_escaped}'" if new_json else 'NULL'},
         '{user or 'system'}', '{ip_address or '0.0.0.0'}',
         '{now}', {str(success).upper()},
         {f"'{error_escaped}'" if error_message else 'NULL'},
         {elapsed_ms})
        """

        # Use subprocess for audit (don't block main queries)
        execute_beeline(sql, config.AUDIT_DATABASE, timeout=60, use_pool=False)
        return True

    except Exception as e:
        logger.error(f"Failed to log audit: {str(e)}")
        return False


# =============================================================================
# Authentication Decorator
# =============================================================================

def require_api_key(f):
    """Decorator to require API key if configured."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if config.API_KEY:
            provided_key = request.headers.get('X-API-Key', '')
            if provided_key != config.API_KEY:
                return jsonify({'success': False, 'error': 'Invalid or missing API key'}), 401

        g.user = request.headers.get('X-User', 'anonymous')
        g.ip_address = request.remote_addr

        return f(*args, **kwargs)
    return decorated


def with_query_limit(f):
    """Decorator to enforce concurrent query limit."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not query_semaphore.acquire(blocking=False):
            return jsonify({
                'success': False,
                'error': 'Too many concurrent queries',
                'max_concurrent': config.MAX_CONCURRENT
            }), 429
        try:
            return f(*args, **kwargs)
        finally:
            query_semaphore.release()
    return decorated


# =============================================================================
# API Endpoints - Basic
# =============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'service': 'hive-proxy',
        'version': '2.1.0-optimized',
        'optimization': 'beeline_session_pool',
        'config': {
            'database': config.DEFAULT_DATABASE,
            'audit_enabled': config.AUDIT_ENABLED,
            'timeout': config.QUERY_TIMEOUT,
            'max_concurrent': config.MAX_CONCURRENT,
            'yarn_queue': config.YARN_QUEUE,
            'session_pool_size': config.SESSION_POOL_SIZE
        },
        'stats': query_stats,
        'session_pool': session_pool.stats(),
        'schema_cache': schema_cache.stats()
    })


@app.route('/test', methods=['GET'])
@require_api_key
def test_connection():
    """Test Hive connection."""
    success, result = execute_beeline("SELECT 1 AS test", timeout=60)

    if success:
        return jsonify({
            'success': True,
            'status': 'connected',
            'result': result
        })
    else:
        return jsonify({
            'success': False,
            'status': 'failed',
            'error': result
        }), 500


# =============================================================================
# API Endpoints - Schema
# =============================================================================

@app.route('/schema/<path:table_name>', methods=['GET'])
@require_api_key
def get_schema(table_name: str):
    """Get table schema."""
    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'

        schema = get_table_schema(database, table, force_refresh=force_refresh)

        if schema:
            return jsonify({
                'success': True,
                'database': database,
                'table': table,
                'schema': schema
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Table {database}.{table} not found or error getting schema'
            }), 404

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/schema/cache/clear', methods=['POST'])
@require_api_key
def clear_schema_cache():
    """Clear schema cache."""
    data = request.get_json() or {}
    database = data.get('database')
    table = data.get('table')

    schema_cache.invalidate(database, table)

    return jsonify({
        'success': True,
        'message': 'Cache cleared',
        'scope': f"{database or '*'}.{table or '*'}"
    })


# =============================================================================
# API Endpoints - Dynamic CRUD (OPTIMIZED with session pool)
# =============================================================================

@app.route('/insert/<path:table_name>', methods=['POST'])
@require_api_key
@with_query_limit
def dynamic_insert(table_name: str):
    """
    Dynamic INSERT with automatic type casting.

    OPTIMIZED: Uses beeline session pool for fast execution.
    """
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        req_data = request.get_json()
        if not req_data or 'data' not in req_data:
            return jsonify({'success': False, 'error': 'Missing data parameter'}), 400

        record_data = req_data['data']

        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']
        column_map_original = schema.get('column_map_original', column_map)

        columns = []
        values = []

        for col_name, value in record_data.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()

            if safe_col_lower not in column_map:
                logger.warning(f"Column '{safe_col}' not in schema, skipping")
                continue

            col_type = column_map[safe_col_lower]
            formatted_value = format_value_for_hive(value, col_type)

            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            columns.append(original_col)
            values.append(formatted_value)

        if not columns:
            return jsonify({
                'success': False,
                'error': 'No valid columns provided',
                'input_columns': list(record_data.keys()),
                'schema_columns': list(column_map.keys())[:10]
            }), 400

        sql = f"INSERT INTO {database}.{table} ({', '.join(columns)}) VALUES ({', '.join(values)})"

        logger.info(f"Dynamic INSERT into {database}.{table} (using session pool)")

        with query_lock:
            query_stats['total'] += 1
            query_stats['insert'] += 1

        # Use session pool for fast execution
        success, result = execute_beeline(sql, database, use_pool=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        record_id = record_data.get(schema.get('primary_key'))
        log_audit(
            operation='INSERT',
            database=database,
            table=table,
            record_id=str(record_id) if record_id else None,
            new_values=record_data,
            user=getattr(g, 'user', None),
            ip_address=getattr(g, 'ip_address', None),
            success=success,
            error_message=result.get('error') if not success else None,
            elapsed_ms=elapsed_ms
        )

        with query_lock:
            if success:
                query_stats['success'] += 1
            else:
                query_stats['failed'] += 1

        if success:
            return jsonify({
                'success': True,
                'operation': 'INSERT',
                'table': f"{database}.{table}",
                'elapsed_ms': elapsed_ms,
                'session_pooled': True
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error'),
                'elapsed_ms': elapsed_ms
            }), 500

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f"INSERT error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/update/<path:table_name>', methods=['POST', 'PUT'])
@require_api_key
@with_query_limit
def dynamic_update(table_name: str):
    """Dynamic UPDATE with automatic type casting."""
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        req_data = request.get_json()
        if not req_data:
            return jsonify({'success': False, 'error': 'Missing request body'}), 400

        where_clause = req_data.get('where', {})
        update_data = req_data.get('data', {})

        if not where_clause:
            return jsonify({'success': False, 'error': 'WHERE clause required for UPDATE'}), 400

        if not update_data:
            return jsonify({'success': False, 'error': 'No data to update'}), 400

        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']
        column_map_original = schema.get('column_map_original', column_map)

        # Build SET clause
        set_clauses = []
        for col_name, value in update_data.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()

            if safe_col_lower not in column_map:
                continue

            col_type = column_map[safe_col_lower]
            formatted_value = format_value_for_hive(value, col_type)
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            set_clauses.append(f"{original_col} = {formatted_value}")

        if not set_clauses:
            return jsonify({
                'success': False,
                'error': 'No valid columns to update'
            }), 400

        # Build WHERE clause
        where_parts = []
        for col_name, value in where_clause.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()
            col_type = column_map.get(safe_col_lower, 'string')
            formatted_value = format_value_for_hive(value, col_type)
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            where_parts.append(f"{original_col} = {formatted_value}")

        sql = f"UPDATE {database}.{table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_parts)}"

        logger.info(f"Dynamic UPDATE on {database}.{table} (using session pool)")

        with query_lock:
            query_stats['total'] += 1
            query_stats['update'] += 1

        success, result = execute_beeline(sql, database, use_pool=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        pk_col = schema.get('primary_key')
        pk_value = where_clause.get(pk_col) if pk_col else None

        log_audit(
            operation='UPDATE',
            database=database,
            table=table,
            record_id=str(pk_value) if pk_value else None,
            new_values=update_data,
            user=getattr(g, 'user', None),
            ip_address=getattr(g, 'ip_address', None),
            success=success,
            error_message=result.get('error') if not success else None,
            elapsed_ms=elapsed_ms
        )

        with query_lock:
            if success:
                query_stats['success'] += 1
            else:
                query_stats['failed'] += 1

        if success:
            return jsonify({
                'success': True,
                'operation': 'UPDATE',
                'table': f"{database}.{table}",
                'elapsed_ms': elapsed_ms,
                'session_pooled': True
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error'),
                'elapsed_ms': elapsed_ms
            }), 500

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f"UPDATE error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/delete/<path:table_name>', methods=['POST', 'DELETE'])
@require_api_key
@with_query_limit
def dynamic_delete(table_name: str):
    """Dynamic DELETE with automatic type casting."""
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        req_data = request.get_json()
        if not req_data:
            return jsonify({'success': False, 'error': 'Missing request body'}), 400

        where_clause = req_data.get('where', {})
        soft_delete = req_data.get('soft_delete', True)
        soft_delete_column = req_data.get('soft_delete_column', 'deleted_at')
        deleted_by = req_data.get('deleted_by', getattr(g, 'user', 'system'))

        if not where_clause:
            return jsonify({'success': False, 'error': 'WHERE clause required for DELETE'}), 400

        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']
        column_map_original = schema.get('column_map_original', column_map)

        # Build WHERE clause
        where_parts = []
        for col_name, value in where_clause.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()
            col_type = column_map.get(safe_col_lower, 'string')
            formatted_value = format_value_for_hive(value, col_type)
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            where_parts.append(f"{original_col} = {formatted_value}")

        soft_delete_col_lower = soft_delete_column.lower()
        if soft_delete and soft_delete_col_lower in column_map:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            original_soft_del_col = find_original_column_name(column_map_original, soft_delete_col_lower, soft_delete_column)
            set_clauses = [f"{original_soft_del_col} = '{now}'"]

            if 'updated_at' in column_map:
                original_updated_at = find_original_column_name(column_map_original, 'updated_at', 'updated_at')
                set_clauses.append(f"{original_updated_at} = '{now}'")
            if 'updated_by' in column_map:
                original_updated_by = find_original_column_name(column_map_original, 'updated_by', 'updated_by')
                set_clauses.append(f"{original_updated_by} = '{deleted_by}'")

            sql = f"UPDATE {database}.{table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_parts)}"
            operation = 'SOFT_DELETE'
        else:
            sql = f"DELETE FROM {database}.{table} WHERE {' AND '.join(where_parts)}"
            operation = 'HARD_DELETE'

        logger.info(f"Dynamic {operation} on {database}.{table} (using session pool)")

        with query_lock:
            query_stats['total'] += 1
            query_stats['delete'] += 1

        success, result = execute_beeline(sql, database, use_pool=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        pk_col = schema.get('primary_key')
        pk_value = where_clause.get(pk_col) if pk_col else None

        log_audit(
            operation=operation,
            database=database,
            table=table,
            record_id=str(pk_value) if pk_value else None,
            user=getattr(g, 'user', None),
            ip_address=getattr(g, 'ip_address', None),
            success=success,
            error_message=result.get('error') if not success else None,
            elapsed_ms=elapsed_ms
        )

        with query_lock:
            if success:
                query_stats['success'] += 1
            else:
                query_stats['failed'] += 1

        if success:
            return jsonify({
                'success': True,
                'operation': operation,
                'table': f"{database}.{table}",
                'elapsed_ms': elapsed_ms,
                'session_pooled': True
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error'),
                'elapsed_ms': elapsed_ms
            }), 500

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f"DELETE error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# API Endpoints - Query
# =============================================================================

@app.route('/query', methods=['POST'])
@require_api_key
@with_query_limit
def execute_query():
    """Execute a SELECT query."""
    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'sql' not in data:
            return jsonify({'success': False, 'error': 'Missing sql parameter'}), 400

        sql = data['sql'].strip()
        database = data.get('database', config.DEFAULT_DATABASE)
        timeout = data.get('timeout', config.QUERY_TIMEOUT)

        sql_upper = sql.upper()
        if not (sql_upper.startswith('SELECT') or
                sql_upper.startswith('SHOW') or
                sql_upper.startswith('DESCRIBE')):
            return jsonify({
                'success': False,
                'error': 'Only SELECT, SHOW, DESCRIBE allowed. Use /execute for writes.'
            }), 400

        logger.info(f"Query: {sql[:100]}...")

        with query_lock:
            query_stats['total'] += 1
            query_stats['select'] += 1

        success, result = execute_beeline(sql, database, timeout, use_pool=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        with query_lock:
            if success:
                query_stats['success'] += 1
            else:
                query_stats['failed'] += 1

        result['elapsed_ms'] = elapsed_ms

        if success:
            return jsonify({'success': True, **result})
        else:
            return jsonify({'success': False, **result}), 500

    except Exception as e:
        logger.exception(f"Query error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/execute', methods=['POST'])
@require_api_key
@with_query_limit
def execute_write():
    """Execute a raw write query (INSERT, UPDATE, DELETE)."""
    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'sql' not in data:
            return jsonify({'success': False, 'error': 'Missing sql parameter'}), 400

        sql = data['sql'].strip()
        database = data.get('database', config.DEFAULT_DATABASE)
        timeout = data.get('timeout', config.QUERY_TIMEOUT)

        sql_upper = sql.upper()
        blocked = ['DROP DATABASE', 'DROP TABLE', 'TRUNCATE', 'ALTER TABLE']
        for blocked_op in blocked:
            if blocked_op in sql_upper:
                return jsonify({
                    'success': False,
                    'error': f'{blocked_op} not allowed'
                }), 403

        logger.info(f"Execute: {sql[:100]}...")

        with query_lock:
            query_stats['total'] += 1

        success, result = execute_beeline(sql, database, timeout, use_pool=True)
        elapsed_ms = int((time.time() - start_time) * 1000)

        with query_lock:
            if success:
                query_stats['success'] += 1
            else:
                query_stats['failed'] += 1

        result['elapsed_ms'] = elapsed_ms

        if success:
            return jsonify({'success': True, **result})
        else:
            return jsonify({'success': False, **result}), 500

    except Exception as e:
        logger.exception(f"Execute error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# API Endpoints - Batch Operations
# =============================================================================

@app.route('/batch/insert/<path:table_name>', methods=['POST'])
@require_api_key
@with_query_limit
def batch_insert(table_name: str):
    """
    Batch INSERT multiple records in a single session.

    POST /batch/insert/mrw_ima.portfolio_hive
    {
        "records": [
            {"portfolio_id": "PF001", "name": "Portfolio 1"},
            {"portfolio_id": "PF002", "name": "Portfolio 2"}
        ]
    }
    """
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        req_data = request.get_json()

        if not req_data or 'records' not in req_data:
            return jsonify({'success': False, 'error': 'Missing records parameter'}), 400

        records = req_data['records']
        if not records:
            return jsonify({'success': False, 'error': 'Empty records list'}), 400

        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({'success': False, 'error': f'Cannot get schema for {database}.{table}'}), 500

        column_map = schema['column_map']
        column_map_original = schema.get('column_map_original', column_map)

        # Build all INSERT statements
        insert_sqls = []

        for record_data in records:
            columns = []
            values = []

            for col_name, value in record_data.items():
                safe_col = sanitize_identifier(col_name)
                safe_col_lower = safe_col.lower()

                if safe_col_lower not in column_map:
                    continue

                col_type = column_map[safe_col_lower]
                formatted_value = format_value_for_hive(value, col_type)
                original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
                columns.append(original_col)
                values.append(formatted_value)

            if columns:
                sql = f"INSERT INTO {database}.{table} ({', '.join(columns)}) VALUES ({', '.join(values)})"
                insert_sqls.append(sql)

        if not insert_sqls:
            return jsonify({'success': False, 'error': 'No valid records to insert'}), 400

        # Execute all in one session
        results = []
        success_count = 0
        fail_count = 0

        session = session_pool.acquire(timeout=30)
        if not session:
            return jsonify({'success': False, 'error': 'No session available'}), 503

        try:
            for i, sql in enumerate(insert_sqls):
                success, result = session.execute(sql)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                results.append({'index': i, 'success': success, 'error': result.get('error')})
        finally:
            session_pool.release(session)

        elapsed_ms = int((time.time() - start_time) * 1000)

        with query_lock:
            query_stats['total'] += len(records)
            query_stats['insert'] += len(records)
            query_stats['success'] += success_count
            query_stats['failed'] += fail_count

        return jsonify({
            'success': fail_count == 0,
            'operation': 'BATCH_INSERT',
            'table': f"{database}.{table}",
            'total': len(records),
            'success_count': success_count,
            'fail_count': fail_count,
            'elapsed_ms': elapsed_ms,
            'details': results if fail_count > 0 else None
        })

    except Exception as e:
        logger.exception(f"Batch INSERT error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# API Endpoints - Utility
# =============================================================================

@app.route('/databases', methods=['GET'])
@require_api_key
def list_databases():
    """List all databases."""
    success, result = execute_beeline("SHOW DATABASES", timeout=60, use_pool=False)

    if success:
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 500


@app.route('/tables', methods=['GET'])
@require_api_key
def list_tables():
    """List tables in a database."""
    database = request.args.get('database', config.DEFAULT_DATABASE)
    success, result = execute_beeline(f"SHOW TABLES IN {database}", timeout=60, use_pool=False)

    if success:
        return jsonify({'success': True, 'database': database, **result})
    else:
        return jsonify({'success': False, **result}), 500


@app.route('/stats', methods=['GET'])
@require_api_key
def get_stats():
    """Get detailed statistics."""
    return jsonify({
        'success': True,
        'stats': query_stats,
        'session_pool': session_pool.stats(),
        'schema_cache': schema_cache.stats(),
        'config': {
            'database': config.DEFAULT_DATABASE,
            'audit_enabled': config.AUDIT_ENABLED,
            'max_concurrent': config.MAX_CONCURRENT,
            'timeout': config.QUERY_TIMEOUT,
            'session_pool_size': config.SESSION_POOL_SIZE
        }
    })


@app.route('/sessions/warmup', methods=['POST'])
@require_api_key
def warmup_sessions():
    """
    Pre-create sessions for faster first requests.

    POST /sessions/warmup
    {"count": 2}
    """
    data = request.get_json() or {}
    count = min(data.get('count', 1), config.SESSION_POOL_SIZE)

    created = 0
    for _ in range(count):
        session = session_pool._create_session()
        if session:
            session_pool.release(session)
            created += 1

    return jsonify({
        'success': True,
        'requested': count,
        'created': created,
        'pool_stats': session_pool.stats()
    })


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'success': False, 'error': 'Bad request'}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("HIVE REST PROXY v2.1 - OPTIMIZED")
    print("=" * 60)
    print(f"Database: {config.DEFAULT_DATABASE}")
    print(f"Audit: {config.AUDIT_ENABLED} -> {config.AUDIT_DATABASE}.{config.AUDIT_TABLE}")
    print(f"Timeout: {config.QUERY_TIMEOUT}s")
    print(f"Max Concurrent: {config.MAX_CONCURRENT}")
    print(f"API Key: {'enabled' if config.API_KEY else 'disabled'}")
    print(f"Schema Cache TTL: {config.SCHEMA_CACHE_TTL}s")
    print("-" * 60)
    print("OPTIMIZATION: Beeline Session Pool")
    print(f"  Pool Size: {config.SESSION_POOL_SIZE}")
    print(f"  Session Max Age: {config.SESSION_MAX_AGE}s")
    print(f"  Health Check: {config.SESSION_HEALTH_CHECK_INTERVAL}s")
    print("=" * 60)
    print("Expected Performance:")
    print("  First request: ~10s (creates session)")
    print("  Subsequent:    ~1-3s (reuses session)")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)
