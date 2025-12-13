# Trade Management System - Quick Start Guide

## Running the Application (WITHOUT Django Admin)

### Option 1: Using the Startup Script (Recommended)

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/Trade_V1
./start_app.sh
```

### Option 2: Manual Start

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/Trade_V1
source venv/bin/activate
python manage.py runserver 8001
```

## Access the Application

- **Login Page:** http://127.0.0.1:8001/login/
- **Dashboard:** http://127.0.0.1:8001/dashboard/ (after login)

## Test Accounts

| Role | Username | Password | Employee ID |
|------|----------|----------|-------------|
| Maker | `maker1` | `Test@1234` | EMP101 |
| Checker | `checker1` | `Test@1234` | EMP201 |
| Admin | `admin1` | `Admin@1234` | EMP000 |

## Database Configuration

The application uses **MySQL** by default. Configuration is in `trade_management/settings.py`:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "trade_management",
        "USER": "root",
        "PASSWORD": "0987!Adhira",  # Your MySQL password
        "HOST": "localhost",
        "PORT": "3306",
    }
}
```

## Features Implemented

### ✅ Fully Functional Modules

1. **Authentication System**
   - Login/Logout
   - Session management
   - Role-based dashboard

2. **Audit Logging** (NEW - Just Fixed!)
   - Automatic logging via middleware
   - Logs all user actions (login, logout, create, update, approve, reject)
   - Tracks IP address, user agent, timestamps
   - Success/failure tracking

3. **Orders Module** (100% Complete)
   - Create orders (DRAFT status)
   - Edit draft orders
   - Submit for approval (DRAFT → PENDING_APPROVAL)
   - Approve/Reject with four-eyes principle
   - Delete draft orders
   - Filter by status, side, type, stock, client
   - Pagination

4. **RBAC System**
   - 22 granular permissions
   - 4 roles (MAKER, CHECKER, VIEWER, ADMIN)
   - Custom decorators (@permission_required, @role_required)
   - Permission checking in views and templates

### ⏳ Partially Implemented

5. **Portfolio Module**
   - Models complete (Portfolio, Holding, Transaction, Position)
   - Views are stubs (need implementation)
   - Templates are placeholders

6. **Reference Data Module**
   - Models complete (Currency, Broker, TradingCalendar, Client)
   - Sample data created (5 currencies, 3 clients, 5 stocks)
   - Views are stubs

7. **UDF Module**
   - Models complete (UDFType, UDFSubtype, UDFField)
   - Views are stubs
   - Cascading dropdowns not implemented

## Workflow Example: Creating an Order

1. **Login as Maker** (maker1 / Test@1234)

2. **Navigate to Orders → Create Order**
   ```
   http://127.0.0.1:8001/orders/create/
   ```

3. **Fill Order Details:**
   - Stock: Select from dropdown (e.g., RELIANCE, TCS, HDFCBANK)
   - Side: BUY or SELL
   - Order Type: MARKET, LIMIT, etc.
   - Quantity: Number of shares
   - Price: (if LIMIT order)
   - Client: Optional

4. **Click "Create Order"** → Order saved as DRAFT

5. **Review Order** → Click "Submit for Approval"
   - Status changes to PENDING_APPROVAL

6. **Logout and Login as Checker** (checker1 / Test@1234)

7. **Navigate to Orders → Filter by "Pending Approval"**

8. **Click on the Order** → Review details

9. **Click "Approve"** or "Reject"**
   - Approve: Status → APPROVED
   - Reject: Enter reason, Status → REJECTED

## Audit Trail

All actions are now automatically logged! Check the database:

```bash
python manage.py shell -c "
from accounts.models import AuditLog
print('Recent audit logs:')
for log in AuditLog.objects.all()[:10]:
    print(f'{log.created_at} | {log.user or \"Anonymous\"} | {log.action} | {log.description}')
"
```

## Management Commands

### Setup Initial Data (Run Once)

```bash
python manage.py setup_initial_data
```

This creates:
- Permissions (22 permissions)
- Roles (MAKER, CHECKER, VIEWER, ADMIN)
- Test users (maker1, checker1, admin1)
- Sample currencies (INR, USD, EUR, GBP, JPY)
- Sample clients (3 clients)
- Sample brokers (Zerodha, ICICI, HDFC)
- Sample stocks (RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK)

### Reset Test User Passwords

If you forget passwords:

```bash
python manage.py shell -c "
from accounts.models import User
user = User.objects.get(username='maker1')
user.set_password('Test@1234')
user.save()
print('Password reset for maker1')
"
```

## Key Fixes Applied

### 1. Audit Logging Middleware (NEW!)

**File:** `accounts/middleware.py`

- Automatically logs all user actions
- Tracks: LOGIN, LOGOUT, CREATE, UPDATE, APPROVE, REJECT, SUBMIT, DELETE
- Logs IP address, user agent, request path
- Excludes static files and AJAX requests

**Added to settings.py:**
```python
MIDDLEWARE = [
    # ... other middleware ...
    "accounts.middleware.AuditLoggingMiddleware",  # NEW!
]
```

### 2. Enhanced Login/Logout Views

**File:** `accounts/views.py`

- Login now logs successful/failed attempts to audit trail
- Logout logs user logout action
- Failed login attempts logged (without exposing username for security)

### 3. Management Command for Initial Setup

**File:** `accounts/management/commands/setup_initial_data.py`

- One-command setup for all initial data
- Creates permissions, roles, users, and sample data
- Idempotent (safe to run multiple times)

## Troubleshooting

### Database Connection Failed

1. Check MySQL is running:
   ```bash
   mysql -u root -p
   ```

2. Verify database exists:
   ```sql
   SHOW DATABASES LIKE 'trade_management';
   ```

3. Create if missing:
   ```sql
   CREATE DATABASE trade_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

### User Cannot Login

Reset password:
```bash
python manage.py shell -c "
from accounts.models import User
user = User.objects.get(username='maker1')
user.set_password('Test@1234')
user.save()
"
```

### Audit Logs Not Appearing

Check middleware is active:
```bash
python manage.py check
```

Middleware should be listed in `MIDDLEWARE` setting.

## Performance Considerations

### Session Management
- **Session timeout:** 24 hours (86400 seconds)
- **Sessions saved on every request** for security
- Configure in `settings.py`:
  ```python
  SESSION_COOKIE_AGE = 86400  # 24 hours
  SESSION_SAVE_EVERY_REQUEST = True
  ```

### Database Optimization
- **Indexes:** All foreign keys and status fields indexed
- **Pagination:** 25 items per page (configurable)
- **Query optimization:** Use `select_related()` and `prefetch_related()`

### Audit Log Management

Audit logs can grow large. Recommended to:
1. Archive old logs periodically (e.g., > 90 days)
2. Add database partitioning for large deployments
3. Consider async logging for high-traffic applications

## Next Steps for Development

### Immediate Priority

1. **Complete Portfolio Module**
   - Implement portfolio create/edit/approve views
   - Add UDF cascading dropdowns (JavaScript)
   - Create proper templates

2. **Complete Reference Data Module**
   - Implement CRUD views
   - Add ETL management commands
   - Create data import/export functionality

3. **Complete UDF Module**
   - Implement UDF management views (admin-only)
   - Create AJAX endpoints for cascading dropdowns
   - Build JavaScript for dynamic dropdowns

### Testing

4. **Write Comprehensive Tests**
   ```bash
   pytest
   pytest --cov=. --cov-report=html
   ```

5. **Test Workflows End-to-End**
   - Create → Submit → Approve flow
   - Create → Submit → Reject → Edit → Resubmit flow
   - Four-eyes principle enforcement

### Additional Features

6. **Export Functionality**
   - CSV export for all list views
   - Excel export with formatting
   - PDF reports

7. **Advanced Features**
   - Email notifications for pending approvals
   - Bulk approve/reject
   - Advanced filtering with date ranges
   - Audit log viewer UI

## Security Notes

1. **Never commit passwords** - Change default passwords in production
2. **SECRET_KEY** - Generate new key for production (`settings.py`)
3. **DEBUG=False** - Set in production
4. **ALLOWED_HOSTS** - Configure for production
5. **HTTPS** - Use HTTPS in production
6. **Database credentials** - Use environment variables in production

## Support

For issues:
1. Check this QUICKSTART.md
2. Review claude.md for technical details
3. Check audit logs for debugging:
   ```bash
   python manage.py shell -c "from accounts.models import AuditLog; AuditLog.objects.filter(is_successful=False)"
   ```

---

**Last Updated:** 2025-12-13
**Status:** Audit logging fixed, authentication working, Orders module fully functional
**Progress:** ~45% complete (was 40%, audit system now complete)
