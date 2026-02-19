# CLAUDE.md - CIS Trade Hive Project Guide

## Project Overview

**CisTrade** is an enterprise-grade Trade Management System built with Django 5.2.9. It manages trade portfolios, market data, and security master data with comprehensive audit logging, role-based access control, and maker-checker workflow (Four-Eyes principle).

## Database Architecture

**All data is stored in Apache Hive Managed Tables with ORC file format and ACID transaction support.**

### Storage Technology
- **Hive Managed Tables**: Full ACID support (INSERT, UPDATE, DELETE)
- **ORC File Format**: Columnar storage with SNAPPY compression
- **Bucketing**: All tables use CLUSTERED BY with 4 buckets for optimal performance
- **Execution Engine**: MapReduce for transactional operations

> **Important:** See [docs/HIVE_ACID_LIMITATIONS.md](docs/HIVE_ACID_LIMITATIONS.md) for known limitations (GROUP BY, DISTINCT, ORDER BY fail on ACID tables) and workarounds.

### Environments
| Environment | Hive Host | Port | Notes |
|-------------|-----------|------|-------|
| **Local Dev** | `localhost` | `10000` | HiveServer2 with MapReduce |
| **Work/Prod** | Cloudera | `10000` | Cloudera Hive deployment |

### Key Hive Tables (Database: `gmp_cis`)

**Core Tables:**
- `cis_user` - User accounts
- `cis_user_group` - User groups/roles
- `cis_group_permissions` - Permission assignments
- `cis_user_group_membership` - User-group relationships
- `cis_audit_log` - System audit trail

**Business Tables:**
- `cis_portfolio` - Portfolio master data
- `cis_portfolio_history` - Portfolio audit trail
- `cis_trade` - Trade records
- `cis_trade_history` - Trade audit trail
- `cis_trade_note` - Trade annotations
- `cis_trade_position` - Position tracking

**Security & Market Data:**
- `cis_security` - Security master data
- `cis_security_history` - Security audit trail
- `cis_equity_price` - Equity price history
- `cis_fx_rate` - FX rate history

**Reference Data:**
- `cis_counterparty` - Counterparty/broker data
- `cis_currency` - Currency definitions
- `cis_country` - Country definitions

**Extensibility:**
- `cis_udf_field` - User-defined field definitions
- `cis_udf_value` - User-defined field values
- `cis_sequence` - ID sequence generator
- `cis_help_content` - Help documentation

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Start HiveServer2 (if not running)
hiveserver2 &

# Test Hive connection
python manage.py test_hive

# Create all Hive tables
beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira' \
  -f sql/hive_ddl/create_all_tables.sql

# Run development server
python manage.py runserver 0.0.0.0:8000

# Run tests
pytest

# Run with coverage
pytest --cov=core --cov=portfolio --cov=trade --cov=security --cov=udf --cov=reference_data
```

## Project Structure

```
cis_trade_hive/
├── config/              # Django settings, URLs, WSGI/ASGI
├── core/                # Foundation: auth, audit, ACL, middleware
│   ├── repositories/
│   │   ├── hive_connection.py       # Hive connection pool manager
│   │   ├── hive_base_repository.py  # Abstract base repository
│   │   └── acl_repository.py        # ACL data access
│   └── audit/
│       └── audit_hive_repository.py # Audit logging
├── portfolio/           # Portfolio management with maker-checker
│   └── repositories/
│       └── portfolio_hive_repository.py
├── trade/               # Trade execution and settlement
│   └── repositories/
│       └── trade_hive_repository.py
├── market_data/         # FX rates and equity prices
│   └── repositories/
│       └── market_data_hive_repository.py
├── reference_data/      # Currencies, countries, counterparties
│   └── repositories/
│       └── reference_data_hive_repository.py
├── security/            # Security master data
│   └── repositories/
│       └── security_hive_repository.py
├── udf/                 # User-Defined Fields for extensibility
│   └── repositories/
│       └── udf_hive_repository.py
├── templates/           # HTML templates (Bootstrap 5)
├── static/              # CSS, JS, images (local, no CDN)
├── sql/
│   └── hive_ddl/        # Hive DDL scripts
│       └── create_all_tables.sql
└── docs/                # Project documentation
```

## Key Architecture Decisions

### Hive Managed Tables with ORC + ACID
- All application data stored in Hive managed tables
- ORC file format with SNAPPY compression
- Full ACID transaction support (INSERT, UPDATE, DELETE)
- MapReduce execution engine for transactional operations
- Connection pool via `HiveConnectionManager`
- Database: `gmp_cis`

### SOLID Architecture
- **Models:** Data wrappers (e.g., `TradeWrapper` for dict data)
- **Services:** Business logic (`*_service.py`)
- **Views:** HTTP handling
- **Repositories:** Data access (`*_hive_repository.py`)

### Repository Pattern
All repositories inherit from `HiveBaseRepository`:
```python
class HiveBaseRepository(ABC):
    @property
    @abstractmethod
    def table_name(self) -> str: pass

    @property
    @abstractmethod
    def primary_key(self) -> str: pass

    @property
    @abstractmethod
    def columns(self) -> List[str]: pass
```

### Four-Eyes Principle (Maker-Checker)
Status flow: `DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → INACTIVE → CLOSED`

## Common Commands

```bash
# Hive Operations
beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira'

# Create tables
beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira' \
  -f sql/hive_ddl/create_all_tables.sql

# Test Hive connection
python manage.py test_hive

# Testing
pytest                           # Run all tests
pytest core/tests/               # Run specific module
pytest -v --tb=short             # Verbose with short traceback

# Static files
python manage.py collectstatic --noinput

# Production
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 4
```

## Key Files

| File | Purpose |
|------|---------|
| `config/settings.py` | Django settings, Hive config |
| `core/repositories/hive_connection.py` | Hive connection pool manager |
| `core/repositories/hive_base_repository.py` | Abstract base repository |
| `core/repositories/acl_repository.py` | ACL data access |
| `core/services/acl_service.py` | Role-based access control |
| `core/middleware/acl_middleware.py` | ACL attachment to requests |
| `core/middleware/audit_middleware.py` | Audit logging middleware |
| `core/audit/audit_hive_repository.py` | Audit logging to Hive |
| `portfolio/repositories/portfolio_hive_repository.py` | Portfolio data access |
| `trade/repositories/trade_hive_repository.py` | Trade data access |
| `security/repositories/security_hive_repository.py` | Security data access |
| `market_data/repositories/market_data_hive_repository.py` | Market data access |
| `reference_data/repositories/reference_data_hive_repository.py` | Reference data access |
| `udf/repositories/udf_hive_repository.py` | UDF data access |
| `sql/hive_ddl/create_all_tables.sql` | DDL for all 22 tables |

## Environment Variables

Key settings in `.env`:

```ini
# Django
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=your-secret-key

# Hive - Local Development
HIVE_HOST=localhost
HIVE_PORT=10000
HIVE_DB=gmp_cis
HIVE_AUTH=NONE
HIVE_USERNAME=prakashhosalli
HIVE_PASSWORD=0987!Adhira
HIVE_POOL_SIZE=10
HIVE_TIMEOUT=120

# Hive - Cloudera (work/prod)
# HIVE_HOST=your-cloudera-host
# HIVE_PORT=10000
# HIVE_AUTH=LDAP  # or KERBEROS
# HIVE_USERNAME=your-username
# HIVE_PASSWORD=your-password
```

## URL Patterns

| App | Base URL | Key Endpoints |
|-----|----------|---------------|
| Core | `/` | `/login/`, `/logout/`, `/dashboard/` |
| Portfolio | `/portfolio/` | `/create/`, `/<name>/`, `/pending-validation/` |
| Trade | `/trade/` | `/create/`, `/<id>/`, `/pending-settlement/` |
| Market Data | `/market-data/` | `/fx-rates/`, `/equity-prices/`, `/dashboard/` |
| Reference Data | `/reference-data/` | `/currencies/`, `/countries/`, `/counterparties/` |
| Security | `/security/` | `/`, `/create/`, `/<id>/edit/` |
| UDF | `/udf/` | `/definitions/`, `/values/<entity_type>/` |

## Hive Query Patterns

```python
# Using HiveConnectionManager
from core.repositories.hive_connection import hive_manager

# Execute query
results = hive_manager.execute_query(
    "SELECT * FROM cis_trade WHERE deleted_at IS NULL LIMIT 10",
    database='gmp_cis'
)

# Execute write (INSERT/UPDATE/DELETE)
hive_manager.execute_write(
    "INSERT INTO cis_trade (trade_id, ...) VALUES ('TRD001', ...)",
    database='gmp_cis'
)

# Using repository pattern
from trade.repositories.trade_hive_repository import trade_hive_repository

# Create
trade_id = trade_hive_repository.create_trade(trade_data, created_by='user1')

# Read
trade = trade_hive_repository.find_by_id(trade_id)

# Update
trade_hive_repository.update(trade_id, {'status': 'APPROVED'})

# Soft Delete
trade_hive_repository.soft_delete(trade_id, deleted_by='user1')
```

## Testing

- **Framework:** pytest + pytest-django
- **Config:** `pytest.ini`, `.coveragerc`

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## Code Style Guidelines

- Follow PEP 8
- Use type hints where practical
- Services handle business logic, not views
- Repositories handle Hive data access
- All database writes should be audited
- Use soft delete pattern (`deleted_at` timestamp)
- Four-Eyes workflow for critical operations
- All repositories inherit from `HiveBaseRepository`

## Dependencies

**Core:**
- Django 5.2.9
- PyHive 0.7.0 (HiveServer2 connection)
- thrift 0.16.0, thrift-sasl 0.4.3 (required by PyHive)
- djangorestframework 3.16.1

**Testing:**
- pytest 9.0.1
- pytest-cov 7.0.0

**Frontend:**
- Bootstrap 5.3.3 (local)
- jQuery, Select2 (local)

## Audit Logging

All writes are logged to Hive `cis_audit_log` table with:
- Action type (CREATE, UPDATE, DELETE, APPROVE, REJECT, etc.)
- Old/new values as JSON
- User, IP, timestamp
- Four-Eyes approval status

## Performance Notes

- Hive connection pool: 10 connections
- ACL caching: 300s per user
- Audit logging: async (non-blocking)
- Static files: WhiteNoise compression
- ORC with SNAPPY compression for storage efficiency
- Bucketed tables for optimal query performance

## Hive ACID Configuration

Required Hive settings for ACID support:
```sql
SET hive.support.concurrency=true;
SET hive.enforce.bucketing=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.compactor.initiator.on=true;
SET hive.compactor.worker.threads=1;
SET hive.execution.engine=mr;  -- MapReduce for transactional ops
```

## Troubleshooting

**Hive connection fails:**
```bash
# Check if HiveServer2 is running
pgrep -f HiveServer2

# Start HiveServer2 if not running
hiveserver2 &

# Test connection with beeline
beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira' \
  -e "SHOW DATABASES"
```

**ACID operations fail:**
```bash
# Verify table is transactional
beeline -e "DESCRIBE FORMATTED gmp_cis.cis_trade" | grep transactional

# Set execution engine to MapReduce
SET hive.execution.engine=mr;
```

**Permission denied:**
- Check ACL tables in Hive (`cis_user`, `cis_user_group`, `cis_group_permissions`)
- Verify user group assignments
- Query: `SELECT * FROM gmp_cis.cis_user WHERE username = 'your-user'`

**Table doesn't exist:**
```bash
# Create all tables
beeline -u "jdbc:hive2://localhost:10000" -n prakashhosalli -p '0987!Adhira' \
  -f sql/hive_ddl/create_all_tables.sql

# Verify tables exist
beeline -e "SHOW TABLES IN gmp_cis"
```

## Migration from Kudu/Impala

This branch (`hive-managed-tables`) migrated from Kudu/Impala to Hive Managed Tables:

| Component | Old (Kudu) | New (Hive) |
|-----------|------------|------------|
| Connection | `ImpalaConnectionManager` | `HiveConnectionManager` |
| Port | 21050 | 10000 |
| Write Pattern | UPSERT | INSERT/UPDATE/DELETE |
| Storage | Kudu | ORC with SNAPPY |
| Transactions | Limited | Full ACID |
| Repositories | `*_kudu_repository.py` | `*_hive_repository.py` |

Backward compatibility aliases are provided:
```python
from core.repositories.hive_connection import hive_manager
# Also available as:
from core.repositories.hive_connection import impala_manager  # alias
```

## CML (Cloudera Machine Learning) Deployment

### Deploying as CML Project Application

**Entry Point:** `config/cml_app.py`

1. **Create CML Project:**
   - Import this repository into CML as a new project
   - Ensure Python 3.10+ runtime is selected

2. **Set Environment Variables in CML Project Settings:**
   ```
   HIVE_HOST=your-cloudera-hive-host
   HIVE_PORT=10000
   HIVE_DB=gmp_cis
   HIVE_AUTH=LDAP  # or KERBEROS
   HIVE_USERNAME=your-username
   HIVE_PASSWORD=your-password
   DJANGO_SECRET_KEY=your-production-secret-key
   DJANGO_DEBUG=false
   DJANGO_ALLOWED_HOSTS=*.your-cml-domain.com
   ```

3. **Create Application:**
   - Go to **Applications** → **New Application**
   - **Name:** CIS Trade Hive
   - **Subdomain:** cis-trade-hive
   - **Script:** `config/cml_app.py`
   - **Resource Profile:** 2 vCPU / 4 GB Memory (minimum)

4. **Optional Gunicorn Settings (Environment Variables):**
   ```
   GUNICORN_WORKERS=4
   GUNICORN_THREADS=4
   GUNICORN_TIMEOUT=120
   ```

### What cml_app.py Does

1. Creates/activates virtual environment (`.venv`)
2. Installs dependencies from `requirements.txt`
3. Configures Django for CML (allowed hosts, debug mode)
4. Collects static files
5. Runs database migrations (if applicable)
6. Starts Gunicorn WSGI server on `CDSW_APP_PORT`

### CML Environment Variables (Auto-Set by CML)

| Variable | Description |
|----------|-------------|
| `CDSW_APP_PORT` | Port assigned to the application |
| `CDSW_DOMAIN` | CML domain for allowed hosts |

## Performance Benchmarking

### Quick Start

```bash
# Run quick benchmark (50 users, 2 minutes)
./run_benchmark.sh quick

# Run standard benchmark (500 users, 10 minutes)
./run_benchmark.sh standard

# Run stress test (1000 users, 5 minutes)
./run_benchmark.sh stress

# Run Locust Web UI for real-time monitoring
locust --host=http://localhost:8000
# Open http://localhost:8089 in browser
```

### Benchmark Scenarios

| Scenario | Users | Duration | Spawn Rate | Use Case |
|----------|-------|----------|------------|----------|
| `quick` | 50 | 2m | 5/s | Post-deployment sanity check |
| `standard` | 500 | 10m | 10/s | Regular performance validation |
| `stress` | 1000 | 5m | 50/s | Find breaking point |
| `soak` | 200 | 2h | 5/s | Detect memory leaks |

### User Profiles (locustfile.py)

| User Type | Weight | Description |
|-----------|--------|-------------|
| TradeUser | 25% | Trade CRUD operations |
| PortfolioUser | 15% | Portfolio management |
| SecurityUser | 15% | Security master data |
| EquityPriceUser | 10% | Equity price updates |
| FXRateUser | 10% | FX rate updates |
| CounterpartyUser | 10% | Counterparty management |
| ReferenceDataUser | 5% | Reference data browsing |
| UDFUser | 5% | UDF configuration |
| DashboardUser | 5% | Dashboard monitoring |

### Performance Targets (500 Users)

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Median Response | <300ms | 300-500ms | >500ms |
| 95th Percentile | <2000ms | 2000-3000ms | >3000ms |
| Requests/sec | >100 | 50-100 | <50 |
| Error Rate | 0% | <0.5% | >1% |

### Latest Benchmark Results (2026-02-18)

Quick test (50 users, 2 minutes):

| Endpoint | Requests | Median | Avg | 95th %ile | RPS |
|----------|----------|--------|-----|-----------|-----|
| Trade List | 55 | 12ms | 18ms | 37ms | 0.46 |
| Portfolio List | 35 | 9ms | 12ms | 23ms | 0.30 |
| Security List | 28 | 4ms | 8ms | 14ms | 0.24 |
| Equity Price List | 20 | 6ms | 10ms | 63ms | 0.17 |
| FX Rate List | 25 | 5ms | 7ms | 14ms | 0.21 |
| Dashboard | 9 | 5ms | 6ms | 15ms | 0.08 |
| **Aggregated** | 1505 | 6ms | 39ms | 27ms | 12.69 |

### Results Location

```
benchmark_results/
├── quick_[timestamp]/
│   ├── report.html         # Visual HTML report
│   ├── stats.csv           # Request statistics
│   ├── stats_history.csv   # Time-series data
│   └── failures.csv        # Error details
```

### Documentation

- Full guide: `BENCHMARKING.md`
- Locust config: `locustfile.py`
- Benchmark script: `run_benchmark.sh`

## Feature Migration Status

This branch (`hive-managed-tables`) contains all functionality migrated from the `cis_trade_hive` branch.

### Migration Summary

| Module | Features | Status |
|--------|----------|--------|
| **Core** | Auth, ACL, Audit, Connection Pool | ✅ Complete |
| **Portfolio** | CRUD + Maker-Checker Workflow | ✅ Complete |
| **Trade** | CRUD + Workflow + Positions | ✅ Complete |
| **Security** | CRUD + Workflow | ✅ Complete |
| **Market Data** | FX Rates + Equity Prices + History | ✅ Complete |
| **Reference Data** | Currency, Country, Counterparty | ✅ Complete |
| **UDF** | Field Definitions + Values | ✅ Complete |
| **Lookup** | Configuration Tables | ✅ Complete |

### Database Tables (24 Total)

| Category | Tables |
|----------|--------|
| Core/ACL | cis_user, cis_user_group, cis_group_permissions, cis_user_group_membership |
| Audit | cis_audit_log |
| Portfolio | cis_portfolio, cis_portfolio_history |
| Trade | cis_trade, cis_trade_history, cis_trade_note, cis_trade_position |
| Security | cis_security, cis_security_history |
| Market Data | cis_equity_price, cis_equity_price_history, cis_fx_rate, cis_fx_rate_history |
| Reference | cis_counterparty, cis_currency, cis_country |
| UDF | cis_udf_field, cis_udf_value |
| Helper | cis_sequence, cis_help_content |

### Key Architectural Changes from Kudu

| Aspect | Old (Kudu) | New (Hive) |
|--------|------------|------------|
| Database | Kudu | Hive Managed Tables |
| Port | 21050 | 10000 |
| Format | Kudu native | ORC + SNAPPY |
| Transactions | UPSERT only | Full ACID |
| Connection | ImpalaConnectionManager | HiveConnectionManager |

### Full Documentation

See [docs/FUNCTIONALITY_COMPARISON.md](docs/FUNCTIONALITY_COMPARISON.md) for:
- Complete feature inventory
- API endpoints
- Database schema details
- Workflow diagrams
- Testing checklist
