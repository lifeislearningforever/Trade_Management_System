# CisTrade – Unit Test Cases Index

**Project:** CisTrade Trade Management System  
**Framework:** pytest + pytest-django  
**Total Collected:** 1,455 tests across 27 test files  
**Date:** 2026-06-16  

---

## Table of Contents

1. [Core App](#1-core-app)
2. [Portfolio App](#2-portfolio-app)
3. [Trade App](#3-trade-app)
4. [Market Data App](#4-market-data-app)
5. [Reference Data App](#5-reference-data-app)
6. [Security App](#6-security-app)
7. [UDF App](#7-udf-app)
8. [Upload App](#8-upload-app)
9. [Query Builder App](#9-query-builder-app)
10. [Hive POC App](#10-hive-poc-app)
11. [Root-Level Tests](#11-root-level-tests)
12. [Stress Tests](#12-stress-tests)

---

## 1. Core App

### `core/tests/test_audit_models.py`

#### ActionTypeEnumTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 1 | `test_all_action_types_have_values` | All enum members have non-empty string values |
| 2 | `test_create_value` | CREATE action type resolves to correct string |
| 3 | `test_login_value` | LOGIN action type resolves to correct string |
| 4 | `test_approve_value` | APPROVE action type resolves to correct string |

#### AuditStatusEnumTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 5 | `test_success` | SUCCESS status value |
| 6 | `test_failure` | FAILURE status value |
| 7 | `test_partial` | PARTIAL status value |

#### EntityTypeEnumTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 8 | `test_portfolio` | PORTFOLIO entity type value |
| 9 | `test_trade` | TRADE entity type value |

#### AuditEntryTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 10 | `test_creates_with_required_fields` | AuditEntry instantiates with mandatory fields |
| 11 | `test_auto_sets_timestamp` | `timestamp` auto-populates on creation |
| 12 | `test_auto_sets_audit_date` | `audit_date` auto-populates as date |
| 13 | `test_default_status_is_success` | Default status is SUCCESS |
| 14 | `test_optional_fields_default_to_none` | Optional fields are None by default |
| 15 | `test_to_dict_converts_enums_to_values` | `to_dict()` serialises enum values |
| 16 | `test_to_dict_with_entity_type` | `to_dict()` includes entity_type |
| 17 | `test_to_dict_with_none_entity_type` | `to_dict()` handles None entity_type |
| 18 | `test_to_dict_serializes_request_params` | `to_dict()` serialises request params |
| 19 | `test_to_dict_serializes_tags` | `to_dict()` serialises tags list |
| 20 | `test_to_dict_serializes_metadata` | `to_dict()` serialises metadata dict |
| 21 | `test_to_hive_values_returns_tuple` | `to_hive_values()` returns a tuple |
| 22 | `test_to_hive_values_contains_username` | Tuple contains username |
| 23 | `test_to_hive_values_contains_action_type` | Tuple contains action type |
| 24 | `test_from_request_authenticated_user` | Factory builds entry from authenticated request |
| 25 | `test_from_request_anonymous_user` | Factory handles anonymous user |
| 26 | `test_from_request_post_method` | Factory captures POST method |
| 27 | `test_get_client_ip_x_forwarded_for` | Extracts IP from X-Forwarded-For header |
| 28 | `test_get_client_ip_remote_addr_fallback` | Falls back to REMOTE_ADDR |

---

### `core/tests/test_auth_views.py`

#### LoginViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 29 | `test_login_view_get` | GET /login/ renders login template |
| 30 | `test_login_view_already_logged_in_redirects` | Logged-in user redirected away from login |
| 31 | `test_login_success` | Valid credentials create session and redirect |
| 32 | `test_login_failure_invalid_user` | Invalid credentials return error |
| 33 | `test_login_empty_login` | Empty credentials return validation error |

#### LogoutViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 34 | `test_logout_success` | POST /logout/ clears session |

#### AutoLoginTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 35 | `test_auto_login_success` | Dev auto-login creates session |
| 36 | `test_auto_login_failure` | Auto-login with missing user returns error |

#### RequireLoginDecoratorTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 37 | `test_require_login_redirects_when_not_logged_in` | Unauthenticated request redirects to login |
| 38 | `test_require_login_allows_access_when_logged_in` | Authenticated request passes through |

#### RequirePermissionDecoratorTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 39 | `test_permission_denied_logged` | Missing permission returns 403 |

#### SessionManagementTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 40 | `test_session_data_persistence` | Session data persists across requests |
| 41 | `test_logout_clears_all_session_data` | Logout flushes all session keys |

---

### `core/tests/test_middleware.py`

#### ACLMiddlewareTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 42 | `test_attaches_acl_service_to_request` | Middleware attaches `acl_service` to request |
| 43 | `test_unauthenticated_user_gets_empty_permissions` | Anonymous user gets empty ACL |
| 44 | `test_authenticated_user_gets_permissions` | Authenticated user gets populated ACL |
| 45 | `test_process_request_returns_none` | Middleware returns None (passes through) |

---

### `core/tests/test_notifications.py`

#### TestUserGroup / TestRoleGroup / TestAdminGroup
| # | Test Method | Description |
|---|-------------|-------------|
| 46–60 | Various | Channel group name sanitisation (special chars, spaces, injection, alphanumeric) |

#### TestEventSeverity
| # | Test Method | Description |
|---|-------------|-------------|
| 61–70 | `test_*_is_*` | Event type maps to correct severity (success/warning/error/info) |
| 71 | `test_all_events_covered` | All defined events have a severity mapping |

#### TestGetChannelLayer
| # | Test Method | Description |
|---|-------------|-------------|
| 72 | `test_returns_layer_when_configured` | Returns channel layer when configured |
| 73 | `test_returns_none_when_channels_not_installed` | Returns None when channels not installed |
| 74 | `test_returns_none_when_get_channel_layer_returns_none` | Returns None when layer unavailable |
| 75 | `test_exception_inside_returns_none` | Exceptions are swallowed, returns None |

#### TestBuildMessage
| # | Test Method | Description |
|---|-------------|-------------|
| 76–82 | Various | Message structure, severity lookup, timestamp format, payload truncation |

#### TestSendToGroup / TestNotifyUser / TestNotifyRole / TestNotifyAdmins / TestNotifyMultipleUsers
| # | Test Method | Description |
|---|-------------|-------------|
| 83–110 | Various | Send to group/user/role/admin; empty inputs skipped; success/failure returns; concurrency counts |

#### TestNotificationConsumerConnect / Disconnect / ReceiveJson / NotificationSend
| # | Test Method | Description |
|---|-------------|-------------|
| 111–155 | Various | WebSocket lifecycle: accept/reject, group joins, welcome message, ping/pong, mark-read, disconnect cleanup |

#### TestResolveGroups / TestIsAdmin / TestCloseCodes
| # | Test Method | Description |
|---|-------------|-------------|
| 156–175 | Various | Group resolution (v1/v2 ACL), admin detection, WebSocket close code values |

---

## 2. Portfolio App

### `portfolio/tests/test_repositories.py`

#### PortfolioHiveRepositoryTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 176 | `test_get_all_portfolios` | Returns list of all portfolios |
| 177 | `test_get_portfolio_by_code` | Finds portfolio by short name |
| 178 | `test_get_portfolio_by_code_not_found` | Returns None for unknown code |
| 179 | `test_insert_portfolio` | Inserts new portfolio row |
| 180 | `test_update_portfolio_status` | Updates status field |
| 181 | `test_get_currencies` | Returns currency list |

---

### `portfolio/tests/test_views.py`

#### PortfolioListViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 182 | `test_portfolio_list_view_success` | Portfolio list renders with 200 |
| 183 | `test_portfolio_list_search` | Search filter narrows results |
| 184 | `test_portfolio_list_status_filter` | Status filter narrows results |
| 185 | `test_portfolio_csv_export` | CSV export returns correct content-type |

#### PortfolioDetailViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 186 | `test_portfolio_detail_view_success` | Detail page renders for existing portfolio |
| 187 | `test_portfolio_detail_not_found` | 404 returned for unknown portfolio |

#### PortfolioCreateViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 188 | `test_portfolio_create_view_get` | GET create form renders |
| 189 | `test_portfolio_create_success` | POST creates portfolio and redirects |

#### PortfolioEditViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 190 | `test_portfolio_edit_view_get` | GET edit form renders with existing data |
| 191 | `test_portfolio_edit_success` | POST updates portfolio |

#### PortfolioWorkflowTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 192 | `test_portfolio_submit_for_approval` | Status changes to PENDING_APPROVAL |
| 193 | `test_portfolio_approve` | Checker approves → APPROVED |
| 194 | `test_portfolio_reject` | Checker rejects → REJECTED |

#### PortfolioCloseReactivateTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 195 | `test_portfolio_close` | ACTIVE → CLOSED |
| 196 | `test_portfolio_reactivate` | CLOSED → ACTIVE |

#### PortfolioWrapperTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 197 | `test_wrapper_initialization` | PortfolioWrapper maps dict to attributes |
| 198 | `test_wrapper_missing_fields` | Missing fields default safely |

#### PortfolioURLTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 199–202 | `test_*_url_resolves` | URL reversals resolve to correct views |

---

## 3. Trade App

### `trade/tests/test_repositories.py`

#### TradeKuduRepositoryTestCase (80+ tests)

**Escape & Type Helpers**
| # | Test Method | Description |
|---|-------------|-------------|
| 203 | `test_escape_value_string` | Escapes single quotes in strings |
| 204 | `test_escape_value_none` | None → NULL string |
| 205 | `test_escape_value_integer` | Integer passes through |
| 206 | `test_escape_value_float` | Float passes through |
| 207 | `test_escape_value_boolean` | Boolean → 1/0 |
| 208 | `test_escape_value_date` | Date formatted correctly |
| 209–215 | `test_to_decimal_*` | Decimal conversion (None, 0, negative, large, precision, Decimal input, string) |

**ID Generation**
| # | Test Method | Description |
|---|-------------|-------------|
| 216 | `test_get_next_id_success` | Returns next sequential ID |
| 217 | `test_get_next_id_first_record` | Returns 1 when table empty |

**Validation**
| # | Test Method | Description |
|---|-------------|-------------|
| 218–228 | `test_validate_trade_data_*` | Missing required fields, invalid types, valid data, boundary values |

**Read Operations**
| # | Test Method | Description |
|---|-------------|-------------|
| 229–233 | `test_get_all_trades*` | All trades, with portfolio filter, security filter, date range, exception |
| 234–235 | `test_get_all_trades_multi_filter_*` | Combined filters |
| 236–238 | `test_get_trade_by_id*` | By ID: found, not found, exception |
| 239–240 | `test_get_trade_by_deal_number*` | By deal number: found, not found |

**Write Operations**
| # | Test Method | Description |
|---|-------------|-------------|
| 241–242 | `test_insert_trade_*` | Successful insert, duplicate handling |
| 243–245 | `test_update_trade_*` | Update status, update fields, not found |
| 246–247 | `test_soft_delete_trade_*` | Soft delete: success, already deleted |

**Workflow (Four-Eyes)**
| # | Test Method | Description |
|---|-------------|-------------|
| 248–250 | `test_submit_for_validation_*` | Submit: success, already pending, not found |
| 251–253 | `test_validate_trade_*` | Validate: success, self-validation rejected, not found |
| 254–255 | `test_reject_trade_*` | Reject: success, wrong status |
| 256–257 | `test_settle_trade_*` | Settle: success, already settled |

**Detail & Position**
| # | Test Method | Description |
|---|-------------|-------------|
| 258–262 | `test_get_trade_detail*` | Detail with/without charges, not found, exception |
| 263–268 | `test_update_position_from_trade_*` | BUY/SELL positions, charges included, rounding |

**History & Statistics**
| # | Test Method | Description |
|---|-------------|-------------|
| 269–271 | `test_insert_trade_history_*` | Insert history: success, no optional fields |
| 272 | `test_get_trade_history` | Returns ordered history records |
| 273–275 | `test_get_trade_statistics*` | Stats with data, empty table, exception |

**Position Access**
| # | Test Method | Description |
|---|-------------|-------------|
| 276–277 | `test_get_pending_*_trades` | Pending settlement, pending validation |
| 278–279 | `test_trade_type_constants`, `test_all_trade_types_list` | BUY/SELL/etc constants |
| 280–284 | Status constants, editable/actionable status sets | |
| 285 | `test_get_position_alias` | Alias resolves |
| 286–288 | `test_get_position_by_id*` | By ID: found, not found, exception |
| 289–292 | `test_get_all_positions*` | All, with portfolio filter, security filter, exception |
| 293–295 | `test_get_position_versions*` | Version history: found, empty, exception |
| 296–299 | `test_get_position_statistics*` | Stats: all portfolios, filtered, empty, exception |
| 300–303 | `test_get_equity_price_*` | Price: found, not found, stale, exception |
| 304–307 | `test_refresh_market_values*` | Refresh: success, no price, partial, exception |
| 308 | `test_spreadsheet_pnl_lifecycle` | Full BUY→SELL P&L lifecycle scenario |

---

### `trade/tests/test_services.py`

#### TradeDropdownServiceTestCase (60+ tests)
| # | Test Method | Description |
|---|-------------|-------------|
| 309–310 | `test_get_trade_types*` | Returns trade type list with structure |
| 311 | `test_get_trade_statuses` | Returns status list |
| 312–314 | `test_get_portfolios*` | All, with search, empty |
| 315–316 | `test_get_securities*` | All, with ISIN filter |
| 317 | `test_get_counterparties` | Returns counterparty list |
| 318–319 | `test_get_brokers_*` | From counterparty table, fallback defaults |
| 320–321 | `test_get_gl_fund_types_*` | From UDF, fallback |
| 322 | `test_get_gl_cost_centres_from_udf` | From UDF lookup |
| 323 | `test_get_gl_account_codes_from_udf` | From UDF lookup |
| 324–325 | `test_get_selling_rules_*` | From UDF, fallback |
| 326–327 | `test_get_custodians_*` | From counterparty, fallback |
| 328 | `test_get_sub_custodians_from_udf` | From UDF lookup |
| 329–330 | `test_get_open_close_options_*` | From UDF, fallback |
| 331–338 | Various UDF dropdown tests | Extensions, Fund Types, Income/Exp Types, UOBN, Section, Revision, Amortisation, Delivery |
| 339–341 | `test_get_income_types_*`, `test_get_split_types_*`, `test_get_reduction_types_*` | From UDF |
| 342 | `test_get_all_dropdown_options` | Aggregates all dropdowns |
| 343–346 | `test_get_udf_options_*` | UDF options: found, empty, exception, cache |
| 347–348 | `test_database_constant`, `test_object_type_constant` | Constants correct |

#### TradeDropdownServiceFallbackTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 349–355 | `test_get_*_fallback_defaults` | Each dropdown has sensible fallback values |

---

### `trade/tests/test_views.py`

#### TradeWrapperTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 356 | `test_trade_wrapper_basic_fields` | String fields map correctly |
| 357 | `test_trade_wrapper_numeric_fields` | Numeric fields parse to correct types |
| 358 | `test_trade_wrapper_date_fields` | Date fields parse correctly |
| 359 | `test_trade_wrapper_udf_fields` | UDF fields accessible via wrapper |
| 360 | `test_trade_wrapper_workflow_fields` | Maker-checker fields present |
| 361 | `test_trade_wrapper_default_values` | Missing fields default safely |
| 362 | `test_trade_wrapper_data_attribute` | `data` attribute holds raw dict |

#### GetUserInfoTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 363 | `test_get_user_info_from_session` | Extracts user info from session |
| 364 | `test_get_user_info_defaults` | Missing session keys use defaults |

#### TradeListViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 365 | `test_trade_list_basic` | Trade list renders with 200 |

---

### `trade/tests/test_position_service.py`

#### TestAVPCalculation
| # | Test Method | Description |
|---|-------------|-------------|
| 366 | `test_buy_new_position` | First BUY creates position with correct AVP |
| 367 | `test_buy_add_to_existing_position` | Second BUY blends into existing AVP |
| 368 | `test_buy_multiple_times_avp_accumulates` | Multiple BUYs accumulate correctly |
| 369 | `test_sell_partial_position` | SELL reduces qty; AVP unchanged; realised P&L correct |

---

### `trade/tests/test_settlement_service.py`

#### TestSettlementDateRules
| # | Test Method | Description |
|---|-------------|-------------|
| 370 | `test_current_date_settlement` | T+0 settles immediately |
| 371 | `test_future_date_settlement_queued` | T+1/T+2 enters settlement queue |
| 372 | `test_backdated_within_limit_allowed` | Backdated settlement allowed and queued |

---

### `trade/tests/test_position_queue_service.py`

#### TestQueueEnqueue
| # | Test Method | Description |
|---|-------------|-------------|
| 373 | `test_enqueue_to_db_queue` | Item persisted to `cis_position_queue` |
| 374 | `test_enqueue_to_memory_queue` | Item added to in-memory queue |
| 375 | `test_enqueue_includes_multicurrency_fields` | FX fields included in queue item |

#### TestQueueProcessing
| # | Test Method | Description |
|---|-------------|-------------|
| 376 | `test_process_item_success` | Queue item processed and position updated |

---

### `trade/tests/test_cash_flow_service.py`

#### CashFlowServiceTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 377 | `test_list_all_delegates_to_repository` | Service delegates to repository |
| 378 | `test_status_constants` | Status constants correct |
| 379 | `test_list_all_passes_filters` | Filters passed through to repository |
| 380 | `test_get_by_id` | Returns cash flow by ID |
| 381 | `test_get_by_id_not_found` | Returns None for unknown ID |
| 382 | `test_get_pending_approvals` | Returns INITIAL/MODIFIED cash flows |
| 383 | `test_get_by_portfolio` | Filters by portfolio name |
| 384 | `test_create_missing_required_field_returns_error` | Validation error on missing field |
| 385 | `test_create_invalid_portfolio_returns_error` | Invalid portfolio returns error |

---

### `trade/tests/test_multicurrency_service.py`

#### TestFXRateLookup
| # | Test Method | Description |
|---|-------------|-------------|
| 386 | `test_same_currency_returns_one` | Same ccy/ccy → rate 1.0 |
| 387 | `test_direct_pair_lookup` | Direct pair returns stored rate |
| 388 | `test_reverse_pair_inverted` | Reverse pair returns 1/rate |
| 389 | `test_no_rate_returns_one` | Unknown pair → 1.0 fallback |
| 390 | `test_null_currencies_return_one` | None inputs → 1.0 |
| 391 | `test_historical_rate_lookup` | Lookup by specific date |

#### TestFXRateCache
| # | Test Method | Description |
|---|-------------|-------------|
| 392 | `test_rate_cached` | Same-day rate reused from cache |

---

### `trade/tests/test_trade_event_queue_service.py`

#### TradeEventQueueServiceConstantsTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 393 | `test_status_constants` | Status constants (PENDING, PROCESSING, etc.) |
| 394 | `test_config_constants` | Config constants (batch size, poll interval) |

#### TradeEventQueueServiceWorkerTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 395 | `test_initial_state_not_running` | Worker starts in stopped state |
| 396 | `test_start_worker_returns_true` | First start returns True |
| 397 | `test_start_worker_second_call_returns_false` | Double-start returns False |
| 398 | `test_stop_worker_returns_true_when_running` | Stop returns True when running |
| 399 | `test_stop_worker_returns_false_when_not_running` | Stop returns False when not running |
| 400 | `test_get_stats_returns_dict` | Stats dict has expected keys |

#### TradeEventQueueServiceHelperTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 401 | `test_escape_normal_string` | Normal string passed through |
| 402 | `test_escape_single_quote` | Single quote escaped |
| 403 | `test_escape_none` | None → NULL |
| 404–407 | `test_calculate_charges_*` | Charge aggregation (commission + fee + other) |

#### TradeEventQueueServiceQueryTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 408–410 | `test_get_pending_count*` | Pending count: success, empty, exception |
| 411–412 | `test_get_failed_events*` | Failed events: list, empty |

---

### `trade/tests/test_validation_repository.py`

#### ValidationResultTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 413 | `test_validation_result_creation` | ValidationResult instantiates correctly |
| 414 | `test_validation_result_with_details` | Details dict populated |
| 415 | `test_validation_result_invalid` | Invalid result carries error message |

#### TradeValidationRepositoryTestCase (50+ tests)
| # | Test Method | Description |
|---|-------------|-------------|
| 416–420 | `test_escape_value_*` | Escape: string, quote, None, int, special chars |
| 421–429 | `test_validate_portfolio_*` | Valid, not found, inactive, pending, null, empty, whitespace, injection, closed |
| 430–433 | `test_get_valid_portfolios*` | All valid, with filter, empty, exception |
| 434–448 | `test_validate_security_*` | 15 scenarios: valid, not found, inactive, type filters, currency mismatch, etc. |
| 449–451 | `test_get_valid_securities*` | All valid, with filter, exception |
| 452–458 | `test_validate_counterparty_*` | 7 scenarios: valid, not found, inactive, type mismatch, etc. |
| 459–461 | `test_get_valid_counterparties*` | All valid, with filter, exception |
| 462–464 | `test_validate_trade_references_*` | All valid, partial invalid, all invalid |
| 465–466 | `test_get_validation_errors`, `test_get_validation_errors_all_valid` | Error aggregation |
| 467–468 | `test_get_portfolio_details*` | Portfolio details: found, not found |
| 469–470 | `test_get_security_details*` | Security details: found, not found |
| 471–472 | `test_get_counterparty_details*` | Counterparty details: found, not found |
| 473–478 | Constants tests | DB name, table names, valid statuses, cache TTL |

---

## 4. Market Data App

### `market_data/tests/test_models.py`

#### FXRateModelTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 479 | `test_create_fx_rate_success` | FX rate model creates successfully |
| 480 | `test_fx_rate_str_representation` | `__str__` returns expected format |
| 481 | `test_currency_pair_validation_missing_slash` | Pair without `/` raises validation error |
| 482 | `test_auto_populate_base_quote_from_currency_pair` | Base/quote split from pair string |
| 483 | `test_rate_must_be_positive` | Zero/negative rate raises error |
| 484 | `test_bid_cannot_be_greater_than_ask` | Bid > Ask raises error |
| 485 | `test_auto_calculate_mid_rate` | Mid = (bid+ask)/2 auto-calculated |
| 486 | `test_decimal_precision` | Rate stored to configured precision |
| 487 | `test_get_freshness_color` | Color code by staleness |
| 488 | `test_get_freshness_status_fresh` | Recent rate → "fresh" |
| 489 | `test_get_freshness_status_normal` | Day-old rate → "normal" |
| 490 | `test_get_freshness_status_stale` | Old rate → "stale" |
| 491 | `test_get_spread_method` | `get_spread()` returns ask-bid |
| 492 | `test_get_spread_method_none_when_missing` | Returns None when bid/ask missing |
| 493 | `test_get_spread_percentage_method` | Spread as percentage of mid |
| 494 | `test_is_active_default` | Default `is_active=True` |
| 495 | `test_is_fresh_method_true` | `is_fresh()` True for recent rate |
| 496 | `test_is_fresh_method_false` | `is_fresh()` False for stale rate |
| 497 | `test_is_stale_method_true` | `is_stale()` True for old rate |
| 498 | `test_is_stale_method_false` | `is_stale()` False for recent rate |
| 499 | `test_metadata_json_field` | Metadata stored as JSON |
| 500 | `test_notes_field` | Notes field accepts text |
| 501 | `test_ordering` | Default ordering by rate_date desc |
| 502 | `test_rate_date_cannot_be_future` | Future date raises validation error |
| 503 | `test_source_choices` | Source choices match expected set |
| 504 | `test_unique_constraint` | Duplicate pair+date raises error |

---

### `market_data/tests/test_repositories.py`

#### HiveConnectionTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 505 | `test_execute_query_success` | Returns rows from query |
| 506 | `test_execute_query_empty_result` | Returns empty list on no rows |
| 507 | `test_execute_query_filters_logging` | Log output filtered correctly |
| 508 | `test_execute_query_raises_on_error` | Raises on Impala error |
| 509 | `test_execute_write_raises_on_error` | Write raises on Impala error |

#### FXRateHiveRepositoryTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 510 | `test_get_all_fx_rates_no_filters` | Returns all FX rates |
| 511 | `test_get_all_fx_rates_with_currency_pair_filter` | Filters by currency pair |

---

### `market_data/tests/test_views.py`

#### FXRateListViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 512 | `test_fx_rate_list_view_success` | FX rate list renders with 200 |
| 513 | `test_fx_rate_list_view_empty` | Empty state renders correctly |
| 514 | `test_fx_rate_list_search_filter` | Search filter applied |
| 515 | `test_fx_rate_list_currency_pair_filter` | Currency pair filter applied |

---

## 5. Reference Data App

### `reference_data/tests/test_repositories.py`

#### ImpalaReferenceRepositoryTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 516 | `test_execute_query_success` | Query returns expected rows |
| 517 | `test_execute_query_returns_empty_list_on_none` | None result → empty list |
| 518 | `test_execute_query_raises_on_error` | Raises on Impala exception |
| 519 | `test_execute_write_success` | Write executes without error |
| 520 | `test_execute_write_raises_on_error` | Write raises on Impala exception |
| 521 | `test_escape_sql_handles_quotes` | Single quotes doubled |
| 522 | `test_escape_sql_handles_none` | None → NULL string |

---

### `reference_data/tests/test_services.py`

#### CurrencyServiceTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 523 | `test_list_all_returns_currencies` | Returns currency list |
| 524 | `test_list_all_with_search` | Search narrows results |
| 525 | `test_get_by_code_returns_currency` | Lookup by currency code |

*(Additional service tests cover Corporate Action service, Party service, Counterparty CIF service, CA dropdown service)*

---

### `reference_data/tests/test_views.py`

#### CurrencyListViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 526 | `test_currency_list_view_success` | Currency list renders with 200 |
| 527 | `test_currency_search` | Search filter applied |
| 528 | `test_currency_csv_export` | CSV export returns correct headers |

---

### `reference_data/tests/test_ca_cash_flow_service.py`

#### CACashFlowServiceTestCase (30+ tests)
Key scenarios covered: CA cash flow generation for dividend/bonus/rights/warrants, partial failure handling, security resolution, holdings lookup, portfolio filtering, queue item creation, escape string handling.

---

### `reference_data/tests/test_ca_cash_flow_queue_repository.py`

48+ tests covering CA cash flow queue: enqueue, dequeue, status updates, retry logic, dead letter handling.

---

### `reference_data/tests/test_process_corporate_actions_command.py`

26+ tests covering the `process_corporate_actions` management command: CA selection, status transitions, cash flow creation, error handling, dry-run mode.

---

## 6. Security App

### `security/tests/test_security_id_registry.py`

#### TestBuildNaturalKey
| # | Test Method | Description |
|---|-------------|-------------|
| 529 | `test_isin_and_exchange_code_takes_priority` | ISIN+Exchange is primary key |
| 530 | `test_isin_and_country_when_no_exchange_code` | Falls back to ISIN+Country |
| 531 | `test_isin_only_when_no_exchange_or_country` | Falls back to ISIN alone |
| 532 | `test_name_and_exchange_when_no_isin` | Uses Name+Exchange without ISIN |
| 533 | `test_name_and_country_when_no_isin_and_no_exchange` | Uses Name+Country |
| 534 | `test_name_only_as_last_resort` | Name alone as final fallback |
| 535 | `test_isin_normalised_to_uppercase` | ISIN normalised to uppercase |
| 536 | `test_name_normalised_to_uppercase` | Name normalised to uppercase |
| 537 | `test_whitespace_stripped_from_all_fields` | Whitespace stripped from all fields |
| 538 | `test_cross_listed_same_isin_different_exchange_gives_different_keys` | Cross-listed securities get unique keys |
| 539 | `test_missing_security_data_keys_handled_gracefully` | Missing dict keys don't raise |

---

### `security/tests/test_views.py`

#### SecurityListViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 540 | `test_security_list_view_success` | Security list renders with 200 |
| 541 | `test_security_list_empty` | Empty state renders |
| 542 | `test_security_list_with_search` | Search filter applied |
| 543 | `test_security_list_with_status_filter` | Status filter applied |
| 544 | `test_security_list_csv_export` | CSV export (column headers verified) |

#### SecurityDetailViewTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 545 | `test_security_detail_view_success` | Detail renders for existing security |
| 546 | `test_security_detail_not_found` | 404 for unknown security |

---

## 7. UDF App

### `udf/tests/test_models.py`

#### UDFModelTestCase (44 tests)
Key scenarios: field type choices validation, entity type choices, dropdown validation (requires options), field ordering, model string representation, computed properties.

---

### `udf/tests/test_repositories.py`

#### UDFRepositoryTestCase (6 tests)
Repository CRUD: get all, get by entity, insert, update, soft delete, restore.

---

### `udf/tests/test_udf_field_repository.py` (70+ tests)
Full CRUD coverage: create, read (by id, by entity, by object type), update, soft_delete, restore, pagination, search filtering, validation.

---

### `udf/tests/test_udf_field_service.py`

#### UDFFieldServiceGetObjectTypesTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 547 | `test_get_object_types_success` | Returns list of object types |
| 548 | `test_get_object_types_empty` | Returns empty list when no data |
| 549 | `test_get_object_types_exception` | Exception handled gracefully |

#### UDFFieldServiceGetFieldsByEntityTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 550 | `test_get_fields_by_entity_success` | Returns fields for entity type |
| 551 | `test_get_fields_by_entity_empty` | Empty list for unknown entity |
| 552 | `test_get_fields_by_entity_exception` | Exception handled gracefully |

#### UDFFieldServiceGetAllFieldsTestCase
| # | Test Method | Description |
|---|-------------|-------------|
| 553 | `test_get_all_fields_no_filters` | Returns all UDF field definitions |

*(Additional service test methods cover CRUD operations, validation, field ordering)*

---

### `udf/tests/test_views.py` / `test_views_simplified.py`

55+ tests covering UDF management views: list, create, edit, delete, restore, value management, entity-level UDF display.

---

## 8. Upload App

### `upload/tests/test_upload_service.py` (110+ tests)

Key test scenarios:
- File parsing (CSV, Excel, multi-sheet)
- Column mapping and validation
- Data type coercion (dates, numbers, strings)
- Staging and commit pipeline
- Position upload (standardised format)
- Equity price upload
- Error reporting and partial failure handling
- Datasource configuration lookup
- Upload history and status tracking

---

## 9. Query Builder App

### `query_builder/tests/test_export_service.py` (24 tests)

Key scenarios: CSV export, Excel export, column formatting, empty result sets, special characters in data.

### `query_builder/tests/test_sql_builder_service.py` (73 tests)

Key scenarios: SELECT clause building, WHERE clause generation, JOIN assembly, ORDER BY, LIMIT/OFFSET, SQL injection prevention, Kudu-specific syntax, complex filter combinations.

---

## 10. Hive POC App

### `hive_poc/tests/test_services.py`

#### TestPortfolioHiveService
| # | Test Method | Description |
|---|-------------|-------------|
| 554 | `test_get_type_choices` | Portfolio type choices returned |
| 555 | `test_get_status_choices` | Portfolio status choices returned |
| 556 | `test_get_currency_choices` | Currency choices returned |
| 557 | `test_validate_valid_portfolio` | Valid portfolio passes validation |
| 558 | `test_validate_invalid_name` | Blank name fails validation |
| 559 | `test_validate_invalid_type` | Invalid type fails validation |
| 560 | `test_create_success` | Portfolio created in Hive |
| 561 | `test_create_duplicate_code` | Duplicate portfolio code raises error |

---

## 11. Root-Level Tests

### `test_audit_logging.py` (3 tests)
Integration smoke tests for the audit logging pipeline: write to Kudu, fallback to file, replay from file.

### `test_connection.py` (4 tests)
Impala connection smoke tests: connect, simple query, connection pool, timeout handling.

### `test_hybrid_connection.py` (6 tests)
Hybrid ORM+Kudu connection tests: dual-write, read routing, failover.

---

## 12. Stress Tests

### `tests/stress/test_kudu_stress.py` (10 tests, 2 skipped)
| # | Test Method | Description |
|---|-------------|-------------|
| S1 | Concurrent reads | 10 threads reading positions simultaneously |
| S2 | Concurrent writes | 5 threads inserting trades simultaneously |
| S3–S4 | *(skipped — require live Kudu)* | High-volume batch insert |
| S5–S10 | Various | Pool exhaustion, reconnect, latency benchmarks |

---

## File & Count Summary

| App | Test Files | Approx Tests |
|-----|-----------|-------------|
| core | 4 | ~175 |
| portfolio | 2 | ~27 |
| trade | 8 | ~360 |
| market_data | 3 | ~37 |
| reference_data | 5 | ~110 |
| security | 2 | ~19 |
| udf | 6 | ~170 |
| upload | 1 | ~110 |
| query_builder | 2 | ~97 |
| hive_poc | 1 | ~15 |
| root-level | 3 | ~13 |
| stress | 1 | ~10 |
| **Total** | **38** | **~1,455** |
