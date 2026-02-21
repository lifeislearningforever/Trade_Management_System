# Hive REST Proxy

A lightweight Flask-based REST API that runs on the edge node and executes Hive queries via beeline. This allows CML (Cloudera Machine Learning) or any HTTP client to interact with Hive without needing native SASL libraries or SSH access.

## Why This Solution?

**Problem:**
- CML Docker containers have older glibc (< 2.38)
- Native SASL libraries need glibc 2.38+
- Pure-sasl doesn't implement GSSAPI properly
- Direct Python connections (pyhive, impyla) fail with "TSocket read 0 bytes"

**Solution:**
- Deploy a lightweight REST API on the edge node
- Edge node has proper Kerberos setup and beeline access
- CML connects via HTTP (no SASL needed)
- Proxy executes queries via beeline subprocess

## Architecture

```
┌─────────────────────┐     HTTP      ┌─────────────────────┐     beeline     ┌─────────────────────┐
│   CML Application   │ ──────────────│   Hive REST Proxy   │ ────────────────│    HiveServer2      │
│   (Django/Python)   │    :5000      │   (Edge Node)       │    ZooKeeper    │    (Kerberos)       │
└─────────────────────┘               └─────────────────────┘                 └─────────────────────┘
```

## Quick Start

### 1. Deploy on Edge Node

```bash
# SSH to edge node
ssh owntmrwsg@edge-node.sg.uobnet.com

# Create directory
mkdir -p /home/owntmrwsg/hive_proxy
cd /home/owntmrwsg/hive_proxy

# Copy app.py to this directory (via scp or paste content)
scp app.py owntmrwsg@edge-node:/home/owntmrwsg/hive_proxy/

# Install dependencies
pip install flask gunicorn --user

# Ensure Kerberos ticket is valid
kinit -kt /path/to/keytab owntmrwsg@TST.UOBNET.COM
# OR
kinit owntmrwsg@TST.UOBNET.COM

# Verify beeline works
beeline -u "jdbc:hive2://lxmrwtsgv0m1.sg.uobnet.com:2181,lxmrwtsgv0m2.sg.uobnet.com:2181,lxmrwtsgv0w1.sg.uobnet.com:2181/gmp_cis;principal=hive/_HOST@TST.UOBNET.COM;serviceDiscoveryMode=zooKeeper;zookeeperNamespace=hiveserver2;ssl=true;sslTrustStore=/var/lib/cloudera-scm-agent/agent-cert/cm-auto-global_truststore.jks;trustStoreType=jks" -e "SELECT 1"
```

### 2. Configure Environment Variables (Optional)

```bash
# Override defaults if needed
export HIVE_ZOOKEEPER_HOSTS="lxmrwtsgv0m1.sg.uobnet.com:2181,lxmrwtsgv0m2.sg.uobnet.com:2181,lxmrwtsgv0w1.sg.uobnet.com:2181"
export HIVE_PRINCIPAL="hive/_HOST@TST.UOBNET.COM"
export HIVE_ZK_NAMESPACE="hiveserver2"
export HIVE_DATABASE="gmp_cis"
export HIVE_QUERY_TIMEOUT="120"
export MAX_CONCURRENT_QUERIES="10"

# Optional: Set API key for authentication
export HIVE_PROXY_API_KEY="your-secret-api-key"
```

### 3. Start the Proxy

**Development mode (single worker):**
```bash
python app.py
```

**Production mode (with gunicorn):**
```bash
# 4 workers, listening on all interfaces
gunicorn -b 0.0.0.0:5000 -w 4 --timeout 300 app:app

# With logging
gunicorn -b 0.0.0.0:5000 -w 4 --timeout 300 --access-logfile access.log --error-logfile error.log app:app

# As a background service
nohup gunicorn -b 0.0.0.0:5000 -w 4 --timeout 300 app:app > proxy.log 2>&1 &
```

### 4. Test from CML

```bash
# Set environment
export HIVE_PROXY_URL="http://edge-node:5000"
export HIVE_PROXY_API_KEY="your-secret-api-key"  # if configured

# Run test client
python test_proxy_client.py
```

## API Endpoints

### Health Check
```bash
GET /health

# Response
{
  "status": "healthy",
  "service": "hive-proxy",
  "version": "1.0.0",
  "config": {...},
  "stats": {"total": 10, "success": 9, "failed": 1}
}
```

### Test Connection
```bash
GET /test

# Response
{"status": "connected", "result": {...}}
```

### Execute SELECT Query
```bash
POST /query
Content-Type: application/json
X-API-Key: your-api-key  # if configured

{
  "sql": "SELECT * FROM cis_user LIMIT 10",
  "database": "gmp_cis",
  "timeout": 60
}

# Response
{
  "success": true,
  "data": [...],
  "rows": 10,
  "elapsed_ms": 150
}
```

### Execute Write Query (INSERT/UPDATE/DELETE)
```bash
POST /execute
Content-Type: application/json
X-API-Key: your-api-key  # if configured

{
  "sql": "INSERT INTO cis_audit_log (...) VALUES (...)",
  "database": "gmp_cis",
  "timeout": 120
}

# Response
{
  "success": true,
  "elapsed_ms": 500
}
```

### Batch Queries
```bash
POST /batch
Content-Type: application/json

{
  "queries": [
    {"sql": "INSERT INTO ...", "type": "write"},
    {"sql": "SELECT ...", "type": "read"}
  ],
  "database": "gmp_cis",
  "stop_on_error": true
}

# Response
{
  "success": true,
  "results": [...],
  "executed": 2,
  "total": 2
}
```

### List Databases
```bash
GET /databases

# Response
{"success": true, "data": ["default", "gmp_cis", ...]}
```

### List Tables
```bash
GET /tables?database=gmp_cis

# Response
{"success": true, "database": "gmp_cis", "data": ["cis_user", "cis_trade", ...]}
```

## Security Notes

1. **Run behind firewall** - Only expose on internal network
2. **Use API key** - Set `HIVE_PROXY_API_KEY` environment variable
3. **Use HTTPS in production** - Put behind nginx with SSL termination
4. **Restrict queries** - `/query` only allows SELECT/SHOW/DESCRIBE
5. **Block dangerous operations** - DROP DATABASE/TABLE blocked on `/execute`

## Integration with Django

Use the `HiveProxyClient` in your Django application:

```python
# core/repositories/hive_proxy_client.py

import requests
from typing import Dict, Any, List, Optional

class HiveProxyClient:
    def __init__(self, base_url: str, api_key: str = None, timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        return headers

    def execute_query(self, sql: str, database: str = 'gmp_cis') -> List[Dict]:
        """Execute SELECT query and return results."""
        response = requests.post(
            f"{self.base_url}/query",
            json={'sql': sql, 'database': database, 'timeout': self.timeout},
            headers=self._headers(),
            timeout=self.timeout + 10
        )
        result = response.json()
        if not result.get('success'):
            raise Exception(result.get('error', 'Query failed'))
        return result.get('data', [])

    def execute_write(self, sql: str, database: str = 'gmp_cis') -> bool:
        """Execute INSERT/UPDATE/DELETE query."""
        response = requests.post(
            f"{self.base_url}/execute",
            json={'sql': sql, 'database': database, 'timeout': self.timeout},
            headers=self._headers(),
            timeout=self.timeout + 10
        )
        result = response.json()
        if not result.get('success'):
            raise Exception(result.get('error', 'Write failed'))
        return True

# Usage
client = HiveProxyClient(
    base_url='http://edge-node:5000',
    api_key='your-api-key'
)

# Read
users = client.execute_query("SELECT * FROM cis_user LIMIT 10")

# Write
client.execute_write("INSERT INTO cis_audit_log (...) VALUES (...)")
```

## Kerberos Ticket Renewal

For long-running deployments, set up automatic Kerberos ticket renewal:

```bash
# Create a cron job for ticket renewal
crontab -e

# Add this line (renew every 4 hours)
0 */4 * * * kinit -kt /path/to/keytab owntmrwsg@TST.UOBNET.COM
```

## Troubleshooting

### Proxy not starting
```bash
# Check if port is in use
netstat -tlnp | grep 5000

# Check Python/Flask installation
python -c "from flask import Flask; print('Flask OK')"

# Check beeline works
beeline -e "SELECT 1"
```

### Queries timing out
```bash
# Increase timeout in environment
export HIVE_QUERY_TIMEOUT=300

# Check HiveServer2 status
beeline -e "SELECT 1" --timeout=10
```

### Kerberos errors
```bash
# Check ticket
klist

# Renew ticket
kinit -kt /path/to/keytab principal@REALM
```

### Connection refused from CML
```bash
# Check firewall on edge node
sudo firewall-cmd --list-all

# Allow port 5000
sudo firewall-cmd --add-port=5000/tcp --permanent
sudo firewall-cmd --reload
```

## Files

- `app.py` - Main Flask application
- `test_proxy_client.py` - Test client for CML
- `README.md` - This documentation
