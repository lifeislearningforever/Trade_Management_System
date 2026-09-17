# Trade Processing Architecture

## Overview

CIS Trade Hive uses an **async-first architecture** for trade processing. The system is designed for speed (user sees response in ~200ms) while all heavy processing happens asynchronously in background workers.

---

## 1. Trade Creation Flow (~200ms User Response)

```
USER POST /trade/create/
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [SYNC] Validate Trade Data                                  │
│   ├── Check required fields (portfolio, security, trade_type)│
│   ├── Validate references in DB (portfolio/security exist)  │
│   └── Returns entity_details to avoid duplicate queries     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [SYNC - BLOCKING] insert_trade_fast()                       │
│   └── Single UPSERT to cis_trade (status='INITIAL')         │
│   └── Returns trade_id (~100ms)                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [ASYNC - NON-BLOCKING] _queue_trade_events()                │
│   ├── Queue HISTORY event → cis_trade_event_queue           │
│   └── Queue SETTLEMENT event → cis_trade_event_queue        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ [ASYNC] audit_log_kudu_repository.log_action_async()        │
│   └── Fire-and-forget audit logging                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
RESPONSE: Redirect with success message (~200ms total)
```

### Key Files
- `trade/views.py` - `trade_create()` view
- `trade/repositories/trade_kudu_repository.py` - `insert_trade_fast()`
- `core/audit/audit_kudu_repository.py` - `log_action_async()`

---

## 2. Four-Eyes Workflow (Maker-Checker Principle)

The system enforces the **Four-Eyes Principle** where critical actions require approval from a different user than the one who initiated the action.

### Status Flow

```
INITIAL → MODIFIED → PENDING_VALIDATION → VALIDATED → SETTLED
                                       ↘ REJECTED/CANCELLED
```

### Workflow Actions

| Action | Endpoint | Status Change | Role | Validation |
|--------|----------|---------------|------|------------|
| Create | `POST /trade/create/` | → INITIAL | Maker | - |
| Edit | `POST /trade/<id>/edit/` | → MODIFIED | Maker | Must be in INITIAL/MODIFIED |
| Submit | `POST /trade/<id>/submit/` | → PENDING_VALIDATION | Maker | Must be in INITIAL/MODIFIED |
| Validate | `POST /trade/<id>/validate/` | → VALIDATED | Checker | validator ≠ submitter |
| Reject | `POST /trade/<id>/validate/` | → CANCELLED | Checker | validator ≠ submitter |
| Settle | `POST /trade/<id>/settle/` | → SETTLED + Queue AVP | Checker | Must be VALIDATED |
| Cancel | `POST /trade/<id>/cancel/` | → CANCELLED | Maker | Must be editable status |

### Four-Eyes Enforcement

```python
# trade/views.py - trade_validate()
def trade_validate(request, trade_id):
    submitted_by = trade_data.get('submitted_by')
    current_user = request.session.get('user_login')

    # Four-Eyes Check
    if submitted_by == current_user:
        raise PermissionError("Cannot validate your own submission")
```

---

## 3. Settlement Service (Async Queue)

All settlements are **queued for asynchronous processing** to keep the user response fast.

### Settlement Types

| Type | Condition | Queue | Processing |
|------|-----------|-------|------------|
| **T+0** | settle_date == today | `cis_position_queue` | Immediate by background worker |
| **Future (T+1/T+2)** | settle_date > today | `cis_settlement_queue` | EOD job on settle_date |
| **Backdated** | settle_date < today | `cis_position_queue` + CHAIN_RECALC | Immediate + chain recalculation |

### Code Flow

```python
# settlement_service.py
def process_trade_settlement(..., async_mode=True):
    settle_dt = parse_date(settle_date)
    today = datetime.now().date()

    if settle_dt == today:
        # T+0: Queue for immediate processing
        settlement_type = 'T+0'
        queue → cis_position_queue

    elif settle_dt > today:
        # Future: Queue for EOD processing
        settlement_type = 'FUTURE'
        queue → cis_settlement_queue

    else:
        # BACKDATED: Chain recalculation required
        settlement_type = 'BACKDATED'
        queue → cis_position_queue + CHAIN_RECALC metadata
```

### Backdated Trade Handling

When a trade is backdated, it affects all subsequent positions. The system:

1. Gets position BEFORE the backdated date (base position)
2. Gets ALL trades from backdated date to today
3. Recalculates positions in chronological order

```
Example:
- Existing: T1 settled 5th March → Position: qty=100, avg=$130
- New: T3 entered today, settle date 3rd March (BACKDATED)

Chain Recalculation:
1. Get position as of 2nd March (before backdated date)
2. Process T3 (3rd March) → New position
3. Process T1 (5th March) → Updated position
4. Result: All positions recalculated correctly
```

### Key Files
- `trade/services/settlement_service.py` - Settlement logic
- `trade/services/position_queue_service.py` - Queue processing

---

## 4. AVP (Average Price) Position Calculation

### Formulas

**BUY Trade:**
```
new_quantity = old_quantity + buy_quantity
new_total_cost = old_total_cost + (buy_quantity × price) + charges
new_avg_cost = new_total_cost / new_quantity
```

**SELL Trade:**
```
new_quantity = old_quantity - sell_quantity
avg_cost = UNCHANGED (uses existing average)
realized_pnl = (sell_price - avg_cost) × sell_quantity
```

### Position States

| State | Condition |
|-------|-----------|
| OPEN | quantity > 0 |
| CLOSED | quantity = 0 (fully sold) |

### Precision
- All calculations use **DECIMAL(20, 8)** - 8 decimal places
- Rounding: ROUND_HALF_UP

### Code Example

```python
# position_service.py
def _process_buy(current_position, quantity, price, charges):
    if current_position:
        # Existing position - weighted average
        old_qty = current_position['quantity']
        old_avg_cost = current_position['average_cost']
        old_total_cost = old_qty * old_avg_cost

        trade_cost = (quantity * price) + charges
        new_qty = old_qty + quantity
        new_avg_cost = (old_total_cost + trade_cost) / new_qty
    else:
        # New position
        new_qty = quantity
        new_avg_cost = (quantity * price + charges) / quantity

    return new_qty, new_avg_cost

def _process_sell(current_position, quantity, price):
    old_qty = current_position['quantity']
    old_avg_cost = current_position['average_cost']

    # Validation: No short selling
    if quantity > old_qty:
        raise ValueError(f"Insufficient quantity: {old_qty} available")

    # Calculate realized P&L
    realized_pnl = (price - old_avg_cost) * quantity

    new_qty = old_qty - quantity
    # AVP unchanged on sell

    return new_qty, old_avg_cost, realized_pnl
```

### Key Files
- `trade/services/position_service.py` - AVP calculation logic
- `sql/ddl/13_avp_tables_kudu.sql` - Position table DDL

---

## 5. Background Worker (Position Queue Service)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ PositionQueueService                                        │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Worker 1   │    │  Worker 2   │    │  Worker 3   │ ... │
│  │ (Thread)    │    │ (Thread)    │    │ (Thread)    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │ cis_position_   │                       │
│                   │ queue (Kudu)    │                       │
│                   └─────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| Workers | 4 | ThreadPoolExecutor threads |
| Batch Size | 100 | Items per poll |
| Poll Interval | 10 seconds | Sleep between polls |
| SLA | < 5 minutes | Queue to completion |
| Max Retries | 3 | Before dead letter |

### Worker Loop

```python
# position_queue_service.py
class PositionQueueService:
    def _worker_loop(self):
        while self._worker_running:
            try:
                # Get pending items from database queue
                pending_items = self.get_pending_items(limit=100)

                for item in pending_items:
                    self._update_status(item['queue_id'], 'PROCESSING')

                    if self._is_chain_recalc(item):
                        # Backdated: recalculate ALL positions from that date
                        self._process_chain_recalculation(item)
                    else:
                        # T+0: Direct calculation
                        position_service.calculate_position(
                            portfolio_id=item['portfolio_id'],
                            security_id=item['security_id'],
                            trade_type=item['trade_type'],
                            quantity=item['quantity'],
                            price=item['price'],
                            charges=item['charges'],
                            position_date=item['settle_date'],
                            trade_id=item['trade_id']
                        )

                    self._update_status(item['queue_id'], 'COMPLETED')

                if not pending_items:
                    time.sleep(10)  # Poll interval

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(10)
```

### Queue Item Structure

```python
queue_item = {
    'queue_id': 123456789,              # Unique ID
    'trade_id': 987654321,              # Trade reference
    'portfolio_id': 'PORT001',          # Portfolio
    'security_id': 'AAPL.US',           # Security
    'trade_type': 'BUY',                # BUY or SELL
    'quantity': 100.0,                  # Trade quantity
    'price': 150.50,                    # Trade price
    'charges': 10.00,                   # Commission + fees
    'settle_date': '2026-03-24',        # Settlement date
    'security_currency': 'USD',         # Security currency (FC)
    'portfolio_currency': 'SGD',        # Portfolio currency (LC)
    'status': 'PENDING',                # PENDING → PROCESSING → COMPLETED/FAILED
    'retry_count': 0,                   # Retry attempts
    'queued_at': timestamp,             # Queue timestamp
    'queued_by': 'username',            # Who queued it
    'error_message': None               # Error details or CHAIN_RECALC metadata
}
```

### Key Files
- `trade/services/position_queue_service.py` - Queue worker

---

## 6. Connection Pooling

### ImpalaConnectionManager

```python
# core/repositories/impala_connection.py
class ImpalaConnectionManager:
    """
    Singleton connection pool for Impala/Kudu.
    """

    # Pool Configuration
    pool_size = 35              # Max connections (4 workers × 4 threads + margin)
    async_workers = 15          # ThreadPoolExecutor for async writes
    connection_timeout = 3600   # 1 hour
    validation_skip = 30        # Skip ping if used within 30 seconds
```

### Connection Usage

```python
# Synchronous read
with impala_manager.get_cursor(database='gmp_cis') as cursor:
    cursor.execute("SELECT * FROM cis_trade WHERE trade_id = ?", [trade_id])
    results = cursor.fetchall()

# Synchronous write (blocking)
success = impala_manager.execute_write(
    "UPSERT INTO cis_trade (...) VALUES (...)",
    database='gmp_cis'
)

# Asynchronous write (non-blocking, fire-and-forget)
impala_manager.execute_write_async(
    "INSERT INTO cis_audit_log (...) VALUES (...)",
    database='gmp_cis'
)
```

### Connection Lifecycle

```
get_connection()
    │
    ├── Try get from pool (non-blocking)
    │   └── If available & valid → Return connection
    │
    ├── If pool empty & under limit
    │   └── Create new connection
    │
    └── If at limit
        └── Wait for pool (blocking, 30s timeout)

return_connection()
    │
    ├── Set last_used timestamp
    └── Put back in pool (if valid)
```

### Key Files
- `core/repositories/impala_connection.py` - Connection manager

---

## 7. Retry Logic & Dead Letter Queue

### Retry Flow

```
┌─────────────┐
│  PENDING    │
└──────┬──────┘
       │
       ▼
┌─────────────┐     Success     ┌─────────────┐
│ PROCESSING  │ ───────────────▶│  COMPLETED  │
└──────┬──────┘                 └─────────────┘
       │
       │ Failure
       ▼
┌──────────────────────────────────────────────┐
│ retry_count < 3?                             │
│   YES → Re-queue as PENDING (retry_count++)  │
│   NO  → Move to DEAD_LETTER                  │
└──────────────────────────────────────────────┘
```

### Dead Letter Handling

Items in DEAD_LETTER status require manual intervention:

```sql
-- View dead letter items
SELECT * FROM gmp_cis.cis_position_queue
WHERE status = 'DEAD_LETTER';

-- Retry a dead letter item
UPDATE gmp_cis.cis_position_queue
SET status = 'PENDING', retry_count = 0, error_message = NULL
WHERE queue_id = 123456789;
```

---

## 8. Key Optimizations

| Optimization | Impact | Implementation |
|--------------|--------|----------------|
| **Skip validation on insert** | Saves ~200ms | `skip_validation=True` in `insert_trade_fast()` |
| **Entity details from validation** | No duplicate DB queries | Validation returns portfolio/security details |
| **Async audit logging** | Non-blocking | `log_action_async()` |
| **Queue-based settlement** | No wait for AVP | All settlements queued |
| **Connection pooling** | Reuse connections | 35 connection pool |
| **30-sec validation skip** | Reduce ping overhead | Skip connection ping if recently used |
| **Batch processing** | Efficient queue consumption | 100 items per batch |

---

## 9. Database Tables

| Table | Purpose | Read/Write Pattern |
|-------|---------|-------------------|
| `cis_trade` | Trade master data | UPSERT (create/update) |
| `cis_trade_history` | Trade audit trail | INSERT async |
| `cis_trade_position` | Versioned positions | UPSERT (new version per change) |
| `cis_position_queue` | Async position calculation queue | INSERT, UPDATE status |
| `cis_settlement_queue` | Future settlement queue (T+1/T+2) | INSERT for future dates |
| `cis_trade_event_queue` | Event queue (HISTORY, SETTLEMENT) | INSERT async |
| `cis_audit_log` | System audit trail | INSERT async |

### Position Versioning

Positions use a versioned approach for full audit trail:

```sql
-- Each position change creates new version
cis_trade_position:
  - version_id (PK)
  - position_id
  - position_date
  - is_latest (true for current version)
  - ... position data ...
```

---

## 10. Multi-Currency Support

### Currency Types

| Type | Description | Example |
|------|-------------|---------|
| **FC (Foreign Currency)** | Security trading currency | USD for US stocks |
| **LC (Local Currency)** | Portfolio base currency | SGD for Singapore portfolio |

### FX Rate Lookup

```python
# multicurrency_service.py
def get_fx_rate(from_ccy, to_ccy, rate_date=None):
    # 1. Try direct pair: USD-SGD
    # 2. Try reverse pair: SGD-USD (invert)
    # 3. Try triangulation through USD: EUR-USD-SGD

    rate, date_used = _lookup_rate(from_ccy, to_ccy, rate_date)
    return rate, date_used
```

### Position with Multi-Currency

```python
position_data = {
    # Local currency (Security)
    'average_cost': 150.00,           # In FC (USD)
    'total_cost': 15000.00,           # In FC
    'realized_pnl_fc': 500.00,        # In FC
    'unrealized_pnl_fc': 200.00,      # In FC

    # Base currency (Portfolio)
    'average_cost_base': 202.50,      # In LC (SGD)
    'total_cost_base': 20250.00,      # In LC
    'realized_pnl_lc': 675.00,        # In LC
    'unrealized_pnl_lc': 270.00,      # In LC

    # FX Info
    'security_currency': 'USD',
    'portfolio_currency': 'SGD',
    'fx_rate': 1.35                   # USD → SGD
}
```

### Key Files
- `trade/services/multicurrency_service.py` - FX rate lookup and conversion

---

## 11. Complete Request/Response Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ TRADE CREATION FLOW                                                  │
└─────────────────────────────────────────────────────────────────────┘

USER POST /trade/create/ (form data)
    │
    ▼
[VIEW] trade_create() - Collects form, validates (~50ms)
    │
    ├── SYNC: validate_trade_data()
    │   ├── Check required fields
    │   └── Validate portfolio/security in DB
    │       (returns entity_details for reuse)
    │
    └── If valid: insert_trade_fast() (~100ms)
        │
        ├── SYNC (BLOCKING): UPSERT cis_trade
        │   └── status='INITIAL', src_system='CIS'
        │
        └── ASYNC (NON-BLOCKING): _queue_trade_events()
            ├── INSERT HISTORY event
            └── INSERT SETTLEMENT event
    │
    ▼
ASYNC AUDIT: log_action_async() (parallel, non-blocking)
    │
    ▼
RESPONSE: Redirect to trade_list (~200ms total)


┌─────────────────────────────────────────────────────────────────────┐
│ BACKGROUND SETTLEMENT PROCESSING (Decoupled)                        │
└─────────────────────────────────────────────────────────────────────┘

Background Worker (PositionQueueService) - runs continuously
    │
    └── Polls cis_position_queue every 10 seconds
        │
        ├── Gets PENDING items (batch of 100)
        │
        └── For each item:
            │
            ├── IF BACKDATED (has CHAIN_RECALC metadata):
            │   └── _process_chain_recalculation()
            │       ├── Get trades from backdated date to today
            │       └── Recalculate each position chronologically
            │
            └── ELSE (T+0 normal):
                └── position_service.calculate_position()
                    ├── Get current position
                    ├── Calculate new AVP
                    └── Save new version (is_latest=true)
            │
            ▼
        Update queue status = COMPLETED

SLA: < 5 minutes from queue to completion
```

---

## 12. Monitoring & Troubleshooting

### Queue Health Check

```sql
-- Check queue status distribution
SELECT status, COUNT(*) as count
FROM gmp_cis.cis_position_queue
GROUP BY status;

-- Check SLA breaches (> 5 minutes)
SELECT *
FROM gmp_cis.cis_position_queue
WHERE status = 'COMPLETED'
  AND (completed_at - queued_at) > 300;

-- View failed items
SELECT *
FROM gmp_cis.cis_position_queue
WHERE status IN ('FAILED', 'DEAD_LETTER')
ORDER BY queued_at DESC;
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Queue items stuck in PENDING | Worker not running | Start worker: `position_queue_service.start_worker()` |
| SLA breaches | High load or slow DB | Scale workers or optimize queries |
| DEAD_LETTER items | Persistent failures | Check error_message, fix data, re-queue |
| Connection pool exhausted | Too many concurrent requests | Increase pool_size or add connection wait |

---

## 13. Performance Monitoring (Long-Running Applications)

For Cloudera applications that run continuously without restarts, we provide comprehensive monitoring.

### Health Check Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/core/health/` | GET | Overall health status with all checks |
| `/core/pool-stats/` | GET | Detailed connection pool statistics |
| `/core/reset-stats/` | POST | Reset performance counters |

### Health Check Response Example

```json
{
  "status": "healthy",
  "timestamp": "2026-03-25T10:30:00.000Z",
  "checks": {
    "impala_pool": {
      "status": "healthy",
      "active_connections": 5,
      "pool_size": 35,
      "pool_available": 30,
      "utilization_pct": 14.3
    },
    "async_queue": {
      "status": "healthy",
      "queue_size": 12
    },
    "performance": {
      "status": "healthy",
      "request_count": 1523,
      "slow_request_count": 3,
      "slow_request_pct": 0.2,
      "avg_request_time_ms": 245.5
    },
    "impala_connectivity": {
      "status": "healthy"
    }
  }
}
```

### Performance Middleware

The `PerformanceMonitoringMiddleware` automatically:
- Logs slow requests (> 5 seconds)
- Periodically logs pool statistics (every 5 minutes)
- Recycles idle connections (> 5 minutes idle)
- Adds `X-Request-Duration-Ms` header to responses

### Connection Pool Optimizations

| Optimization | Description | Impact |
|--------------|-------------|--------|
| Validation Skip | Skip SELECT 1 ping for connections used < 10 seconds ago | ~200ms saved per request |
| Idle Recycling | Close connections idle > 5 minutes | Prevents stale connections |
| Batch FX Rates | Single query for all currency pairs | ~500ms saved on trade list |
| Dropdown Caching | Only load on GET, not successful POST | ~30s saved on trade create |
| Entity Caching | Cache portfolio/security validation 15s | ~200ms saved per validation |

### Monitoring Commands

```python
# Get pool statistics programmatically
from core.repositories.impala_connection import impala_manager

stats = impala_manager.get_pool_stats()
print(f"Pool utilization: {stats['pool_utilization_pct']}%")

# Log pool stats
impala_manager.log_pool_stats()

# Reset counters
impala_manager.reset_stats()

# Recycle idle connections
impala_manager.recycle_idle_connections(max_idle_seconds=300)
```

---

## Summary

The trade processing system is designed with these principles:

1. **Fast User Response (~200ms)** - Only blocking operation is trade insert
2. **Async Settlement Processing** - All position calculations queued
3. **Versioned Positions** - Full audit trail with is_latest flag
4. **Chain Recalculation** - Backdated trades handled correctly
5. **SLA Monitoring** - < 5 minutes queue to completion
6. **Retry with Dead Letter** - 3 retries before manual intervention
7. **Connection Pooling** - Efficient database resource usage with monitoring
8. **Four-Eyes Workflow** - Maker-checker enforcement
9. **Performance Monitoring** - Health endpoints and automatic logging for long-running apps
