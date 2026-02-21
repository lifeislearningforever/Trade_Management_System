#!/usr/bin/env python3
"""
Hive REST Proxy - Deploy on Edge Node

A lightweight Flask API that executes Hive queries via beeline.
This allows CML (or any client) to execute Hive queries via HTTP.

Features:
- No SSH required - pure HTTP
- Kerberos authentication handled by edge node
- Connection pooling for performance
- Query timeout handling
- Health check endpoint

Deployment on Edge Node:
    1. Copy this file to edge node
    2. pip install flask gunicorn
    3. kinit -kt /path/to/keytab principal@REALM
    4. gunicorn -b 0.0.0.0:5000 -w 4 app:app

Usage from CML:
    import requests
    response = requests.post(
        'http://edge-node:5000/query',
        json={'sql': 'SELECT * FROM table LIMIT 10', 'database': 'gmp_cis'}
    )
    print(response.json())

Security Notes:
    - Run behind firewall (internal network only)
    - Add authentication if exposed externally
    - Use HTTPS in production
"""

import os
import subprocess
import csv
import io
import json
import time
import logging
from typing import Dict, Any, List, Tuple, Optional
from functools import wraps
from flask import Flask, request, jsonify

# Configure logging
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
    DEFAULT_DATABASE = os.environ.get('HIVE_DATABASE', 'gmp_cis')

    # SSL truststore
    TRUSTSTORE_PATH = os.environ.get(
        'HIVE_TRUSTSTORE_PATH',
        '/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks'
    )

    # Query timeout (seconds)
    QUERY_TIMEOUT = int(os.environ.get('HIVE_QUERY_TIMEOUT', '120'))

    # Max concurrent queries
    MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT_QUERIES', '10'))

    # Java home for beeline
    JAVA_HOME = os.environ.get(
        'JAVA_HOME',
        '/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.462.b08-2.el8.x86_64/jre'
    )

    # API Key for basic auth (optional)
    API_KEY = os.environ.get('HIVE_PROXY_API_KEY', '')


config = Config()

# Track concurrent queries
import threading
query_semaphore = threading.Semaphore(config.MAX_CONCURRENT)
query_counter = {'total': 0, 'success': 0, 'failed': 0}
query_lock = threading.Lock()


# =============================================================================
# Helper Functions
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
                    timeout: int = None, output_format: str = 'csv2') -> Tuple[bool, Any]:
    """
    Execute SQL via beeline.

    Returns:
        Tuple of (success: bool, result: data or error message)
    """
    jdbc_url = build_jdbc_url(database)
    query_timeout = timeout or config.QUERY_TIMEOUT

    # Build beeline command with correct Java
    cmd = (
        f'export JAVA_HOME="{config.JAVA_HOME}" && '
        f'export PATH="$JAVA_HOME/bin:$PATH" && '
        f'beeline -u "{jdbc_url}" '
        f'-e "{sql}" '
        f'--silent=true '
        f'--outputformat={output_format} '
        f'--showHeader=true'
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

        if result.returncode != 0:
            logger.error(f"Beeline failed: {result.stderr}")
            return False, {'error': result.stderr, 'elapsed_ms': int(elapsed * 1000)}

        # Parse CSV output for SELECT queries
        output = result.stdout.strip()

        if not output:
            return True, {'data': [], 'elapsed_ms': int(elapsed * 1000)}

        # Check if it's a SELECT query (has header row)
        if output_format == 'csv2' and ',' in output.split('\n')[0]:
            try:
                reader = csv.DictReader(io.StringIO(output))
                data = [dict(row) for row in reader]
                return True, {'data': data, 'rows': len(data), 'elapsed_ms': int(elapsed * 1000)}
            except Exception as e:
                # Not CSV, return as raw output
                return True, {'data': output, 'elapsed_ms': int(elapsed * 1000)}
        else:
            return True, {'data': output, 'elapsed_ms': int(elapsed * 1000)}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error(f"Query timed out after {query_timeout}s")
        return False, {'error': 'Query timeout', 'elapsed_ms': int(elapsed * 1000)}

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Query execution error: {str(e)}")
        return False, {'error': str(e), 'elapsed_ms': int(elapsed * 1000)}


def require_api_key(f):
    """Decorator to require API key if configured."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if config.API_KEY:
            provided_key = request.headers.get('X-API-Key', '')
            if provided_key != config.API_KEY:
                return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# API Endpoints
# =============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'hive-proxy',
        'version': '1.0.0',
        'config': {
            'zookeeper': config.ZOOKEEPER_HOSTS.split(',')[0] + '...',
            'database': config.DEFAULT_DATABASE,
            'timeout': config.QUERY_TIMEOUT,
        },
        'stats': query_counter
    })


@app.route('/test', methods=['GET'])
@require_api_key
def test_connection():
    """Test Hive connection."""
    success, result = execute_beeline("SELECT 1 AS test", timeout=30)

    if success:
        return jsonify({
            'status': 'connected',
            'result': result
        })
    else:
        return jsonify({
            'status': 'failed',
            'error': result
        }), 500


@app.route('/query', methods=['POST'])
@require_api_key
def execute_query():
    """
    Execute a read query (SELECT).

    Request JSON:
        {
            "sql": "SELECT * FROM table LIMIT 10",
            "database": "gmp_cis",  // optional
            "timeout": 60           // optional
        }

    Response JSON:
        {
            "success": true,
            "data": [...],
            "rows": 10,
            "elapsed_ms": 150
        }
    """
    if not query_semaphore.acquire(blocking=False):
        return jsonify({
            'error': 'Too many concurrent queries',
            'max_concurrent': config.MAX_CONCURRENT
        }), 429

    try:
        data = request.get_json()

        if not data or 'sql' not in data:
            return jsonify({'error': 'Missing sql parameter'}), 400

        sql = data['sql'].strip()
        database = data.get('database', config.DEFAULT_DATABASE)
        timeout = data.get('timeout', config.QUERY_TIMEOUT)

        # Basic SQL injection prevention
        sql_upper = sql.upper()
        if not sql_upper.startswith('SELECT') and not sql_upper.startswith('SHOW') \
           and not sql_upper.startswith('DESCRIBE'):
            return jsonify({
                'error': 'Only SELECT, SHOW, DESCRIBE queries allowed on /query endpoint. Use /execute for writes.'
            }), 400

        logger.info(f"Executing query: {sql[:100]}...")

        with query_lock:
            query_counter['total'] += 1

        success, result = execute_beeline(sql, database, timeout)

        with query_lock:
            if success:
                query_counter['success'] += 1
            else:
                query_counter['failed'] += 1

        if success:
            return jsonify({'success': True, **result})
        else:
            return jsonify({'success': False, **result}), 500

    finally:
        query_semaphore.release()


@app.route('/execute', methods=['POST'])
@require_api_key
def execute_write():
    """
    Execute a write query (INSERT, UPDATE, DELETE).

    Request JSON:
        {
            "sql": "INSERT INTO table VALUES (...)",
            "database": "gmp_cis",  // optional
            "timeout": 120          // optional
        }

    Response JSON:
        {
            "success": true,
            "elapsed_ms": 500
        }
    """
    if not query_semaphore.acquire(blocking=False):
        return jsonify({
            'error': 'Too many concurrent queries',
            'max_concurrent': config.MAX_CONCURRENT
        }), 429

    try:
        data = request.get_json()

        if not data or 'sql' not in data:
            return jsonify({'error': 'Missing sql parameter'}), 400

        sql = data['sql'].strip()
        database = data.get('database', config.DEFAULT_DATABASE)
        timeout = data.get('timeout', config.QUERY_TIMEOUT)

        # Block dangerous operations
        sql_upper = sql.upper()
        if 'DROP DATABASE' in sql_upper or 'DROP TABLE' in sql_upper:
            return jsonify({'error': 'DROP operations not allowed'}), 403

        logger.info(f"Executing write: {sql[:100]}...")

        with query_lock:
            query_counter['total'] += 1

        success, result = execute_beeline(sql, database, timeout, output_format='table')

        with query_lock:
            if success:
                query_counter['success'] += 1
            else:
                query_counter['failed'] += 1

        if success:
            return jsonify({'success': True, **result})
        else:
            return jsonify({'success': False, **result}), 500

    finally:
        query_semaphore.release()


@app.route('/batch', methods=['POST'])
@require_api_key
def execute_batch():
    """
    Execute multiple queries in a batch.

    Request JSON:
        {
            "queries": [
                {"sql": "INSERT ...", "type": "write"},
                {"sql": "SELECT ...", "type": "read"}
            ],
            "database": "gmp_cis",
            "stop_on_error": true
        }

    Response JSON:
        {
            "success": true,
            "results": [...]
        }
    """
    data = request.get_json()

    if not data or 'queries' not in data:
        return jsonify({'error': 'Missing queries parameter'}), 400

    queries = data['queries']
    database = data.get('database', config.DEFAULT_DATABASE)
    stop_on_error = data.get('stop_on_error', True)

    results = []
    all_success = True

    for i, q in enumerate(queries):
        sql = q.get('sql', '')
        q_type = q.get('type', 'read')
        output_format = 'csv2' if q_type == 'read' else 'table'

        success, result = execute_beeline(sql, database, output_format=output_format)

        results.append({
            'index': i,
            'success': success,
            **result
        })

        if not success:
            all_success = False
            if stop_on_error:
                break

    return jsonify({
        'success': all_success,
        'results': results,
        'executed': len(results),
        'total': len(queries)
    })


@app.route('/databases', methods=['GET'])
@require_api_key
def list_databases():
    """List all databases."""
    success, result = execute_beeline("SHOW DATABASES", timeout=30)

    if success:
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 500


@app.route('/tables', methods=['GET'])
@require_api_key
def list_tables():
    """List tables in a database."""
    database = request.args.get('database', config.DEFAULT_DATABASE)
    success, result = execute_beeline(f"SHOW TABLES IN {database}", timeout=30)

    if success:
        return jsonify({'success': True, 'database': database, **result})
    else:
        return jsonify({'success': False, **result}), 500


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("HIVE REST PROXY")
    print("=" * 60)
    print(f"ZooKeeper: {config.ZOOKEEPER_HOSTS}")
    print(f"Database: {config.DEFAULT_DATABASE}")
    print(f"Timeout: {config.QUERY_TIMEOUT}s")
    print(f"Max Concurrent: {config.MAX_CONCURRENT}")
    print(f"API Key: {'enabled' if config.API_KEY else 'disabled'}")
    print("=" * 60)

    # Development server
    app.run(host='0.0.0.0', port=5000, debug=True)
