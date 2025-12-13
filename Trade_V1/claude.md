# Trade Management System V1 - Technical Documentation

## Project Overview

**Trade Management System V1** is a comprehensive Django-based trading platform with advanced Role-Based Access Control (RBAC), maker-checker workflow, and User Defined Fields (UDF) system. The system manages trading orders, portfolios, reference data, and reporting with strict approval workflows and audit trails.

**Version:** 1.0.0-beta
**Status:** In Development (40% Complete)
**Last Updated:** 2025-12-13

---

## Technology Stack

### Backend
- **Framework:** Django 5.2.9
- **Python:** 3.11+
- **Database:** MySQL (via PyMySQL) + SQLite (for development)
- **API:** Django REST Framework 3.16.1
- **Filters:** Django Filters 25.2

### Frontend
- **CSS Framework:** Bootstrap 5.3.3 (local)
- **Icons:** Bootstrap Icons 1.11.3 (local)
- **JavaScript:** Bootstrap Bundle (includes Popper.js)
- **Custom Styling:** Professional custom.css with color variables

### Additional Packages
- **Forms:** django-crispy-forms 2.5, crispy-bootstrap5 2025.6
- **Admin UI:** Jazzmin (professional admin interface)
- **Images:** Pillow 12.0.0
- **Development:** django-extensions 4.1
- **Testing:** pytest, pytest-django, pytest-cov

### Database Configuration
- **Primary:** MySQL (`trade_management` database)
- **Development:** SQLite (optional fallback)
- **Character Set:** utf8mb4_unicode_ci
- **Connection:** PyMySQL (installed as MySQLdb)

---

## Architecture Overview

### Project Structure

```
Trade_V1/
├── manage.py                      # Django management script
├── requirements.txt               # Python dependencies
├── pytest.ini                     # Pytest configuration
├── conftest.py                    # Pytest fixtures
├── README.md                      # Project documentation
├── STATUS.md                      # Implementation status
├── db.sqlite3                     # SQLite database (fallback)
│
├── trade_management/              # Project settings & main config
│   ├── settings.py                # Django settings (MySQL, apps, Jazzmin)
│   ├── urls.py                    # Root URL configuration
│   ├── wsgi.py                    # WSGI application
│   └── asgi.py                    # ASGI application (not configured)
│
├── accounts/                      # Authentication, RBAC & Audit
│   ├── models.py                  # User, Role, Permission, RolePermission, UserRole, AuditLog
│   ├── views.py                   # Login, logout, dashboard views
│   ├── urls.py                    # Authentication URLs
│   ├── decorators.py              # Custom RBAC decorators (@permission_required, etc.)
│   ├── admin.py                   # Admin configuration
│   ├── forms.py                   # Authentication forms
│   └── tests/                     # Unit tests
│
├── udf/                           # User Defined Fields System
│   ├── models.py                  # UDFType, UDFSubtype, UDFField
│   ├── views.py                   # UDF management views (stub)
│   ├── urls.py                    # UDF URLs
│   └── admin.py                   # Admin configuration
│
├── orders/                        # Trading Orders Module
│   ├── models.py                  # Stock, Order, Trade
│   ├── views.py                   # Order CRUD + workflow views (complete)
│   ├── forms.py                   # OrderForm, OrderRejectForm, OrderFilterForm
│   ├── validators.py              # Workflow validation functions
│   ├── urls.py                    # Order URLs (8 routes)
│   ├── admin.py                   # Admin configuration
│   └── tests/                     # Unit tests
│       ├── test_forms.py
│       └── test_validators.py
│
├── portfolio/                     # Portfolio Management Module
│   ├── models.py                  # Portfolio, Holding, Transaction, Position
│   ├── views.py                   # Portfolio views (stub)
│   ├── urls.py                    # Portfolio URLs
│   └── admin.py                   # Admin configuration
│
├── reference_data/                # Reference Data Module
│   ├── models.py                  # Currency, Broker, TradingCalendar, Client
│   ├── views.py                   # Reference data views (stub)
│   ├── urls.py                    # Reference data URLs
│   └── admin.py                   # Admin configuration
│
├── reporting/                     # Report Generation Module
│   ├── models.py                  # Report (with UDF integration)
│   ├── views.py                   # Report generation views (stub)
│   └── admin.py                   # Admin configuration
│
├── templates/                     # HTML Templates
│   ├── base.html                  # Base template with navbar
│   ├── base_with_sidebar.html     # Base with sidebar for list pages
│   ├── includes/                  # Reusable components
│   │   ├── navbar.html
│   │   ├── messages.html
│   │   ├── pagination.html
│   │   └── status_badge.html
│   ├── accounts/                  # Authentication templates
│   │   ├── login.html
│   │   └── dashboard.html
│   ├── orders/                    # Order templates (7 templates)
│   ├── portfolio/                 # Portfolio templates (placeholder)
│   ├── udf/                       # UDF templates (placeholder)
│   └── reference_data/            # Reference data templates (placeholder)
│
├── static/                        # Static files (Bootstrap, custom CSS)
│   ├── css/
│   │   ├── bootstrap.min.css
│   │   ├── bootstrap-icons.css
│   │   └── custom.css             # Professional custom styling
│   ├── js/
│   │   └── bootstrap.bundle.min.js
│   └── fonts/                     # Bootstrap Icons fonts
│
├── staticfiles/                   # Collected static files (production)
├── media/                         # User uploads (profile pictures, etc.)
├── htmlcov/                       # Code coverage reports
└── venv/                          # Virtual environment
```

---

## Module Details

### 1. Accounts Module (100% Complete)

**Purpose:** Authentication, Authorization, RBAC, and Audit Logging

#### Models

**User (Custom User Model - AbstractUser)**
- 50+ attributes for comprehensive user management
- Personal: first_name, last_name, middle_name, full_name (auto-generated)
- Employee: employee_id, department, designation, reporting_manager
- Contact: phone_number, mobile_number, alternate_email, address fields
- Professional: joining_date, leaving_date, employment_status
- Security: last_login_ip, failed_login_attempts, account_locked_until
- Profile: profile_picture, bio, timezone, language
- Audit: created_at, updated_at, created_by, updated_by

**Key Methods:**
- `has_role(role_code)` - Check if user has a specific role
- `has_permission(permission_code)` - Check if user has permission
- `has_any_permission(permission_codes)` - Check multiple permissions
- `get_all_permissions()` - Get all permissions from roles
- `get_display_name()` - Returns "Full Name (EMP001)"
- `get_role_codes()` - Get list of user's role codes

**Permission**
- Granular permissions for system actions
- Examples: view_customer_data, edit_product_inventory, approve_trade
- Fields: code, name, description, category, is_active

**Role**
- Job functions/groups (Manager, Trader, Checker, Maker)
- Many-to-many with Permissions via RolePermission
- Fields: code, name, description, is_active, is_system_role, display_order

**UserRole**
- Maps users to roles with validity periods
- Fields: user, role, valid_from, valid_until, is_active

**RolePermission**
- Maps roles to permissions with audit trail
- Fields: role, permission, granted_at, granted_by

**AuditLog**
- Complete audit trail for all actions
- 17 action types: CREATE, UPDATE, DELETE, APPROVE, REJECT, LOGIN, LOGOUT, etc.
- Tracks: user, action, description, category, object_type, object_id
- IP tracking: ip_address, user_agent, request_method, request_path
- Change tracking: old_values, new_values (JSON)
- Success tracking: is_successful, error_message

**Convenience Method:**
```python
AuditLog.log_action(
    user=request.user,
    action='CREATE',
    description='Created order ORD-123',
    category='order',
    object_type='Order',
    object_id='uuid-here',
    ip_address=request.META.get('REMOTE_ADDR')
)
```

#### Views
- `login_view` - User authentication
- `logout_view` - User logout
- `dashboard_view` - Role-based dashboard with statistics

#### Custom Decorators (accounts/decorators.py)
- `@permission_required('permission_code')` - Check custom permissions
- `@role_required('ROLE_CODE')` - Check user roles
- `@superuser_required()` - Admin-only access
- `@maker_required()` - Shortcut for maker role
- `@checker_required()` - Shortcut for checker role

---

### 2. UDF Module (Stub Implementation)

**Purpose:** User Defined Fields for dynamic dropdowns across the system

#### Models

**UDFType**
- Main category of UDF (PORTFOLIO, TRADE, ORDER, REPORT)
- Fields: code, name, description, is_active, display_order

**UDFSubtype**
- Subcategories within a UDF type
- Example: PORTFOLIO -> GROUP, SUBGROUP, MANAGER, STRATEGY
- Fields: udf_type (FK), code, name, field_label, is_required, is_active

**UDFField**
- Actual dropdown values
- Example: PORTFOLIO.GROUP -> "EQUITY", "FIXED_INCOME", "DERIVATIVES"
- Fields: udf_subtype (FK), code, value, description, is_active, is_default, display_order, metadata (JSON)

**Helper Methods:**
```python
# Get active fields for dropdown
UDFField.get_active_fields('PORTFOLIO', 'GROUP')

# Get default field
UDFField.get_default_field('PORTFOLIO', 'GROUP')

# Get Django form choices
UDFField.get_choices('PORTFOLIO', 'GROUP', include_blank=True)
```

#### Example UDF Hierarchy
```
UDFType: PORTFOLIO
├── UDFSubtype: GROUP
│   ├── UDFField: EQUITY (Equity Investments)
│   ├── UDFField: FIXED_INCOME (Fixed Income)
│   └── UDFField: DERIVATIVES (Derivatives)
├── UDFSubtype: MANAGER
│   ├── UDFField: MGR001 (John Smith)
│   └── UDFField: MGR002 (Jane Doe)
└── UDFSubtype: STRATEGY
    ├── UDFField: GROWTH (Growth Strategy)
    └── UDFField: VALUE (Value Investing)
```

---

### 3. Orders Module (100% Complete)

**Purpose:** Trading order management with maker-checker workflow

#### Models

**Stock**
- Stock/Security master data
- Fields: symbol, name, isin, exchange (NSE/BSE/NYSE/NASDAQ/LSE)
- Asset class: EQUITY, DEBT, DERIVATIVE, COMMODITY, CURRENCY
- Additional: sector, industry, currency, lot_size, metadata

**Order (UUID Primary Key)**
- Trading order with complete workflow
- Identification: id (UUID), order_id (auto-generated)
- Order details: stock (FK), side (BUY/SELL), order_type (MARKET/LIMIT/STOP_LOSS)
- Quantities: quantity, filled_quantity
- Prices: price, stop_price, average_price, commission
- Status: DRAFT, PENDING_APPROVAL, APPROVED, REJECTED, SUBMITTED, FILLED, CANCELLED

**Maker-Checker Fields:**
- created_by (FK to User) - Maker
- created_by_name (auto-filled from user.get_display_name())
- created_by_employee_id (auto-filled)
- approved_by (FK to User) - Checker
- approved_by_name (auto-filled)
- approved_by_employee_id (auto-filled)
- approved_at, rejection_reason

**Additional Fields:**
- client (FK to Client), broker (FK to Broker)
- validity: DAY, IOC, GTC
- notes, metadata (JSON)

**Methods:**
- `can_be_approved_by(user)` - Validates four-eyes principle
- `approve(user, notes)` - Approve order
- `reject(user, reason)` - Reject order

**Trade**
- Trade execution records (actual fills)
- Links to Order and Stock
- Tracks: quantity, price, commission, tax, other_charges
- Exchange tracking: exchange_trade_id, executed_at
- Auto-fills: trade_id, executed_by_name (from order.created_by)

#### Workflow Validators (orders/validators.py)
- `can_edit_order(order, user)` - User is creator AND status is DRAFT
- `can_submit_order(order, user)` - User is creator AND status is DRAFT
- `can_approve_order(order, user)` - User is NOT creator AND has permission
- `can_reject_order(order, user)` - Same as approve
- `can_delete_order(order, user)` - User is creator AND status is DRAFT
- `get_workflow_error_message(order, user, action)` - User-friendly errors

#### Views (Function-Based)
1. `order_list` - List with filters and pagination
2. `order_create` - Create order in DRAFT status
3. `order_detail` - View order with workflow actions
4. `order_edit` - Edit DRAFT orders
5. `order_submit` - Submit for approval (DRAFT → PENDING_APPROVAL)
6. `order_approve` - Approve order (PENDING_APPROVAL → APPROVED)
7. `order_reject` - Reject order with reason
8. `order_delete` - Delete DRAFT orders

#### Forms
- `OrderForm` - Create/edit orders with validation
- `OrderRejectForm` - Rejection with mandatory reason
- `OrderFilterForm` - Filter by status, side, type, stock, client

#### URL Patterns
```
/orders/                        # List
/orders/create/                # Create
/orders/<uuid>/                # Detail
/orders/<uuid>/edit/           # Edit
/orders/<uuid>/submit/         # Submit for approval
/orders/<uuid>/approve/        # Approve
/orders/<uuid>/reject/         # Reject
/orders/<uuid>/delete/         # Delete
```

#### Status Transitions
```
DRAFT → PENDING_APPROVAL → APPROVED
              ↓
          REJECTED
```

---

### 4. Portfolio Module (Stub Implementation)

**Purpose:** Portfolio management with UDF integration

#### Models

**Portfolio**
- Portfolio with maker-checker workflow
- Identification: id (UUID), portfolio_id (auto-generated), name, description
- Owner: owner (FK to User), client (FK to Client)
- **UDF Fields:** portfolio_group, portfolio_subgroup, portfolio_manager, strategy
- Financial: initial_capital, current_cash, base_currency
- Status: DRAFT, PENDING_APPROVAL, ACTIVE, REJECTED, SUSPENDED, CLOSED
- Maker-Checker: Same pattern as Order (created_by, approved_by with real names)

**Computed Properties:**
- `total_invested` - initial_capital - current_cash
- `current_value` - cash + holdings value
- `total_pnl` - current_value - initial_capital
- `total_pnl_percentage` - (total_pnl / initial_capital) * 100

**Holding**
- Current stock holdings in portfolio
- Fields: portfolio (FK), stock (FK), quantity, average_buy_price, last_price
- Computed: total_cost, current_value, unrealized_pnl, unrealized_pnl_percentage

**Transaction**
- Portfolio transaction history
- Types: DEPOSIT, WITHDRAWAL, DIVIDEND, INTEREST, FEE, BUY, SELL, OTHER
- Fields: transaction_id (auto-gen), portfolio (FK), transaction_type, amount
- Stock transactions: stock (FK), quantity, price
- Reference: reference_id (links to order/trade)

**Position**
- Historical position snapshots for tracking
- Daily snapshots: portfolio, stock, quantity, prices, P&L
- Unique constraint: (portfolio, stock, snapshot_date)

---

### 5. Reference Data Module (Stub Implementation)

**Purpose:** Static reference tables with ETL support

#### Models

**Currency**
- ISO 4217 currency codes
- Fields: code (3 chars), name, symbol, country, decimal_places
- Flags: is_active, is_base_currency
- ETL: source_system, source_id, last_synced_at

**Broker**
- Broker reference data
- Fields: code, name, full_name, broker_type
- Types: FULL_SERVICE, DISCOUNT, DIRECT_MARKET_ACCESS, INSTITUTIONAL
- Contact: email, phone, website, address
- Regulatory: registration_number, sebi_registration
- Flags: is_active, is_preferred

**TradingCalendar**
- Trading days and holidays per exchange
- Fields: date, exchange, is_trading_day, is_settlement_day, is_holiday
- Holiday details: holiday_name, holiday_type (PUBLIC/TRADING/SETTLEMENT)
- Trading hours: market_open_time, market_close_time, is_half_day
- Unique: (date, exchange)

**Client**
- Customer/client master data
- Client types: INDIVIDUAL, CORPORATE, HNI, INSTITUTIONAL, PROPRIETARY
- Personal: name, legal_name, short_name
- Contact: email, phone, mobile, address
- Regulatory: pan_number, tax_id
- Accounts: account_number, demat_account, trading_account
- Relationship: relationship_manager, account_opening_date
- Status: ACTIVE, INACTIVE, SUSPENDED, CLOSED
- KYC: kyc_status (PENDING/VERIFIED/REJECTED/EXPIRED)
- Risk: risk_category (LOW/MEDIUM/HIGH)

---

### 6. Reporting Module (Stub Implementation)

**Purpose:** Report generation with UDF integration

#### Models

**Report**
- Dynamic report generation
- Identification: id (UUID), report_id (auto-gen), title, description
- **UDF Fields:** report_type, report_category (from UDF system)
- Format: PDF, EXCEL, CSV, JSON
- Parameters: start_date, end_date, parameters (JSON)
- Status: PENDING, GENERATING, COMPLETED, FAILED
- Generation: file_path, file_size, error_message
- Requester: requested_by, requested_by_name (auto-filled)

**Methods:**
- `mark_as_generating()` - Start generation
- `mark_as_completed(file_path, file_size)` - Complete successfully
- `mark_as_failed(error_message)` - Mark as failed

---

## Key Features

### 1. Maker-Checker Workflow

**Four-Eyes Principle:**
- Maker creates the record (DRAFT status)
- Maker submits for approval (PENDING_APPROVAL)
- Checker (different user) approves or rejects
- System prevents self-approval at validator level

**Real Name Display:**
- All maker/checker fields auto-populate with real names
- Format: "John Doe (EMP001)"
- Uses `User.get_display_name()` method

**Status Workflow:**
```python
# Maker creates order
order = Order(created_by=maker_user, status='DRAFT', ...)
order.save()

# Maker submits
order.status = 'PENDING_APPROVAL'
order.submitted_at = timezone.now()
order.save()

# Checker approves (four-eyes check enforced)
if order.can_be_approved_by(checker_user):
    order.approve(checker_user, notes='Approved')
else:
    raise ValueError("Cannot approve own order")
```

### 2. Role-Based Access Control (RBAC)

**Permission System:**
- Granular permissions (e.g., `create_order`, `approve_order`, `view_customer_data`)
- Permissions grouped into Roles
- Users assigned multiple roles with validity periods
- Permission checking via decorators and model methods

**Example Usage:**
```python
# In views
@permission_required('create_order')
def order_create(request):
    # Only users with create_order permission can access
    pass

# In models
if request.user.has_permission('approve_order'):
    # Show approve button
    pass

# Check multiple permissions
if request.user.has_any_permission(['approve_order', 'approve_portfolio']):
    # User is a checker
    pass
```

### 3. Audit Logging

**Automatic Tracking:**
- All CRUD operations logged
- User, IP address, timestamp tracked
- Before/after values stored as JSON
- Success/failure tracking

**17 Action Types:**
CREATE, UPDATE, DELETE, VIEW, APPROVE, REJECT, SUBMIT, CANCEL, EXECUTE, IMPORT, EXPORT, LOGIN, LOGOUT, PASSWORD_CHANGE, ACCOUNT_LOCK, ACCOUNT_UNLOCK, OTHER

**Usage Example:**
```python
from accounts.models import AuditLog

# Log order creation
AuditLog.log_action(
    user=request.user,
    action='CREATE',
    description=f'Created order {order.order_id}',
    category='order',
    object_type='Order',
    object_id=str(order.id),
    new_values={'side': 'BUY', 'quantity': 100},
    ip_address=request.META.get('REMOTE_ADDR'),
    request_path=request.path
)
```

### 4. User Defined Fields (UDF)

**Dynamic Dropdowns:**
- Centralized management of dropdown values
- Three-level hierarchy: Type → Subtype → Field
- Used across Portfolio, Reports, and other modules

**Integration Example:**
```python
# In forms
from udf.models import UDFField

class PortfolioForm(forms.ModelForm):
    portfolio_group = forms.ChoiceField(
        choices=UDFField.get_choices('PORTFOLIO', 'GROUP', include_blank=True)
    )
```

### 5. Professional UI/UX

**Bootstrap 5 with Custom CSS:**
- Professional color scheme (primary, accent, success, warning, danger)
- Responsive design
- Stat cards with hover effects
- Status badges with color coding
- Custom scrollbars
- Print-friendly styles

**Reusable Components:**
- navbar.html - Navigation menu
- messages.html - Bootstrap alerts with icons
- pagination.html - Pagination controls
- status_badge.html - Color-coded status badges

---

## Database Schema

### Tables Summary (14 Core Tables)

**Accounts Module:**
1. `user` - Custom user model (50+ fields)
2. `role` - Job functions/roles
3. `permission` - Granular permissions
4. `user_role` - User-to-role mapping (many-to-many)
5. `role_permission` - Role-to-permission mapping (many-to-many)
6. `audit_log` - Complete audit trail

**UDF Module:**
7. `udf_type` - UDF categories
8. `udf_subtype` - UDF subcategories
9. `udf_field` - UDF field values

**Orders Module:**
10. `stock` - Stock/security master
11. `order` - Trading orders
12. `trade` - Trade executions

**Portfolio Module:**
13. `portfolio` - Portfolio master
14. `holding` - Current holdings
15. `transaction` - Transaction history
16. `position` - Historical snapshots

**Reference Data Module:**
17. `currency` - Currency master
18. `broker` - Broker master
19. `trading_calendar` - Trading days/holidays
20. `client` - Client/customer master

**Reporting Module:**
21. `report` - Generated reports

### Key Indexes
- Status-based indexes for fast filtering
- Date-based indexes for time-series queries
- Foreign key indexes for joins
- Composite indexes for common query patterns

---

## Development Setup

### Prerequisites
- Python 3.11+
- MySQL 8.0+ (or SQLite for development)
- pip and virtualenv

### Installation Steps

**1. Clone and Setup Virtual Environment**
```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/Trade_V1
python3 -m venv venv
source venv/bin/activate
```

**2. Install Dependencies**
```bash
pip install -r requirements.txt
```

**3. Database Setup (MySQL)**
```bash
mysql -u root -p
CREATE DATABASE trade_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

Update password in `trade_management/settings.py`:
```python
DATABASES = {
    "default": {
        "PASSWORD": "your_mysql_password",  # Update this
    }
}
```

**4. Run Migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

**5. Create Superuser**
```bash
python manage.py createsuperuser
```

**6. Collect Static Files**
```bash
python manage.py collectstatic
```

**7. Run Development Server**
```bash
python manage.py runserver
# Or custom port
python manage.py runserver 8001
```

**8. Access Application**
- Login: http://127.0.0.1:8000/login/
- Dashboard: http://127.0.0.1:8000/dashboard/
- Admin: http://127.0.0.1:8000/admin/

### Test Users (if created)
- **Maker:** maker1 / Test@1234
- **Checker:** checker1 / Test@1234

---

## Testing Strategy

### Test Framework
- **Framework:** pytest with pytest-django
- **Coverage:** pytest-cov
- **Markers:** unit, integration, workflow, auth

### Configuration (pytest.ini)
```ini
[pytest]
DJANGO_SETTINGS_MODULE = trade_management.settings
python_files = test_*.py
addopts = -v --tb=short --cov=. --cov-report=html
testpaths = accounts/tests orders/tests portfolio/tests
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific module
pytest orders/tests/

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific marker
pytest -m unit
pytest -m workflow
```

### Test Coverage Goals
- Unit tests: 90%+ coverage
- Integration tests for workflows
- End-to-end tests for maker-checker flows

---

## Current Implementation Status

### Completed (100%)

**Phase 1: Foundation**
- ✅ Django project setup
- ✅ MySQL/SQLite configuration
- ✅ Custom User model with 50+ fields
- ✅ RBAC system (Role, Permission, UserRole, RolePermission)
- ✅ Audit logging system
- ✅ UDF system (Type, Subtype, Field)
- ✅ Reference data models (Currency, Broker, Calendar, Client)
- ✅ Custom decorators (@permission_required, @role_required)
- ✅ Base templates (base.html, base_with_sidebar.html)
- ✅ Reusable components (navbar, messages, pagination, status_badge)
- ✅ Professional custom CSS
- ✅ Authentication (login, logout, dashboard)

**Phase 2: Orders Module**
- ✅ Order and Trade models
- ✅ Stock master model
- ✅ 8 workflow views (list, create, detail, edit, submit, approve, reject, delete)
- ✅ 3 forms (OrderForm, OrderRejectForm, OrderFilterForm)
- ✅ 6 validators (can_edit, can_submit, can_approve, etc.)
- ✅ 7 templates (list, form, detail, reject, confirm_delete, etc.)
- ✅ URL configuration
- ✅ Maker-checker workflow with four-eyes principle
- ✅ Real name auto-population
- ✅ Filtering and pagination
- ✅ Unit tests (test_forms.py, test_validators.py)

### Partial Implementation (Stubs)

**Phase 3: Portfolio Module**
- ✅ Portfolio, Holding, Transaction, Position models
- ⏳ Stub views created
- ⏳ Placeholder templates created
- ❌ UDF cascading dropdowns (JavaScript)
- ❌ Complete workflow implementation

**Phase 4: UDF Module**
- ✅ UDF Type, Subtype, Field models
- ⏳ Stub views created
- ❌ UDF management views
- ❌ AJAX API endpoints for cascading dropdowns
- ❌ JavaScript for dynamic dropdowns

**Phase 5: Reference Data Module**
- ✅ All models complete
- ⏳ Stub views created
- ❌ CRUD implementation
- ❌ ETL management commands

### Not Started

**Phase 6: Testing**
- ❌ Comprehensive unit tests for all modules
- ❌ Integration tests
- ❌ End-to-end workflow tests
- ❌ 90%+ code coverage

**Additional Features:**
- ❌ Export to CSV/Excel
- ❌ Advanced filtering with date ranges
- ❌ Audit log viewer
- ❌ Email notifications
- ❌ Bulk operations
- ❌ Management commands for ETL
- ❌ API endpoints (DRF)

---

## Next Steps (Priority Order)

### Immediate (This Week)
1. Complete Portfolio module following Orders pattern
2. Implement UDF cascading dropdowns (JavaScript)
3. Create UDF management views (admin-only)

### Short-term (Next Week)
4. Complete Reference Data CRUD views
5. Write comprehensive unit tests
6. Create management commands for data import

### Medium-term (Next Month)
7. Implement Reporting module
8. Add export functionality (CSV/Excel)
9. Build audit log viewer
10. Add email notifications

### Long-term
11. REST API endpoints
12. Advanced analytics dashboard
13. Performance optimization
14. Deployment setup (Docker, CI/CD)

---

## Important Design Patterns

### 1. Function-Based Views (FBVs)
- Chosen for simpler workflow logic
- Easier to add decorators
- Clearer control flow for approval/rejection
- Less boilerplate than CBVs

### 2. Template Inheritance
```
base.html (common layout)
  ↓
base_with_sidebar.html (list pages with filters)
  ↓
module templates (orders, portfolio, etc.)
```

### 3. Component Reuse
- Status badges for consistent status display
- Pagination for all list views
- Messages for flash notifications
- Navbar for consistent navigation

### 4. Transaction Safety
```python
from django.db import transaction

@transaction.atomic
def order_approve(request, order_id):
    # All DB operations are atomic
    # Rollback on any error
    pass
```

### 5. Auto-Population Pattern
```python
def save(self, *args, **kwargs):
    # Auto-generate IDs
    if not self.order_id:
        self.order_id = f"ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4()[:8]}"

    # Auto-fill real names
    if self.created_by:
        self.created_by_name = self.created_by.get_display_name()

    super().save(*args, **kwargs)
```

---

## Security Features

1. **Account Lockout** - After failed login attempts
2. **Password Policy** - Enforced by Django validators
3. **Session Management** - 24-hour sessions
4. **IP Tracking** - Login IPs logged in audit trail
5. **Audit Trail** - Complete action history
6. **RBAC** - Granular permission checking
7. **SQL Injection Protection** - Django ORM
8. **CSRF Protection** - Django middleware
9. **XSS Protection** - Template auto-escaping
10. **Four-Eyes Principle** - Enforced at validator level

---

## Jazzmin Admin Configuration

**Custom Settings:**
- Professional admin interface
- Custom icons for all models
- Organized sidebar with app grouping
- Custom links for audit logs
- Horizontal tabs for change forms
- Fixed navbar and sidebar
- Dark mode support

**Access:** http://127.0.0.1:8000/admin/

---

## Useful Commands

```bash
# Development
python manage.py runserver
python manage.py runserver 8001

# Database
python manage.py makemigrations
python manage.py migrate
python manage.py dbshell

# Users
python manage.py createsuperuser
python manage.py changepassword username

# Static files
python manage.py collectstatic

# Shell
python manage.py shell
python manage.py shell_plus  # django-extensions

# Testing
pytest
pytest --cov=. --cov-report=html
pytest -v orders/tests/

# Code quality
python manage.py check
python manage.py validate_templates
```

---

## Configuration Files

### settings.py Key Settings
- `AUTH_USER_MODEL = 'accounts.User'` - Custom user model
- `LOGIN_URL = '/login/'` - Login redirect
- `PAGINATION_PAGE_SIZE = 25` - Default pagination
- `SESSION_COOKIE_AGE = 86400` - 24-hour sessions
- `CRISPY_TEMPLATE_PACK = 'bootstrap5'` - Form styling

### URLs Configuration
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),      # Auth & dashboard
    path('orders/', include('orders.urls')),
    path('portfolio/', include('portfolio.urls')),
    path('udf/', include('udf.urls')),
    path('reference/', include('reference_data.urls')),
]
```

---

## Common Workflows

### Order Creation Workflow
```
1. Maker logs in
2. Navigate to Orders > Create Order
3. Fill form (stock, side, quantity, price)
4. Click "Create" → Order saved as DRAFT
5. Review order in detail view
6. Click "Submit for Approval" → Status = PENDING_APPROVAL
7. Checker logs in
8. Navigate to Orders > Filter by "Pending Approval"
9. Click order to view details
10. Click "Approve" or "Reject"
   - Approve → Status = APPROVED
   - Reject → Enter reason, Status = REJECTED
```

### Portfolio Creation Workflow
```
1. Maker creates portfolio (DRAFT)
2. Select UDF values from cascading dropdowns
   - Portfolio Group → Portfolio Subgroup
   - Portfolio Manager
   - Strategy
3. Submit for approval
4. Checker reviews and approves/rejects
5. If approved → Portfolio becomes ACTIVE
```

---

## Known Limitations

1. **No REST API** - Currently web-only (DRF configured but not implemented)
2. **No Email Notifications** - Approval notifications manual
3. **No Export** - CSV/Excel export not implemented
4. **No Bulk Operations** - One record at a time
5. **Limited Reporting** - Reporting module is stub
6. **No Real-time Updates** - Manual refresh required

---

## Support & Documentation

**Internal Documentation:**
- README.md - Project overview
- STATUS.md - Implementation status
- claude.md - Technical documentation (this file)

**External Resources:**
- Django 5.2 Docs: https://docs.djangoproject.com/en/5.2/
- Django REST Framework: https://www.django-rest-framework.org/
- Bootstrap 5: https://getbootstrap.com/docs/5.3/
- pytest-django: https://pytest-django.readthedocs.io/

**Contact:**
For issues or questions:
1. Check this documentation
2. Review model docstrings
3. Inspect audit logs for debugging
4. Contact system administrator

---

## License

Internal use only - Proprietary software

---

**Last Updated:** 2025-12-13
**Documented By:** Claude Code
**Version:** 1.0.0-beta
