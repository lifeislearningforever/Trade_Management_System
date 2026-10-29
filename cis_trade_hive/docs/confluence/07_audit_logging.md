# Audit Logging

> **Audience:** Support, SA, Developer, Compliance
> **Read time:** ~6 minutes

---

## What Is the Audit Log?

The audit log is a permanent, tamper-evident record of everything that happens in CIS:
- Every record created, edited, deleted, approved, rejected
- Every login and logout
- Every access-denied event
- Every export or import

You can think of it as a CCTV system for data — a complete history of who did what, when.

---

## What Gets Logged

| Action | When it's logged |
|--------|----------------|
| `CREATE` | New trade, portfolio, security, counterparty, etc. created |
| `UPDATE` | Any field on any record changed |
| `DELETE` | Record soft-deleted (marked inactive) |
| `APPROVE` | Checker approves a trade or portfolio |
| `REJECT` | Checker rejects a trade or portfolio |
| `LOGIN` | User logs in |
| `LOGOUT` | User logs out |
| `ACCESS_DENIED` | User tries to access something they don't have permission for |
| `EXPORT` | Data exported |
| `IMPORT` | Data imported (file upload, ETL) |

---

## What Each Log Entry Contains

| Field | Description |
|-------|-------------|
| `log_id` | Unique ID |
| `timestamp` | Exact time (millisecond precision) |
| `user` | Username who took the action |
| `action` | Action type (CREATE, UPDATE, etc.) |
| `severity` | INFO / WARNING / ERROR / CRITICAL |
| `object_type` | What was affected (TRADE, PORTFOLIO, etc.) |
| `object_id` | The ID of the affected record |
| `old_values` | JSON snapshot of the record before the change |
| `new_values` | JSON snapshot of the record after the change |
| `ip_address` | Client IP address |
| `endpoint` | URL that was called |
| `approval_status` | Four-eyes: PENDING / APPROVED / REJECTED |
| `approved_by` | Who approved (for approval actions) |
| `approved_at` | When approved |

---

## Severity Levels

| Level | When used |
|-------|----------|
| `INFO` | Normal operations — creates, reads, updates |
| `WARNING` | Unusual but not critical (e.g. empty data, late GMP feed) |
| `ERROR` | An operation failed |
| `CRITICAL` | Security events — ACCESS_DENIED, failed login attempts, invalid approval attempts |

---

## How Audit Logging Works (Technical)

Audit logging is **asynchronous** — it does not slow down the user's request.

```
User action completes (e.g. trade created)
  │
  ▼ AuditKuduRepository.log_action(action, user, object, old, new)
  │   → Builds audit record
  │   → Puts it in an in-memory queue
  │
  ▼ Background worker thread (4 workers, queue size 1000)
  │   Picks up from queue
  │   UPSERT INTO gmp_cis.cis_audit_log (...)
  │
User sees success message — audit write happens in background
```

Configuration:
- `AUDIT_ASYNC_ENABLED = True` — async mode (production)
- `AUDIT_ASYNC_WORKERS = 4` — number of writer threads
- `AUDIT_QUEUE_SIZE = 1000` — max queued entries before back-pressure
- `AUDIT_ONLY_WRITES = True` — in production, GET requests are not logged (only writes)
- `AUDIT_LOGGER_TYPE = 'impala'` — write to Kudu (`'console'` in dev)

---

## Viewing the Audit Log

### In the UI
1. Go to **Core → Audit Log**
2. Filter by:
   - Date range
   - User
   - Action type
   - Object type
   - Severity
3. Click any row to see full before/after JSON diff

### Via SQL (for support/investigation)
```sql
-- All actions by a user today
SELECT timestamp, action, object_type, object_id, new_values
FROM gmp_cis.cis_audit_log
WHERE user = 'alice'
  AND timestamp >= '2026-04-22 00:00:00'
ORDER BY timestamp DESC
LIMIT 100;

-- All changes to a specific trade
SELECT timestamp, user, action, old_values, new_values
FROM gmp_cis.cis_audit_log
WHERE object_type = 'TRADE'
  AND object_id = 'TRD-12345'
ORDER BY timestamp DESC;

-- All ACCESS_DENIED events
SELECT timestamp, user, endpoint, ip_address
FROM gmp_cis.cis_audit_log
WHERE action = 'ACCESS_DENIED'
  AND timestamp >= '2026-04-22 00:00:00'
ORDER BY timestamp DESC;

-- All approvals today
SELECT timestamp, user, object_type, object_id, approved_by
FROM gmp_cis.cis_audit_log
WHERE action = 'APPROVE'
  AND timestamp >= '2026-04-22 00:00:00'
ORDER BY timestamp DESC;
```

---

## Retention Policy

Audit logs are retained for **7 years** (regulatory requirement). After 2 years, older records may be archived to cold HDFS storage but remain queryable.

---

## For Support: Common Questions

| Question | Where to look |
|----------|--------------|
| Who changed this trade? | Filter `cis_audit_log` by `object_type='TRADE'` and `object_id=<trade_id>` |
| Why was this user denied access? | Filter by `action='ACCESS_DENIED'` and `user=<username>` |
| What changed at 3pm yesterday? | Filter by timestamp range and `action='UPDATE'` |
| Who approved this portfolio? | Filter by `action='APPROVE'` and `object_type='PORTFOLIO'` |
| Is someone trying to break in? | Filter `severity='CRITICAL'` — look for repeated ACCESS_DENIED from same IP |

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `core/audit/audit_kudu_repository.py` | Async audit writer — queue + workers |
| `core/middleware/audit_middleware.py` | Legacy HTTP-level audit (deprecated) |
| `sql/ddl/01_core_tables.sql` | `cis_audit_log` table DDL |
