# Code Structure

Organization of the CisTrade Django application following clean architecture principles.

## Project Layout

```
cis_trade_hive/
├── config/                 # Django settings and URL configuration
│   ├── settings.py        # Application settings
│   ├── urls.py            # Root URL routing
│   └── wsgi.py            # WSGI application
├── core/                   # Core functionality
│   ├── audit/             # Audit logging
│   ├── repositories/      # Base repository classes
│   ├── services/          # Shared services
│   └── views/             # Auth and dashboard views
├── portfolio/              # Portfolio management module
│   ├── models.py          # Portfolio and history models
│   ├── views.py           # Portfolio views
│   ├── services/          # Portfolio business logic
│   ├── repositories/      # Portfolio data access
│   └── templates/         # Portfolio HTML templates
├── udf/                    # User Defined Fields module
├── market_data/            # Market data module (FX rates)
├── reference_data/         # Reference data module
├── static/                 # Static files (CSS, JS, images)
├── templates/              # Shared HTML templates
└── manage.py              # Django management script
```

## Architectural Layers

### 1. Models Layer (Django ORM)

**Location**: `{app}/models.py`

**Purpose**: Database models, Django ORM entities

**Example**:
```python
class Portfolio(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20)
```

### 2. Repository Layer

**Location**: `{app}/repositories/`

**Purpose**: Data access abstraction, Impala/Kudu queries

**Pattern**: Repository pattern separates data access from business logic

**Example**:
```python
class PortfolioHiveRepository:
    def get_all_portfolios(self, limit=100):
        query = f"SELECT * FROM {self.TABLE_NAME}"
        return impala_manager.execute_query(query)
```

### 3. Service Layer

**Location**: `{app}/services/`

**Purpose**: Business logic, orchestration

**Pattern**: Service layer coordinates between views and repositories

**Example**:
```python
class PortfolioService:
    @staticmethod
    def create_portfolio(user, data):
        # Validate data
        # Create portfolio
        # Log audit
        # Return result
```

### 4. Views Layer

**Location**: `{app}/views.py`

**Purpose**: HTTP request handling, template rendering

**Responsibilities**:
- Validate request parameters
- Call service methods
- Render templates or return JSON
- Handle errors

### 5. Template Layer

**Location**: `templates/`

**Purpose**: HTML rendering with Django template language

**Shared Templates**:
- `base.html`: Base layout
- `components/`: Reusable UI components

## Module Structure

### Core Module

**Responsibilities**:
- Authentication (ACL integration)
- Authorization (permissions)
- Audit logging
- Dashboard
- Base repository classes

**Key Files**:
```
core/
├── views/
│   ├── auth_views.py          # Login, logout, decorators
│   └── dashboard_views.py     # Dashboard view
├── repositories/
│   ├── acl_repository.py      # ACL data access
│   └── impala_connection.py   # Impala connection manager
├── audit/
│   └── audit_kudu_repository.py  # Audit logging to Kudu
└── services/
    └── help_service.py        # Help content service
```

### Portfolio Module

**Responsibilities**:
- Portfolio CRUD operations
- Four-eyes workflow (maker-checker)
- Portfolio status management
- History tracking

**Key Files**:
```
portfolio/
├── models.py                          # Portfolio, PortfolioHistory models
├── views.py                           # Portfolio views
├── services/
│   ├── portfolio_service.py          # Core business logic
│   └── portfolio_dropdown_service.py # Dropdown data
└── repositories/
    └── portfolio_hive_repository.py  # Kudu data access
```

### Reference Data Module

**Responsibilities**:
- Currency reference
- Country reference
- Calendar/holidays
- Counterparty data

**Key Files**:
```
reference_data/
├── views.py                           # Reference data views
├── services/
│   └── reference_data_service.py     # Service layer
└── repositories/
    └── reference_data_repository.py  # Hive external tables
```

### UDF Module

**Responsibilities**:
- UDF definition management
- UDF value management
- History tracking

### Market Data Module

**Responsibilities**:
- FX rate management
- Rate history
- Dashboard views

## Design Patterns

### Repository Pattern

**Purpose**: Separate data access from business logic

**Benefits**:
- Easy to test (mock repositories)
- Database agnostic
- Centralized query logic

**Example**:
```python
# Repository handles data access
class PortfolioRepository:
    def get_by_code(self, code):
        query = f"SELECT * FROM portfolio WHERE code = '{code}'"
        return self.execute(query)

# Service uses repository
class PortfolioService:
    def get_portfolio(self, code):
        return portfolio_repository.get_by_code(code)
```

### Service Layer Pattern

**Purpose**: Encapsulate business logic

**Benefits**:
- Reusable across multiple views
- Centralized validation
- Transaction management

**Example**:
```python
class PortfolioService:
    @staticmethod
    def submit_for_approval(portfolio, user):
        # Business rules
        if portfolio.status != 'DRAFT':
            raise ValidationError("Only drafts can be submitted")

        # Update status
        portfolio.status = 'PENDING_APPROVAL'

        # Log audit
        audit_log.log(...)

        return portfolio
```

### Decorator Pattern (Authentication)

**Purpose**: Add cross-cutting concerns

**Usage**:
```python
@require_login
def portfolio_list(request):
    # User is guaranteed to be authenticated

@require_permission('cis-portfolio', 'WRITE')
def portfolio_create(request):
    # User has WRITE permission
```

## Database Access

### Impala Connection

**Singleton Pattern**: One connection pool

**Location**: `core/repositories/impala_connection.py`

**Usage**:
```python
from core.repositories.impala_connection import impala_manager

results = impala_manager.execute_query(query, database='gmp_cis')
```

### Query Execution

**Read Queries**:
```python
query = "SELECT * FROM gmp_cis.cis_portfolio"
results = impala_manager.execute_query(query)
# Returns: List[Dict]
```

**Write Queries** (Kudu):
```python
query = "INSERT INTO gmp_cis.cis_portfolio VALUES (...)"
success = impala_manager.execute_update(query)
# Returns: bool
```

## Static Files

### CSS

**Location**: `static/css/`

**Files**:
- `cistrade.css`: Main application styles
- `custom.css`: Additional custom styles

### JavaScript

**Location**: `static/js/`

**Files**:
- `cistrade.js`: Common JavaScript functions
- `custom.js`: Custom scripts

### Images

**Location**: `static/images/`

## Templates

### Base Template

**File**: `templates/base.html`

**Provides**:
- HTML structure
- Navigation
- Sidebar
- Footer
- Common CSS/JS includes

### Components

**Location**: `templates/components/`

**Reusable UI elements**:
- `navbar_acl.html`: Top navigation bar
- `sidebar.html`: Left sidebar menu
- `messages.html`: Django messages display

### App Templates

Each app has its own templates in `{app}/templates/{app}/`

**Example** (Portfolio):
```
portfolio/templates/portfolio/
├── portfolio_list.html
├── portfolio_detail.html
├── portfolio_form.html
└── pending_approvals.html
```

## Configuration

### Settings

**File**: `config/settings.py`

**Key Settings**:
```python
DEBUG = True/False
SKIP_PERMISSION_CHECKS = DEBUG
IMPALA_CONFIG = {...}
DATABASES = {...}
```

### URL Routing

**Root URLs**: `config/urls.py`

**App URLs**: `{app}/urls.py`

**Pattern**:
```python
# config/urls.py
urlpatterns = [
    path('portfolio/', include('portfolio.urls')),
]

# portfolio/urls.py
urlpatterns = [
    path('', views.portfolio_list, name='list'),
    path('<str:code>/', views.portfolio_detail, name='detail'),
]
```

## Testing Structure

**Location**: `{app}/tests/`

**Types**:
- Unit tests: Test individual functions
- Integration tests: Test multiple components
- View tests: Test HTTP requests/responses

## Code Style

### Python (PEP 8)

- 4 spaces indentation
- Maximum line length: 100 characters
- Docstrings for all public methods
- Type hints where beneficial

### HTML

- 2 spaces indentation
- Semantic HTML5 elements
- Django template language

### JavaScript

- 2 spaces indentation
- ES6+ features
- Avoid global variables

## Related Documentation

- [Architecture](architecture.md) - High-level design
- [Database Schema](database-schema.md) - Data models
- [Development Guide](development-guide.md) - Setup and development
- [API Reference](api-reference.md) - Method documentation
