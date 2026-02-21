#!/usr/bin/env python3
"""
Hive REST Proxy v2.0 - Enhanced with Dynamic Table Operations

Features:
- Dynamic INSERT/UPDATE/DELETE with automatic type casting
- Schema caching for performance
- Audit logging to mrw_ima.hive_proxy_audit
- Corner case handling (SQL injection, NULL, special chars, timestamps)
- Rate limiting and connection pooling
- Health checks and monitoring

Deployment:
    gunicorn -b 0.0.0.0:5000 -w 4 --timeout 300 app_v2:app

Version: 2.0.0
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
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional, Union
from functools import wraps
from threading import Lock, Semaphore
from collections import OrderedDict

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
    'delete': 0
}

# =============================================================================
# Schema Cache
# =============================================================================

class SchemaCache:
    """
    Cache for table schemas to avoid repeated DESCRIBE queries.

    Schema format:
    {
        'database.table': {
            'columns': [{'name': 'col1', 'type': 'string'}, ...],
            'primary_key': 'id',
            'cached_at': timestamp,
            'hash': 'xxxx'
        }
    }
    """

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
                # Check if cached_at exists and is valid
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
    """Extract base type from Hive type string (e.g., 'varchar(255)' -> 'varchar')."""
    type_str = type_str.lower().strip()
    # Handle parameterized types
    match = re.match(r'^(\w+)', type_str)
    return match.group(1) if match else 'string'


def format_value_for_hive(value: Any, hive_type: str) -> str:
    """
    Format a Python value for Hive SQL based on column type.

    Handles:
    - NULL values
    - String escaping (SQL injection prevention)
    - Timestamps and dates
    - Booleans
    - Numbers
    - Special characters
    """
    # Handle None/NULL
    if value is None:
        return 'NULL'

    # Handle empty string (could be NULL or empty depending on context)
    if value == '':
        return "NULL" if hive_type in ('timestamp', 'date', 'int', 'bigint', 'float', 'double', 'decimal', 'boolean') else "''"

    base_type = parse_hive_type(hive_type)

    # String types - escape single quotes and special characters
    if base_type in ('string', 'varchar', 'char'):
        # Escape single quotes by doubling them
        escaped = str(value).replace("'", "''")
        # Escape backslashes
        escaped = escaped.replace("\\", "\\\\")
        return f"'{escaped}'"

    # Numeric types
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

    # Boolean
    if base_type == 'boolean':
        if isinstance(value, bool):
            return 'TRUE' if value else 'FALSE'
        if isinstance(value, str):
            return 'TRUE' if value.lower() in ('true', '1', 'yes') else 'FALSE'
        return 'TRUE' if value else 'FALSE'

    # Timestamp
    if base_type == 'timestamp':
        if isinstance(value, datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
        if isinstance(value, str):
            value_lower = value.lower().strip()
            # Handle 'now' and 'current_timestamp' keywords
            if value_lower in ('now', 'current_timestamp', 'current'):
                return 'CURRENT_TIMESTAMP'
            # Try to parse common formats
            for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(value, fmt)
                    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}'"
                except ValueError:
                    continue
            # Return as-is if can't parse
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        # For other types, use current timestamp
        return 'CURRENT_TIMESTAMP'

    # Date
    if base_type == 'date':
        if isinstance(value, (datetime, date)):
            return f"'{value.strftime('%Y-%m-%d')}'"
        if isinstance(value, str):
            return f"'{value[:10]}'"  # Take first 10 chars (YYYY-MM-DD)
        return 'NULL'

    # Default: treat as string
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sanitize_identifier(name: str) -> str:
    """
    Sanitize SQL identifier (table/column name) to prevent injection.
    Only allows alphanumeric characters and underscores.
    """
    if not name:
        raise ValueError("Identifier cannot be empty")

    # Only allow alphanumeric and underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)

    if not sanitized:
        raise ValueError(f"Invalid identifier: {name}")

    # Cannot start with a number
    if sanitized[0].isdigit():
        sanitized = '_' + sanitized

    return sanitized


def validate_table_name(full_table_name: str) -> Tuple[str, str]:
    """
    Validate and parse a fully qualified table name (database.table).
    Returns (database, table) tuple.
    """
    if '.' in full_table_name:
        parts = full_table_name.split('.', 1)
        database = sanitize_identifier(parts[0])
        table = sanitize_identifier(parts[1])
    else:
        database = config.DEFAULT_DATABASE
        table = sanitize_identifier(full_table_name)

    return database, table


def find_original_column_name(column_map_original: Dict, col_name_lower: str, default: str) -> str:
    """
    Find the original column name from the schema using case-insensitive lookup.
    Returns the original case column name or the default if not found.
    """
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
# Beeline Execution
# =============================================================================

def build_jdbc_url(database: str = None) -> str:
    """Build JDBC URL for beeline."""
    db = database or config.DEFAULT_DATABASE

    url = (
        f"jdbc:hive2://{config.ZOOKEEPER_HOSTS}/{db};"
        f"principal={config.HIVE_PRINCIPAL};"
        f"serviceDiscoveryMode=zooKeeper;"
        f"zookeeperNamespace={config.ZK_NAMESPACE};"
        f"ssl=true;"
        f"sslTrustStore={config.TRUSTSTORE_PATH};"
        f"trustStoreType=jks"
    )

    return url


def execute_beeline(sql: str, database: str = None,
                    timeout: int = None, output_format: str = 'csv2') -> Tuple[bool, Dict]:
    """
    Execute SQL via beeline with enhanced error handling.

    Returns:
        Tuple of (success: bool, result: dict)
    """
    jdbc_url = build_jdbc_url(database)
    query_timeout = timeout or config.QUERY_TIMEOUT

    # Escape double quotes in SQL for shell
    sql_escaped = sql.replace('"', '\\"')

    # Build beeline command
    cmd = (
        f'export JAVA_HOME="{config.JAVA_HOME}" && '
        f'export PATH="$JAVA_HOME/bin:$PATH" && '
        f'beeline -u "{jdbc_url}" '
        f'-e "{sql_escaped}" '
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

        # Check for errors
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
            logger.error(f"Beeline failed: {error_msg}")
            return False, {
                'error': error_msg,
                'elapsed_ms': elapsed_ms,
                'returncode': result.returncode
            }

        # Parse output
        output = result.stdout.strip()

        # Filter out Hive info messages
        lines = [l for l in output.split('\n') if not l.startswith('INFO') and not l.startswith('WARNING')]
        output = '\n'.join(lines).strip()

        if not output:
            return True, {'data': [], 'rows': 0, 'elapsed_ms': elapsed_ms}

        # Parse CSV output
        if output_format == 'csv2':
            try:
                reader = csv.DictReader(io.StringIO(output))
                data = [dict(row) for row in reader]
                return True, {
                    'data': data,
                    'rows': len(data),
                    'elapsed_ms': elapsed_ms
                }
            except Exception as e:
                # Not valid CSV, return raw
                return True, {'data': output, 'elapsed_ms': elapsed_ms}
        else:
            return True, {'data': output, 'elapsed_ms': elapsed_ms}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error(f"Query timed out after {query_timeout}s")
        return False, {
            'error': f'Query timeout after {query_timeout}s',
            'elapsed_ms': int(elapsed * 1000)
        }

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Query execution error: {str(e)}")
        return False, {
            'error': str(e),
            'elapsed_ms': int(elapsed * 1000)
        }


# =============================================================================
# Schema Operations
# =============================================================================

def get_table_schema(database: str, table: str, force_refresh: bool = False) -> Optional[Dict]:
    """
    Get table schema with caching.

    Returns:
        {
            'columns': [{'name': 'col1', 'type': 'string'}, ...],
            'column_map': {'col1': 'string', ...},  # lowercase keys for case-insensitive lookup
            'column_map_original': {'col1': 'string', ...},  # original case
            'primary_key': 'id' (guessed from first column)
        }
    """
    # Check cache first
    if not force_refresh:
        cached = schema_cache.get(database, table)
        if cached:
            return cached

    # Query schema from Hive
    sql = f"DESCRIBE {database}.{table}"
    success, result = execute_beeline(sql, database, timeout=120)

    if not success:
        logger.error(f"Failed to get schema for {database}.{table}: {result.get('error')}")
        return None

    # Parse DESCRIBE output
    columns = []
    column_map = {}  # lowercase keys
    column_map_original = {}  # original case

    data = result.get('data', [])
    logger.info(f"Schema data for {database}.{table}: type={type(data)}, length={len(data) if isinstance(data, list) else 'N/A'}")

    # Log first few rows to understand format
    if data and isinstance(data, list):
        for i, row in enumerate(data[:3]):
            logger.info(f"  Row {i}: {row} (type: {type(row).__name__})")
            if isinstance(row, dict):
                logger.info(f"    Keys: {list(row.keys())}")

    for row in data:
        col_name = None
        data_type = None

        if isinstance(row, dict):
            # Get all keys from the dict (filter out None keys)
            keys = [k for k in row.keys() if k is not None]
            values = [v for v in row.values()]

            # DESCRIBE output in CSV2 format typically has headers like:
            # 'col_name', 'data_type', 'comment'
            # But could also be: 'name', 'type' or numbered

            if len(keys) >= 2:
                # Try multiple key patterns to find column name and type
                col_name_keys = ['col_name', 'name', 'field', 'column_name', 'column']
                data_type_keys = ['data_type', 'type', 'datatype', 'column_type']

                for key in keys:
                    if key is None:
                        continue
                    try:
                        key_lower = str(key).lower().strip()
                    except (AttributeError, TypeError):
                        continue

                    # Check for column name key
                    if any(k in key_lower for k in col_name_keys):
                        val = row.get(key)
                        col_name = str(val).strip() if val is not None else None
                    # Check for data type key
                    elif any(k in key_lower for k in data_type_keys):
                        val = row.get(key)
                        data_type = str(val).strip() if val is not None else None

                # If still not found by key names, use positional (first=name, second=type)
                if not col_name and values:
                    first_val = values[0]
                    if first_val is not None:
                        first_val_str = str(first_val).strip()
                        # Make sure it looks like a column name (not empty, not a header)
                        if first_val_str and first_val_str.lower() not in ('col_name', 'name', 'column_name', ''):
                            col_name = first_val_str

                if not data_type and len(values) > 1:
                    second_val = values[1]
                    if second_val is not None:
                        second_val_str = str(second_val).strip()
                        if second_val_str and second_val_str.lower() not in ('data_type', 'type', ''):
                            data_type = second_val_str

            elif len(keys) == 1:
                # Single column - probably just column name
                first_val = values[0] if values else None
                col_name = str(first_val).strip() if first_val is not None else None
                data_type = 'string'

        elif isinstance(row, str):
            # Parse string format: "col_name    data_type    comment"
            row = row.strip()
            if not row:
                continue
            parts = row.split()
            if len(parts) >= 2:
                col_name = parts[0].strip()
                data_type = parts[1].strip()
            elif len(parts) == 1:
                col_name = parts[0].strip()
                data_type = 'string'

        # Skip empty rows, partition info, and header markers
        if col_name is None or col_name == '':
            continue

        # Ensure col_name is a string
        try:
            col_name = str(col_name).strip()
        except (TypeError, AttributeError):
            continue

        if not col_name:
            continue

        if col_name.startswith('#') or col_name.startswith('|'):
            continue
        # Skip header row values
        col_name_lower = col_name.lower()
        if col_name_lower in ('', 'col_name', 'name', 'column_name', 'field'):
            continue
        # Skip partition markers
        if col_name.startswith('# ') or 'Partition' in col_name:
            continue

        # Clean up column name (remove table prefix if present)
        if '.' in col_name:
            col_name = col_name.split('.')[-1]

        # Store with both original case and lowercase for lookup
        columns.append({'name': col_name, 'type': data_type or 'string'})
        column_map[col_name.lower()] = data_type or 'string'
        column_map_original[col_name] = data_type or 'string'

    logger.info(f"Parsed {len(columns)} columns for {database}.{table}: {[c['name'] for c in columns[:5]]}{'...' if len(columns) > 5 else ''}")

    if not columns:
        logger.error(f"No columns found for {database}.{table}. Raw data: {data[:3] if data else 'empty'}")
        return None

    schema = {
        'columns': columns,
        'column_map': column_map,  # lowercase keys for case-insensitive lookup
        'column_map_original': column_map_original,  # original case
        'primary_key': columns[0]['name'] if columns else None  # Assume first column is PK
    }

    # Cache the schema
    schema_cache.set(database, table, schema)

    return schema


# =============================================================================
# Audit Logging
# =============================================================================

def log_audit(
    operation: str,
    database: str,
    table: str,
    record_id: str = None,
    old_values: Dict = None,
    new_values: Dict = None,
    user: str = None,
    ip_address: str = None,
    success: bool = True,
    error_message: str = None,
    elapsed_ms: int = 0
) -> bool:
    """
    Log an audit record to the audit table.

    Audit table schema (mrw_ima.hive_proxy_audit):
        audit_id STRING,
        operation STRING,        -- INSERT, UPDATE, DELETE, SELECT
        database_name STRING,
        table_name STRING,
        record_id STRING,
        old_values STRING,       -- JSON
        new_values STRING,       -- JSON
        performed_by STRING,
        ip_address STRING,
        performed_at TIMESTAMP,
        success BOOLEAN,
        error_message STRING,
        elapsed_ms INT
    """
    if not config.AUDIT_ENABLED:
        return True

    try:
        audit_id = hashlib.md5(f"{time.time()}{operation}{table}".encode()).hexdigest()[:16]
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Escape values
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

        # Execute async (don't wait for result)
        execute_beeline(sql, config.AUDIT_DATABASE, timeout=60, output_format='table')
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
                return jsonify({
                    'success': False,
                    'error': 'Invalid or missing API key'
                }), 401

        # Store request info for audit
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
        'status': 'healthy',
        'service': 'hive-proxy',
        'version': '2.0.0',
        'config': {
            'database': config.DEFAULT_DATABASE,
            'audit_enabled': config.AUDIT_ENABLED,
            'timeout': config.QUERY_TIMEOUT,
            'max_concurrent': config.MAX_CONCURRENT
        },
        'stats': query_stats,
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
    """
    Get table schema.

    GET /schema/mrw_ima.portfolio_hive
    GET /schema/portfolio_hive?database=mrw_ima
    """
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
# API Endpoints - Dynamic CRUD
# =============================================================================

@app.route('/insert/<path:table_name>', methods=['POST'])
@require_api_key
@with_query_limit
def dynamic_insert(table_name: str):
    """
    Dynamic INSERT with automatic type casting.

    POST /insert/mrw_ima.portfolio_hive
    {
        "data": {
            "portfolio_id": "PF001",
            "portfolio_name": "Test Portfolio",
            "status": "DRAFT",
            "created_at": "now"
        }
    }
    """
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        req_data = request.get_json()
        if not req_data or 'data' not in req_data:
            return jsonify({'success': False, 'error': 'Missing data parameter'}), 400

        record_data = req_data['data']

        # Get schema for type casting
        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']  # lowercase keys
        column_map_original = schema.get('column_map_original', column_map)

        # Build INSERT statement
        columns = []
        values = []

        logger.debug(f"Schema column_map keys: {list(column_map.keys())}")
        logger.debug(f"Input data keys: {list(record_data.keys())}")

        for col_name, value in record_data.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()

            # Case-insensitive lookup
            if safe_col_lower not in column_map:
                logger.warning(f"Column '{safe_col}' not in schema (available: {list(column_map.keys())[:5]}...), skipping")
                continue

            col_type = column_map[safe_col_lower]
            formatted_value = format_value_for_hive(value, col_type)

            # Use the original column name for SQL (preserve case)
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            columns.append(original_col)
            values.append(formatted_value)

        if not columns:
            logger.error(f"No valid columns! Input keys: {list(record_data.keys())}, Schema keys: {list(column_map.keys())}")
            return jsonify({
                'success': False,
                'error': 'No valid columns provided',
                'input_columns': list(record_data.keys()),
                'schema_columns': list(column_map.keys())[:10]
            }), 400

        sql = f"""
        INSERT INTO {database}.{table} ({', '.join(columns)})
        VALUES ({', '.join(values)})
        """

        logger.info(f"Dynamic INSERT into {database}.{table}")

        with query_lock:
            query_stats['total'] += 1
            query_stats['insert'] += 1

        success, result = execute_beeline(sql, database, output_format='table')
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Audit logging
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
                'elapsed_ms': elapsed_ms
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
    """
    Dynamic UPDATE with automatic type casting.

    POST /update/mrw_ima.portfolio_hive
    {
        "where": {"portfolio_id": "PF001"},
        "data": {
            "status": "APPROVED",
            "updated_at": "now",
            "updated_by": "user1"
        }
    }
    """
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

        # Get schema
        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']  # lowercase keys
        column_map_original = schema.get('column_map_original', column_map)

        # Fetch old values for audit
        old_values = None
        pk_col = schema.get('primary_key')
        pk_value = where_clause.get(pk_col) if pk_col else None

        # Try case-insensitive pk lookup
        if not pk_value and pk_col:
            pk_col_lower = str(pk_col).lower() if pk_col else ''
            for key, val in where_clause.items():
                if key and str(key).lower() == pk_col_lower:
                    pk_value = val
                    break

        if pk_value:
            select_sql = f"SELECT * FROM {database}.{table} WHERE {pk_col} = '{pk_value}'"
            sel_success, sel_result = execute_beeline(select_sql, database, timeout=60)
            if sel_success and sel_result.get('data'):
                old_values = sel_result['data'][0] if sel_result['data'] else None

        # Build SET clause with case-insensitive lookup
        set_clauses = []
        for col_name, value in update_data.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()

            if safe_col_lower not in column_map:
                logger.warning(f"Column '{safe_col}' not in schema, skipping")
                continue

            col_type = column_map[safe_col_lower]
            formatted_value = format_value_for_hive(value, col_type)

            # Use original column name for SQL
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            set_clauses.append(f"{original_col} = {formatted_value}")

        if not set_clauses:
            return jsonify({
                'success': False,
                'error': 'No valid columns to update',
                'input_columns': list(update_data.keys()),
                'schema_columns': list(column_map.keys())[:10]
            }), 400

        # Build WHERE clause with case-insensitive lookup
        where_parts = []
        for col_name, value in where_clause.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()
            col_type = column_map.get(safe_col_lower, 'string')
            formatted_value = format_value_for_hive(value, col_type)

            # Use original column name for SQL
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            where_parts.append(f"{original_col} = {formatted_value}")

        sql = f"""
        UPDATE {database}.{table}
        SET {', '.join(set_clauses)}
        WHERE {' AND '.join(where_parts)}
        """

        logger.info(f"Dynamic UPDATE on {database}.{table}")

        with query_lock:
            query_stats['total'] += 1
            query_stats['update'] += 1

        success, result = execute_beeline(sql, database, output_format='table')
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Audit logging
        log_audit(
            operation='UPDATE',
            database=database,
            table=table,
            record_id=str(pk_value) if pk_value else None,
            old_values=old_values,
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
                'elapsed_ms': elapsed_ms
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
    """
    Dynamic DELETE with automatic type casting.

    POST /delete/mrw_ima.portfolio_hive
    {
        "where": {"portfolio_id": "PF001"},
        "soft_delete": true,
        "soft_delete_column": "deleted_at"
    }
    """
    start_time = time.time()

    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        req_data = request.get_json()
        if not req_data:
            return jsonify({'success': False, 'error': 'Missing request body'}), 400

        where_clause = req_data.get('where', {})
        soft_delete = req_data.get('soft_delete', True)  # Default to soft delete
        soft_delete_column = req_data.get('soft_delete_column', 'deleted_at')
        deleted_by = req_data.get('deleted_by', getattr(g, 'user', 'system'))

        if not where_clause:
            return jsonify({'success': False, 'error': 'WHERE clause required for DELETE'}), 400

        # Get schema
        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']  # lowercase keys
        column_map_original = schema.get('column_map_original', column_map)

        # Fetch old values for audit
        pk_col = schema.get('primary_key')
        pk_value = where_clause.get(pk_col) if pk_col else None

        # Try case-insensitive pk lookup
        if not pk_value and pk_col:
            pk_col_lower = str(pk_col).lower() if pk_col else ''
            for key, val in where_clause.items():
                if key and str(key).lower() == pk_col_lower:
                    pk_value = val
                    break

        old_values = None

        if pk_value:
            select_sql = f"SELECT * FROM {database}.{table} WHERE {pk_col} = '{pk_value}'"
            sel_success, sel_result = execute_beeline(select_sql, database, timeout=60)
            if sel_success and sel_result.get('data'):
                old_values = sel_result['data'][0] if sel_result['data'] else None

        # Build WHERE clause with case-insensitive lookup
        where_parts = []
        for col_name, value in where_clause.items():
            safe_col = sanitize_identifier(col_name)
            safe_col_lower = safe_col.lower()
            col_type = column_map.get(safe_col_lower, 'string')
            formatted_value = format_value_for_hive(value, col_type)

            # Use original column name for SQL
            original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
            where_parts.append(f"{original_col} = {formatted_value}")

        # Soft delete or hard delete (case-insensitive check)
        soft_delete_col_lower = soft_delete_column.lower()
        if soft_delete and soft_delete_col_lower in column_map:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get original column names
            original_soft_del_col = find_original_column_name(column_map_original, soft_delete_col_lower, soft_delete_column)
            set_clauses = [f"{original_soft_del_col} = '{now}'"]

            if 'updated_at' in column_map:
                original_updated_at = find_original_column_name(column_map_original, 'updated_at', 'updated_at')
                set_clauses.append(f"{original_updated_at} = '{now}'")
            if 'updated_by' in column_map:
                original_updated_by = find_original_column_name(column_map_original, 'updated_by', 'updated_by')
                set_clauses.append(f"{original_updated_by} = '{deleted_by}'")

            sql = f"""
            UPDATE {database}.{table}
            SET {', '.join(set_clauses)}
            WHERE {' AND '.join(where_parts)}
            """
            operation = 'SOFT_DELETE'
        else:
            sql = f"""
            DELETE FROM {database}.{table}
            WHERE {' AND '.join(where_parts)}
            """
            operation = 'HARD_DELETE'

        logger.info(f"Dynamic {operation} on {database}.{table}")

        with query_lock:
            query_stats['total'] += 1
            query_stats['delete'] += 1

        success, result = execute_beeline(sql, database, output_format='table')
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Audit logging
        log_audit(
            operation=operation,
            database=database,
            table=table,
            record_id=str(pk_value) if pk_value else None,
            old_values=old_values,
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
                'elapsed_ms': elapsed_ms
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

        # Only allow read queries
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

        success, result = execute_beeline(sql, database, timeout)
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

        # Block dangerous operations
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

        success, result = execute_beeline(sql, database, timeout, output_format='table')
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
# API Endpoints - Utility
# =============================================================================

@app.route('/databases', methods=['GET'])
@require_api_key
def list_databases():
    """List all databases."""
    success, result = execute_beeline("SHOW DATABASES", timeout=60)

    if success:
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 500


@app.route('/tables', methods=['GET'])
@require_api_key
def list_tables():
    """List tables in a database."""
    database = request.args.get('database', config.DEFAULT_DATABASE)
    success, result = execute_beeline(f"SHOW TABLES IN {database}", timeout=60)

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
        'schema_cache': schema_cache.stats(),
        'config': {
            'database': config.DEFAULT_DATABASE,
            'audit_enabled': config.AUDIT_ENABLED,
            'max_concurrent': config.MAX_CONCURRENT,
            'timeout': config.QUERY_TIMEOUT
        }
    })


@app.route('/debug/describe/<path:table_name>', methods=['GET'])
@require_api_key
def debug_describe(table_name: str):
    """
    Debug endpoint to see raw DESCRIBE output.
    GET /debug/describe/mrw_ima.portfolio_hive
    """
    try:
        database, table = validate_table_name(table_name)
        database = request.args.get('database', database)

        sql = f"DESCRIBE {database}.{table}"
        success, result = execute_beeline(sql, database, timeout=120)

        if success:
            return jsonify({
                'success': True,
                'database': database,
                'table': table,
                'raw_result': result,
                'data_type': str(type(result.get('data'))),
                'first_row_type': str(type(result.get('data', [None])[0])) if result.get('data') else 'N/A'
            })
        else:
            return jsonify({'success': False, 'error': result.get('error')}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/debug/sql', methods=['POST'])
@require_api_key
def debug_sql():
    """
    Debug endpoint to generate SQL without executing.
    POST /debug/sql
    {
        "operation": "insert",
        "table": "mrw_ima.portfolio_hive",
        "data": {"portfolio_id": "TEST", "status": "DRAFT"}
    }
    """
    try:
        req_data = request.get_json()
        operation = req_data.get('operation', 'insert')
        table_name = req_data.get('table')
        data = req_data.get('data', {})
        where = req_data.get('where', {})

        if not table_name:
            return jsonify({'success': False, 'error': 'Missing table parameter'}), 400

        database, table = validate_table_name(table_name)

        # Get schema
        schema = get_table_schema(database, table)
        if not schema:
            return jsonify({
                'success': False,
                'error': f'Cannot get schema for {database}.{table}'
            }), 500

        column_map = schema['column_map']  # lowercase keys
        column_map_original = schema.get('column_map_original', column_map)

        if operation == 'insert':
            columns = []
            values = []
            for col_name, value in data.items():
                safe_col = sanitize_identifier(col_name)
                safe_col_lower = safe_col.lower()
                if safe_col_lower in column_map:
                    col_type = column_map[safe_col_lower]
                    formatted_value = format_value_for_hive(value, col_type)
                    original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
                    columns.append(original_col)
                    values.append(formatted_value)

            sql = f"INSERT INTO {database}.{table} ({', '.join(columns)}) VALUES ({', '.join(values)})"

        elif operation == 'update':
            set_clauses = []
            for col_name, value in data.items():
                safe_col = sanitize_identifier(col_name)
                safe_col_lower = safe_col.lower()
                if safe_col_lower in column_map:
                    col_type = column_map[safe_col_lower]
                    formatted_value = format_value_for_hive(value, col_type)
                    original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
                    set_clauses.append(f"{original_col} = {formatted_value}")

            where_parts = []
            for col_name, value in where.items():
                safe_col = sanitize_identifier(col_name)
                safe_col_lower = safe_col.lower()
                col_type = column_map.get(safe_col_lower, 'string')
                formatted_value = format_value_for_hive(value, col_type)
                original_col = find_original_column_name(column_map_original, safe_col_lower, safe_col)
                where_parts.append(f"{original_col} = {formatted_value}")

            sql = f"UPDATE {database}.{table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_parts)}"

        else:
            sql = f"SELECT * FROM {database}.{table} LIMIT 1"

        return jsonify({
            'success': True,
            'operation': operation,
            'table': f"{database}.{table}",
            'schema': schema,
            'generated_sql': sql
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
    print("HIVE REST PROXY v2.0")
    print("=" * 60)
    print(f"Database: {config.DEFAULT_DATABASE}")
    print(f"Audit: {config.AUDIT_ENABLED} -> {config.AUDIT_DATABASE}.{config.AUDIT_TABLE}")
    print(f"Timeout: {config.QUERY_TIMEOUT}s")
    print(f"Max Concurrent: {config.MAX_CONCURRENT}")
    print(f"API Key: {'enabled' if config.API_KEY else 'disabled'}")
    print(f"Schema Cache TTL: {config.SCHEMA_CACHE_TTL}s")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)
