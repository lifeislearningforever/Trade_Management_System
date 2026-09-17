# ACL Integration - Authentication and Authorization

## Overview
The CIS Trade Hive application now has integrated ACL (Access Control List) based authentication using data from Hive tables. This provides session-based authentication with fine-grained permissions.

## Default User

**Login ID**: `TMP3RC`
**Name**: `PRAKASH HOSALLI`
**Email**: `prakash.hosalli1@uobgroup.com`
**Group**: `CIS-DEV` (Group ID: 1)
**Status**: Active and Enabled

### User Permissions
The TMP3RC user has the following permissions through the CIS-DEV group:

| Permission | Access Level | Description |
|------------|-------------|-------------|
| cis-report | WRITE | Create and modify reports |
| cis-portfolio | READ, WRITE | Full access to portfolios |
| cis-currency | WRITE | Manage currency data |
| cis-udf-view | READ | View UDF fields |
| cis-udflist | READ, WRITE | Manage UDF lists |
| cis-trade | WRITE | Manage trades |
| cis-udf-create | READ_WRITE | Create UDF fields |
| cis-udf-delete | READ_ | Delete UDF fields |
| cis-audit | READ | View audit logs |

## Architecture

### Components

**1. ACL Repository** (`core/repositories/acl_repository.py`)
- Handles all interactions with Hive ACL tables
- Methods:
  - `get_user_by_login(login)` - Fetch user by login ID
  - `get_user_permissions(group_id)` - Get all permissions for a group
  - `get_user_group(group_id)` - Get group information
  - `has_permission(group_id, permission, access_level)` - Check specific permission
  - `authenticate_user(login)` - Full authentication with permissions
  - `get_all_users()` - List all active users
  - `update_last_login(login)` - Log user login

**2. Authentication Views** (`core/views/auth_views.py`)
- `LoginView` - Handle user login
- `LogoutView` - Handle user logout
- `auto_login_tmp3rc()` - Quick login for development
- `@require_login` - Decorator to protect views
- `@require_permission(perm, level)` - Decorator for permission-based access

**3. Dashboard View** (`core/views/dashboard_views.py`)
- Main dashboard after login
- Shows user information
- Displays available modules based on permissions
- Lists all user permissions

**4. Templates**
- `templates/core/login.html` - Login page
- `templates/core/dashboard.html` - Dashboard page
- `templates/components/navbar_acl.html` - Navigation bar with user info

## URLs

### Authentication Routes
- `/` - Home (redirects to dashboard if logged in, otherwise login)
- `/login/` - Login page
- `/logout/` - Logout
- `/auto-login/` - Quick login as TMP3RC (development only)
- `/dashboard/` - Main dashboard (requires login)

### Module Routes (Protected)
- `/portfolio/` - Portfolio management
- `/trade/` - Trade management (when implemented)
- `/udf/` - UDF management
- `/reference-data/` - Reference data
- `/reports/` - Reports (when implemented)
- `/audit/` - Audit logs (when implemented)

## Session Data

When logged in, the following data is stored in the session:

```python
request.session['user_login']        # 'TMP3RC'
request.session['user_id']           # 2
request.session['user_name']         # 'PRAKASH HOSALLI'
request.session['user_email']        # 'prakash.hosalli1@uobgroup.com'
request.session['user_group_id']     # 1
request.session['user_group_name']   # 'CIS-DEV'
request.session['user_permissions']  # {permission: access_level} dict
```

## Usage Examples

### Protecting a View with Login
```python
from core.views.auth_views import require_login

@require_login
def my_view(request):
    # User must be logged in
    user_name = request.session.get('user_name')
    return HttpResponse(f"Hello {user_name}")
```

### Protecting a View with Permission
```python
from core.views.auth_views import require_permission

@require_permission('cis-portfolio', 'WRITE')
def create_portfolio(request):
    # User must have WRITE access to cis-portfolio
    return HttpResponse("Creating portfolio...")
```

### Checking Permissions in Templates
```django
{% if 'cis-portfolio' in request.session.user_permissions %}
    <a href="/portfolio/">Portfolios</a>
{% endif %}
```

### Accessing User Info in Templates
```django
<p>Welcome, {{ request.session.user_name }}!</p>
<p>Email: {{ request.session.user_email }}</p>
<p>Group: {{ request.session.user_group_name }}</p>
```

## Login Process

### 1. Manual Login
1. Navigate to `/login/`
2. Enter login ID (e.g., `TMP3RC`)
3. Click "Login"
4. Redirected to dashboard at `/dashboard/`

### 2. Auto Login (Development)
1. Navigate to `/auto-login/`
2. Automatically logged in as TMP3RC
3. Redirected to dashboard

### 3. Home Page
- If not logged in: Redirected to `/login/`
- If logged in: Redirected to `/dashboard/`

## Dashboard Features

### User Information Card
- Shows user avatar (initials)
- Displays full name
- Shows login ID and email
- Displays group membership
- Logout button

### Available Modules
Cards showing modules the user can access:
- Portfolio Management
- Trade Management
- UDF Management
- Reports
- Currency Reference
- Audit Log

Each card shows:
- Module name and icon
- Access level (READ, WRITE, READ_WRITE)
- Link to module

### Permissions Table
Complete list of all user permissions with access levels

## Configuration

### Settings.py Updates

**Added to INSTALLED_APPS**:
```python
'django.contrib.sessions',  # Required for session-based ACL auth
```

**Added to MIDDLEWARE**:
```python
'django.contrib.sessions.middleware.SessionMiddleware',  # Required for session-based auth
```

### Base Template Updates

**Updated navbar include** in `templates/base.html`:
```django
{% include 'components/navbar_acl.html' %}
```

## Security Notes

### Current Implementation
- **No password authentication** - Login by ID only (simplified for Hive integration)
- Session-based authentication
- Permission checking via session data
- All data stored in Hive (read-only from Django)

### Production Considerations
1. **Add Password Authentication**: Implement password hashing and verification
2. **Session Timeout**: Configure appropriate session timeout
3. **HTTPS**: Always use HTTPS in production
4. **CSRF Protection**: Enabled by default
5. **Session Security**: Configure secure session cookies
6. **Audit Logging**: Log all authentication events

### Recommended settings.py additions for production:
```python
# Session Security
SESSION_COOKIE_SECURE = True  # HTTPS only
SESSION_COOKIE_HTTPONLY = True  # No JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_COOKIE_AGE = 3600  # 1 hour timeout

# CSRF
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
```

## Testing

### Manual Testing
1. Start Django server: `python manage.py runserver`
2. Navigate to `http://localhost:8000/`
3. Should redirect to login page
4. Click "Auto-login as PRAKASH HOSALLI" link
5. Should redirect to dashboard showing user name "PRAKASH HOSALLI"
6. Verify navbar shows correct user name
7. Verify logout button works

### Automated Testing
```python
from django.test import TestCase, Client

class ACLAuthTest(TestCase):
    def test_login_redirect(self):
        """Test that home redirects to login when not authenticated."""
        client = Client()
        response = client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')

    def test_auto_login(self):
        """Test auto-login functionality."""
        client = Client()
        response = client.get('/auto-login/', follow=True)
        self.assertEqual(response.status_code, 200)
        session = client.session
        self.assertEqual(session['user_login'], 'TMP3RC')
        self.assertEqual(session['user_name'], 'PRAKASH HOSALLI')

    def test_dashboard_requires_login(self):
        """Test that dashboard requires login."""
        client = Client()
        response = client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
```

## Troubleshooting

### "User not found" Error
- Verify user exists in Hive: `SELECT * FROM cis_user WHERE login = 'TMP3RC';`
- Check user is enabled: `enabled = 'true'`
- Check user not deleted: `is_deleted = 'false'`

### Session Not Persisting
- Ensure `django.contrib.sessions` is in INSTALLED_APPS
- Ensure `SessionMiddleware` is in MIDDLEWARE
- Run migrations: `python manage.py migrate`

### Permission Denied
- Check user's group permissions in Hive
- Verify permission mapping in session
- Use `@require_permission` decorator correctly

### Navbar Not Showing User Name
- Check session data exists
- Verify `navbar_acl.html` is being used in base.html
- Check template context has request.session

## Files Created/Modified

### New Files
- `core/repositories/acl_repository.py`
- `core/views/auth_views.py`
- `core/views/dashboard_views.py`
- `templates/core/login.html`
- `templates/core/dashboard.html`
- `templates/components/navbar_acl.html`

### Modified Files
- `config/urls.py` - Added auth and dashboard routes
- `config/settings.py` - Added sessions support
- `templates/base.html` - Updated navbar include

## Summary

✓ **ACL-based authentication** using Hive tables
✓ **Default user**: TMP3RC (PRAKASH HOSALLI)
✓ **Session-based** login/logout
✓ **Fine-grained permissions** from cis_group_permissions
✓ **Dashboard** shows user info and available modules
✓ **Navbar** displays user name "PRAKASH HOSALLI"
✓ **First link** after login is dashboard
✓ **Protection decorators** for views
✓ **Auto-login** for development

The ACL integration is complete and ready for use!

---
**Created**: 2025-12-24
**Default User**: TMP3RC (PRAKASH HOSALLI)
**Status**: ✓ Complete and Ready
