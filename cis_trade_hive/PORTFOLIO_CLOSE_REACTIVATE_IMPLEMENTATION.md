# Portfolio Close/Reactivate Implementation - Kudu/Impala Only

**Date:** 2025-12-27
**Database:** Kudu via Impala
**No Django ORM** - All operations use Impala queries

---

## Overview

Implemented portfolio soft delete (close) and reactivation functionality using **only Kudu/Impala database**. All operations are recorded in Kudu audit tables.

---

## Database Setup Required

### Step 1: Create Portfolio History Table

Run this SQL script via Impala:

```bash
impala-shell -f sql/ddl/01_create_portfolio_history_kudu.sql
```

This creates `gmp_cis.cis_portfolio_history` table to track all portfolio changes.

### Step 2: Verify/Update Portfolio Table Columns

Check if `cis_portfolio` table has required columns:

```bash
impala-shell -q "DESCRIBE gmp_cis.cis_portfolio"
```

**Required columns:**
- `code` (STRING) - Portfolio unique identifier
- `status` (STRING) - Should already exist
- `is_active` (BOOLEAN) - For soft delete flag
- `updated_by` (STRING) - Track who made changes
- `updated_at` (STRING) - Timestamp of last update

If `is_active` or `updated_by` columns are missing, refer to:
```
sql/ddl/02_alter_portfolio_add_columns.sql
sql/ddl/portfolio_kudu_tables.sql
```

---

## Architecture

### Data Flow

```
User Action (UI)
    ↓
Django View (portfolio/views.py)
    ↓
Service Layer (portfolio/services/portfolio_service.py)
    ↓
Repository Layer (portfolio/repositories/portfolio_hive_repository.py)
    ↓
Impala Connection (core/repositories/impala_connection.py)
    ↓
Kudu Tables:
  - gmp_cis.cis_portfolio (UPDATE status, is_active)
  - gmp_cis.cis_portfolio_history (INSERT change record)
  - gmp_cis.cis_audit_log (INSERT audit record)
```

**No Django ORM Used** - All database operations via Impala UPSERT/UPDATE statements.

---

## Implementation Details

### 1. Repository Layer (Kudu Operations)

**File:** `portfolio/repositories/portfolio_hive_repository.py`

**New Methods:**

#### `update_portfolio_status()`
Updates portfolio status in Kudu using UPDATE statement:
```python
UPDATE gmp_cis.cis_portfolio
SET status = 'CLOSED', is_active = false, updated_by = 'username', updated_at = '2025-12-27 12:00:00'
WHERE code = 'PORTFOLIO_CODE'
```

#### `insert_portfolio_history()`
Inserts change record into Kudu using UPSERT:
```python
UPSERT INTO gmp_cis.cis_portfolio_history
(history_id, portfolio_code, action, status, changes, comments, performed_by, created_at)
VALUES (...)
```

#### `get_portfolio_by_code()`
Retrieves portfolio from Kudu by code:
```python
SELECT * FROM gmp_cis.cis_portfolio WHERE code = 'PORTFOLIO_CODE'
```

### 2. Service Layer (Business Logic)

**File:** `portfolio/services/portfolio_service.py`

**Refactored Methods:**

#### `close_portfolio(portfolio_code, user_id, username, user_email, reason)`
- Validates portfolio status is ACTIVE
- Updates Kudu: status='CLOSED', is_active=False
- Inserts history record with action='CLOSE'
- Logs to Kudu audit table

#### `reactivate_portfolio(portfolio_code, user_id, username, user_email, comments)`
- Validates portfolio status is CLOSED
- Requires mandatory comments
- Updates Kudu: status='ACTIVE', is_active=True
- Inserts history record with action='REACTIVATE'
- Logs to Kudu audit table

#### `can_user_close(portfolio_status, user)`
- Checks status == 'ACTIVE'
- Checks user has 'portfolio.close_portfolio' permission

#### `can_user_reactivate(portfolio_status, user)`
- Checks status == 'CLOSED'
- Checks user has 'portfolio.reactivate_portfolio' permission

### 3. View Layer (HTTP Handlers)

**File:** `portfolio/views.py`

#### `portfolio_close(request, pk)`
- GET: Redirects to detail page
- POST:
  - Gets portfolio object (Django ORM for UI only)
  - Extracts portfolio_code
  - Calls `PortfolioService.close_portfolio()` with Kudu operations
  - All data changes happen in Kudu, not Django DB

#### `portfolio_reactivate(request, pk)`
- Similar to close, but for reactivation
- Requires comments field (mandatory)

#### `portfolio_detail(request, pk)` - Updated
- Added permission checks: can_close, can_reactivate
- Passes to template for UI button visibility

#### `portfolio_edit(request, pk)` - Updated
- Added can_close permission check

### 4. Templates (UI)

**Files:**
- `templates/portfolio/portfolio_detail.html`
- `templates/portfolio/portfolio_list.html`
- `templates/portfolio/portfolio_form.html`

**Changes:**
- Close button for ACTIVE portfolios (with modal)
- Reactivate button for CLOSED portfolios (with modal)
- Visual distinction for CLOSED portfolios (grayed out)
- Dark badge for CLOSED status

---

## Kudu Tables

### cis_portfolio
**Operations:** UPDATE (status, is_active, updated_by, updated_at)

**Example:**
```sql
UPDATE gmp_cis.cis_portfolio
SET status = 'CLOSED',
    is_active = false,
    updated_by = 'john.doe',
    updated_at = '2025-12-27 14:30:00'
WHERE code = 'PFLIO001'
```

### cis_portfolio_history
**Operations:** UPSERT (insert change records)

**Schema:**
```sql
history_id BIGINT (PRIMARY KEY)
portfolio_code STRING
action STRING (CLOSE, REACTIVATE, UPDATE, etc.)
status STRING (CLOSED, ACTIVE, etc.)
changes STRING (JSON with old/new values)
comments STRING
performed_by STRING
created_at STRING
```

**Example Record:**
```json
{
  "history_id": 1735300800000,
  "portfolio_code": "PFLIO001",
  "action": "CLOSE",
  "status": "CLOSED",
  "changes": "{\"status\": {\"old\": \"ACTIVE\", \"new\": \"CLOSED\"}, \"is_active\": {\"old\": true, \"new\": false}, \"reason\": \"Portfolio no longer needed\"}",
  "comments": "Portfolio no longer needed",
  "performed_by": "john.doe",
  "created_at": "2025-12-27 14:30:00"
}
```

### cis_audit_log
**Operations:** UPSERT (audit trail)

**Records Created:**
- action_type='CLOSE' when portfolio is closed
- action_type='REACTIVATE' when portfolio is reactivated
- Includes: user_id, username, user_email, entity_type='PORTFOLIO', entity_id=portfolio_code, action_description

---

## Permissions

### Required Django Permissions

Add to Django groups via admin or management command:

**Makers Group:**
- `portfolio.close_portfolio` - Can close ACTIVE portfolios

**Checkers Group:**
- `portfolio.reactivate_portfolio` - Can reactivate CLOSED portfolios

### Setup Permissions

Via Django shell:
```python
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from portfolio.models import Portfolio

# Get content type
ct = ContentType.objects.get_for_model(Portfolio)

# Get or create permissions (created via migrations)
close_perm = Permission.objects.get(codename='close_portfolio', content_type=ct)
reactivate_perm = Permission.objects.get(codename='reactivate_portfolio', content_type=ct)

# Assign to groups
makers = Group.objects.get(name='Makers')
makers.permissions.add(close_perm)

checkers = Group.objects.get(name='Checkers')
checkers.permissions.add(reactivate_perm)
```

---

## Testing Steps

### 1. Create Kudu Tables

```bash
impala-shell -f sql/ddl/01_create_portfolio_history_kudu.sql
```

### 2. Verify Table Structure

```bash
impala-shell -q "DESCRIBE gmp_cis.cis_portfolio"
impala-shell -q "DESCRIBE gmp_cis.cis_portfolio_history"
impala-shell -q "DESCRIBE gmp_cis.cis_audit_log"
```

### 3. Test Close Portfolio

1. Login as user with 'Makers' group
2. Navigate to ACTIVE portfolio detail page
3. Click "Close Portfolio" button
4. Enter optional reason
5. Submit

**Verify in Kudu:**
```sql
-- Check portfolio status updated
SELECT code, status, is_active, updated_by, updated_at
FROM gmp_cis.cis_portfolio
WHERE code = 'YOUR_PORTFOLIO_CODE';

-- Check history record created
SELECT *
FROM gmp_cis.cis_portfolio_history
WHERE portfolio_code = 'YOUR_PORTFOLIO_CODE'
AND action = 'CLOSE'
ORDER BY created_at DESC
LIMIT 1;

-- Check audit log
SELECT *
FROM gmp_cis.cis_audit_log
WHERE entity_type = 'PORTFOLIO'
AND entity_id = 'YOUR_PORTFOLIO_CODE'
AND action_type = 'CLOSE'
ORDER BY audit_timestamp DESC
LIMIT 1;
```

### 4. Test Reactivate Portfolio

1. Login as user with 'Checkers' group
2. Navigate to CLOSED portfolio detail page
3. Click "Reactivate Portfolio" button
4. Enter required justification comments
5. Submit

**Verify in Kudu:**
```sql
-- Check portfolio status updated
SELECT code, status, is_active, updated_by, updated_at
FROM gmp_cis.cis_portfolio
WHERE code = 'YOUR_PORTFOLIO_CODE';

-- Check history record created
SELECT *
FROM gmp_cis.cis_portfolio_history
WHERE portfolio_code = 'YOUR_PORTFOLIO_CODE'
AND action = 'REACTIVATE'
ORDER BY created_at DESC
LIMIT 1;

-- Check audit log
SELECT *
FROM gmp_cis.cis_audit_log
WHERE entity_type = 'PORTFOLIO'
AND entity_id = 'YOUR_PORTFOLIO_CODE'
AND action_type = 'REACTIVATE'
ORDER BY audit_timestamp DESC
LIMIT 1;
```

---

## Files Modified

### Repository Layer
- `portfolio/repositories/portfolio_hive_repository.py` - Added Kudu UPDATE/UPSERT methods

### Service Layer
- `portfolio/services/portfolio_service.py` - Refactored to use only Kudu operations

### View Layer
- `portfolio/views.py` - Updated close/reactivate views for Kudu

### URL Configuration
- `portfolio/urls.py` - Added close/reactivate routes

### Templates
- `templates/portfolio/portfolio_detail.html` - Added close/reactivate buttons and modals
- `templates/portfolio/portfolio_list.html` - Visual distinction for CLOSED portfolios
- `templates/portfolio/portfolio_form.html` - Close button on edit page

### Database DDL
- `sql/ddl/01_create_portfolio_history_kudu.sql` - Create history table
- `sql/ddl/02_alter_portfolio_add_columns.sql` - Optional column additions
- `sql/ddl/portfolio_kudu_tables.sql` - Complete table definitions

### Models (Permissions Only)
- `portfolio/models.py` - Added close_portfolio and reactivate_portfolio permissions

---

## Key Differences from Django ORM Approach

| Aspect | Django ORM | Kudu/Impala (This Implementation) |
|--------|------------|-----------------------------------|
| Data Read | `Portfolio.objects.get(code='X')` | `SELECT * FROM cis_portfolio WHERE code='X'` via Impala |
| Data Update | `portfolio.save()` | `UPDATE cis_portfolio SET ...` via Impala |
| History Tracking | `PortfolioHistory.objects.create()` | `UPSERT INTO cis_portfolio_history` via Impala |
| Transactions | Django atomic transactions | Kudu handles consistency |
| Audit Logging | Signals/post_save | Direct UPSERT to cis_audit_log |

---

## Troubleshooting

### Issue: "Table cis_portfolio_history does not exist"
**Solution:** Run `impala-shell -f sql/ddl/01_create_portfolio_history_kudu.sql`

### Issue: "Column 'is_active' does not exist"
**Solution:** Your cis_portfolio table needs the is_active column. Refer to `sql/ddl/02_alter_portfolio_add_columns.sql`

### Issue: "Column 'code' does not exist"
**Solution:** Your table might use 'name' as primary key. Update repository to use 'name' instead of 'code', or recreate table with 'code' column.

### Issue: "Permission denied"
**Solution:** Ensure user has 'portfolio.close_portfolio' or 'portfolio.reactivate_portfolio' permission.

### Issue: "Failed to update portfolio in Kudu"
**Solution:** Check Impala connection and Kudu master addresses in table properties. Check logs for detailed error.

---

## Summary

✅ **100% Kudu/Impala Implementation**
- No Django ORM for data changes
- All updates via Impala UPDATE/UPSERT
- Complete audit trail in Kudu

✅ **Three Kudu Tables Used:**
- `cis_portfolio` - Portfolio master data
- `cis_portfolio_history` - Change tracking
- `cis_audit_log` - Audit trail

✅ **Full Feature Implementation:**
- Close ACTIVE portfolios (soft delete)
- Reactivate CLOSED portfolios
- Permission-based access control
- UI with modals for user input
- Visual distinction for closed portfolios
- Complete audit logging

✅ **Production Ready:**
- Error handling
- Validation
- Audit logging
- Permission checks
- User-friendly messages
