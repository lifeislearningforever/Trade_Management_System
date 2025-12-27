# CisTrade - Enterprise Trade Management System

A comprehensive, enterprise-grade trade management system built with Django 5.2.9, following SOLID principles.

## Features

### Core Features
- ✅ **SOLID Architecture**: Clean, maintainable code following all SOLID principles
- ✅ **Role-Based Access Control (RBAC)**: ACL system using Kudu tables
- ✅ **Comprehensive Audit Logging**: Every action is logged with full context
- ✅ **Four-Eyes Principle**: Maker-Checker workflow for critical operations
- ✅ **Dual Database Support**: SQLite/MySQL for Django + Kudu/Impala for reference data
- ✅ **Professional Admin Interface**: Jazzmin-powered admin panel
- ✅ **REST API**: Django REST Framework with filtering and pagination
- ✅ **Responsive Design**: Bootstrap 5.3.3 (local, no CDN)

### Modules
1. **Core**: Base infrastructure, audit logging, ACL, utilities
2. **Portfolio**: Trade portfolio management with maker-checker workflow
3. **UDF**: User-defined fields and custom data management
4. **Reference Data**: Currency, Country, Calendar, Counterparty management

## Technology Stack

### Backend
- **Framework:** Django 5.2.9
- **Python:** 3.11+
- **Database (Primary):** SQLite (dev) / MySQL (prod)
- **Database (Reference):** Kudu/Impala
- **API:** Django REST Framework 3.16.1
- **Filters:** Django Filters 25.2

### Frontend
- **CSS Framework:** Bootstrap 5.3.3 (local)
- **Icons:** Bootstrap Icons 1.11.3 (local)
- **JavaScript:** Bootstrap Bundle (includes Popper.js)

### Additional Packages
- Forms: django-crispy-forms 2.5, crispy-bootstrap5 2025.6
- Admin UI: Jazzmin 3.0.0
- Testing: pytest, pytest-django, pytest-cov
- Images: Pillow 12.0.0
- Environment: python-dotenv 1.0.1

## Project Structure

```
cis_trade/
├── config/                 # Django project settings
│   ├── settings.py        # Comprehensive settings
│   ├── urls.py           # URL configuration
│   └── wsgi.py           # WSGI configuration
├── core/                  # Core application
│   ├── models.py         # BaseModel, AuditLog
│   ├── admin.py          # Admin configuration
│   ├── services/         # Business logic services
│   │   └── acl_service.py
│   ├── middleware/       # Custom middleware
│   │   ├── acl_middleware.py
│   │   └── audit_middleware.py
│   ├── repositories/     # Database access layer
│   │   ├── impala_connection.py
│   │   └── db_router.py
│   └── utils/            # Utility functions
│       └── context_processors.py
├── portfolio/            # Portfolio management
├── udf/                  # User-defined fields
├── reference_data/       # Reference data management
├── templates/            # HTML templates
├── static/              # Static files (CSS, JS, images)
├── sql/                 # DDL and sample data
│   ├── ddl/
│   └── sample_data/
├── tests/               # Test suite
├── docs/                # Documentation
└── requirements.txt     # Python dependencies
```

## Installation

### 1. Clone the Repository

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
- Database credentials
- Impala/Kudu connection details
- Email configuration
- Secret key (for production)

### 5. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### 8. Run Development Server

```bash
python manage.py runserver
```

Visit: http://localhost:8000

## Architecture

### SOLID Principles Implementation

#### 1. Single Responsibility Principle (SRP)
- **Models**: Only handle data structure
- **Services**: Handle business logic
- **Views**: Handle HTTP request/response
- **Repositories**: Handle data access

Example:
```python
# core/models.py - Only data structure
class AuditLog(models.Model):
    timestamp = models.DateTimeField(...)

# core/services/acl_service.py - Only ACL logic
class ACLService:
    def has_permission(self, user, permission):
        ...

# core/repositories/impala_connection.py - Only database access
class ImpalaConnectionManager:
    def get_connection(self):
        ...
```

#### 2. Open/Closed Principle (OCP)
- BaseModel provides extensible foundation
- Middleware can be added without modifying existing code
- Database router easily extended for new databases

#### 3. Liskov Substitution Principle (LSP)
- All models inherit from BaseModel
- Services can be swapped with compatible implementations

#### 4. Interface Segregation Principle (ISP)
- Separate services for ACL, Audit, Connections
- Each service has focused interface

#### 5. Dependency Inversion Principle (DIP)
- Views depend on service abstractions, not implementations
- Database router abstracts database access
- Middleware uses service interfaces

### Audit Logging

Every significant action is automatically logged:

```python
from core.models import AuditLog

# Manual logging
AuditLog.log_action(
    action='CREATE',
    user=request.user,
    object_type='Portfolio',
    object_id=portfolio.id,
    object_repr=str(portfolio),
    description='Created new portfolio'
)

# Automatic logging via middleware
# - All POST, PUT, PATCH, DELETE requests
# - Login/logout events
# - Admin actions
```

### ACL (Access Control)

Role-based access control using Kudu tables:

```python
# Check permission in view
from django.core.exceptions import PermissionDenied

def my_view(request):
    if not request.acl_service.has_permission(request.user, 'portfolio_create'):
        raise PermissionDenied
    ...

# Or use decorator (to be implemented)
@require_permission('portfolio_create')
def my_view(request):
    ...
```

### Four-Eyes Principle (Maker-Checker)

Critical operations require approval:

1. **Maker**: Creates/modifies record (status: PENDING)
2. **Checker**: Reviews and approves/rejects
3. Only approved records become active

## Development Status

### ✅ Completed
- Project structure and configuration
- Core infrastructure (models, services, middleware)
- Audit logging system
- ACL system
- Database routing
- Admin interface setup

### ✅ Completed (Updated: 2025-12-27)
- ✅ Project structure and configuration
- ✅ Core infrastructure (models, services, middleware)
- ✅ **Comprehensive Audit Logging** with Kudu integration
- ✅ **ACL System** with session-based authentication
- ✅ **Reference Data Module** (Currency, Country, Calendar, Counterparty)
- ✅ **Portfolio Module** with Four-Eyes workflow
- ✅ **UDF Module** with dynamic field management
- ✅ **Market Data Module** (FX rates, yield curves)
- ✅ Database routing (Django DB + Kudu/Impala)
- ✅ Admin interface with Jazzmin
- ✅ **90-test comprehensive test suite** (39.33% coverage)
- ✅ Professional Bootstrap 5 UI

### 🚧 In Progress
- Service layer test coverage expansion
- Dashboard views testing
- Integration tests

### 📋 To Do
- API documentation with OpenAPI/Swagger
- Deployment guides (Docker, K8s)
- Performance optimization
- Advanced reporting features

## Testing

### Test Suite Overview

**Total: 90 Tests | Coverage: 39.33%**

| Module | Tests | View Coverage | Repository Coverage |
|--------|-------|---------------|---------------------|
| Core (Auth) | 13 | 90.00% ✅ | - |
| Reference Data | 29 | 90.78% ✅ | 70.93% |
| Portfolio | 26 | 76.75% | 65.12% |
| UDF | 22 | 61.90% | 61.18% |

### Quick Start

```bash
# Install test dependencies
pip install pytest pytest-django pytest-cov coverage

# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=portfolio --cov=udf --cov=reference_data

# Run specific module tests
pytest core/tests/
pytest portfolio/tests/
pytest udf/tests/
pytest reference_data/tests/

# Generate HTML coverage report
pytest --cov=. --cov-report=html
open htmlcov/index.html

# Use the automation script
chmod +x run_tests.sh
./run_tests.sh
```

### Test Structure

```
tests/
├── core/tests/
│   └── test_auth_views.py          # 13 authentication tests
├── portfolio/tests/
│   ├── test_views.py               # 19 view tests
│   └── test_repositories.py        # 7 repository tests
├── udf/tests/
│   ├── test_views.py               # 17 view tests
│   └── test_repositories.py        # 5 repository tests
└── reference_data/tests/
    ├── test_views.py               # 25 view tests
    └── test_repositories.py        # 4 repository tests
```

### What's Tested

**✅ Authentication & Security**
- Login/logout flows with Kudu audit logging
- Session management
- Permission checks
- Access denial logging

**✅ CRUD Operations**
- Portfolio management
- UDF definitions
- Reference data (currencies, countries, calendars, counterparties)

**✅ Business Logic**
- Four-Eyes workflow (submit → approve/reject)
- Portfolio status transitions
- UDF validation

**✅ Data Export**
- CSV exports for all modules
- Data formatting and encoding

**✅ Repository Layer**
- Kudu/Impala queries
- Data transformation
- Error handling

For detailed testing documentation, see [TESTING.md](TESTING.md)

## Performance Benchmarking

### Overview

CisTrade includes comprehensive performance benchmarking using **Locust** to validate the system can handle **500 concurrent users** with acceptable response times.

### Quick Start

```bash
# Install benchmarking tools
pip install -r requirements-dev.txt

# Run quick smoke test (50 users, 2 minutes)
chmod +x run_benchmark.sh
./run_benchmark.sh quick

# Run standard benchmark (500 users, 10 minutes)
./run_benchmark.sh standard
```

### Benchmark Scenarios

| Scenario | Users | Duration | Use Case |
|----------|-------|----------|----------|
| **Quick** | 50 | 2 min | Post-deployment sanity check |
| **Standard** | 500 | 10 min | Regular performance validation |
| **Stress** | 1000+ | 5 min | Find system breaking point |
| **Soak** | 200 | 2 hours | Detect memory leaks |

### Performance Targets (500 Users)

| Metric | Target | Status |
|--------|--------|--------|
| **Average Response Time** | <1000ms | ✅ |
| **95th Percentile** | <2000ms | ✅ |
| **Error Rate** | 0% | ✅ |
| **Throughput** | >100 req/sec | ✅ |

### User Behavior Profiles

The benchmark simulates 5 realistic user types:

- **Portfolio Traders (40%)**: Heavy CRUD operations on portfolios
- **Reference Data Ops (30%)**: Frequent searches and CSV exports
- **UDF Admins (15%)**: Configure custom fields
- **Dashboard Monitors (15%)**: View dashboards and audit logs
- **Mixed Users**: Navigate across all modules

### Using Locust Web UI

```bash
# Start interactive web interface
locust --host=http://localhost:8000

# Open browser at http://localhost:8089
# Configure users, spawn rate, and start test
```

### Results

Results are saved to `benchmark_results/` with:
- HTML report with charts (`report.html`)
- CSV statistics (`stats_stats.csv`)
- Failure details (`stats_failures.csv`)
- Execution logs (`locust.log`)

For detailed benchmarking documentation, see [BENCHMARKING.md](BENCHMARKING.md)

For project management and optimization strategies, see [PROJECT_MANAGEMENT.md](PROJECT_MANAGEMENT.md)

## Contributing

1. Follow SOLID principles
2. Write tests for new features
3. Update documentation
4. Use type hints
5. Follow PEP 8 style guide

## License

Proprietary - All rights reserved

## Support

For questions or issues, contact the development team.

---

**CisTrade** © 2025 - Enterprise Trade Management System
