# CisTrade – Unit Test Execution Report

**Run Date:** 2026-06-16  
**Environment:** Local macOS (Darwin 25.5.0, Python 3.12.11)  
**Impala:** Not connected (Docker container offline — expected for local unit tests)  
**Command:** `pytest --tb=line -q --no-header`  
**Duration:** 208.99 seconds (3 min 28 sec)  

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Collected** | 1,455 |
| **Passed** | 1,436 |
| **Failed** | 15 |
| **Skipped** | 4 |
| **Warnings** | 66 |
| **Pass Rate** | **98.7%** |
| **Overall Coverage** | **36.98%** |

---

## Test Results by App

| App | Test File | Pass | Fail | Skip | Notes |
|-----|-----------|------|------|------|-------|
| core | test_audit_models.py | 19 | 0 | 0 | All pass |
| core | test_auth_views.py | 3 | 8 | 0 | URL config issue (see failures) |
| core | test_middleware.py | 4 | 0 | 0 | All pass |
| core | test_notifications.py | 92 | 0 | 0 | All pass |
| market_data | test_models.py | 26 | 0 | 0 | All pass |
| market_data | test_repositories.py | 18 | 0 | 0 | All pass |
| market_data | test_views.py | 17 | 0 | 0 | All pass |
| portfolio | test_repositories.py | 6 | 0 | 0 | All pass |
| portfolio | test_views.py | 21 | 0 | 0 | All pass |
| reference_data | test_ca_cash_flow_queue_repository.py | 48 | 0 | 0 | All pass |
| reference_data | test_ca_cash_flow_service.py | 28 | 2 | 0 | Escape + partial failure test |
| reference_data | test_process_corporate_actions_command.py | 26 | 0 | 0 | All pass |
| reference_data | test_repositories.py | 48 | 0 | 0 | All pass |
| reference_data | test_services.py | 66 | 0 | 0 | All pass |
| reference_data | test_views.py | 70 | 0 | 0 | All pass |
| security | test_security_id_registry.py | 22 | 0 | 0 | All pass |
| security | test_views.py | 7 | 1 | 0 | CSV column header mismatch |
| trade | test_cash_flow_service.py | 10 | 0 | 0 | All pass |
| trade | test_repositories.py | ~148 | 2 | 0 | Exception handling + statistics |
| trade | test_services.py | ~58 | 2 | 0 | Securities dropdown filter |
| trade | test_trade_event_queue_service.py | 21 | 0 | 0 | All pass |
| trade | test_validation_repository.py | 66 | 0 | 0 | All pass |
| trade | test_views.py | 78 | 0 | 0 | All pass |
| trade | test_multicurrency_service.py | 22 | 0 | 0 | All pass |
| trade | test_position_queue_service.py | 15 | 0 | 0 | All pass |
| trade | test_position_service.py | 18 | 0 | 0 | All pass |
| trade | test_settlement_service.py | 18 | 0 | 0 | All pass |
| udf | test_models.py | 44 | 0 | 0 | All pass |
| udf | test_repositories.py | 6 | 0 | 0 | All pass |
| udf | test_udf_field_repository.py | 70 | 0 | 0 | All pass |
| udf | test_udf_field_service.py | 50 | 0 | 0 | All pass |
| udf | test_views.py | 29 | 0 | 0 | All pass |
| udf | test_views_simplified.py | 54 | 0 | 0 | All pass |
| upload | test_upload_service.py | 110 | 0 | 0 | All pass |
| query_builder | test_export_service.py | 24 | 0 | 0 | All pass |
| query_builder | test_sql_builder_service.py | 73 | 0 | 0 | All pass |
| hive_poc | test_services.py | 15 | 0 | 0 | All pass |
| root | test_audit_logging.py | 3 | 0 | 0 | All pass |
| root | test_connection.py | 4 | 0 | 0 | All pass |
| root | test_hybrid_connection.py | 6 | 0 | 0 | All pass |
| stress | test_kudu_stress.py | 8 | 0 | 4 (skip) | Skipped — require live Kudu |

---

## Failed Tests Detail

### 1. `core/tests/test_auth_views.py` — 8 failures

**Root Cause:** `NoReverseMatch: Reverse for 'auto_login' not found`

The `core/login.html` template contains `{% url 'auto_login' %}` but the `auto_login` URL name is not registered in the test URL configuration.

**Affected Tests:**
| Test | Error |
|------|-------|
| `LoginViewTestCase::test_login_view_get` | NoReverseMatch on template render |
| `LoginViewTestCase::test_login_success` | NoReverseMatch on template render |
| `LoginViewTestCase::test_login_failure_invalid_user` | NoReverseMatch on template render |
| `LoginViewTestCase::test_login_empty_login` | NoReverseMatch on template render |
| `LogoutViewTestCase::test_logout_success` | NoReverseMatch on template render |
| `AutoLoginTestCase::test_auto_login_success` | `KeyError: 'user_id'` — mock user dict missing field |
| `AutoLoginTestCase::test_auto_login_failure` | NoReverseMatch on template render |
| `RequireLoginDecoratorTestCase::test_require_login_redirects_when_not_logged_in` | NoReverseMatch on template render |

**Fix Required:**  
Add `auto_login` URL to test URL config, or update `core/login.html` to use `{% url 'auto_login' %}` conditionally. Also fix mock user dict in `AutoLoginTestCase` to include `user_id` key.

---

### 2. `reference_data/tests/test_ca_cash_flow_service.py` — 2 failures

**Failure A: `test_escape_string`**
```
AssertionError: "test\\'s value" != "test''s value"
```
The escape function uses backslash-quote (`\'`) but the test expects SQL-standard double-single-quote (`''`). The test expectation reflects the correct SQL standard; the implementation should be updated to use `''` for Impala compatibility.

**Failure B: `test_process_ca_cash_flows_partial_failure`**
```
AssertionError: True is not false
```
The test expects `success=False` when one CA fails to generate cash flows (partial failure), but the service currently returns `True` even on partial failures. The service should return `False` if any item in the batch fails.

---

### 3. `security/tests/test_views.py::SecurityListViewTestCase::test_security_list_csv_export` — 1 failure

```
AssertionError: 'Security ID' not found in 'Security Name,ISIN,...'
```
The CSV export column header was renamed from `Security ID` to `Security Name` in the repository/view, but the test still asserts the old header name. The test needs updating to match the current CSV output.

---

### 4. `trade/tests/test_repositories.py` — 2 failures

**Failure A: `test_get_all_trades_exception`**
```
AssertionError: Lists differ: [{...2 trades...}] != []
```
The test mocks an Impala exception and expects an empty list back. The repository is currently returning cached or default data instead of an empty list on exception. The exception handler branch needs to return `[]`.

**Failure B: `test_get_trade_statistics`**
```
AssertionError: 0 != 38
```
Statistics query returns 0 when the test expects 38 (count of seeded trades). The mock for the statistics query is not returning the expected fixture data — mock setup needs to be aligned with the current query structure.

---

### 5. `trade/tests/test_services.py` — 2 failures

**Failure A: `test_get_securities`**
```
AssertionError: 'TEST' not found in 'SEC001'
```
The securities dropdown mock returns `SEC001` fixtures but the test filters for `'TEST'` prefix. The mock data or filter logic has drifted — either update mock data to include `TEST` prefixed securities or update the test assertion.

**Failure B: `test_get_securities_with_isin`**
```
AssertionError: 'US1234567890' not found in 'SEC001'
```
Same issue: ISIN filter test expects the returned security to contain the ISIN in its label/display, but mock data uses `SEC001` format. Mock needs updating to include ISIN in the response structure.

---

## Failure Summary Table

| # | Test | Category | Root Cause | Priority |
|---|------|----------|-----------|----------|
| 1–7 | `test_auth_views.*` | URL Config | `auto_login` URL missing from test config | Medium |
| 8 | `test_auth_views::test_auto_login_success` | Mock Data | Mock user dict missing `user_id` key | Medium |
| 9 | `test_escape_string` | Implementation | Escape uses `\'` instead of SQL-standard `''` | High |
| 10 | `test_process_ca_cash_flows_partial_failure` | Business Logic | Service returns True on partial batch failure | High |
| 11 | `test_security_list_csv_export` | Test Drift | CSV header renamed; test not updated | Low |
| 12 | `test_get_all_trades_exception` | Mock/Impl | Exception handler returns data instead of `[]` | Medium |
| 13 | `test_get_trade_statistics` | Mock Data | Mock doesn't align with current query structure | Medium |
| 14 | `test_get_securities` | Mock Data | Mock data doesn't match test filter expectations | Low |
| 15 | `test_get_securities_with_isin` | Mock Data | ISIN not included in mock response structure | Low |

---

## Code Coverage Report

> Coverage measured across all app source files. Impala-connected code (repositories, services calling Kudu) shows lower coverage as those paths require a live database.

### By App — Summary

| App | Statements | Missed | Coverage |
|-----|-----------|--------|----------|
| **core** | ~2,200 | ~1,600 | ~27% |
| **portfolio** | ~1,100 | ~600 | ~47% |
| **trade** | ~5,100 | ~3,000 | ~41% |
| **market_data** | ~900 | ~660 | ~27% |
| **reference_data** | ~3,000 | ~1,800 | ~40% |
| **security** | ~600 | ~420 | ~30% |
| **udf** | ~1,000 | ~350 | ~65% |
| **upload** | ~2,500 | ~2,100 | ~16% |
| **query_builder** | ~500 | ~200 | ~60% |
| **hive_poc** | ~600 | ~400 | ~35% |
| **TOTAL** | **26,474** | **16,685** | **36.98%** |

---

### Key Files — Coverage Detail

#### Core App

| File | Coverage | Notes |
|------|----------|-------|
| `core/audit/audit_models.py` | **100%** |  |
| `core/middleware/acl_middleware.py` | **100%** |  |
| `core/consumers.py` | **94%** | WebSocket consumer |
| `core/notifications/sender.py` | **91%** |  |
| `core/notifications/constants.py` | **100%** |  |
| `core/repositories/impala_connection.py` | **55%** | Pool paths need live Kudu |
| `core/audit/async_audit_queue.py` | **66%** |  |
| `core/audit/audit_kudu_repository.py` | **45%** | Write paths need live Kudu |
| `core/views/auth_views.py` | **50%** | Failures affect coverage |
| `core/services/acl_service.py` | **28%** | Needs live Kudu |
| `core/audit/audit_hive_repository.py` | **17%** | Legacy; low priority |
| `core/audit/replay_fallback.py` | **0%** | Not tested |

#### Trade App

| File | Coverage | Notes |
|------|----------|-------|
| `trade/repositories/trade_validation_repository.py` | **84%** |  |
| `trade/repositories/trade_kudu_repository.py` | **77%** |  |
| `trade/views.py` | **75%** |  |
| `trade/services/settlement_service.py` | **62%** |  |
| `trade/services/position_queue_service.py` | **52%** |  |
| `trade/services/trade_dropdown_service.py` | **52%** |  |
| `trade/services/position_service.py` | **47%** |  |
| `trade/services/cash_flow_service.py` | **31%** |  |
| `trade/repositories/cash_flow_repository.py` | **15%** | Needs live Kudu |
| `trade/repositories/position_repository.py` | **11%** | Needs live Kudu |

#### UDF App (Highest Coverage)

| File | Coverage | Notes |
|------|----------|-------|
| `udf/services/udf_field_service.py` | **100%** |  |
| `udf/models.py` | **99%** |  |
| `udf/views.py` | **100%** |  |
| `udf/repositories/udf_field_repository.py` | **94%** |  |

#### Reference Data App

| File | Coverage | Notes |
|------|----------|-------|
| `reference_data/repositories/ca_cash_flow_queue_repository.py` | **100%** |  |
| `reference_data/repositories/counterparty_cif_repository.py` | **95%** |  |
| `reference_data/services/counterparty_cif_service.py` | **100%** |  |
| `reference_data/models.py` | **95%** |  |
| `reference_data/services/reference_data_service.py` | **95%** |  |
| `reference_data/repositories/reference_data_repository.py` | **92%** |  |
| `reference_data/management/commands/process_corporate_actions.py` | **88%** |  |
| `reference_data/services/ca_cash_flow_service.py` | **45%** | Large file; complex CA types |
| `reference_data/services/corporate_action_service.py` | **19%** | Needs more service tests |

#### Query Builder App

| File | Coverage | Notes |
|------|----------|-------|
| `query_builder/services/export_service.py` | **97%** |  |
| `query_builder/services/sql_builder_service.py` | **94%** |  |

#### Market Data App

| File | Coverage | Notes |
|------|----------|-------|
| `market_data/models.py` | **96%** |  |
| `market_data/views.py` | **45%** |  |
| `market_data/repositories/fx_rate_hive_repository.py` | **41%** | Needs live Kudu |
| `market_data/services/fx_rate_service.py` | **17%** | Needs live Kudu |

---

## Skipped Tests

| Test | Reason |
|------|--------|
| `tests/stress/test_kudu_stress.py` × 4 | Marked `@pytest.mark.skip` — require live Kudu with data |

---

## Warnings Summary (66 total)

Most warnings are expected in local dev without Kudu:
- `[ERROR] Failed to create Impala connection: Could not connect to localhost:21050` — Docker not running
- `[WARNING] No active system date found in cis_system_date table` — no DB connection
- Django deprecation warnings (template rendering, query API)
- PyHive/thrift transport warnings on connection retry

These do not indicate test failures and are expected in offline mode.

---

## Recommended Fixes (Priority Order)

### High Priority
1. **`test_escape_string`** — Fix `ca_cash_flow_service.py` to use `''` (double-single-quote) instead of `\'` for SQL escaping in Impala
2. **`test_process_ca_cash_flows_partial_failure`** — Update service to return `False` when any batch item fails

### Medium Priority
3. **`test_auth_views.*` (7 tests)** — Add `auto_login` URL pattern to test URL configuration in `conftest.py` or test URL conf
4. **`test_auto_login_success`** — Add `user_id` to mock user dict in `AutoLoginTestCase`
5. **`test_get_all_trades_exception`** — Fix exception handler in `get_all_trades()` to return `[]` on Impala error
6. **`test_get_trade_statistics`** — Update mock to align with current statistics query output format

### Low Priority
7. **`test_security_list_csv_export`** — Update test assertion from `'Security ID'` to `'Security Name'`
8. **`test_get_securities` / `test_get_securities_with_isin`** — Update mock data to include ISIN-format security labels

---

## Coverage Improvement Targets

| Priority | File | Current | Target |
|----------|------|---------|--------|
| 1 | `reference_data/services/corporate_action_service.py` | 19% | 80% |
| 2 | `core/services/acl_service.py` | 28% | 70% |
| 3 | `trade/services/position_service.py` | 47% | 80% |
| 4 | `trade/services/cash_flow_service.py` | 31% | 75% |
| 5 | `market_data/services/fx_rate_service.py` | 17% | 60% |
| 6 | `core/audit/audit_kudu_repository.py` | 45% | 70% |
| 7 | `upload/services/upload_service.py` | 24% | 60% |
