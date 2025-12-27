# CisTrade - Quick Reference Guide

**Last Updated:** 2025-12-27

---

## Development Commands

### Server

```bash
# Start development server
python manage.py runserver 0.0.0.0:8000

# Start with specific port
python manage.py runserver 0.0.0.0:9000

# Run in background
python manage.py runserver 0.0.0.0:8000 &
```

### Database

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Interactive shell
python manage.py shell

# Database shell
python manage.py dbshell
```

### Testing

```bash
# Run all tests
pytest

# Run specific module
pytest core/tests/
pytest portfolio/tests/test_views.py

# Run with coverage
pytest --cov=core --cov=portfolio --cov=udf --cov=reference_data

# Generate HTML coverage report
pytest --cov=. --cov-report=html
open htmlcov/index.html

# Run specific test
pytest core/tests/test_auth_views.py::LoginViewTestCase::test_login_success

# Run with verbose output
pytest -v

# Use automation script
./run_tests.sh
```

### Benchmarking

```bash
# Quick smoke test (50 users, 2 min)
./run_benchmark.sh quick

# Standard benchmark (500 users, 10 min)
./run_benchmark.sh standard

# Stress test (1000+ users, 5 min)
./run_benchmark.sh stress

# Soak test (200 users, 2 hours)
./run_benchmark.sh soak

# Custom benchmark
./run_benchmark.sh standard 300 5m

# Interactive web UI
locust --host=http://localhost:8000
# Open http://localhost:8089

# Headless mode
locust --host=http://localhost:8000 --users 500 --spawn-rate 10 --run-time 10m --headless
```

### Code Quality

```bash
# Format code with Black
black .

# Check linting with Flake8
flake8 .

# Sort imports with isort
isort .

# Type checking with mypy
mypy .

# Security scan
bandit -r . -f json -o security_report.json

# Dependency vulnerability check
safety check
```

### Static Files

```bash
# Collect static files
python manage.py collectstatic --noinput

# Clear collected static files
python manage.py collectstatic --clear --noinput
```

### Users

```bash
# Create superuser
python manage.py createsuperuser

# Change password
python manage.py changepassword <username>
```

---

## Project Structure

```
cis_trade_hive/
├── config/                     # Django settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                       # Core app (auth, audit, ACL)
│   ├── views/
│   │   ├── auth_views.py      # Login, logout, permissions
│   │   └── dashboard_views.py
│   ├── services/
│   │   └── acl_service.py
│   ├── repositories/
│   │   └── impala_connection.py
│   ├── middleware/
│   │   ├── acl_middleware.py
│   │   └── audit_middleware.py
│   └── tests/
│       └── test_auth_views.py
├── portfolio/                  # Portfolio management
│   ├── models.py
│   ├── views.py
│   ├── services/
│   │   └── portfolio_service.py
│   ├── repositories/
│   │   └── portfolio_hive_repository.py
│   └── tests/
│       ├── test_views.py
│       └── test_repositories.py
├── udf/                        # User-defined fields
│   ├── views.py
│   ├── services/
│   ├── repositories/
│   └── tests/
├── reference_data/             # Reference data
│   ├── views.py
│   ├── repositories/
│   │   ├── currency_repository.py
│   │   ├── country_repository.py
│   │   └── counterparty_repository.py
│   └── tests/
├── templates/                  # HTML templates
│   ├── auth/
│   ├── core/
│   ├── portfolio/
│   ├── udf/
│   └── reference_data/
├── static/                     # Static files
│   ├── css/
│   ├── js/
│   └── images/
├── sql/                        # SQL scripts
│   ├── ddl/
│   └── sample_data/
├── logs/                       # Application logs
├── benchmark_results/          # Benchmark results
├── locustfile.py              # Locust load testing
├── run_benchmark.sh           # Benchmark script
├── run_tests.sh               # Test script
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development dependencies
├── pytest.ini                 # Pytest configuration
├── .coveragerc                # Coverage configuration
├── README.md                  # Project overview
├── TESTING.md                 # Testing documentation
├── BENCHMARKING.md            # Benchmarking guide
└── PROJECT_MANAGEMENT.md      # PM documentation
```

---

## Key URLs

### Development

- **Application:** http://localhost:8000
- **Admin:** http://localhost:8000/admin/
- **API:** http://localhost:8000/api/
- **Locust UI:** http://localhost:8089 (when running)
- **Silk Profiler:** http://localhost:8000/silk/ (if enabled)

### Application Routes

```
/                           → Redirect to login
/auth/login/               → Login page
/auth/logout/              → Logout
/dashboard/                → Main dashboard
/audit-log/                → Audit log viewer

/portfolio/                → Portfolio list
/portfolio/<id>/           → Portfolio detail
/portfolio/create/         → Create portfolio
/portfolio/<id>/edit/      → Edit portfolio
/portfolio/<id>/submit/    → Submit for approval
/portfolio/<id>/approve/   → Approve (checker)
/portfolio/<id>/reject/    → Reject (checker)

/reference-data/currency/      → Currency list
/reference-data/country/       → Country list
/reference-data/calendar/      → Calendar list
/reference-data/counterparty/  → Counterparty list

/udf/                      → UDF definition list
/udf/<id>/                 → UDF detail
/udf/create/               → Create UDF
/udf/<id>/edit/            → Edit UDF
```

---

## Environment Variables (.env)

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (Django)
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# Kudu/Impala
IMPALA_HOST=your-impala-host
IMPALA_PORT=21050
IMPALA_DATABASE=your_database
IMPALA_USE_SSL=False
IMPALA_AUTH_MECHANISM=PLAIN

# Development Flags
SKIP_PERMISSION_CHECKS=True
AUTO_LOGIN_USER=admin

# Email (optional)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password
```

---

## Testing Targets

| Module | Tests | View Coverage | Repository Coverage |
|--------|-------|---------------|---------------------|
| Core (Auth) | 13 | 90.00% ✅ | - |
| Reference Data | 29 | 90.78% ✅ | 70.93% |
| Portfolio | 26 | 76.75% | 65.12% |
| UDF | 22 | 61.90% | 61.18% |
| **Total** | **90** | **39.33%** | |

---

## Performance Targets (500 Users)

| Metric | Target | Current |
|--------|--------|---------|
| Average Response Time | <1000ms | ✅ |
| 95th Percentile | <2000ms | ✅ |
| Error Rate | 0% | ✅ |
| Throughput | >100 req/sec | ✅ |
| CPU Usage | <60% | ⚠️ Monitor |
| Memory Usage | <70% | ⚠️ Monitor |

---

## Common Tasks

### Add New App

```bash
# Create app
python manage.py startapp myapp

# Add to INSTALLED_APPS in config/settings.py
INSTALLED_APPS = [
    ...
    'myapp',
]

# Create URLs
# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
]

# Include in main URLs
# config/urls.py
urlpatterns = [
    ...
    path('myapp/', include('myapp.urls')),
]
```

### Add Audit Logging to View

```python
from core.audit.audit_kudu_repository import audit_log_kudu_repository

def my_view(request):
    # Your logic here

    # Log action
    audit_log_kudu_repository.log_action(
        user_id=str(request.session.get('user_id', '0')),
        username=request.session.get('user_login', 'anonymous'),
        user_email=request.session.get('user_email', ''),
        action_type='VIEW',  # CREATE, UPDATE, DELETE, VIEW, etc.
        entity_type='MY_ENTITY',
        entity_name='My Entity',
        entity_id='123',
        action_description='Viewed my entity',
        request_method=request.method,
        request_path=request.path,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        status='SUCCESS'  # or 'FAILURE'
    )

    return render(request, 'template.html')
```

### Add Permission Check

```python
from django.core.exceptions import PermissionDenied

def my_view(request):
    # Check permission
    from core.services.acl_service import ACLService
    acl_service = ACLService()

    if not acl_service.has_permission(request.session.get('user_login'), 'my_permission'):
        raise PermissionDenied("You don't have permission to access this resource")

    # Your logic here
    ...
```

### Add Test

```python
# myapp/tests/test_views.py
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

class MyViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('my_view')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('myapp.views.my_repository.get_data')
    def test_my_view_success(self, mock_get):
        mock_get.return_value = [{'id': 1, 'name': 'Test'}]

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'myapp/template.html')
```

---

## Troubleshooting

### Server Won't Start

```bash
# Port already in use
lsof -i :8000
kill -9 <PID>

# Database locked
rm db.sqlite3
python manage.py migrate

# Static files missing
python manage.py collectstatic --noinput
```

### Tests Failing

```bash
# Clear pytest cache
pytest --cache-clear

# Recreate test database
pytest --create-db

# Verbose output
pytest -vv -s

# Check specific test
pytest path/to/test.py::TestClass::test_method -vv
```

### Benchmark Errors

```bash
# Server not responding
curl -v http://localhost:8000/dashboard/

# Database connection
python manage.py shell
>>> from core.repositories.impala_connection import impala_manager
>>> impala_manager.execute_query("SELECT 1")

# Clear benchmark results
rm -rf benchmark_results/*
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check Python path
python -c "import sys; print(sys.path)"

# Verify imports
python manage.py check
```

---

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Stage changes
git add .

# Commit
git commit -m "feat: Add my feature"

# Push to remote
git push origin feature/my-feature

# Pull latest changes
git pull origin main

# Merge main into feature branch
git merge main

# Delete branch after merge
git branch -d feature/my-feature
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing (`pytest`)
- [ ] Code quality checks pass (`flake8`, `black --check`)
- [ ] Security scan clean (`bandit`, `safety check`)
- [ ] Benchmark run successful (`./run_benchmark.sh standard`)
- [ ] Database migrations tested
- [ ] Environment variables configured
- [ ] Backup created

### Deployment

- [ ] Stop application server
- [ ] Pull latest code
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Run migrations (`python manage.py migrate`)
- [ ] Collect static files (`python manage.py collectstatic --noinput`)
- [ ] Restart application server
- [ ] Run smoke test (`./run_benchmark.sh quick`)
- [ ] Monitor logs for errors

### Post-Deployment

- [ ] Verify critical flows working
- [ ] Check error logs
- [ ] Monitor performance metrics
- [ ] Notify stakeholders
- [ ] Update deployment log

---

## Support & Documentation

- **README.md** - Project overview and installation
- **TESTING.md** - Comprehensive testing guide
- **BENCHMARKING.md** - Performance benchmarking guide
- **PROJECT_MANAGEMENT.md** - PM strategies, roadmap, housekeeping
- **QUICK_REFERENCE.md** - This file

For questions or issues, contact the development team.

---

**CisTrade Quick Reference** © 2025
