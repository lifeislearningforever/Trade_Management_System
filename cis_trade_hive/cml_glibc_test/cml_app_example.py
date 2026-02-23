#!/usr/bin/env python3
"""
CML Application Example - Using HybridConnectionManager
========================================================

This is an example CML application that demonstrates:
1. The glibc error when trying direct Hive connections
2. The REST Proxy solution using HybridConnectionManager

Deploy this in CML to test the connectivity issue and solution.

CML Deployment:
---------------
1. Create CML Project
2. Upload these files:
   - hybrid_connection.py
   - cml_app_example.py
   - requirements.txt

3. Set Environment Variables in CML Project Settings:
   HIVE_REST_PROXY_URL=http://edge-node.sg.uobnet.com:5000
   HIVE_DATABASE=mrw_ima

4. Create Application:
   Script: cml_app_example.py
   Subdomain: cis-glibc-test
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

# Import hybrid connection manager
from hybrid_connection import (
    HybridConnectionManager,
    CMLConfig,
    attempt_direct_pyhive_connection,
    GlibcCompatibilityError,
    SASlAuthenticationError,
    RestProxyError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cml_app')

# Flask app
app = Flask(__name__)

# Initialize connection manager
config = CMLConfig()
manager = None

try:
    manager = HybridConnectionManager(config)
    logger.info("HybridConnectionManager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize HybridConnectionManager: {e}")


# HTML template for web UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CML glibc Test - CIS Trade Hive</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #333; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .success { color: #28a745; }
        .error { color: #dc3545; }
        .warning { color: #ffc107; }
        .info { color: #17a2b8; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:hover { background: #0056b3; }
        button.danger { background: #dc3545; }
        button.danger:hover { background: #c82333; }
        .result { margin-top: 10px; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #f2f2f2; }
        .env-var { font-family: monospace; background: #e9ecef; padding: 2px 6px; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>CML glibc Test - CIS Trade Hive</h1>
        <p>Testing Hive connectivity from CML Docker container</p>

        <div class="card">
            <h2>Environment Information</h2>
            <table>
                <tr><th>Variable</th><th>Value</th></tr>
                <tr><td>CDSW_PROJECT</td><td>{{ env.get('CDSW_PROJECT', 'Not set') }}</td></tr>
                <tr><td>CDSW_DOMAIN</td><td>{{ env.get('CDSW_DOMAIN', 'Not set') }}</td></tr>
                <tr><td>HIVE_REST_PROXY_URL</td><td>{{ env.get('HIVE_REST_PROXY_URL', 'Not set') }}</td></tr>
                <tr><td>HIVE_DATABASE</td><td>{{ env.get('HIVE_DATABASE', 'mrw_ima') }}</td></tr>
                <tr><td>Python</td><td>{{ python_version }}</td></tr>
                <tr><td>Timestamp</td><td>{{ timestamp }}</td></tr>
            </table>
        </div>

        <div class="card">
            <h2>Test 1: Direct Connection (Will Fail)</h2>
            <p class="warning">⚠️ This test attempts direct PyHive connection - it will fail in CML due to glibc issues</p>
            <button onclick="testDirect()">Test Direct Connection</button>
            <div id="direct-result" class="result"></div>
        </div>

        <div class="card">
            <h2>Test 2: REST Proxy Connection (Solution)</h2>
            <p class="info">ℹ️ This test uses REST Proxy to bypass glibc issues</p>
            <button onclick="testProxy()">Test REST Proxy</button>
            <button onclick="testQuery()">Test Query</button>
            <div id="proxy-result" class="result"></div>
        </div>

        <div class="card">
            <h2>Test 3: CRUD Operations</h2>
            <p class="info">ℹ️ Test full CRUD cycle via REST Proxy</p>
            <button onclick="testCrud()">Run CRUD Test</button>
            <div id="crud-result" class="result"></div>
        </div>

        <div class="card">
            <h2>API Endpoints</h2>
            <ul>
                <li><code>GET /health</code> - Health check</li>
                <li><code>GET /test/direct</code> - Test direct connection (will fail)</li>
                <li><code>GET /test/proxy</code> - Test REST Proxy connection</li>
                <li><code>POST /query</code> - Execute SQL query</li>
                <li><code>POST /insert</code> - Insert record</li>
                <li><code>GET /test/crud</code> - Run CRUD test cycle</li>
            </ul>
        </div>
    </div>

    <script>
        async function fetchApi(url, options = {}) {
            try {
                const response = await fetch(url, options);
                return await response.json();
            } catch (e) {
                return { error: e.message };
            }
        }

        function showResult(elementId, data) {
            const el = document.getElementById(elementId);
            const isError = data.error || data.success === false;
            el.innerHTML = `<pre class="${isError ? 'error' : 'success'}">${JSON.stringify(data, null, 2)}</pre>`;
        }

        async function testDirect() {
            showResult('direct-result', { status: 'Testing...' });
            const result = await fetchApi('/test/direct');
            showResult('direct-result', result);
        }

        async function testProxy() {
            showResult('proxy-result', { status: 'Testing...' });
            const result = await fetchApi('/test/proxy');
            showResult('proxy-result', result);
        }

        async function testQuery() {
            showResult('proxy-result', { status: 'Executing query...' });
            const result = await fetchApi('/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sql: 'SELECT 1 AS test' })
            });
            showResult('proxy-result', result);
        }

        async function testCrud() {
            showResult('crud-result', { status: 'Running CRUD test...' });
            const result = await fetchApi('/test/crud');
            showResult('crud-result', result);
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Render main page."""
    return render_template_string(
        HTML_TEMPLATE,
        env=os.environ,
        python_version=sys.version,
        timestamp=datetime.now().isoformat()
    )


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'cml-glibc-test',
        'timestamp': datetime.now().isoformat(),
        'environment': {
            'cdsw_project': os.environ.get('CDSW_PROJECT'),
            'cdsw_domain': os.environ.get('CDSW_DOMAIN'),
            'rest_proxy_url': config.rest_proxy_url,
            'database': config.hive_database
        },
        'manager_initialized': manager is not None
    })


@app.route('/test/direct')
def test_direct():
    """
    Test direct PyHive connection.

    This WILL FAIL in CML due to glibc compatibility issues.
    """
    logger.info("Testing direct PyHive connection (expected to fail in CML)")

    host = request.args.get('host', 'lxmrwtsgv0m1.sg.uobnet.com')
    port = int(request.args.get('port', 10000))
    database = request.args.get('database', config.hive_database)

    result = {
        'test': 'direct_connection',
        'host': host,
        'port': port,
        'database': database,
        'success': False,
        'error': None,
        'error_type': None,
        'solution': None,
        'timestamp': datetime.now().isoformat()
    }

    try:
        success, message = attempt_direct_pyhive_connection(
            host=host,
            port=port,
            database=database,
            auth='KERBEROS'
        )
        result['success'] = success
        result['message'] = message

    except GlibcCompatibilityError as e:
        result['error'] = str(e)
        result['error_type'] = 'GLIBC_COMPATIBILITY'
        result['solution'] = 'Use REST Proxy (app_v2.py on edge node)'
        logger.error(f"GLIBC Error (expected): {e}")

    except SASlAuthenticationError as e:
        result['error'] = str(e)
        result['error_type'] = 'SASL_AUTHENTICATION'
        result['solution'] = 'Use REST Proxy (app_v2.py on edge node)'
        logger.error(f"SASL Error (expected): {e}")

    except ImportError as e:
        result['error'] = f"Missing dependency: {e}"
        result['error_type'] = 'IMPORT_ERROR'
        result['solution'] = 'Install: pip install pyhive thrift thrift-sasl sasl'

    except Exception as e:
        result['error'] = str(e)
        result['error_type'] = type(e).__name__
        logger.exception(f"Unexpected error: {e}")

    return jsonify(result)


@app.route('/test/proxy')
def test_proxy():
    """Test REST Proxy connection (the solution)."""
    logger.info("Testing REST Proxy connection")

    if not manager:
        return jsonify({
            'success': False,
            'error': 'HybridConnectionManager not initialized',
            'solution': 'Set HIVE_REST_PROXY_URL environment variable'
        }), 500

    try:
        result = manager.test_proxy_connection()
        result['test'] = 'rest_proxy_connection'
        result['proxy_url'] = config.rest_proxy_url
        result['timestamp'] = datetime.now().isoformat()
        return jsonify(result)

    except RestProxyError as e:
        return jsonify({
            'success': False,
            'test': 'rest_proxy_connection',
            'error': str(e),
            'error_type': 'REST_PROXY_ERROR',
            'solution': 'Ensure app_v2.py is running on edge node',
            'proxy_url': config.rest_proxy_url,
            'timestamp': datetime.now().isoformat()
        }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/query', methods=['POST'])
def execute_query():
    """Execute SQL query via REST Proxy."""
    if not manager:
        return jsonify({'success': False, 'error': 'Manager not initialized'}), 500

    data = request.get_json() or {}
    sql = data.get('sql')

    if not sql:
        return jsonify({'success': False, 'error': 'Missing sql parameter'}), 400

    try:
        rows = manager.execute_query(sql)
        return jsonify({
            'success': True,
            'data': rows,
            'rows': len(rows),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/insert', methods=['POST'])
def insert_record():
    """Insert record via REST Proxy."""
    if not manager:
        return jsonify({'success': False, 'error': 'Manager not initialized'}), 500

    data = request.get_json() or {}
    table = data.get('table')
    record = data.get('data')

    if not table or not record:
        return jsonify({'success': False, 'error': 'Missing table or data parameter'}), 400

    try:
        result = manager.insert(table, record)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/test/crud')
def test_crud():
    """Run full CRUD test cycle."""
    if not manager:
        return jsonify({'success': False, 'error': 'Manager not initialized'}), 500

    table = request.args.get('table', 'portfolio_hive')
    test_id = f"GLIBC_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    results = {
        'test': 'crud_cycle',
        'table': table,
        'test_id': test_id,
        'steps': [],
        'success': True,
        'timestamp': datetime.now().isoformat()
    }

    # Step 1: INSERT
    try:
        result = manager.insert(table, {
            'name': test_id,
            'description': 'glibc test record',
            'status': 'DRAFT',
            'created_by': 'cml_glibc_test',
            'created_at': 'now'
        })
        results['steps'].append({
            'operation': 'INSERT',
            'success': True,
            'elapsed_ms': result.get('elapsed_ms')
        })
    except Exception as e:
        results['steps'].append({
            'operation': 'INSERT',
            'success': False,
            'error': str(e)
        })
        results['success'] = False
        return jsonify(results)

    # Step 2: SELECT
    try:
        rows = manager.execute_query(
            f"SELECT * FROM {table} WHERE name = '{test_id}'"
        )
        results['steps'].append({
            'operation': 'SELECT',
            'success': True,
            'rows_found': len(rows),
            'data': rows[0] if rows else None
        })
    except Exception as e:
        results['steps'].append({
            'operation': 'SELECT',
            'success': False,
            'error': str(e)
        })

    # Step 3: UPDATE
    try:
        result = manager.update(
            table,
            where={'name': test_id},
            data={
                'status': 'ACTIVE',
                'description': 'Updated by glibc test',
                'updated_by': 'cml_glibc_test',
                'updated_at': 'now'
            }
        )
        results['steps'].append({
            'operation': 'UPDATE',
            'success': True,
            'elapsed_ms': result.get('elapsed_ms')
        })
    except Exception as e:
        results['steps'].append({
            'operation': 'UPDATE',
            'success': False,
            'error': str(e)
        })

    # Step 4: DELETE (soft)
    try:
        result = manager.delete(
            table,
            where={'name': test_id},
            soft_delete=True
        )
        results['steps'].append({
            'operation': 'SOFT_DELETE',
            'success': True,
            'elapsed_ms': result.get('elapsed_ms')
        })
    except Exception as e:
        results['steps'].append({
            'operation': 'SOFT_DELETE',
            'success': False,
            'error': str(e)
        })

    # Determine overall success
    results['success'] = all(step.get('success', False) for step in results['steps'])

    return jsonify(results)


# CML Application entry point
if __name__ == '__main__':
    # Get port from CML environment or default
    port = int(os.environ.get('CDSW_APP_PORT', 8080))

    logger.info(f"Starting CML glibc Test Application on port {port}")
    logger.info(f"REST Proxy URL: {config.rest_proxy_url}")
    logger.info(f"Database: {config.hive_database}")

    app.run(host='127.0.0.1', port=port, debug=False)
