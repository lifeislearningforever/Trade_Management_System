# DEV MODE - All Permissions Enabled

**Environment:** Development
**Date:** 2025-12-27
**Status:** ✅ RUNNING

---

## Changes Made for Dev Mode

### 1. Permission Checks Disabled

All permission checks have been **bypassed** to allow full access to all functionality during development testing.

#### Service Layer (portfolio/services/portfolio_service.py)

**`can_user_close()`** - Lines 558-565
```python
# DEV MODE: Allow all users to close ACTIVE portfolios
return portfolio_status == 'ACTIVE'

# PRODUCTION: Uncomment below to enforce permissions
# return (
#     portfolio_status == 'ACTIVE' and
#     (user.has_perm('portfolio.close_portfolio') or user.is_superuser)
# )
```

**`can_user_reactivate()`** - Lines 579-586
```python
# DEV MODE: Allow all users to reactivate CLOSED portfolios
return portfolio_status == 'CLOSED'

# PRODUCTION: Uncomment below to enforce permissions
# return (
#     portfolio_status == 'CLOSED' and
#     (user.has_perm('portfolio.reactivate_portfolio') or user.is_superuser)
# )
```

#### View Layer (portfolio/views.py)

**`portfolio_close()`** - Lines 380-383
```python
# DEV MODE: Permission check bypassed
# PRODUCTION: Uncomment below to enforce permissions
# if not PortfolioService.can_user_close(portfolio.status, request.user):
#     raise PermissionDenied('You do not have permission to close this portfolio.')
```

**`portfolio_reactivate()`** - Lines 414-417
```python
# DEV MODE: Permission check bypassed
# PRODUCTION: Uncomment below to enforce permissions
# if not PortfolioService.can_user_reactivate(portfolio.status, request.user):
#     raise PermissionDenied('You do not have permission to reactivate this portfolio.')
```

### 2. Template Updates - All Buttons Visible

#### Portfolio Detail (templates/portfolio/portfolio_detail.html)

**Line 23:** Added DEV MODE comment
```html
<!-- DEV MODE: All buttons visible based on status only -->
```

**Removed Permission Checks:**
- No `can_close` check - ACTIVE portfolios show close button
- No `can_reactivate` check - CLOSED portfolios show reactivate button
- No `created_by == request.user` check - All users can edit DRAFT/REJECTED
- No `perms.portfolio.can_approve` check - All users can approve/reject

#### Portfolio Form (templates/portfolio/portfolio_form.html)

**Line 201:** DEV MODE comment added
```html
<!-- DEV MODE: Show close button for ACTIVE portfolios -->
```

**Removed:** `can_close` permission check

### 3. Portfolio List - Actions Column Added

#### Portfolio List (templates/portfolio/portfolio_list.html)

**New Column Added:**
- **Header** (Line 112): "Actions" column with sticky positioning
- **Buttons** (Lines 148-159):
  - **View** (eye icon) - All portfolios
  - **Edit** (pencil icon) - DRAFT and REJECTED portfolios only

**Sticky Column Feature:**
- Actions column stays visible when scrolling horizontally
- Background color adjusts for CLOSED portfolios

---

## Available Functionality (DEV MODE)

### Portfolio List Page
- ✅ View all portfolios from Kudu
- ✅ Search and filter portfolios
- ✅ **NEW:** View button (eye icon) - Navigate to detail page
- ✅ **NEW:** Edit button (pencil icon) - For DRAFT/REJECTED portfolios
- ✅ Visual distinction for CLOSED portfolios (grayed out)
- ✅ Export to CSV

### Portfolio Detail Page
**Based on Status:**

| Status | Available Actions |
|--------|------------------|
| DRAFT | Edit, Submit for Approval |
| REJECTED | Edit |
| PENDING_APPROVAL | Approve, Reject |
| ACTIVE | **Close Portfolio** (with modal) |
| CLOSED | **Reactivate Portfolio** (with modal) |

### Close Portfolio (ACTIVE → CLOSED)
- Click "Close Portfolio" button
- Modal appears with:
  - Warning message
  - Optional reason field
  - Cancel/Close buttons
- ✅ Updates Kudu: status='CLOSED', is_active=false
- ✅ Records to cis_portfolio_history
- ✅ Logs to cis_audit_log

### Reactivate Portfolio (CLOSED → ACTIVE)
- Click "Reactivate Portfolio" button
- Modal appears with:
  - Info message
  - **Required** justification field
  - Cancel/Reactivate buttons
- ✅ Updates Kudu: status='ACTIVE', is_active=true
- ✅ Records to cis_portfolio_history
- ✅ Logs to cis_audit_log

---

## Running Application

### Server Status
```
✅ Django Dev Server: Running on http://localhost:8000
✅ Kudu/Impala: Running (Docker containers)
✅ Database: gmp_cis via Impala
```

### Access
**URL:** http://localhost:8000

**Auto-Login:** Enabled
- User: PRAKASH HOSALLI
- No password required in dev mode

### Check Server
```bash
# View server logs
docker ps --filter "name=kudu"

# Check if Django is running
curl http://localhost:8000
```

---

## Testing Steps

### 1. Test Portfolio List
```
1. Go to http://localhost:8000/portfolio/
2. Verify Actions column visible
3. Click View (eye icon) on any portfolio
4. Click Edit (pencil icon) on DRAFT portfolio
```

### 2. Test Close Portfolio
```
1. Find an ACTIVE portfolio
2. Go to detail page
3. Click "Close Portfolio" button
4. Enter optional reason: "Testing close functionality"
5. Click "Close Portfolio"
6. Verify status changed to CLOSED
7. Verify in Kudu:

   docker exec -i kudu-impala-new impala-shell -q "
   SELECT name, status, is_active, updated_by
   FROM gmp_cis.cis_portfolio
   WHERE name = 'PORTFOLIO_NAME';
   "
```

### 3. Test Reactivate Portfolio
```
1. Find a CLOSED portfolio (or use one you just closed)
2. Go to detail page
3. Click "Reactivate Portfolio" button
4. Enter required justification: "Testing reactivation"
5. Click "Reactivate Portfolio"
6. Verify status changed to ACTIVE
7. Verify in Kudu:

   docker exec -i kudu-impala-new impala-shell -q "
   SELECT name, status, is_active, updated_by
   FROM gmp_cis.cis_portfolio
   WHERE name = 'PORTFOLIO_NAME';
   "
```

### 4. Test Audit Trail
```bash
# Check portfolio history
docker exec -i kudu-impala-new impala-shell -q "
SELECT * FROM gmp_cis.cis_portfolio_history
ORDER BY created_at DESC
LIMIT 10;
"

# Check audit log
docker exec -i kudu-impala-new impala-shell -q "
SELECT action_type, entity_id, action_description, username, audit_timestamp
FROM gmp_cis.cis_audit_log
WHERE action_type IN ('CLOSE', 'REACTIVATE')
ORDER BY audit_timestamp DESC
LIMIT 10;
"
```

---

## Switching to Production Mode

When ready for production, **uncomment** the following:

### 1. Service Layer
```python
# portfolio/services/portfolio_service.py

# In can_user_close() - uncomment lines 562-565
return (
    portfolio_status == 'ACTIVE' and
    (user.has_perm('portfolio.close_portfolio') or user.is_superuser)
)

# In can_user_reactivate() - uncomment lines 583-586
return (
    portfolio_status == 'CLOSED' and
    (user.has_perm('portfolio.reactivate_portfolio') or user.is_superuser)
)
```

### 2. Views
```python
# portfolio/views.py

# In portfolio_close() - uncomment lines 382-383
if not PortfolioService.can_user_close(portfolio.status, request.user):
    raise PermissionDenied('You do not have permission to close this portfolio.')

# In portfolio_reactivate() - uncomment lines 416-417
if not PortfolioService.can_user_reactivate(portfolio.status, request.user):
    raise PermissionDenied('You do not have permission to reactivate this portfolio.')
```

### 3. Templates
```html
<!-- portfolio_detail.html - line 23 -->
<!-- Change comment from DEV MODE to PRODUCTION MODE and add back permission checks -->

<!-- portfolio_form.html - line 201 -->
<!-- Change comment and add back: {% if portfolio and portfolio.status == 'ACTIVE' and can_close %} -->
```

### 4. Setup Permissions
```bash
# Via Django shell
python manage.py shell

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from portfolio.models import Portfolio

ct = ContentType.objects.get_for_model(Portfolio)
close_perm = Permission.objects.get(codename='close_portfolio', content_type=ct)
reactivate_perm = Permission.objects.get(codename='reactivate_portfolio', content_type=ct)

# Assign permissions
makers = Group.objects.get(name='Makers')
makers.permissions.add(close_perm)

checkers = Group.objects.get(name='Checkers')
checkers.permissions.add(reactivate_perm)
```

---

## File Locations

### Modified Files (Dev Mode)
- `portfolio/services/portfolio_service.py` - Permission checks bypassed
- `portfolio/views.py` - Permission validation commented
- `templates/portfolio/portfolio_detail.html` - All buttons visible
- `templates/portfolio/portfolio_list.html` - Actions column added
- `templates/portfolio/portfolio_form.html` - Close button always visible

### Kudu Tables
- `gmp_cis.cis_portfolio` - Portfolio master data
- `gmp_cis.cis_portfolio_history` - Change tracking (CLOSE, REACTIVATE)
- `gmp_cis.cis_audit_log` - Audit trail

### Documentation
- `PORTFOLIO_CLOSE_REACTIVATE_IMPLEMENTATION.md` - Full implementation details
- `DEV_MODE_SETUP.md` - This file

---

## Troubleshooting

### Issue: Buttons not showing
**Check:** Template changes saved and server auto-reloaded
**Solution:** Check server logs, manually refresh browser

### Issue: Close/Reactivate fails
**Check:** Kudu connection and table structure
```bash
docker exec -i kudu-impala-new impala-shell -q "DESCRIBE gmp_cis.cis_portfolio;"
```

### Issue: No history records
**Check:** cis_portfolio_history table exists
```bash
docker exec -i kudu-impala-new impala-shell -q "SELECT COUNT(*) FROM gmp_cis.cis_portfolio_history;"
```

### Issue: Actions column not sticky
**Clear:** Browser cache and hard refresh (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows)

---

## Summary

✅ **All permissions bypassed for development**
✅ **Actions column added to portfolio list**
✅ **Edit buttons visible in list**
✅ **Close/Reactivate fully functional**
✅ **All changes logged to Kudu**
✅ **100% Kudu/Impala - No Django ORM for data updates**

**Ready for full testing!** 🚀
