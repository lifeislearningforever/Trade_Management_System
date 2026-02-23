# CML glibc/SASL Error Replication and Solution

This directory contains code to replicate the glibc/SASL connectivity issue in CML Docker containers and demonstrates the REST Proxy solution.

## The Problem

When running in CML (Cloudera Machine Learning) Docker containers, direct connections to HiveServer2 fail with errors like:

```
version `GLIBC_2.29' not found (required by /usr/lib64/libsasl2.so)
```

Or:

```
Could not start SASL: None of the mechanisms listed meet all required properties
```

### Why This Happens

1. CML Docker containers use a different glibc version than Cloudera edge nodes
2. Kerberos/SASL native libraries are compiled against specific glibc versions
3. Docker isolation prevents using the host's native libraries
4. PyHive/impyla require native SASL libraries for Kerberos authentication

## The Solution

Use REST Proxy (`app_v2.py`) deployed on an edge node:

```
CML Container  --HTTP-->  Edge Node (app_v2.py)  --Beeline-->  HiveServer2
```

- Edge node has correct glibc and native libraries
- REST Proxy handles beeline/Hive connections
- CML app communicates via HTTP (no native dependencies)

## Files

| File | Description |
|------|-------------|
| `hybrid_connection.py` | HybridConnectionManager - abstraction layer for CML connectivity |
| `test_glibc_error.py` | Test script to replicate the error and test solution |
| `cml_app_example.py` | Example CML application with web UI |
| `requirements.txt` | Python dependencies |

## Quick Start

### 1. Deploy REST Proxy on Edge Node

```bash
# On edge node (where glibc is compatible)
cd hive_proxy
gunicorn -b 0.0.0.0:5000 -w 1 --timeout 300 app_v2_optimized:app
```

### 2. Test from CML

```bash
# Set environment variable
export HIVE_REST_PROXY_URL=http://edge-node.sg.uobnet.com:5000
export HIVE_DATABASE=mrw_ima

# Test the error (will fail)
python test_glibc_error.py --direct --host lxmrwtsgv0m1.sg.uobnet.com

# Test the solution
python test_glibc_error.py --proxy http://edge-node:5000
```

### 3. Use in Your Code

```python
from hybrid_connection import HybridConnectionManager, CMLConfig

# Configure
config = CMLConfig(
    rest_proxy_url="http://edge-node.sg.uobnet.com:5000",
    hive_database="mrw_ima"
)

# Create manager
manager = HybridConnectionManager(config)

# Execute queries (via REST Proxy)
rows = manager.execute_query("SELECT * FROM portfolio_hive LIMIT 10")

# Insert records
manager.insert("portfolio_hive", {
    "name": "TEST_PORTFOLIO",
    "status": "DRAFT",
    "created_at": "now"
})
```

## CML Deployment

### 1. Create CML Project

1. Go to CML Workspace
2. Create New Project
3. Import from Git or upload files

### 2. Set Environment Variables

In Project Settings → Environment Variables:

```
HIVE_REST_PROXY_URL=http://edge-node.sg.uobnet.com:5000
HIVE_DATABASE=mrw_ima
```

### 3. Create Application

1. Go to Applications → New Application
2. Settings:
   - Name: CIS glibc Test
   - Subdomain: cis-glibc-test
   - Script: cml_app_example.py
   - Resource Profile: 1 vCPU / 2 GB Memory

### 4. Access Application

Open: `https://cis-glibc-test.<your-cml-domain>/`

## Expected Test Results

### Direct Connection Test (in CML)

```
[GLIBC ERROR] Expected error in CML environment!
Error: GLIBC version mismatch detected!
  version `GLIBC_2.29' not found

>>> This is the error we are trying to replicate <<<
>>> Solution: Use REST Proxy <<<
```

### REST Proxy Test

```
[SUCCESS] REST Proxy is healthy!
  Version: 2.1.0-optimized
  Database: mrw_ima

[SUCCESS] Query executed successfully!
  Result: [{'test_value': '1'}]
```

## API Reference

### HybridConnectionManager

```python
# Query execution
rows = manager.execute_query("SELECT * FROM table")

# Write execution
manager.execute_write("INSERT INTO table (...) VALUES (...)")

# Dynamic INSERT
manager.insert("table", {"col1": "val1", "col2": 123})

# Dynamic UPDATE
manager.update("table", where={"id": 1}, data={"status": "ACTIVE"})

# Dynamic DELETE (soft)
manager.delete("table", where={"id": 1}, soft_delete=True)

# Batch INSERT
manager.batch_insert("table", [
    {"col1": "val1"},
    {"col1": "val2"}
])

# Get schema
schema = manager.get_schema("table")
```

### REST Proxy Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/test` | GET | Test Hive connection |
| `/query` | POST | Execute SELECT query |
| `/execute` | POST | Execute raw SQL |
| `/insert/<table>` | POST | Dynamic INSERT |
| `/update/<table>` | POST | Dynamic UPDATE |
| `/delete/<table>` | POST | Dynamic DELETE |
| `/batch/insert/<table>` | POST | Batch INSERT |
| `/schema/<table>` | GET | Get table schema |

## Troubleshooting

### "Cannot connect to REST Proxy"

1. Check if REST Proxy is running on edge node
2. Verify network connectivity from CML to edge node
3. Check firewall rules for port 5000

### "GLIBC version not found"

This is expected in CML. Use REST Proxy solution.

### "SASL mechanism failure"

This is expected in CML. Use REST Proxy solution.

### "Kerberos ticket expired"

On edge node, renew the ticket:
```bash
kinit -kt /app/prodlib/owntarwsg.keytab owntarwsg@TST.UOBNET.COM
```
