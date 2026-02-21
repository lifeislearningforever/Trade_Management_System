# Hybrid Connection Guide (Impala + Hive)

This guide covers the hybrid connection architecture for CIS Trade Hive in Cloudera CML environments.

## Overview

The hybrid connection manager uses:
- **Impala** for **fast reads** (SELECT queries)
- **Hive** for **ACID writes** (INSERT, UPDATE, DELETE)

Both use **Kerberos (GSSAPI)** authentication via `pure-sasl` (pure Python, no C dependencies).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Django Application                        │
├─────────────────────────────────────────────────────────────┤
│                  HybridConnectionManager                     │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │   Impala Pool       │    │    Hive Pool        │        │
│  │   (for reads)       │    │    (for writes)     │        │
│  │   Port: 21050       │    │    Port: 10000      │        │
│  │   Auth: GSSAPI      │    │    Auth: GSSAPI     │        │
│  └─────────────────────┘    └─────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
              │                          │
              ▼                          ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│      Impala Daemon      │  │      HiveServer2        │
│   (Fast MPP Queries)    │  │   (ACID Transactions)   │
└─────────────────────────┘  └─────────────────────────┘
              │                          │
              └──────────┬───────────────┘
                         ▼
              ┌─────────────────────────┐
              │    Hive Metastore       │
              │    (gmp_cis database)   │
              └─────────────────────────┘
```

## Installation

### Requirements (Pure Python - No C Dependencies)

```bash
pip install pure-sasl thrift-sasl pyhive impyla
```

Or add to `requirements.txt`:
```
pure-sasl==0.6.2
thrift-sasl==0.4.3
pyhive==0.7.0
impyla==0.19.0
```

## Configuration

### Environment Variables (CML)

Set these in your CML Project Settings:

```bash
# ============================================
# IMPALA Configuration (for FAST READS)
# ============================================
IMPALA_HOST=your-impala-coordinator-host
IMPALA_PORT=21050
IMPALA_DB=gmp_cis
IMPALA_AUTH=GSSAPI
IMPALA_KERBEROS_SERVICE_NAME=impala
IMPALA_USE_SSL=true
IMPALA_TIMEOUT=120
IMPALA_POOL_SIZE=10

# ============================================
# HIVE Configuration (for ACID WRITES)
# ============================================
HIVE_HOST=your-hiveserver2-host
HIVE_PORT=10000
HIVE_DB=gmp_cis
HIVE_AUTH=GSSAPI
HIVE_KERBEROS_SERVICE_NAME=hive
HIVE_TIMEOUT=120
HIVE_POOL_SIZE=10
```

### Settings (settings.py)

The configuration is automatically loaded from environment variables:

```python
# IMPALA (for FAST READS)
IMPALA_CONFIG = {
    'HOST': os.environ.get('IMPALA_HOST', 'localhost'),
    'PORT': int(os.environ.get('IMPALA_PORT', '21050')),
    'DATABASE': os.environ.get('IMPALA_DB', 'gmp_cis'),
    'AUTH': os.environ.get('IMPALA_AUTH', 'GSSAPI'),
    'KERBEROS_SERVICE_NAME': os.environ.get('IMPALA_KERBEROS_SERVICE_NAME', 'impala'),
    'USE_SSL': os.environ.get('IMPALA_USE_SSL', 'true').lower() == 'true',
    'TIMEOUT': int(os.environ.get('IMPALA_TIMEOUT', '120')),
    'POOL_SIZE': int(os.environ.get('IMPALA_POOL_SIZE', '10')),
}

# HIVE (for ACID WRITES)
HIVE_CONFIG = {
    'HOST': os.environ.get('HIVE_HOST', 'localhost'),
    'PORT': int(os.environ.get('HIVE_PORT', '10000')),
    'DATABASE': os.environ.get('HIVE_DB', 'gmp_cis'),
    'AUTH': os.environ.get('HIVE_AUTH', 'GSSAPI'),
    'KERBEROS_SERVICE_NAME': os.environ.get('HIVE_KERBEROS_SERVICE_NAME', 'hive'),
    'TIMEOUT': int(os.environ.get('HIVE_TIMEOUT', '120')),
    'POOL_SIZE': int(os.environ.get('HIVE_POOL_SIZE', '10')),
}
```

## Testing Connections

### Management Command

```bash
# Basic test
python manage.py test_hybrid_connection

# Verbose output
python manage.py test_hybrid_connection --verbose

# Test write operations
python manage.py test_hybrid_connection --test-write
```

### Django Shell Test

```python
# Start Django shell
python manage.py shell

# ==================================================
# Test 1: Import and check library availability
# ==================================================
from core.repositories.hybrid_connection import (
    hybrid_manager,
    IMPYLA_AVAILABLE,
    PYHIVE_AVAILABLE
)

print(f"Impyla available: {IMPYLA_AVAILABLE}")
print(f"PyHive available: {PYHIVE_AVAILABLE}")

# ==================================================
# Test 2: Test both connections
# ==================================================
results = hybrid_manager.test_connection()
print(f"Impala connected: {results['impala']}")
print(f"Hive connected: {results['hive']}")

# ==================================================
# Test 3: Check pool statistics
# ==================================================
stats = hybrid_manager.get_pool_stats()
print(f"Impala: {stats['impala']}")
print(f"Hive: {stats['hive']}")

# ==================================================
# Test 4: Read via Impala (fast)
# ==================================================
tables = hybrid_manager.get_tables()
print(f"Found {len(tables)} tables: {tables[:5]}")

# ==================================================
# Test 5: Execute read query via Impala
# ==================================================
result = hybrid_manager.execute_query(
    "SELECT * FROM cis_portfolio LIMIT 5"
)
print(f"Query returned {len(result)} rows")
for row in result:
    print(f"  {row}")

# ==================================================
# Test 6: Execute write query via Hive
# ==================================================
# Note: This uses Hive for ACID support
success = hybrid_manager.execute_write(
    """
    INSERT INTO cis_audit_log
    (log_id, action, entity_type, entity_id, created_at, created_by)
    VALUES
    ('TEST001', 'TEST', 'SYSTEM', 'TEST', current_timestamp(), 'test_user')
    """
)
print(f"Write successful: {success}")

# ==================================================
# Test 7: Direct cursor access (advanced)
# ==================================================
# Read cursor (Impala)
with hybrid_manager.get_read_cursor() as cursor:
    cursor.execute("SELECT current_timestamp()")
    result = cursor.fetchone()
    print(f"Impala timestamp: {result}")

# Write cursor (Hive)
with hybrid_manager.get_write_cursor() as cursor:
    cursor.execute("SELECT current_timestamp()")
    result = cursor.fetchone()
    print(f"Hive timestamp: {result}")
```

### Quick Connection Test Script

Save as `test_connection.py` and run with `python manage.py shell < test_connection.py`:

```python
"""Quick connection test script for CML."""
from core.repositories.hybrid_connection import hybrid_manager

print("=" * 50)
print("HYBRID CONNECTION TEST")
print("=" * 50)

# Test connections
results = hybrid_manager.test_connection()
print(f"\nImpala: {'OK' if results['impala'] else 'FAILED'}")
print(f"Hive:   {'OK' if results['hive'] else 'FAILED'}")

# Pool stats
stats = hybrid_manager.get_pool_stats()
print(f"\nImpala Pool: {stats['impala']['active']}/{stats['impala']['max']} active")
print(f"Hive Pool:   {stats['hive']['active']}/{stats['hive']['max']} active")

# Read test
tables = hybrid_manager.get_tables()
print(f"\nTables found: {len(tables)}")

print("\n" + "=" * 50)
print("TEST COMPLETE")
print("=" * 50)
```

## Usage in Application Code

### Basic Usage (Backward Compatible)

Existing code works without changes:

```python
from core.repositories.hive_connection import hive_manager

# Reads automatically go via Impala
results = hive_manager.execute_query("SELECT * FROM cis_trade LIMIT 10")

# Writes automatically go via Hive
hive_manager.execute_write("INSERT INTO cis_trade (...) VALUES (...)")
```

### Explicit Read/Write Separation

```python
from core.repositories.hybrid_connection import hybrid_manager

# Explicit read via Impala
with hybrid_manager.get_read_cursor() as cursor:
    cursor.execute("SELECT * FROM cis_portfolio WHERE status = 'ACTIVE'")
    portfolios = cursor.fetchall()

# Explicit write via Hive
with hybrid_manager.get_write_cursor() as cursor:
    cursor.execute("SET hive.execution.engine=mr")  # For ACID
    cursor.execute("UPDATE cis_portfolio SET status = 'INACTIVE' WHERE name = 'OLD'")
```

### Async Writes (Non-blocking)

For audit logs and history tables:

```python
# Non-blocking write
hybrid_manager.execute_write_async(
    "INSERT INTO cis_audit_log (...) VALUES (...)",
    callback=lambda success: print(f"Audit logged: {success}")
)

# Wait for all async writes to complete
completed = hybrid_manager.wait_for_async_writes(timeout=30.0)
print(f"Completed {completed} async writes")
```

## Repository Pattern

All repositories use the hybrid connection automatically:

```python
from core.repositories.hive_base_repository import HiveBaseRepository

class TradeHiveRepository(HiveBaseRepository):
    @property
    def table_name(self) -> str:
        return 'cis_trade'

    def find_active_trades(self):
        # Uses Impala for fast reads
        return self.hive_manager.execute_query(
            "SELECT * FROM cis_trade WHERE status = 'ACTIVE'"
        )

    def create_trade(self, trade_data):
        # Uses Hive for ACID writes
        return self.hive_manager.execute_write(
            "INSERT INTO cis_trade (...) VALUES (...)"
        )
```

## Troubleshooting

### Common Errors

#### 1. Kerberos Ticket Not Found

```
GSSError: No Kerberos credentials available
```

**Solution:** Ensure you have a valid Kerberos ticket:
```bash
kinit your-username@YOUR.REALM
klist  # Verify ticket
```

In CML, Kerberos is usually handled automatically.

#### 2. Service Name Mismatch

```
GSSError: Server not found in Kerberos database
```

**Solution:** Check the Kerberos service name:
```bash
# For Impala
IMPALA_KERBEROS_SERVICE_NAME=impala

# For Hive (might be 'hive' or 'hiveserver2')
HIVE_KERBEROS_SERVICE_NAME=hive
```

#### 3. Connection Timeout

```
thrift.transport.TTransport.TTransportException: Connection timed out
```

**Solution:** Increase timeout and check network:
```bash
IMPALA_TIMEOUT=300
HIVE_TIMEOUT=300
```

#### 4. SSL Certificate Error

```
ssl.SSLCertVerificationError: certificate verify failed
```

**Solution:** For development, you can disable SSL (not recommended for production):
```bash
IMPALA_USE_SSL=false
```

### Debug Mode

Enable debug logging in settings:

```python
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Check Configuration

```python
from django.conf import settings

print("IMPALA_CONFIG:")
for k, v in settings.IMPALA_CONFIG.items():
    print(f"  {k}: {v}")

print("\nHIVE_CONFIG:")
for k, v in settings.HIVE_CONFIG.items():
    print(f"  {k}: {v}")
```

## Performance Tips

1. **Use Impala for all reads** - It's 10-100x faster than Hive for SELECT queries
2. **Batch writes** - Group multiple INSERTs into single statements
3. **Connection pooling** - Pool size of 10 is good for most workloads
4. **Async audit logs** - Use `execute_write_async()` for non-critical writes

## Authentication Modes

| Mode | Impala AUTH | Hive AUTH | Use Case |
|------|-------------|-----------|----------|
| Kerberos | `GSSAPI` | `GSSAPI` | CML Production |
| LDAP | `LDAP` | `LDAP` | Non-Kerberized clusters |
| None | `NOSASL` | `NONE` | Local development |

## File Reference

| File | Purpose |
|------|---------|
| `core/repositories/hybrid_connection.py` | Main hybrid connection manager |
| `core/repositories/hive_connection.py` | Backward compatibility wrapper |
| `config/settings.py` | IMPALA_CONFIG and HIVE_CONFIG |
| `core/management/commands/test_hybrid_connection.py` | Test command |
| `requirements.txt` | Dependencies (pure-sasl, pyhive, impyla) |
