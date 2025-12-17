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

### 🚧 In Progress
- Reference Data module implementation
- Portfolio module with Four-Eyes principle
- UDF module
- Templates and UI

### 📋 To Do
- Complete all module models, services, views
- Professional UI templates
- DDL files with sample data
- Comprehensive test suite
- API documentation
- Deployment guides

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific app tests
pytest portfolio/tests/

# View coverage report
open htmlcov/index.html
```

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
