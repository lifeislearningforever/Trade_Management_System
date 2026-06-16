# CisTrade – Code Review File Index

**Project:** CisTrade Trade Management System  
**Framework:** Django 5.2.9  
**Database:** Apache Kudu via Impala (`gmp_cis`)  
**Date:** 2026-06-16  

---

## Table of Contents

1. [Config](#1-config)
2. [Core App](#2-core-app)
3. [Portfolio App](#3-portfolio-app)
4. [Trade App](#4-trade-app)
5. [Market Data App](#5-market-data-app)
6. [Reference Data App](#6-reference-data-app)
7. [Security App](#7-security-app)
8. [UDF App](#8-udf-app)
9. [Lookup App](#9-lookup-app)
10. [Hive POC App](#10-hive-poc-app-legacy)
11. [Templates](#11-templates)
12. [Static Files](#12-static-files)
13. [SQL / DDL](#13-sql--ddl)
14. [Root-Level Scripts](#14-root-level-scripts)

---

## 1. Config

| File | Purpose |
|------|---------|
| `config/__init__.py` | Package init |
| `config/settings.py` | Django settings — Impala config, installed apps, middleware |
| `config/urls.py` | Root URL configuration |
| `config/wsgi.py` | WSGI entry point |
| `config/asgi.py` | ASGI entry point |
| `config/environments.py` | Environment-specific settings (local/CML) |
| `config/cml_app.py` | Cloudera Machine Learning deployment entry point |

---

## 2. Core App

### Main

| File | Purpose |
|------|---------|
| `core/__init__.py` | Package init |
| `core/apps.py` | App config |
| `core/models.py` | Django ORM placeholder models |
| `core/urls.py` | Core URL routes (auth, dashboard, RBAC admin) |
| `core/permissions_map.py` | Permission-to-action mapping constants |
| `core/routing.py` | WebSocket routing |
| `core/consumers.py` | WebSocket consumers (notifications) |
| `core/old_views.py` | Deprecated views (reference only) |
| `core/admin.py` | Django admin registrations |

### Views

| File | Purpose |
|------|---------|
| `core/views/__init__.py` | Package init |
| `core/views/auth_views.py` | Login / logout / profile views |
| `core/views/dashboard_views.py` | Main dashboard view |
| `core/views/notification_views.py` | In-app notification views |
| `core/views/rbac_admin_views.py` | RBAC admin CRUD views |

### Repositories

| File | Purpose |
|------|---------|
| `core/repositories/__init__.py` | Package init |
| `core/repositories/impala_connection.py` | **ImpalaConnectionManager** — 35-connection pool (primary DB layer) |
| `core/repositories/hive_connection.py` | Legacy Hive connection (pre-Kudu) |
| `core/repositories/hybrid_connection.py` | Hybrid ORM + Kudu connection wrapper |
| `core/repositories/acl_repository.py` | ACL data access (Kudu) |
| `core/repositories/acl_repository_v2.py` | ACL repository v2 with RBAC numeric IDs |
| `core/repositories/rbac_admin_repository.py` | RBAC admin CRUD repository |
| `core/repositories/system_date_repository.py` | System/business date access |
| `core/repositories/help_repository.py` | Help content repository |
| `core/repositories/db_router.py` | Django DB router |

### Services

| File | Purpose |
|------|---------|
| `core/services/__init__.py` | Package init |
| `core/services/acl_service.py` | Role-based access control service (ACL caching 300s) |
| `core/services/permission_service.py` | Permission check helpers |
| `core/services/system_date_service.py` | Business date service |
| `core/services/help_service.py` | Contextual help content service |

### Middleware

| File | Purpose |
|------|---------|
| `core/middleware/__init__.py` | Package init |
| `core/middleware/acl_middleware.py` | Attaches ACL/permissions to every request |
| `core/middleware/audit_middleware.py` | Async audit logging middleware |
| `core/middleware/audit_middleware_hive.py` | Hive-specific audit middleware (legacy) |
| `core/middleware/permission_middleware.py` | Permission enforcement middleware |
| `core/middleware/performance_middleware.py` | Request timing / performance logging |

### Audit Subsystem

| File | Purpose |
|------|---------|
| `core/audit/__init__.py` | Package init |
| `core/audit/audit_kudu_repository.py` | Writes audit records to `cis_audit_log` Kudu table |
| `core/audit/audit_hive_repository.py` | Legacy Hive audit repository |
| `core/audit/audit_logger.py` | High-level audit logging API |
| `core/audit/audit_models.py` | Audit record data classes |
| `core/audit/audit_context.py` | Request-scoped audit context (user, IP, action) |
| `core/audit/audit_decorator.py` | `@audit_action` decorator for view/service functions |
| `core/audit/async_audit_queue.py` | Async queue for non-blocking audit writes |
| `core/audit/circuit_breaker.py` | Circuit breaker for audit write failures |
| `core/audit/file_audit_logger.py` | File-based audit fallback when Kudu is unavailable |
| `core/audit/replay_fallback.py` | Replay file-logged audits back into Kudu |
| `core/audit/examples.py` | Usage examples (dev reference) |

### Notifications

| File | Purpose |
|------|---------|
| `core/notifications/__init__.py` | Package init |
| `core/notifications/sender.py` | Send in-app notifications |
| `core/notifications/kudu_store.py` | Persist notifications to `cis_notification` Kudu table |
| `core/notifications/constants.py` | Notification type constants |

### Management Commands

| File | Purpose |
|------|---------|
| `core/management/commands/create_hive_db.py` | Create all Kudu/Impala tables |
| `core/management/commands/test_hive.py` | Test Impala connection |
| `core/management/commands/setup_test_users.py` | Seed test users / ACL data |
| `core/management/commands/verify_rbac.py` | Verify RBAC permission mapping |
| `core/management/commands/export_ddl.py` | Export current Kudu schema to DDL |

### Template Tags

| File | Purpose |
|------|---------|
| `core/templatetags/__init__.py` | Package init |
| `core/templatetags/core_filters.py` | Custom Django template filters |

### Utils

| File | Purpose |
|------|---------|
| `core/utils/__init__.py` | Package init |
| `core/utils/context_processors.py` | Global template context (user, ACL) |

### Tests

| File | Purpose |
|------|---------|
| `core/tests/__init__.py` | Package init |
| `core/tests/test_auth_views.py` | Auth view tests |
| `core/tests/test_audit_models.py` | Audit model unit tests |
| `core/tests/test_middleware.py` | Middleware tests |
| `core/tests/test_notifications.py` | Notification system tests |

---

## 3. Portfolio App

| File | Purpose |
|------|---------|
| `portfolio/__init__.py` | Package init |
| `portfolio/apps.py` | App config |
| `portfolio/models.py` | Portfolio data wrappers |
| `portfolio/urls.py` | Portfolio URL routes |
| `portfolio/views.py` | Portfolio CRUD + Four-Eyes workflow views |
| `portfolio/tests_django_orm_legacy.py` | Legacy ORM tests (reference only) |
| `portfolio/forms/__init__.py` | Form definitions |
| `portfolio/repositories/__init__.py` | Package init |
| `portfolio/repositories/portfolio_hive_repository.py` | Portfolio Kudu data access |
| `portfolio/services/__init__.py` | Package init |
| `portfolio/services/portfolio_service.py` | Portfolio business logic + maker-checker |
| `portfolio/services/portfolio_dropdown_service.py` | Dropdown population service |
| `portfolio/management/commands/import_portfolios.py` | Bulk import portfolios from CSV |
| `portfolio/tests/__init__.py` | Package init |
| `portfolio/tests/test_repositories.py` | Repository tests |
| `portfolio/tests/test_views.py` | View tests |

---

## 4. Trade App

### Main

| File | Purpose |
|------|---------|
| `trade/__init__.py` | Package init |
| `trade/apps.py` | App config |
| `trade/urls.py` | Trade URL routes |
| `trade/views.py` | Trade CRUD + settlement + pending approval views |
| `trade/views_cash_flow.py` | Cash flow CRUD views |
| `trade/views_position.py` | Position viewer views |

### Repositories

| File | Purpose |
|------|---------|
| `trade/repositories/__init__.py` | Package init |
| `trade/repositories/trade_kudu_repository.py` | Trade CRUD on `cis_trade` Kudu table |
| `trade/repositories/trade_validation_repository.py` | Trade validation queries |
| `trade/repositories/position_repository.py` | Position read/write on `cis_trade_position` |
| `trade/repositories/cash_flow_repository.py` | Cash flow read/write on Kudu |

### Services (AVP System)

| File | Purpose |
|------|---------|
| `trade/services/__init__.py` | Package init |
| `trade/services/position_service.py` | **Phase 1** — AVP calculation (BUY/SELL, weighted avg cost) |
| `trade/services/settlement_service.py` | **Phase 2** — Settlement date logic (T+0/T+1/T+2/backdated) |
| `trade/services/position_queue_service.py` | **Phase 3** — Async position processing queue |
| `trade/services/multicurrency_service.py` | **Phase 4** — Multi-currency P&L (FX impact) |
| `trade/services/trade_dropdown_service.py` | Dropdown population for trade form |
| `trade/services/cash_flow_service.py` | Cash flow business logic + Four-Eyes |
| `trade/services/cash_flow_dropdown_service.py` | Dropdown population for cash flow form |
| `trade/services/trade_event_queue_service.py` | Trade event queue (async processing) |

### Management Commands

| File | Purpose |
|------|---------|
| `trade/management/commands/create_sod_snapshot.py` | Create start-of-day position snapshot |
| `trade/management/commands/position_worker.py` | Background position queue processor |
| `trade/management/commands/process_settlements.py` | Process settlement queue |
| `trade/management/commands/process_approved_cashflows.py` | Process approved cash flows |
| `trade/management/commands/refresh_positions.py` | Recalculate all positions |
| `trade/management/commands/run_trade_event_worker.py` | Start trade event worker daemon |
| `trade/management/commands/trade_event_worker.py` | Trade event worker implementation |
| `trade/management/commands/upload_amsiceq_positions.py` | Upload AMS/ICEQ positions from file |
| `trade/management/commands/extract_db_ddl.py` | Extract Kudu DDL for trade tables |

### Tests

| File | Purpose |
|------|---------|
| `trade/tests/__init__.py` | Package init |
| `trade/tests/test_position_service.py` | AVP Phase 1 unit tests |
| `trade/tests/test_settlement_service.py` | AVP Phase 2 unit tests |
| `trade/tests/test_position_queue_service.py` | AVP Phase 3 unit tests |
| `trade/tests/test_multicurrency_service.py` | AVP Phase 4 unit tests |
| `trade/tests/test_repositories.py` | Repository unit tests |
| `trade/tests/test_validation_repository.py` | Validation repository tests |
| `trade/tests/test_services.py` | General service tests |
| `trade/tests/test_views.py` | View tests |
| `trade/tests/test_cash_flow_service.py` | Cash flow service tests |
| `trade/tests/test_trade_event_queue_service.py` | Event queue service tests |

---

## 5. Market Data App

| File | Purpose |
|------|---------|
| `market_data/__init__.py` | Package init |
| `market_data/apps.py` | App config |
| `market_data/models.py` | FX rate / equity price data wrappers |
| `market_data/urls.py` | Market data URL routes |
| `market_data/views.py` | FX rate + equity price views |
| `market_data/admin.py` | Admin registrations |
| `market_data/repositories/__init__.py` | Package init |
| `market_data/repositories/fx_rate_hive_repository.py` | FX rate Kudu data access |
| `market_data/repositories/equity_price_hive_repository.py` | Equity price Kudu data access |
| `market_data/services/__init__.py` | Package init |
| `market_data/services/fx_rate_service.py` | FX rate business logic |
| `market_data/services/equity_price_service.py` | Equity price business logic |
| `market_data/services/equity_price_dropdown_service.py` | Dropdown population for equity price form |
| `market_data/management/commands/create_equity_price_table.py` | Create equity price Kudu table |
| `market_data/management/commands/setup_equity_price_udf.py` | Seed equity price UDF fields |
| `market_data/tests/__init__.py` | Package init |
| `market_data/tests/test_models.py` | Model tests |
| `market_data/tests/test_repositories.py` | Repository tests |
| `market_data/tests/test_views.py` | View tests |

---

## 6. Reference Data App

### Main

| File | Purpose |
|------|---------|
| `reference_data/__init__.py` | Package init |
| `reference_data/apps.py` | App config |
| `reference_data/models.py` | Currency, Country, Calendar, Counterparty, Corporate Action data wrappers |
| `reference_data/urls.py` | Reference data URL routes |
| `reference_data/views.py` | All reference data CRUD + Four-Eyes views |
| `reference_data/admin.py` | Admin registrations |
| `reference_data/forms/__init__.py` | Form definitions |

### Repositories

| File | Purpose |
|------|---------|
| `reference_data/repositories/__init__.py` | Package init |
| `reference_data/repositories/reference_data_repository.py` | Currency / Country / Calendar Kudu access |
| `reference_data/repositories/corporate_action_repository.py` | Corporate action Kudu CRUD |
| `reference_data/repositories/ca_cash_flow_queue_repository.py` | CA cash flow processing queue |
| `reference_data/repositories/counterparty_cif_repository.py` | Counterparty CIF Kudu access |
| `reference_data/repositories/party_cif_repository.py` | Party CIF Kudu access |
| `reference_data/repositories/party_repository.py` | Party (counterparty) Kudu CRUD |

### Services

| File | Purpose |
|------|---------|
| `reference_data/services/__init__.py` | Package init |
| `reference_data/services/reference_data_service.py` | Currency / Country / Calendar business logic |
| `reference_data/services/corporate_action_service.py` | Corporate action business logic + Four-Eyes |
| `reference_data/services/corporate_action_dropdown_service.py` | Dropdown population for CA form |
| `reference_data/services/ca_cash_flow_service.py` | CA cash flow generation service |
| `reference_data/services/counterparty_cif_service.py` | Counterparty CIF service |
| `reference_data/services/party_service.py` | Party business logic + Four-Eyes |

### Management Commands

| File | Purpose |
|------|---------|
| `reference_data/management/commands/process_corporate_actions.py` | Process pending corporate actions |
| `reference_data/management/commands/sync_gmp_corporate_actions.py` | Sync CAs from GMP source system |

### Tests

| File | Purpose |
|------|---------|
| `reference_data/tests/__init__.py` | Package init |
| `reference_data/tests/test_repositories.py` | Repository tests |
| `reference_data/tests/test_services.py` | Service tests |
| `reference_data/tests/test_views.py` | View tests |
| `reference_data/tests/test_ca_cash_flow_service.py` | CA cash flow service tests |
| `reference_data/tests/test_ca_cash_flow_queue_repository.py` | Queue repository tests |
| `reference_data/tests/test_process_corporate_actions_command.py` | Management command tests |

---

## 7. Security App

| File | Purpose |
|------|---------|
| `security/__init__.py` | Package init |
| `security/apps.py` | App config |
| `security/models.py` | Security master data wrappers |
| `security/urls.py` | Security URL routes |
| `security/views.py` | Security master CRUD views |
| `security/repositories/__init__.py` | Package init |
| `security/repositories/security_hive_repository.py` | Security master Kudu data access |
| `security/services/__init__.py` | Package init |
| `security/services/security_service.py` | Security master business logic |
| `security/services/security_dropdown_service.py` | Dropdown population for security forms |
| `security/management/commands/setup_security_udf.py` | Seed security UDF field definitions |
| `security/tests/__init__.py` | Package init |
| `security/tests/test_security_id_registry.py` | Security ID registry tests |
| `security/tests/test_views.py` | View tests |

---

## 8. UDF App

User-Defined Fields — extensible metadata system for any entity type.

| File | Purpose |
|------|---------|
| `udf/__init__.py` | Package init |
| `udf/apps.py` | App config |
| `udf/models.py` | UDF field definition and value data wrappers |
| `udf/urls.py` | UDF URL routes |
| `udf/views.py` | UDF definition + value CRUD views |
| `udf/admin.py` | Admin registrations |
| `udf/forms/__init__.py` | Form definitions |
| `udf/tests_django_orm_legacy.py` | Legacy ORM tests (reference only) |
| `udf/repositories/__init__.py` | Package init |
| `udf/repositories/udf_field_repository.py` | UDF field definition Kudu CRUD |
| `udf/repositories/udf_hive_repository.py` | UDF value Kudu data access |
| `udf/services/__init__.py` | Package init |
| `udf/services/udf_field_service.py` | UDF field business logic (92% coverage) |
| `udf/services/udf_service.py` | UDF value business logic |
| `udf/management/commands/load_udf_sample_data.py` | Seed sample UDF data |
| `udf/management/commands/recreate_udf_field_table.py` | Recreate UDF field Kudu table |
| `udf/sql/kudu_udf_audit_tables.sql` | UDF audit table DDL |
| `udf/tests/__init__.py` | Package init |
| `udf/tests/test_models.py` | Model tests |
| `udf/tests/test_repositories.py` | Repository tests |
| `udf/tests/test_udf_field_repository.py` | UDF field repository tests |
| `udf/tests/test_udf_field_service.py` | UDF field service tests |
| `udf/tests/test_views.py` | View tests (full) |
| `udf/tests/test_views_simplified.py` | View tests (simplified) |

---

## 9. Lookup App

| File | Purpose |
|------|---------|
| `lookup/__init__.py` | Package init |
| `lookup/urls.py` | Lookup URL routes |
| `lookup/views.py` | Lookup table admin views |
| `lookup/repositories/__init__.py` | Package init |
| `lookup/repositories/lookup_kudu_repository.py` | Lookup table Kudu data access |
| `lookup/services/__init__.py` | Package init |
| `lookup/services/lookup_service.py` | Lookup business logic |

---

## 10. Hive POC App (Legacy)

> **Note:** Proof-of-concept app from early Hive integration phase. Retained for reference. Not used in production.

| File | Purpose |
|------|---------|
| `hive_poc/__init__.py` | Package init |
| `hive_poc/apps.py` | App config |
| `hive_poc/hive_config.py` | Hive connection config (legacy) |
| `hive_poc/urls.py` | URL routes |
| `hive_poc/views.py` | Legacy portfolio/trade views |
| `hive_poc/docker/init-db.sql` | Docker Hive init SQL |
| `hive_poc/repositories/__init__.py` | Package init |
| `hive_poc/repositories/hive_base_repository.py` | Base Hive repository |
| `hive_poc/repositories/hive_connection.py` | Hive connection (legacy) |
| `hive_poc/repositories/portfolio_hive_repository.py` | Legacy portfolio Hive access |
| `hive_poc/repositories/trade_hive_repository.py` | Legacy trade Hive access |
| `hive_poc/services/__init__.py` | Package init |
| `hive_poc/services/portfolio_hive_service.py` | Legacy portfolio service |
| `hive_poc/services/trade_hive_service.py` | Legacy trade service |
| `hive_poc/sql/create_hive_tables.sql` | Legacy table DDL |
| `hive_poc/tests/__init__.py` | Package init |
| `hive_poc/tests/test_services.py` | Legacy service tests |

---

## 11. Templates

### Base & Shared

| File | Purpose |
|------|---------|
| `templates/base.html` | Site-wide base template (Bootstrap 5, sidebar, navbar) |
| `templates/dashboard.html` | Main dashboard |
| `templates/components/navbar.html` | Top navigation bar |
| `templates/components/navbar_acl.html` | ACL-aware navigation |
| `templates/components/sidebar.html` | Left sidebar navigation |
| `templates/components/footer.html` | Page footer |

### Auth

| File | Purpose |
|------|---------|
| `templates/auth/login.html` | Login page |
| `templates/auth/profile.html` | User profile page |

### Core (RBAC Admin)

| File | Purpose |
|------|---------|
| `templates/core/rbac/dashboard.html` | RBAC admin dashboard |
| `templates/core/rbac/user_list.html` | User list |
| `templates/core/rbac/user_form.html` | Create/edit user |
| `templates/core/rbac/user_groups.html` | Assign groups to user |
| `templates/core/rbac/group_list.html` | Group list |
| `templates/core/rbac/group_form.html` | Create/edit group |
| `templates/core/rbac/group_permissions.html` | Assign permissions to group |
| `templates/core/rbac/permission_list.html` | Permission list |
| `templates/core/rbac/permission_form.html` | Create/edit permission |
| `templates/core/rbac/audit.html` | RBAC audit log view |
| `templates/core/rbac/forbidden.html` | 403 Forbidden page |
| `templates/core/audit_log.html` | Audit log viewer |
| `templates/core/dashboard.html` | Core dashboard (legacy) |
| `templates/core/login.html` | Login (legacy) |
| `templates/core/search_results.html` | Global search results |

### Portfolio

| File | Purpose |
|------|---------|
| `templates/portfolio/portfolio_list.html` | Portfolio list with filters |
| `templates/portfolio/portfolio_form.html` | Create / edit portfolio |
| `templates/portfolio/portfolio_detail.html` | Portfolio detail view |
| `templates/portfolio/portfolio_dashboard.html` | Portfolio dashboard |
| `templates/portfolio/dashboard.html` | Portfolio dashboard (alt) |
| `templates/portfolio/pending_approvals.html` | Portfolios pending Four-Eyes approval |

### Trade

| File | Purpose |
|------|---------|
| `templates/trade/trade_list.html` | Trade list with filters |
| `templates/trade/trade_form.html` | Create / edit trade |
| `templates/trade/trade_detail.html` | Trade detail view |
| `templates/trade/trade_dashboard.html` | Trade dashboard |
| `templates/trade/trade_history.html` | Trade audit history |
| `templates/trade/pending_approvals.html` | Trades pending settlement approval |
| `templates/trade/position_list.html` | Position viewer (AVP, intcomma-formatted) |
| `templates/trade/position_detail.html` | Single position detail |
| `templates/trade/cash_flow_list.html` | Cash flow list with filters |
| `templates/trade/cash_flow_form.html` | Create / edit cash flow |
| `templates/trade/cash_flow_detail.html` | Cash flow detail view |
| `templates/trade/cash_flow_pending_approvals.html` | Cash flows pending approval |

### Market Data

| File | Purpose |
|------|---------|
| `templates/market_data/market_data_dashboard.html` | Market data dashboard |
| `templates/market_data/fx_rate_list.html` | FX rate list |
| `templates/market_data/fx_rate_detail.html` | FX rate detail |
| `templates/market_data/fx_rate_dashboard.html` | FX rate dashboard |
| `templates/market_data/equity_price_list.html` | Equity price list |
| `templates/market_data/equity_price_form.html` | Create / edit equity price |
| `templates/market_data/equity_price_detail.html` | Equity price detail |

### Reference Data

| File | Purpose |
|------|---------|
| `templates/reference_data/currency_list.html` | Currency list |
| `templates/reference_data/country_list.html` | Country list |
| `templates/reference_data/calendar_list.html` | Calendar list |
| `templates/reference_data/counterparty_list.html` | Counterparty list |
| `templates/reference_data/counterparty_form.html` | Create / edit counterparty |
| `templates/reference_data/counterparty_details.html` | Counterparty detail |
| `templates/reference_data/party_list.html` | Party list |
| `templates/reference_data/party_form.html` | Create / edit party |
| `templates/reference_data/party_details.html` | Party detail |
| `templates/reference_data/party_pending_approvals.html` | Parties pending approval |
| `templates/reference_data/corporate_action_list.html` | Corporate action list |
| `templates/reference_data/corporate_action_form.html` | Create / edit corporate action |
| `templates/reference_data/corporate_action_detail.html` | Corporate action detail |
| `templates/reference_data/corporate_action_pending_approvals.html` | CAs pending approval |

### Security

| File | Purpose |
|------|---------|
| `templates/security/security_list.html` | Security master list |
| `templates/security/security_form.html` | Create / edit security |
| `templates/security/security_detail.html` | Security detail |
| `templates/security/security_dashboard.html` | Security dashboard |

### UDF

| File | Purpose |
|------|---------|
| `templates/udf/udf_list.html` | UDF field definition list |
| `templates/udf/udf_form.html` | Create / edit UDF field |
| `templates/udf/udf_detail.html` | UDF field detail |
| `templates/udf/udf_value_history.html` | UDF value audit history |
| `templates/udf/list.html` | UDF values list |
| `templates/udf/form.html` | UDF value form |
| `templates/udf/dashboard.html` | UDF dashboard |
| `templates/udf/entity_udf_values.html` | UDF values for a specific entity |

### Lookup

| File | Purpose |
|------|---------|
| `templates/lookup/lookup_table_list.html` | Lookup table list |
| `templates/lookup/lookup_table_detail.html` | Lookup table detail + row listing |
| `templates/lookup/lookup_row_form.html` | Add / edit lookup row |

### Upload

| File | Purpose |
|------|---------|
| `templates/upload/upload_list.html` | File upload history list |
| `templates/upload/upload_form.html` | File upload form |
| `templates/upload/upload_detail.html` | Upload job detail / status |
| `templates/upload/upload_preview.html` | Preview uploaded data before commit |

### Query Builder

| File | Purpose |
|------|---------|
| `templates/query_builder/builder.html` | Visual query builder UI |
| `templates/query_builder/sql_editor.html` | Raw SQL editor |
| `templates/query_builder/saved_reports.html` | Saved query / report list |

---

## 12. Static Files

### JavaScript

| File | Purpose |
|------|---------|
| `static/js/cistrade.js` | **Primary JS** — table sorting (URL-persistent), pagination patch, modals |
| `static/js/select2-init.js` | Global Select2 initialization (`CISSelect2` namespace) |
| `static/js/notifications.js` | WebSocket notification client |
| `static/js/sidebar-toggle.js` | Sidebar collapse / expand toggle |
| `static/js/responsive.js` | Responsive layout helpers |
| `static/js/custom.js` | Misc custom scripts |
| `static/js/jquery-3.7.1.min.js` | jQuery (local, no CDN) |
| `static/js/select2.min.js` | Select2 library (local) |

### CSS

| File | Purpose |
|------|---------|
| `static/css/cistrade.css` | **Primary CSS** — CisTrade custom styles |
| `static/css/custom.css` | Additional custom styles |
| `static/css/responsive.css` | Responsive breakpoints |
| `static/css/select2-custom.css` | Select2 CisTrade theme overrides |
| `static/css/select2.min.css` | Select2 base styles (local) |
| `static/css/select2-bootstrap-5-theme.min.css` | Select2 Bootstrap 5 theme (local) |
| `static/bootstrap/css/bootstrap.min.css` | Bootstrap 5.3.3 (local) |
| `static/bootstrap-icons/…/bootstrap-icons.min.css` | Bootstrap Icons 1.11.3 (local) |

---

## 13. SQL / DDL

### Kudu DDL (Active)

| File | Purpose |
|------|---------|
| `sql/create_database.sql` | Create `gmp_cis` database |
| `sql/ddl/00_all_kudu_tables_docker.sql` | All Kudu tables (Docker compose) |
| `sql/ddl/01_core_tables.sql` | Core user/session tables |
| `sql/ddl/02_portfolio_tables.sql` | Portfolio tables |
| `sql/ddl/03_reference_data_tables.sql` | Currency/Country/Calendar tables |
| `sql/ddl/04_udf_tables.sql` | UDF field + value tables |
| `sql/ddl/05_acl_tables_kudu.sql` | ACL tables (legacy) |
| `sql/ddl/06_trade_tables_kudu.sql` | Trade + trade history tables |
| `sql/ddl/08_trade_lookup_tables_kudu.sql` | Trade lookup (charges, counterparty types) |
| `sql/ddl/13_avp_tables_kudu.sql` | AVP system: `cis_trade_position`, `cis_position_queue`, `cis_settlement_queue` |
| `sql/ddl/14_corporate_actions_kudu.sql` | Corporate action tables |
| `sql/ddl/15_cash_flow_kudu.sql` | Cash flow tables |
| `sql/ddl/16_ca_cash_flow_queue.sql` | CA cash flow processing queue |
| `sql/ddl/17_trade_event_queue_kudu.sql` | Trade event queue |
| `sql/ddl/20_system_date_tables.sql` | System/business date tables |
| `sql/ddl/21_file_upload_table.sql` | File upload tracking table |
| `sql/ddl/50_rbac_tables_kudu.sql` | RBAC tables (users, groups, permissions) |
| `sql/ddl/52_rbac_seed_permissions.sql` | Seed data for RBAC permissions |
| `sql/ddl/60_query_builder_kudu.sql` | Query builder saved reports table |
| `sql/ddl/64_security_id_registry.sql` | Security ID registry |
| `sql/ddl/68_cis_notification_kudu.sql` | In-app notification table |
| `sql/ddl/22_position_queue_add_basis_columns.sql` | Add TRADE_DATE/SETTLE_DATE basis columns to position queue |

### Security & Reference DDL

| File | Purpose |
|------|---------|
| `sql/ddl/cis_security_kudu.sql` | Security master table |
| `sql/ddl/cis_security_kudu_v2.sql` | Security master v2 (extended) |
| `sql/ddl/cis_security_history_kudu.sql` | Security audit history table |
| `sql/ddl/cis_party_kudu.sql` | Party / counterparty table |
| `sql/ddl/cis_counterparty_kudu.sql` | Counterparty table |
| `sql/ddl/cis_equity_price_kudu.sql` | Equity price table |
| `sql/ddl/gmp_cis_sta_dly_fx_rates.sql` | FX rate table |
| `sql/ddl/market_data_tables.sql` | Market data tables |

### Sample Data

| File | Purpose |
|------|---------|
| `sql/sample_data/01_users.sql` | Seed users |
| `sql/sample_data/02_currencies.sql` | Seed currencies |
| `sql/sample_data/03_countries.sql` | Seed countries |
| `sql/sample_data/04_calendars.sql` | Seed calendars |
| `sql/sample_data/05_counterparties.sql` | Seed counterparties |
| `sql/sample_data/06_portfolios.sql` | Seed portfolios |
| `sql/sample_data/07_acl_permissions_kudu.sql` | Seed ACL permissions |
| `sql/sample_data/08_fx_rates.sql` | Seed FX rates |

### ETL / Jobs

| File | Purpose |
|------|---------|
| `sql/etl/merge_gmp_security.sql` | Merge GMP security data into Kudu |
| `sql/etl/merge_gmp_equity_price.sql` | Merge GMP equity prices into Kudu |
| `sql/etl/eod_ca_cash_flow.sql` | EOD CA cash flow processing |
| `sql/jobs/eod_settlement_process.sql` | EOD settlement processing job |
| `sql/pyspark/merge_gmp_security.py` | PySpark security merge |
| `sql/pyspark/merge_gmp_equity_price.py` | PySpark equity price merge |
| `sql/pyspark/eod_ca_cash_flow.py` | PySpark EOD CA cash flow |
| `sql/pyspark/eod_ams_position_etl.py` | PySpark AMS position ETL |
| `sql/pyspark/ingest_trade_hive_to_kudu.py` | PySpark trade migration |
| `sql/pyspark/merge_position_master.py` | PySpark position master merge |
| `sql/pyspark/generic_file_ingest.py` | PySpark generic file ingestion |
| `sql/pyspark/upload_equity_price_csv.py` | Upload equity prices via CSV |

### Hive DDL (Legacy)

| File | Purpose |
|------|---------|
| `sql/hive_ddl/05_cis_portfolio_table.sql` | Portfolio table (Hive) |
| `sql/hive_ddl/08_audit_log_table.sql` | Audit log table (Hive) |
| `sql/hive_ddl/02_acl_tables.sql` | ACL tables (Hive) |
| `sql/hive_ddl/create_hive_external_tables.sql` | External tables (Hive) |
| `sql/hive_ddl/create_position_queue.sql` | Position queue (Hive) |
| `sql/hive_ddl/create_settlement_queue.sql` | Settlement queue (Hive) |
| `sql/hive_ddl/export_acl_to_csv.py` | Export ACL data to CSV |
| `sql/hive_ddl/export_reference_to_csv.py` | Export reference data to CSV |

---

## 14. Root-Level Scripts

| File | Purpose |
|------|---------|
| `manage.py` | Django management entry point |
| `test_connection.py` | Impala connection smoke test |
| `test_pyhive.py` | PyHive library test |
| `test_hybrid_connection.py` | Hybrid ORM+Kudu connection test |
| `test_audit_logging.py` | Audit logging smoke test |
| `kudu_load_test.py` | Kudu write load test |
| `create_db.py` | Standalone DB creation script |
| `load_cif_data.py` | Load CIF data into Kudu |
| `load_cif_data_fast.py` | Fast-load CIF data (parallel) |
| `locustfile.py` | Locust load test definition |
| `locust_cml_app.py` | Locust load test for CML deployment |

---

## File Count Summary

| Area | Count |
|------|-------|
| Config | 7 |
| Core | 73 |
| Portfolio | 18 |
| Trade | 53 |
| Market Data | 20 |
| Reference Data | 28 |
| Security | 16 |
| UDF | 24 |
| Lookup | 7 |
| Hive POC (legacy) | 16 |
| **Total Python files** | **~262** |
| HTML Templates | 82 |
| JavaScript files | 8 |
| CSS files | 6 (custom) |
| SQL/DDL files | 96+ |
| **Grand Total** | **~454** |
