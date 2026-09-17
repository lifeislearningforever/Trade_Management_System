# Audit Logging Plan for CIS Trade Hive

## Objective
Add audit logging for CREATE, UPDATE, and DELETE operations across all repositories, with performance as the primary concern given known Kudu cluster issues.

---

## Current State Analysis

### Known Issues
1. **Kudu Leader Election Failures**: Tablet replicas can get stuck as FOLLOWER with no leader, causing 60+ second timeouts
2. **Blocking Audit Writes**: Current implementation blocks the main request when audit writes fail
3. **No Retry/Circuit Breaker**: Failed writes are not retried; system keeps attempting even when Kudu is down
4. **No Batching**: Each audit entry is inserted individually (inefficient for high volume)
5. **Connection Pool Contention**: Audit operations share the same 35-connection pool as data operations

### Current Architecture
- **AsyncAuditQueue**: Thread-based queue with 4 workers, 1000 max items
- **AuditLogKuduRepository**: Direct UPSERT to `cis_audit_log` table
- **Middleware**: Automatically captures HTTP requests (write operations only)
- **Manual Calls**: Some repositories/services call audit logging directly

---

## Design Principles

### 1. Fire-and-Forget Pattern
Audit logging should NEVER block or slow down the primary data operation:
- Data operation succeeds → Return immediately
- Audit queued asynchronously → Background processing
- Audit failure → Log error, continue (no impact on user)

### 2. Graceful Degradation
When Kudu is unavailable:
- Circuit breaker prevents repeated failed attempts
- Fallback to file-based logging
- Automatic recovery when Kudu is healthy again

### 3. Minimal Overhead
- Audit only what's necessary (CREATE, UPDATE, DELETE - not reads)
- Batch inserts where possible
- Separate connection pool for audit operations

---

## Implementation Plan

### Phase 1: Improve Async Audit Queue (Core Infrastructure)

#### 1.1 Add Circuit Breaker
```python
# core/audit/circuit_breaker.py

class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests fail fast
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,      # Failures before opening
        recovery_timeout: int = 60,       # Seconds before trying again
        success_threshold: int = 2        # Successes before closing
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = 'CLOSED'
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        with self._lock:
            if self.state == 'CLOSED':
                return True
            elif self.state == 'OPEN':
                # Check if recovery timeout has passed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                    self.success_count = 0
                    return True
                return False
            else:  # HALF_OPEN
                return True

    def record_success(self):
        """Record successful execution."""
        with self._lock:
            if self.state == 'HALF_OPEN':
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = 'CLOSED'
                    self.failure_count = 0
            self.failure_count = 0

    def record_failure(self):
        """Record failed execution."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == 'HALF_OPEN':
                self.state = 'OPEN'
            elif self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'
```

#### 1.2 Add File-Based Fallback Logger
```python
# core/audit/file_audit_logger.py

class FileAuditLogger:
    """
    Fallback audit logger that writes to rotating files.
    Used when Kudu is unavailable.
    """

    def __init__(self, log_dir: str = 'logs/audit_fallback'):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = None
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self._lock = threading.Lock()

    def log(self, audit_entry: dict) -> bool:
        """Write audit entry to file as JSON line."""
        with self._lock:
            try:
                file_path = self._get_current_file()
                with open(file_path, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
                return True
            except Exception as e:
                logger.error(f"File audit fallback failed: {e}")
                return False

    def _get_current_file(self) -> Path:
        """Get current log file, rotating if necessary."""
        date_str = datetime.now().strftime('%Y%m%d')
        base_path = self.log_dir / f'audit_fallback_{date_str}.jsonl'

        if base_path.exists() and base_path.stat().st_size > self.max_file_size:
            # Rotate to numbered file
            i = 1
            while True:
                rotated = self.log_dir / f'audit_fallback_{date_str}_{i:03d}.jsonl'
                if not rotated.exists():
                    return rotated
                i += 1

        return base_path
```

#### 1.3 Enhanced Async Audit Queue
```python
# core/audit/async_audit_queue.py (enhanced)

class AsyncAuditQueue:
    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 1000,
        batch_size: int = 10,          # NEW: Batch processing
        batch_timeout: float = 2.0      # NEW: Max wait for batch
    ):
        self.queue = Queue(maxsize=max_queue_size)
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        # Circuit breaker for Kudu
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )

        # Fallback logger
        self.file_logger = FileAuditLogger()

        # Statistics
        self._stats = {
            'processed': 0,
            'errors': 0,
            'fallbacks': 0,
            'circuit_open_count': 0,
            'batches_written': 0
        }

    def _worker_loop(self):
        """Enhanced worker with batching and circuit breaker."""
        worker_name = threading.current_thread().name
        batch = []
        last_flush_time = time.time()

        while not self.shutdown_event.is_set():
            try:
                # Try to get item with timeout
                try:
                    entry = self.queue.get(timeout=0.5)
                    batch.append(entry)
                    self.queue.task_done()
                except Empty:
                    pass

                # Flush batch if full or timeout reached
                should_flush = (
                    len(batch) >= self.batch_size or
                    (batch and time.time() - last_flush_time >= self.batch_timeout)
                )

                if should_flush and batch:
                    self._process_batch(batch)
                    batch = []
                    last_flush_time = time.time()

            except Exception as e:
                logger.error(f"{worker_name} error: {e}")

        # Flush remaining on shutdown
        if batch:
            self._process_batch(batch)

    def _process_batch(self, batch: List):
        """Process a batch of audit entries."""
        if not self.circuit_breaker.can_execute():
            # Circuit open - use fallback
            self._stats['circuit_open_count'] += 1
            for entry in batch:
                self.file_logger.log(entry.to_dict())
                self._stats['fallbacks'] += 1
            return

        try:
            # Try batch insert to Kudu
            success = self._batch_insert_kudu(batch)

            if success:
                self.circuit_breaker.record_success()
                self._stats['processed'] += len(batch)
                self._stats['batches_written'] += 1
            else:
                raise Exception("Batch insert failed")

        except Exception as e:
            self.circuit_breaker.record_failure()
            self._stats['errors'] += len(batch)

            # Fallback to file
            for entry in batch:
                self.file_logger.log(entry.to_dict())
                self._stats['fallbacks'] += 1

    def _batch_insert_kudu(self, batch: List) -> bool:
        """
        Batch insert audit entries using VALUES list.
        More efficient than individual UPSERTs.
        """
        if not batch:
            return True

        try:
            # Build multi-row VALUES clause
            values_list = []
            for entry in batch:
                data = entry.to_dict()
                values = self._format_values(data)
                values_list.append(f"({values})")

            # Single UPSERT with multiple rows
            upsert_query = f"""
            UPSERT INTO gmp_cis.cis_audit_log
            (audit_id, audit_timestamp, user_id, username, action_type,
             entity_type, entity_id, entity_name, action_description,
             old_value, new_value, status, audit_date)
            VALUES {', '.join(values_list)}
            """

            return impala_manager.execute_write(upsert_query, database='gmp_cis')

        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            return False
```

### Phase 2: Create Audit Decorator for Repositories

#### 2.1 Repository Audit Decorator
```python
# core/audit/audit_decorator.py

from functools import wraps
from typing import Callable, Optional
import json

def audit_write(
    action_type: str,          # CREATE, UPDATE, DELETE
    entity_type: str,          # EQUITY_PRICE, PORTFOLIO, etc.
    get_entity_id: Callable = None,     # Function to extract entity ID
    get_entity_name: Callable = None,   # Function to extract entity name
    capture_old_value: bool = False     # For UPDATE/DELETE
):
    """
    Decorator for repository write methods that automatically creates audit entries.

    Usage:
        @audit_write('CREATE', 'EQUITY_PRICE',
                     get_entity_id=lambda args, result: result.get('id'))
        def insert_equity_price(self, data):
            # ... insert logic
            return {'id': new_id, 'success': True}
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Capture old value for UPDATE/DELETE
            old_value = None
            entity_id = None

            if capture_old_value and action_type in ('UPDATE', 'DELETE'):
                # Try to get entity ID from args
                if args:
                    entity_id = args[0]  # Usually first arg is ID
                    old_value = self._get_record_for_audit(entity_id)

            # Execute the actual operation
            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                success = bool(result)
                error_msg = None
            except Exception as e:
                success = False
                error_msg = str(e)
                result = None
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                # Build audit entry (fire and forget)
                _queue_audit_entry(
                    action_type=action_type,
                    entity_type=entity_type,
                    entity_id=_extract_id(get_entity_id, args, kwargs, result),
                    entity_name=_extract_name(get_entity_name, args, kwargs, result),
                    old_value=old_value,
                    new_value=_extract_new_value(args, kwargs) if success else None,
                    success=success,
                    error_message=error_msg,
                    duration_ms=duration_ms,
                    username=kwargs.get('username') or _get_current_user()
                )

            return result
        return wrapper
    return decorator


def _queue_audit_entry(**kwargs):
    """Queue audit entry without blocking."""
    try:
        from core.audit.async_audit_queue import async_audit_queue
        from core.audit.audit_models import AuditEntry

        entry = AuditEntry(
            action_type=kwargs['action_type'],
            entity_type=kwargs['entity_type'],
            entity_id=str(kwargs.get('entity_id', '')),
            entity_name=kwargs.get('entity_name', ''),
            old_value=json.dumps(kwargs['old_value']) if kwargs.get('old_value') else None,
            new_value=json.dumps(kwargs['new_value']) if kwargs.get('new_value') else None,
            status='SUCCESS' if kwargs['success'] else 'FAILURE',
            error_message=kwargs.get('error_message'),
            duration_ms=kwargs.get('duration_ms'),
            username=kwargs.get('username', 'SYSTEM')
        )

        # Non-blocking enqueue
        if not async_audit_queue.enqueue(entry):
            # Queue full - log warning but don't block
            logger.warning(f"Audit queue full, entry dropped: {kwargs['action_type']} {kwargs['entity_type']}")

    except Exception as e:
        # Never let audit logging break the main operation
        logger.error(f"Failed to queue audit entry: {e}")
```

### Phase 3: Apply to Repositories

#### 3.1 Equity Price Repository (Example)
```python
# market_data/repositories/equity_price_hive_repository.py

from core.audit.audit_decorator import audit_write

class EquityPriceHiveRepository:

    @audit_write(
        action_type='CREATE',
        entity_type='EQUITY_PRICE',
        get_entity_id=lambda args, kwargs, result: kwargs.get('equity_price_data', {}).get('equity_price_id'),
        get_entity_name=lambda args, kwargs, result: kwargs.get('equity_price_data', {}).get('security_label')
    )
    def insert_equity_price(self, equity_price_data: Dict[str, Any], username: str = 'SYSTEM') -> bool:
        # Existing implementation (unchanged)
        ...

    @audit_write(
        action_type='UPDATE',
        entity_type='EQUITY_PRICE',
        get_entity_id=lambda args, kwargs, result: args[0] if args else kwargs.get('equity_price_id'),
        capture_old_value=True
    )
    def update_equity_price(self, equity_price_id: int, equity_price_data: Dict[str, Any], username: str = 'SYSTEM') -> bool:
        # Existing implementation (unchanged)
        ...

    @audit_write(
        action_type='DELETE',
        entity_type='EQUITY_PRICE',
        get_entity_id=lambda args, kwargs, result: args[0] if args else kwargs.get('equity_price_id'),
        capture_old_value=True
    )
    def delete_equity_price(self, equity_price_id: int, deleted_by: str) -> bool:
        # Existing implementation (unchanged)
        ...

    def _get_record_for_audit(self, entity_id: int) -> Optional[Dict]:
        """Get current record for audit comparison (used by decorator)."""
        return self.get_equity_price_by_id(entity_id)
```

### Phase 4: Configuration & Settings

#### 4.1 Settings Updates
```python
# config/settings.py

# Audit Logging Configuration
AUDIT_ENABLED = True                    # Master switch
AUDIT_ASYNC_ENABLED = True              # Use async queue
AUDIT_ASYNC_WORKERS = 4                 # Worker threads
AUDIT_QUEUE_SIZE = 2000                 # Increased queue size
AUDIT_BATCH_SIZE = 10                   # Batch inserts
AUDIT_BATCH_TIMEOUT = 2.0               # Seconds to wait for batch

# Circuit Breaker Settings
AUDIT_CIRCUIT_FAILURE_THRESHOLD = 5     # Failures before opening
AUDIT_CIRCUIT_RECOVERY_TIMEOUT = 60     # Seconds before retry
AUDIT_CIRCUIT_SUCCESS_THRESHOLD = 2     # Successes to close

# Fallback Settings
AUDIT_FALLBACK_ENABLED = True           # Enable file fallback
AUDIT_FALLBACK_DIR = 'logs/audit_fallback'
AUDIT_FALLBACK_MAX_FILE_SIZE = 10485760  # 10MB
```

---

## Implementation Order

### Step 1: Core Infrastructure (Priority: HIGH)
1. Create `core/audit/circuit_breaker.py`
2. Create `core/audit/file_audit_logger.py`
3. Enhance `core/audit/async_audit_queue.py` with:
   - Circuit breaker integration
   - Batch processing
   - Fallback logging
4. Update settings with new configuration

### Step 2: Audit Decorator (Priority: HIGH)
1. Create `core/audit/audit_decorator.py`
2. Unit tests for decorator

### Step 3: Repository Integration (Priority: MEDIUM)
Apply decorator to repositories in order:
1. `equity_price_hive_repository.py` (market_data)
2. `trade_kudu_repository.py` (trade)
3. `portfolio_kudu_repository.py` (portfolio)
4. `security_kudu_repository.py` (security)
5. `counterparty_kudu_repository.py` (reference_data)
6. `udf_field_repository.py` (udf)

### Step 4: Fallback Recovery (Priority: LOW)
1. Management command to replay fallback files to Kudu
2. Scheduled task to process fallback files

---

## Performance Considerations

### What We're Avoiding
| Problem | Solution |
|---------|----------|
| Blocking on Kudu writes | Fire-and-forget async queue |
| Kudu unavailable | Circuit breaker + file fallback |
| Individual inserts | Batch processing (10 records/batch) |
| Connection pool exhaustion | Separate audit connection (future) |
| Queue memory exhaustion | Bounded queue (2000 items) |

### Expected Performance
| Metric | Before | After |
|--------|--------|-------|
| Audit overhead per operation | 0-60+ seconds | <1ms (queue only) |
| Kudu writes per operation | 1 | 0.1 (batched) |
| Impact of Kudu failure | Page timeout | None (fallback) |
| Recovery from failure | Manual | Automatic |

---

## Monitoring & Observability

### Metrics to Track
```python
# Access via async_audit_queue.get_stats()
{
    'queue_size': 150,              # Current items waiting
    'processed': 10000,             # Total processed
    'errors': 5,                    # Failed writes
    'fallbacks': 20,                # Written to file
    'circuit_state': 'CLOSED',      # Circuit breaker state
    'batches_written': 1000,        # Batch efficiency
    'avg_batch_size': 8.5           # Items per batch
}
```

### Health Check Endpoint
```python
# Add to dashboard or health check
@api_view(['GET'])
def audit_health(request):
    stats = async_audit_queue.get_stats()
    health = 'healthy' if stats['circuit_state'] == 'CLOSED' else 'degraded'
    return Response({
        'status': health,
        'circuit_state': stats['circuit_state'],
        'queue_utilization': f"{stats['queue_size'] / 2000 * 100:.1f}%",
        'fallback_active': stats['fallbacks'] > 0
    })
```

---

## Rollback Plan

If issues arise:
1. Set `AUDIT_ENABLED = False` in settings
2. Decorator becomes no-op
3. All operations continue without audit logging
4. Investigate and fix issues
5. Re-enable when ready

---

## Files to Create/Modify

### New Files
1. `core/audit/circuit_breaker.py`
2. `core/audit/file_audit_logger.py`
3. `core/audit/audit_decorator.py`
4. `core/management/commands/replay_audit_fallback.py`

### Modified Files
1. `core/audit/async_audit_queue.py` - Add batching, circuit breaker
2. `config/settings.py` - Add new settings
3. `market_data/repositories/equity_price_hive_repository.py` - Add decorators
4. `trade/repositories/trade_kudu_repository.py` - Add decorators
5. `portfolio/repositories/portfolio_kudu_repository.py` - Add decorators
6. `security/repositories/security_kudu_repository.py` - Add decorators
7. `reference_data/repositories/counterparty_kudu_repository.py` - Add decorators
8. `udf/repositories/udf_field_repository.py` - Add decorators

---

## Summary

This plan addresses the core issues:
1. **Performance**: Fire-and-forget pattern with async queue
2. **Reliability**: Circuit breaker prevents cascading failures
3. **Durability**: File fallback ensures no audit data is lost
4. **Efficiency**: Batch inserts reduce Kudu write operations by ~90%
5. **Simplicity**: Decorator pattern makes adding audit logging trivial
6. **Observability**: Comprehensive stats for monitoring

The key insight is that **audit logging should never impact the user experience**. If Kudu is slow or down, we fall back gracefully and recover automatically.
