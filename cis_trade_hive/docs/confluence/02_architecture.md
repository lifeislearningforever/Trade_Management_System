# System Architecture

> **Audience:** Developer, SA, BA, New Joiner (technical)
> **Read time:** ~10 minutes

---

## Plain English Summary

CIS is a Django web application. When a user clicks a button or submits a form:

1. The **browser** sends a request to Django
2. A **View** handles the HTTP request
3. A **Service** applies business rules
4. A **Repository** talks to the database
5. The **database** (Kudu/Hive via Impala) stores or returns data
6. The result comes back up the chain and renders as HTML

Every layer has one job. This makes it easy to change one part without breaking others.

---

## Layered Architecture

```
┌─────────────────────────────────────────────────┐
│                   BROWSER                        │
│          (HTML, Bootstrap 5, jQuery)             │
└────────────────────┬────────────────────────────┘
                     │ HTTP Request / Response
┌────────────────────▼────────────────────────────┐
│              PRESENTATION LAYER                  │
│         Django Templates  ·  Static Files        │
│          (templates/  ·  static/)                │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                VIEW LAYER                        │
│    Handle HTTP · Check permissions · Route       │
│    (*/views.py  ·  */urls.py)                   │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              SERVICE LAYER                       │
│   Business logic · Validation · Workflow         │
│   (*/services/*.py)                              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            REPOSITORY LAYER                      │
│   SQL queries · Impala connections · Mapping     │
│   (*/repositories/*.py)                          │
└────────────────────┬────────────────────────────┘
                     │ Impala SQL (port 21050)
┌────────────────────▼────────────────────────────┐
│               DATA LAYER                         │
│   Apache Kudu tables  ·  Hive external tables    │
│   (database: gmp_cis)                            │
└─────────────────────────────────────────────────┘
```

---

## Django Apps

Each functional area is its own Django app. They are loosely coupled — they share the connection manager and audit logger, but each owns its own models, services, and repositories.

| App | Purpose | Key tables |
|-----|---------|------------|
| `core` | Auth, audit, ACL, middleware, connection pool | `cis_audit_log`, `cis_user*`, `cis_group*` |
| `portfolio` | Portfolio management + maker-checker | `cis_portfolio`, `cis_portfolio_history` |
| `trade` | Trade lifecycle, position queue | `cis_trade`, `cis_trade_history`, `cis_position_queue` |
| `market_data` | FX rates, equity prices (read from GMP) | `gmp_cis_sta_dly_fx_rates`, `gmp_cis_sta_dly_equity_price` |
| `reference_data` | Currency, country, calendar, corporate actions | `gmp_cis_sta_dly_currency/country/calendar`, `cis_corporate_actions` |
| `security` | Security master data | `cis_security`, `cis_security_history` |
| `udf` | User-defined custom fields | `cis_udf_definition`, `cis_udf_value`, `cis_udf_option` |
| `upload` | File upload and Hive external table creation | `cis_file_upload` |
| `lookup` | Lookup/dropdown tables (broker, GL codes, etc.) | `cis_trade_charge_lut` |

---

## Directory Structure

```
cis_trade_hive/
├── config/                  # Django settings, URLs, WSGI, environments
│   ├── settings.py
│   ├── urls.py
│   └── environments.py      # Per-env Impala/Hive connection config
│
├── core/                    # Foundation — used by all apps
│   ├── audit/               # Kudu-based async audit logging
│   ├── repositories/
│   │   ├── impala_connection.py     # Connection pool (reads)
│   │   ├── hive_connection.py       # Hive ACID writes
│   │   ├── hybrid_connection.py     # Routes to Impala or Hive
│   │   ├── acl_repository.py        # RBAC v1
│   │   └── acl_repository_v2.py     # RBAC v2 (multi-group)
│   ├── services/
│   │   ├── acl_service.py
│   │   └── system_date_service.py
│   └── middleware/
│       ├── permission_middleware.py  # URL-level permission check
│       ├── performance_middleware.py
│       └── audit_middleware.py
│
├── portfolio/               # One app per domain
│   ├── repositories/
│   ├── services/
│   ├── views.py
│   ├── urls.py
│   └── models.py
│
├── trade/                   # Largest app — trade + position + cash flow
│   ├── repositories/
│   │   ├── trade_kudu_repository.py
│   │   ├── position_repository.py
│   │   └── cash_flow_repository.py
│   ├── services/
│   │   ├── position_service.py       # AVP calculation
│   │   ├── settlement_service.py     # EOD settlement
│   │   ├── position_queue_service.py # Async queue worker
│   │   └── cash_flow_service.py
│   ├── management/commands/
│   │   ├── process_settlements.py    # EOD job
│   │   ├── refresh_positions.py
│   │   └── run_trade_event_worker.py
│   └── views.py / views_position.py / views_cash_flow.py
│
├── templates/               # All HTML templates
├── static/                  # CSS, JS, images (no CDN — all local)
├── sql/ddl/                 # Kudu/Hive DDL scripts (numbered sequence)
└── scripts/                 # Spark migration + backup scripts
```

---

## Connection Architecture

### Impala Connection Pool (`core/repositories/impala_connection.py`)

This is the most important file in the codebase. Every app uses it.

```
Django Worker
    │
    ├── ImpalaConnectionManager (singleton)
    │       Pool size: 10 per Gunicorn worker
    │       Auth: NOSASL (LOCAL) / GSSAPI (SIT/UAT/PROD)
    │       Timeout: 60s
    │       Port: 21050
    │
    └── Impala coordinator
            │
            ├── Kudu tablets (CIS-owned tables)
            └── HDFS (GMP Hive external tables)
```

All reads (SELECT) go through Impala. All writes (UPSERT/INSERT/DELETE) on Kudu also go through Impala SQL — Kudu does not have its own SQL interface; Impala provides it.

### Hive Connection (`core/repositories/hive_connection.py`)

Used only for Hive ACID managed tables (ORC format). Port 10000. Separate from Impala.

### Hybrid Connection (`core/repositories/hybrid_connection.py`)

Routes queries: Kudu tables → Impala, Hive managed tables → Hive. Most of the system uses Impala only.

---

## Request Lifecycle (Example: Creating a Trade)

```
1. User submits trade form (POST /trade/create/)
   │
2. permission_middleware.py
   │  → Checks: does user have 'trade-create' permission?
   │  → If no: 403, logged to cis_audit_log
   │
3. trade/views.py → create_trade()
   │  → Validates form data
   │  → Calls TradeService.create_trade(user, form_data)
   │
4. trade/services/trade_service.py
   │  → Validates business rules:
   │      Portfolio must exist and be ACTIVE
   │      Security must exist and be APPROVED/ACTIVE
   │      Counterparty must be active
   │  → Calls TradeKuduRepository.insert_trade(data)
   │
5. trade/repositories/trade_kudu_repository.py
   │  → Builds UPSERT SQL
   │  → Calls ImpalaConnectionManager.execute_write(sql)
   │
6. Impala → Kudu (gmp_cis.cis_trade)
   │  → Row inserted with status='INITIAL'
   │
7. audit_kudu_repository.log_action('CREATE', ...)
   │  → Async write to gmp_cis.cis_audit_log
   │
8. HTTP 302 redirect → trade detail page
```

---

## Key Design Patterns

### Repository Pattern
Every app has a repository layer. The service never builds SQL — only the repository does. This means SQL is always in one place per entity.

### Service Layer
Business rules (validation, workflow transitions, calculations) live in services. Views are thin — they handle HTTP and call services.

### Soft Delete
Nothing is ever physically deleted. Records are marked `is_active = false` or `status = 'INACTIVE'`. This keeps the audit trail intact and allows recovery.

### UPSERT (not INSERT)
Kudu's native write is UPSERT (insert-or-update on primary key). This makes ETL re-runs and data corrections idempotent — running the same operation twice produces the same result.

### Async Audit Logging
Audit writes use an internal queue with 4 background worker threads. The user's request returns immediately; audit writes happen in the background. Queue size: 1,000 entries.

---

## Middleware Stack (Request Order)

```
Request comes in
    │
    ▼ SecurityMiddleware (Django built-in)
    ▼ SessionMiddleware
    ▼ AuthenticationMiddleware
    ▼ PermissionMiddleware      ← CIS: checks URL-level ACL
    ▼ PerformanceMiddleware     ← CIS: records response time
    ▼ View function
    ▼ AuditMiddleware (legacy)  ← CIS: logs request/response
Response goes out
```

---

## For New Joiners: Where to Start Reading

1. `config/settings.py` — understand the environment and installed apps
2. `core/repositories/impala_connection.py` — this is how data gets in/out
3. `portfolio/services/portfolio_service.py` — simplest example of the service pattern
4. `trade/repositories/trade_kudu_repository.py` — most complete repository example
5. `trade/services/position_service.py` — most complex service (AVP calculation)

---

## Technology Versions

| Component | Version |
|-----------|---------|
| Python | 3.12 |
| Django | 5.2.9 |
| impyla (Impala client) | via PyHive 0.7.0 |
| thrift | 0.16.0 |
| Bootstrap | 5.3.3 |
| Gunicorn | production WSGI |
| Apache Kudu | 1.17.0 (CDH parcel) |
| Apache Spark | 3.x (CDH parcel) |
