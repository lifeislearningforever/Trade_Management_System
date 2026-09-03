# CIS Trade Hive - Unit Test Coverage Plan

## Overview

This document tracks the current state of unit test coverage across all modules in the CIS Trade Hive project and provides a roadmap for future test development.

**Last Updated:** 2026-01-17

---

## Module Test Coverage Summary

| Module | Tests Exist | Coverage % | Status |
|--------|-------------|------------|--------|
| **trade** | Yes | ~97.39% | Complete |
| **udf (simplified)** | Yes | ~99.11% | Complete |
| **udf (legacy)** | Partial | Unknown | Legacy - Low Priority |
| **core** | Partial | Unknown | Needs Expansion |
| **market_data** | Yes | Unknown | Needs Verification |
| **portfolio** | Partial | Unknown | Needs Expansion |
| **reference_data** | Partial | Unknown | Needs Expansion |
| **security** | No | 0% | **Highest Priority** |

---

## Detailed Module Analysis

### 1. Trade Module (COMPLETE)

**Status:** Complete - 97.39% coverage

**Test Files:**
- `trade/tests/test_repositories.py` (1067 lines)
- `trade/tests/test_validation_repository.py` (781 lines)
- `trade/tests/test_services.py` (1169 lines)
- `trade/tests/test_views.py` (1394 lines)

**Source Files Covered:**
- `trade/repositories/trade_kudu_repository.py`
- `trade/repositories/trade_validation_repository.py`
- `trade/services/trade_dropdown_service.py`
- `trade/views.py`

**What's Tested:**
- Repository CRUD operations
- Trade workflow (submit, validate, reject, settle)
- Four-eyes principle validation
- Status transition logic
- Multi-filter queries
- Pagination and sorting
- Dropdown services
- All view endpoints
- Error handling scenarios

---

### 2. UDF Simplified Module (COMPLETE)

**Status:** Complete - 99.11% coverage

**Test Files:**
- `udf/tests/test_udf_field_repository.py` (877 lines)
- `udf/tests/test_udf_field_service.py` (709 lines)
- `udf/tests/test_views_simplified.py` (780 lines)

**Source Files Covered:**
- `udf/repositories/udf_field_repository.py` - 97.63%
- `udf/services/udf_field_service.py` - 100%
- `udf/views_simplified.py` - 100%

**What's Tested:**
- Composite primary key operations (object_type, field_name, field_value)
- Cascading dropdown logic
- CRUD operations with audit logging
- Dashboard statistics
- Soft delete and restore functionality
- Field validation
- All API endpoints
- Edge cases and error handling

---

### 3. UDF Legacy Module (LOW PRIORITY)

**Status:** Legacy code - Partial tests exist

**Test Files:**
- `udf/tests/test_views.py` (465 lines)
- `udf/tests/test_repositories.py` (104 lines)

**Source Files:**
- `udf/repositories/udf_hive_repository.py`
- `udf/services/udf_service.py`
- `udf/views.py`

**Notes:**
- This is legacy code being replaced by the simplified UDF module
- Tests exist but may conflict with new simplified tests
- Low priority for additional test coverage
- Consider deprecation plan

---

### 4. Core Module (NEEDS EXPANSION)

**Status:** Partial - Auth views only

**Existing Test Files:**
- `core/tests/test_auth_views.py` (355 lines)

**Source Files Requiring Tests:**

| File | Priority | Complexity | Notes |
|------|----------|------------|-------|
| `core/repositories/impala_connection.py` | HIGH | High | Database connection pool |
| `core/repositories/hive_connection.py` | HIGH | Medium | Hive database connection |
| `core/repositories/acl_repository.py` | HIGH | Medium | Access control logic |
| `core/services/acl_service.py` | HIGH | Medium | ACL business logic |
| `core/services/help_service.py` | MEDIUM | Low | Help system |
| `core/repositories/help_repository.py` | MEDIUM | Low | Help data access |
| `core/views/dashboard_views.py` | MEDIUM | Low | Dashboard views |
| `core/middleware/acl_middleware.py` | HIGH | Medium | ACL middleware |
| `core/middleware/audit_middleware.py` | HIGH | Medium | Audit logging |
| `core/audit/audit_logger.py` | HIGH | High | Central audit system |
| `core/audit/audit_kudu_repository.py` | HIGH | High | Audit data storage |
| `core/audit/async_audit_queue.py` | MEDIUM | High | Async audit processing |

**Recommended Test Files to Create:**
1. `core/tests/test_acl_repository.py`
2. `core/tests/test_acl_service.py`
3. `core/tests/test_impala_connection.py`
4. `core/tests/test_audit_logger.py`
5. `core/tests/test_acl_middleware.py`

---

### 5. Market Data Module (NEEDS VERIFICATION)

**Status:** Tests exist - Coverage unknown

**Existing Test Files:**
- `market_data/tests/test_models.py` (274 lines)
- `market_data/tests/test_repositories.py` (340 lines)
- `market_data/tests/test_views.py` (353 lines)

**Source Files:**
- `market_data/repositories/equity_price_hive_repository.py`
- `market_data/repositories/fx_rate_hive_repository.py`
- `market_data/services/equity_price_service.py`
- `market_data/services/equity_price_dropdown_service.py`
- `market_data/services/fx_rate_service.py`
- `market_data/views.py`

**TODO:**
- [ ] Run coverage report for market_data module
- [ ] Identify gaps in test coverage
- [ ] Add tests for dropdown services if missing

---

### 6. Portfolio Module (NEEDS EXPANSION)

**Status:** Partial - Views and basic repository tests

**Existing Test Files:**
- `portfolio/tests/test_repositories.py` (99 lines)
- `portfolio/tests/test_views.py` (481 lines)

**Source Files Requiring Tests:**
| File | Priority | Notes |
|------|----------|-------|
| `portfolio/services/portfolio_service.py` | HIGH | No service tests |
| `portfolio/services/portfolio_dropdown_service.py` | HIGH | No service tests |
| `portfolio/repositories/portfolio_hive_repository.py` | MEDIUM | Basic tests only |

**Recommended Test Files to Create:**
1. `portfolio/tests/test_services.py`
2. `portfolio/tests/test_dropdown_service.py`

---

### 7. Reference Data Module (NEEDS EXPANSION)

**Status:** Partial - Views and basic repository tests

**Existing Test Files:**
- `reference_data/tests/test_repositories.py` (72 lines)
- `reference_data/tests/test_views.py` (380 lines)

**Source Files Requiring Tests:**
| File | Priority | Notes |
|------|----------|-------|
| `reference_data/services/reference_data_service.py` | HIGH | No service tests |
| `reference_data/services/counterparty_cif_service.py` | HIGH | No service tests |
| `reference_data/repositories/counterparty_cif_repository.py` | HIGH | No tests |

**Recommended Test Files to Create:**
1. `reference_data/tests/test_services.py`
2. `reference_data/tests/test_counterparty_cif_repository.py`
3. `reference_data/tests/test_counterparty_cif_service.py`

---

### 8. Security Module (HIGHEST PRIORITY - NO TESTS)

**Status:** No tests - 0% coverage

**Source Files Requiring Tests:**
| File | Priority | Lines | Notes |
|------|----------|-------|-------|
| `security/repositories/security_hive_repository.py` | HIGH | - | Repository layer |
| `security/services/security_service.py` | HIGH | - | Service layer |
| `security/services/security_dropdown_service.py` | HIGH | - | Dropdown service |
| `security/views.py` | HIGH | - | All view endpoints |

**Recommended Test Files to Create:**
1. `security/tests/__init__.py`
2. `security/tests/test_repositories.py`
3. `security/tests/test_services.py`
4. `security/tests/test_dropdown_service.py`
5. `security/tests/test_views.py`

---

## Priority Order for Future Test Development

### Priority 1 - CRITICAL (Security Module)
No tests exist. This is a security-sensitive module.

1. **security/tests/test_repositories.py**
   - Test SecurityHiveRepository CRUD operations
   - Mock Impala database calls
   - Test error handling

2. **security/tests/test_services.py**
   - Test SecurityService business logic
   - Test validation rules
   - Test audit logging integration

3. **security/tests/test_views.py**
   - Test all security view endpoints
   - Test authentication/authorization
   - Test form validation

### Priority 2 - HIGH (Core Module Gaps)
Core functionality that affects all modules.

1. **core/tests/test_impala_connection.py**
   - Connection pool management
   - Connection retry logic
   - Error handling

2. **core/tests/test_acl_service.py**
   - Access control logic
   - Permission checking
   - User role handling

3. **core/tests/test_audit_logger.py**
   - Audit log creation
   - Async queue processing
   - Error scenarios

### Priority 3 - MEDIUM (Service Layer Gaps)
Complete service layer testing for all modules.

1. **portfolio/tests/test_services.py**
2. **reference_data/tests/test_services.py**
3. **reference_data/tests/test_counterparty_cif_service.py**

### Priority 4 - LOW (Verification & Enhancement)
Verify existing tests and enhance coverage.

1. Run coverage reports for all modules
2. Identify specific lines missing coverage
3. Add edge case tests where needed

---

## Testing Patterns and Best Practices

### Standard Test Structure

```python
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock

class TestFeature(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.sample_data = {...}

    def tearDown(self):
        """Clean up after tests"""
        pass

    @patch('module.repository.method')
    def test_success_case(self, mock_method):
        """Test normal operation"""
        mock_method.return_value = self.sample_data
        result = service.method()
        self.assertEqual(result, expected)

    @patch('module.repository.method')
    def test_error_case(self, mock_method):
        """Test error handling"""
        mock_method.side_effect = Exception("Error")
        with self.assertRaises(Exception):
            service.method()
```

### Key Mocking Patterns

**1. Mock Impala Connection:**
```python
@patch('core.repositories.impala_connection.ImpalaConnectionPool.get_connection')
def test_with_mocked_db(self, mock_get_conn):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [...]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_get_conn.return_value.__exit__ = Mock(return_value=False)
```

**2. Mock Session Data:**
```python
mock_request.session.get.side_effect = lambda key, default='': {
    'user_name': 'testuser',
    'user_id': 123
}.get(key, default)
```

**3. Mock Service in View:**
```python
@patch('module.views.service_instance.method')
def test_view(self, mock_method):
    mock_method.return_value = expected_data
    response = self.client.get('/endpoint/')
```

---

## Running Tests

### Run All Tests
```bash
python manage.py test
```

### Run Module-Specific Tests
```bash
python manage.py test trade.tests
python manage.py test udf.tests
python manage.py test core.tests
```

### Run with Coverage
```bash
coverage run --source='trade' manage.py test trade.tests
coverage report --show-missing
coverage html  # Generate HTML report
```

### Run Specific Test File
```bash
python manage.py test trade.tests.test_views
```

### Run Specific Test Class
```bash
python manage.py test trade.tests.test_views.TradeViewsTestCase
```

---

## Test Coverage Goals

| Module | Current | Target | Status |
|--------|---------|--------|--------|
| trade | 97.39% | 95%+ | Achieved |
| udf (simplified) | 99.11% | 95%+ | Achieved |
| security | 0% | 95%+ | Not Started |
| core | ~30% | 80%+ | In Progress |
| portfolio | ~50% | 80%+ | In Progress |
| reference_data | ~40% | 80%+ | In Progress |
| market_data | Unknown | 80%+ | Needs Audit |

---

## Notes

1. **Test Isolation:** All tests use mocks to avoid hitting the actual Kudu/Impala database
2. **Audit Logging:** Tests verify audit logging is called with correct parameters
3. **Session Mocking:** Use side_effect for session.get() to properly handle default values
4. **Template Testing:** Ensure all required context variables are provided (e.g., udf_id for edit URLs)

---

## Changelog

- **2026-01-17:** Initial document created
  - Trade module: 97.39% coverage (292 tests)
  - UDF simplified: 99.11% coverage (169 tests)
  - Identified security module as highest priority gap
