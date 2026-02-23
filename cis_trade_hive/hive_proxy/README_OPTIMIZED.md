# Hive REST Proxy v2.1 - Optimized

## Performance Problem (app_v2.py)

The original `app_v2.py` created a **new beeline subprocess for every request**:

```
Request -> Start JVM -> Connect to ZooKeeper -> Get HiveServer2 -> Execute Query -> Close
           ~5-10s          ~2-3s                    ~1-2s              ~10-20s       ~1s
```

**Total: ~30-40 seconds per INSERT operation**

Each request started a new JVM process, established Kerberos authentication, and connected through ZooKeeper - massive overhead for simple operations.

## Solution (app_v2_optimized.py)

The optimized version uses **persistent beeline sessions** with stdin/stdout communication:

```
First Request:  Create Session (~10s) -> Execute Query (~1-3s)
Later Requests: Reuse Session (~0s)  -> Execute Query (~1-3s)
```

**Result: ~1-3 seconds for subsequent operations (10x improvement)**

## Key Features

### 1. Beeline Session Pool
- Maintains pool of persistent beeline processes
- Sessions stay alive and accept queries via stdin
- Configurable pool size (default: 3 sessions)
- Auto-recovery for unhealthy sessions

### 2. Session Management
- Health checking every 60 seconds
- Auto-expiry after 30 minutes (configurable)
- Graceful shutdown on exit

### 3. Batch Operations
- New `/batch/insert` endpoint for multiple records
- Single session handles multiple INSERTs
- Reduces connection overhead further

## Deployment

### Edge Node (Production)

```bash
# Single worker to share session pool across requests
gunicorn -b 0.0.0.0:5000 -w 1 --timeout 300 app_v2_optimized:app
```

**Important:** Use `workers=1` to ensure all requests share the same session pool.

### Environment Variables

```bash
# Session Pool Settings
export SESSION_POOL_SIZE=3           # Number of persistent sessions
export SESSION_MAX_AGE=1800          # Session lifetime (30 min)
export SESSION_HEALTH_CHECK_INTERVAL=60  # Health check interval

# Existing Settings
export HIVE_ZOOKEEPER_HOSTS="lxmrwtsgv0m1.sg.uobnet.com:2181,..."
export HIVE_PRINCIPAL="hive/_HOST@TST.UOBNET.COM"
export HIVE_DATABASE="mrw_ima"
export HIVE_YARN_QUEUE="EOD_Queue"
```

### Warm Up Sessions (Optional)

Pre-create sessions for immediate fast responses:

```bash
curl -X POST http://localhost:5000/sessions/warmup \
  -H "Content-Type: application/json" \
  -d '{"count": 2}'
```

## API Endpoints

### All Original Endpoints (Compatible)
- `POST /insert/<table>` - Single INSERT (now fast)
- `POST /update/<table>` - UPDATE
- `POST /delete/<table>` - DELETE
- `POST /query` - SELECT queries
- `POST /execute` - Raw SQL
- `GET /schema/<table>` - Get table schema
- `GET /health` - Health check (includes pool stats)
- `GET /stats` - Detailed statistics

### New Endpoints
- `POST /batch/insert/<table>` - Batch INSERT multiple records
- `POST /sessions/warmup` - Pre-create sessions

## Usage Examples

### Single INSERT (Fast after first request)

```bash
# First request (~10s - creates session)
curl -X POST http://localhost:5000/insert/mrw_ima.portfolio_hive \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "name": "TEST_PORTFOLIO",
      "status": "DRAFT",
      "created_at": "now"
    }
  }'

# Second request (~1-3s - reuses session)
curl -X POST http://localhost:5000/insert/mrw_ima.portfolio_hive \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "name": "TEST_PORTFOLIO_2",
      "status": "DRAFT",
      "created_at": "now"
    }
  }'
```

### Batch INSERT (Multiple Records)

```bash
curl -X POST http://localhost:5000/batch/insert/mrw_ima.portfolio_hive \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {"name": "PF001", "status": "DRAFT"},
      {"name": "PF002", "status": "DRAFT"},
      {"name": "PF003", "status": "DRAFT"}
    ]
  }'
```

### Check Pool Statistics

```bash
curl http://localhost:5000/health

# Response:
{
  "success": true,
  "version": "2.1.0-optimized",
  "session_pool": {
    "pool_size": 3,
    "active_sessions": 2,
    "available": 1,
    "total_created": 5
  },
  "stats": {
    "session_reused": 150,
    "session_created": 5
  }
}
```

## Performance Comparison

| Metric | app_v2.py | app_v2_optimized.py |
|--------|-----------|---------------------|
| First INSERT | ~35s | ~12s |
| Second INSERT | ~35s | ~2s |
| 10 INSERTs | ~350s | ~25s |
| Session overhead | Every request | Once per session |

## How It Works

### BeelineSession Class
Maintains a persistent beeline process with stdin/stdout pipes:

```python
class BeelineSession:
    def __init__(self):
        # Start beeline in interactive mode
        self.process = subprocess.Popen(
            ['beeline', '-u', jdbc_url, ...],
            stdin=PIPE, stdout=PIPE
        )

    def execute(self, sql):
        # Send query via stdin
        self.process.stdin.write(f"{sql};\n")
        # Read response from stdout
        return self._read_output()
```

### BeelineSessionPool Class
Manages a pool of sessions:

```python
class BeelineSessionPool:
    def acquire(self):
        # Get available session or create new one
        session = self.available.get_nowait()
        return session if session.healthy else self._create_session()

    def release(self, session):
        # Return session to pool for reuse
        self.available.put(session)
```

## Troubleshooting

### "No session available" Error
- Check if pool is exhausted: `GET /health`
- Increase pool size: `SESSION_POOL_SIZE=5`
- Check for stuck sessions in logs

### Session Keeps Dying
- Check Kerberos ticket: `klist`
- Renew ticket: `kinit -kt /path/to/keytab principal`
- Check `SESSION_MAX_AGE` setting

### Slow First Request
This is expected - first request creates session:
- Pre-warm: `POST /sessions/warmup`
- Or accept ~10s for first request

## Migration from app_v2.py

1. **No code changes needed** - API is identical
2. Deploy `app_v2_optimized.py` instead of `app_v2.py`
3. Use single worker: `gunicorn -w 1 ...`
4. Optionally warm up sessions on startup
