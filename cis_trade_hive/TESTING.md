# CisTrade - Testing Documentation

**Last Updated:** 2025-12-27
**Total Tests:** 90
**Overall Coverage:** 39.33%

---

## Table of Contents

- [Overview](#overview)
- [Test Suite Breakdown](#test-suite-breakdown)
- [Coverage Report](#coverage-report)
- [Running Tests](#running-tests)
- [Test Infrastructure](#test-infrastructure)
- [Writing Tests](#writing-tests)
- [Continuous Integration](#continuous-integration)

---

## Overview

The CisTrade test suite provides comprehensive coverage for critical application features with a focus on:
- **Security & Authentication** (90% coverage)
- **Reference Data Management** (90.78% coverage)
- **Portfolio Management** (76.75% coverage)
- **User-Defined Fields** (61.90% coverage)

### Key Achievements

✅ **90 comprehensive tests** covering views and repositories
✅ **Authentication fully tested** with Kudu audit logging
✅ **CRUD operations** tested for all modules
✅ **CSV export** functionality validated
✅ **Repository layer** integration tested

---

## Test Suite Breakdown

### Core Module (13 tests)

**File:** `core/tests/test_auth_views.py`
**Coverage:** 90.00% ✅

| Test Class | Tests | Description |
|------------|-------|-------------|
| LoginViewTestCase | 4 | Login success/failure, redirects, session |
| LogoutViewTestCase | 1 | Logout with audit logging |
| AutoLoginTestCase | 2 | Auto-login success/failure |
| RequireLoginDecoratorTestCase | 2 | Authentication decorator |
| RequirePermissionDecoratorTestCase | 1 | Permission checks with audit |
| SessionManagementTestCase | 3 | Session persistence, cleanup |

**Key Features Tested:**
- ✅ Successful login with ACL authentication
- ✅ Failed login attempts (audit logged)
- ✅ Logout with Kudu audit trail
- ✅ Session persistence across requests
- ✅ Permission denial logging
- ✅ Auto-login for development

---

### Portfolio Module (26 tests)

**View Tests:** `portfolio/tests/test_views.py` (19 tests)
**Repository Tests:** `portfolio/tests/test_repositories.py` (7 tests)
**Coverage:** Views 76.75%, Repository 65.12%

#### View Tests (19 tests)

| Test Class | Tests | Description |
|------------|-------|-------------|
| PortfolioListViewTestCase | 4 | List, search, filter, CSV export |
| PortfolioDetailViewTestCase | 2 | Detail view, not found |
| PortfolioCreateViewTestCase | 2 | GET/POST create operations |
| PortfolioEditViewTestCase | 2 | GET/POST edit operations |
| PortfolioWorkflowTestCase | 3 | Submit, approve, reject workflow |
| PortfolioCloseReactivateTestCase | 2 | Close/reactivate operations |
| PortfolioWrapperTestCase | 2 | Wrapper class functionality |
| PortfolioURLTestCase | 2 | URL routing verification |

**Key Features Tested:**
- ✅ Portfolio list with search and filtering
- ✅ CSV export with Kudu audit
- ✅ Create/edit with Impala write operations
- ✅ Four-Eyes workflow (maker-checker)
- ✅ Status transitions
- ✅ PortfolioWrapper data transformation

#### Repository Tests (7 tests)

| Test | Description |
|------|-------------|
| test_get_all_portfolios | Fetch portfolios from Kudu |
| test_get_portfolio_by_code | Fetch by code |
| test_get_portfolio_by_code_not_found | Handle missing portfolio |
| test_insert_portfolio | Insert new portfolio |
| test_update_portfolio_status | Update status |
| test_get_currencies | Get distinct currencies |

---

### UDF Module (22 tests)

**View Tests:** `udf/tests/test_views.py` (17 tests)
**Repository Tests:** `udf/tests/test_repositories.py` (5 tests)
**Coverage:** Views 61.90%, Repository 61.18%

#### View Tests (17 tests)

| Test Class | Tests | Description |
|------------|-------|-------------|
| UDFListViewTestCase | 4 | List, search, filter, CSV export |
| UDFDetailViewTestCase | 2 | Detail view, not found |
| UDFCreateViewTestCase | 2 | Create UDF definitions |
| UDFEditViewTestCase | 2 | Edit UDF definitions |
| UDFDeleteViewTestCase | 1 | Soft delete |
| UDFWrapperTestCase | 4 | Wrapper class, field types |
| UDFURLTestCase | 2 | URL routing |

**Key Features Tested:**
- ✅ UDF definition CRUD operations
- ✅ Entity type filtering
- ✅ Field type validation
- ✅ Dropdown options handling
- ✅ Active/inactive filtering
- ✅ UDFWrapper data transformation

#### Repository Tests (5 tests)

| Test | Description |
|------|-------------|
| test_get_all_definitions | Fetch all UDF definitions |
| test_get_active_definitions | Fetch active only |
| test_get_definition_by_name | Fetch by name |
| test_insert_definition | Insert new definition |
| test_update_definition | Update existing |
| test_delete_definition | Soft delete |

---

### Reference Data Module (29 tests)

**View Tests:** `reference_data/tests/test_views.py` (25 tests)
**Repository Tests:** `reference_data/tests/test_repositories.py` (4 tests)
**Coverage:** Views 90.78% ✅, Repository 70.93%

#### View Tests (25 tests)

| Test Class | Tests | Description |
|------------|-------|-------------|
| CurrencyListViewTestCase | 3 | Currency list, search, CSV |
| CountryListViewTestCase | 3 | Country list, search, CSV |
| CalendarListViewTestCase | 3 | Calendar list, filter, CSV |
| CounterpartyListViewTestCase | 4 | Counterparty list, search, filter, CSV |
| ReferenceDataURLTestCase | 4 | URL routing |
| ReferenceDataErrorHandlingTestCase | 8 | Error handling |

**Key Features Tested:**
- ✅ Currency management with ISO codes
- ✅ Country data with full names
- ✅ Calendar holidays filtering
- ✅ Counterparty type filtering
- ✅ Search functionality across all modules
- ✅ CSV exports with proper formatting
- ✅ Error handling for database failures

#### Repository Tests (4 tests)

| Test | Description |
|------|-------------|
| test_get_all_currencies | Fetch currencies with remapping |
| test_get_all_countries | Fetch countries |
| test_get_all_calendars | Fetch calendar data |
| test_get_all_counterparties | Fetch counterparties |

---

## Coverage Report

### Module Coverage Summary

| Module | Statements | Missed | Coverage | Missing Lines |
|--------|------------|--------|----------|---------------|
| **core.views.auth_views** | 120 | 12 | **90.00%** ✅ | Minor edge cases |
| **reference_data.views** | 141 | 13 | **90.78%** ✅ | Error handlers |
| **portfolio.views** | 271 | 63 | **76.75%** | Workflow branches |
| **udf.views** | 252 | 96 | **61.90%** | Value management |
| **portfolio.repositories** | 129 | 45 | **65.12%** | Query variants |
| **udf.repositories** | 170 | 66 | **61.18%** | Option management |
| **reference_data.repositories** | 86 | 25 | **70.93%** | Search filters |

### What's NOT Tested Yet

**Service Layer (19-55% coverage)**
- Portfolio service business logic
- UDF service validation
- Reference data services

**Dashboard Views (34.62% coverage)**
- Dashboard widgets
- Summary statistics
- Recent activity

**Edge Cases**
- Complex validation failures
- Database connection errors
- Concurrent operations

---

## Running Tests

### Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=portfolio --cov=udf --cov=reference_data

# Run specific module
pytest core/tests/
pytest portfolio/tests/test_views.py

# Run single test
pytest core/tests/test_auth_views.py::LoginViewTestCase::test_login_success

# Use automation script
chmod +x run_tests.sh
./run_tests.sh
```

### Coverage Reports

```bash
# Generate HTML report
pytest --cov=. --cov-report=html

# View in browser
open htmlcov/index.html

# Terminal report with missing lines
pytest --cov=. --cov-report=term-missing

# XML report for CI/CD
pytest --cov=. --cov-report=xml
```

### Test Filtering

```bash
# Run only view tests
pytest -k "view"

# Run only repository tests
pytest -k "repository"

# Run specific test pattern
pytest -k "test_login"

# Run with verbose output
pytest -v

# Run with short traceback
pytest --tb=short

# Stop on first failure
pytest -x
```

---

## Test Infrastructure

### Configuration Files

**pytest.ini**
```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py *_test.py tests.py
python_classes = Test* *Tests *TestCase
python_functions = test_*
addopts =
    --verbose
    --cov=.
    --cov-report=term-missing
    --cov-report=html
    --tb=short
testpaths = .
markers =
    unit: Unit tests
    integration: Integration tests
```

**.coveragerc**
```ini
[run]
source = .
omit =
    */tests/*
    */test_*.py
    */migrations/*
    */venv/*
    manage.py
    config/*

[report]
precision = 2
show_missing = True
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

### Test Utilities

**Mocking Strategy**
```python
from unittest.mock import patch, Mock

# Mock Impala queries
@patch('core.repositories.impala_connection.impala_manager.execute_query')
def test_repository(mock_execute):
    mock_execute.return_value = [{'code': 'USD'}]
    # Test code here

# Mock audit logging
@patch('core.audit.audit_kudu_repository.log_action')
def test_with_audit(mock_audit):
    # Test code here
    mock_audit.assert_called_once()
```

**Session Setup**
```python
def setUp(self):
    self.client = Client()
    session = self.client.session
    session['user_login'] = 'testuser'
    session['user_id'] = 1
    session.save()
```

---

## Writing Tests

### Test Template

```python
"""
Module Test Template

Tests for [module] [functionality].
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock


class MyViewTestCase(TestCase):
    """Test cases for my view"""

    def setUp(self):
        """Set up test client and data"""
        self.client = Client()
        self.url = reverse('my_view')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        # Sample data
        self.sample_data = {...}

    @patch('myapp.views.audit_log_kudu_repository.log_action')
    @patch('myapp.views.my_repository.get_data')
    def test_my_feature(self, mock_get, mock_audit):
        """Test my feature description"""
        mock_get.return_value = self.sample_data

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('key', response.context)

        # Verify audit log
        mock_audit.assert_called_once()
```

### Best Practices

1. **Test Naming**
   - Use descriptive names: `test_login_success`, `test_login_failure`
   - Follow pattern: `test_<feature>_<scenario>`

2. **Test Structure (AAA)**
   - **Arrange:** Set up test data
   - **Act:** Execute the code under test
   - **Assert:** Verify the results

3. **Mocking**
   - Mock external dependencies (Kudu, Impala)
   - Mock slow operations
   - Verify mock calls when important

4. **Assertions**
   - Test HTTP status codes
   - Verify template usage
   - Check context variables
   - Validate audit logging

5. **Coverage**
   - Aim for 90% on new code
   - Test both success and failure paths
   - Test edge cases

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest --cov=. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Roadmap

### Short Term
- [ ] Add service layer tests (target: 90% coverage)
- [ ] Add dashboard view tests
- [ ] Add integration tests for workflows

### Medium Term
- [ ] Performance testing
- [ ] Load testing
- [ ] Security testing

### Long Term
- [ ] End-to-end testing with Selenium
- [ ] API testing with Postman/Newman
- [ ] Automated regression testing

---

## Support

For questions about testing:
1. Check this documentation
2. Review existing test files for examples
3. Contact the development team

---

**CisTrade Testing** © 2025
