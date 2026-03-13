# CLAUDE.md - CIS Trade Hive Project Guide

## Project Overview

**CisTrade** is an enterprise-grade Trade Management System built with Django 5.2.9. It manages trade portfolios, market data, and security master data with comprehensive audit logging, role-based access control, and maker-checker workflow (Four-Eyes principle).

## Database Architecture

**All data is stored in Apache Kudu via Impala.** No SQLite or MySQL.

### Environments
| Environment | Impala Host | Notes |
|-------------|-------------|-------|
| **Local Dev** | `localhost:21050` | Docker container with Kudu/Impala |
| **Work/Prod** | Cloudera CML | Cloudera Machine Learning platform |

### Key Kudu Tables (Database: `gmp_cis`)
- `cis_portfolio` - Portfolio master data
- `cis_trade` - Trade records
- `cis_trade_history` - Trade audit trail
- `cis_security_kudu` - Security master data
- `cis_counterparty_kudu` - Counterparty/broker data
- `cis_audit_log` - System audit trail
- `cis_user`, `cis_user_group`, `cis_group_permissions` - ACL tables

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Start Docker Kudu/Impala (local development)
docker start kudu-impala  # or your container name

# Test Impala connection
python manage.py test_hive

# Run development server
python manage.py runserver 0.0.0.0:8000

# Run tests
pytest

# Run with coverage
pytest --cov=core --cov=portfolio --cov=udf --cov=reference_data
```

## Project Structure

```
cis_trade_hive/
├── config/              # Django settings, URLs, WSGI/ASGI
├── core/                # Foundation: auth, audit, ACL, middleware
├── portfolio/           # Portfolio management with maker-checker
├── trade/               # Trade execution and settlement
├── market_data/         # FX rates and market data
├── reference_data/      # Currencies, countries, calendars, counterparties
├── security/            # Security master data (Kudu-based)
├── udf/                 # User-Defined Fields for extensibility
├── templates/           # HTML templates (Bootstrap 5)
├── static/              # CSS, JS, images (local, no CDN)
├── sql/                 # Kudu DDL and sample data
├── kudu_ddl/            # Kudu-specific DDL files
└── docs/                # Project documentation
```

## Key Architecture Decisions

### Kudu/Impala as Primary Database
- All application data stored in Kudu tables
- Accessed via Impala SQL interface using PyHive
- Connection pool: 35 connections via `ImpalaConnectionManager`
- Database: `gmp_cis`

### SOLID Architecture
- **Models:** Data wrappers (e.g., `TradeWrapper` for Kudu dict data)
- **Services:** Business logic (`*_service.py`)
- **Views:** HTTP handling
- **Repositories:** Data access (`*_kudu_repository.py`)

### Four-Eyes Principle (Maker-Checker)
Status flow: `DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → INACTIVE → CLOSED`

## Common Commands

```bash
# Kudu/Impala
python manage.py create_hive_db  # Create Kudu tables
python manage.py test_hive       # Test Impala connection

# Impala Shell (direct access)
impala-shell -i localhost:21050 -d gmp_cis

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
| `config/settings.py` | Django settings, Impala config |
| `core/repositories/impala_connection.py` | Kudu/Impala connection pool manager |
| `core/services/acl_service.py` | Role-based access control |
| `core/middleware/acl_middleware.py` | ACL attachment to requests |
| `core/middleware/audit_middleware.py` | Audit logging |
| `core/audit/audit_kudu_repository.py` | Audit logging to Kudu |
| `trade/repositories/trade_kudu_repository.py` | Trade data access |
| `security/repositories/security_kudu_repository.py` | Security data access |

## Environment Variables

Key settings in `.env`:

```ini
# Django
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=your-secret-key

# Impala/Kudu - Local Docker
IMPALA_HOST=localhost
IMPALA_PORT=21050
IMPALA_DB=gmp_cis
IMPALA_AUTH=NOSASL
IMPALA_TIMEOUT=60
IMPALA_POOL_SIZE=35

# Impala/Kudu - Cloudera CML (work)
# IMPALA_HOST=your-cloudera-host
# IMPALA_PORT=21050
# IMPALA_AUTH=GSSAPI  # or LDAP depending on setup
# IMPALA_USERNAME=your-username
# IMPALA_PASSWORD=your-password
```

## URL Patterns

| App | Base URL | Key Endpoints |
|-----|----------|---------------|
| Core | `/` | `/login/`, `/logout/`, `/dashboard/` |
| Portfolio | `/portfolio/` | `/create/`, `/<name>/`, `/pending-validation/` |
| Trade | `/trade/` | `/create/`, `/<id>/`, `/pending-settlement/` |
| Market Data | `/market-data/` | `/fx-rates/`, `/dashboard/` |
| Reference Data | `/reference-data/` | `/currencies/`, `/countries/`, `/counterparties/` |
| Security | `/security/` | `/`, `/create/`, `/<id>/edit/` |
| UDF | `/udf/` | `/definitions/`, `/values/<entity_type>/` |

## Impala/Kudu Query Patterns

```python
# Using ImpalaConnectionManager
from core.repositories.impala_connection import ImpalaConnectionManager

conn_manager = ImpalaConnectionManager()
with conn_manager.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gmp_cis.cis_trade LIMIT 10")
    results = cursor.fetchall()

# UPSERT for Kudu (not INSERT)
cursor.execute("""
    UPSERT INTO gmp_cis.cis_trade (trade_id, portfolio_short_name, ...)
    VALUES (?, ?, ...)
""", params)
```

## Testing

- **Framework:** pytest + pytest-django
- **Config:** `pytest.ini`, `.coveragerc`
- **Target Coverage:** 95%

### Current Test Coverage (Updated: 2026-03-13)

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| **udf/services/udf_field_service.py** | 92% | 46 | Near Target |
| **trade/repositories/trade_kudu_repository.py** | 86% | 150+ | Good |
| **trade/repositories/trade_validation_repository.py** | 84% | 50+ | Good |
| **trade/views.py** | 84% | 80+ | Good |
| **reference_data/models.py** | 95% | 20+ | Target Met |
| **trade/services** | ~60% | 100+ | In Progress |
| **portfolio** | ~50% | 40+ | Needs Work |
| **security** | ~30% | 20+ | Needs Work |
| **core** | ~20% | 30+ | Needs Work |
| **market_data** | ~15% | 10+ | Needs Work |
| **Overall** | ~30% | 557 | In Progress |

### Test Coverage Improvement Plan

**Priority 1 - Critical Services (Target: 95%)**
- [ ] trade/services/position_service.py (current: ~40%)
- [ ] trade/services/settlement_service.py (current: ~60%)
- [ ] trade/services/position_queue_service.py (current: ~55%)
- [x] udf/services/udf_field_service.py (current: 92%)

**Priority 2 - Repositories (Target: 95%)**
- [x] trade/repositories/trade_kudu_repository.py (current: 86%)
- [x] trade/repositories/trade_validation_repository.py (current: 84%)
- [ ] udf/repositories/udf_field_repository.py (current: ~83%)

**Priority 3 - Views & Integration (Target: 85%)**
- [ ] trade/views.py (current: 84%)
- [ ] portfolio/views.py (current: ~57%)
- [ ] udf/views.py (current: ~19%)

**Priority 4 - Supporting Modules (Target: 80%)**
- [ ] core/audit/* (current: ~0%)
- [ ] core/repositories/impala_connection.py (current: ~22%)
- [ ] market_data/services/* (current: ~17%)

### Running Tests

```bash
# Run all tests with coverage
pytest --cov=core --cov=portfolio --cov=trade --cov=udf --cov=security --cov-report=term-missing

# Run specific module tests
pytest trade/tests/ -v
pytest udf/tests/ -v

# Generate HTML coverage report
pytest --cov=. --cov-report=html
open htmlcov/index.html

# Run specific test file
pytest trade/tests/test_position_service.py -v

# Run with verbose output
pytest -v --tb=short
```

### Known Failing Tests (45 total)
- UDF repository soft_delete/restore tests (need mock updates)
- Trade position/settlement integration tests (need DB mocking)
- Portfolio view tests (need session mocking)
- Core auth tests (need user fixture updates)

## Code Style Guidelines

- Follow PEP 8
- Use type hints where practical
- Services handle business logic, not views
- Repositories handle Kudu data access via Impala
- All database writes should be audited
- Use UPSERT for Kudu writes (not INSERT)
- Four-Eyes workflow for critical operations

## Dependencies

**Core:**
- Django 5.2.9
- PyHive 0.7.0 (Impala connection)
- thrift 0.16.0, thrift-sasl 0.4.3 (required by PyHive)
- djangorestframework 3.16.1

**Testing:**
- pytest 9.0.1
- pytest-cov 7.0.0

**Frontend:**
- Bootstrap 5.3.3 (local)
- jQuery, Select2 (local)

## Audit Logging

All writes are logged to Kudu `cis_audit_log` table with:
- Action type (CREATE, UPDATE, DELETE, APPROVE, REJECT, etc.)
- Old/new values as JSON
- User, IP, timestamp
- Four-Eyes approval status

## Performance Notes

- Impala connection pool: 35 connections
- ACL caching: 300s per user
- Audit logging: async (non-blocking)
- Static files: WhiteNoise compression
- Tested: 500 concurrent users, <1000ms avg response

## AVP (Average Price Position) System

The AVP system tracks portfolio positions with weighted average cost calculations.

### Implementation Phases (All Complete)

| Phase | Service | Lines | Description |
|-------|---------|-------|-------------|
| 1 | `trade/services/position_service.py` | 743 | Basic AVP calculation |
| 2 | `trade/services/settlement_service.py` | 711 | Settlement date logic (T+0, T+1/T+2, backdated) |
| 3 | `trade/services/position_queue_service.py` | 530 | Async background processing |
| 4 | `trade/services/multicurrency_service.py` | 50+ | Multi-currency support |

### AVP Database Tables

| Table | Purpose |
|-------|---------|
| `cis_trade_position` | Core position tracking with versioning |
| `cis_position_queue` | Async processing queue (SLA < 5 min) |
| `cis_settlement_queue` | Future/backdated settlement queue |

**DDL:** `sql/ddl/13_avp_tables_kudu.sql`

### AVP Formulas

```
BUY:  new_avg_cost = (old_total_cost + (qty × price) + charges) / new_qty
SELL: avg_cost unchanged; realized_pnl = (sell_price - avg_cost) × qty
```

- **Precision:** 8 decimal places (DECIMAL(20,8))
- **Charges included:** commission + sec_fee + other_charges

### AVP Calculation Examples

```
# First BUY
Trade: BUY 100 @ $175.00, Commission $10.00
→ Qty: 100, Avg Cost: $175.10, Total: $17,510.00

# Second BUY (adding to position)
Existing: 100 @ $175.10
Trade: BUY 50 @ $180.00, Commission $5.00
→ Qty: 150, Avg Cost: $176.77, Total: $26,515.00

# SELL (partial)
Existing: 150 @ $176.77
Trade: SELL 30 @ $185.00
→ Qty: 120, Avg Cost: $176.77 (unchanged), Realized P&L: $246.90
```

### Settlement Logic

| Scenario | Behavior |
|----------|----------|
| T+0 (today) | Position calculated immediately |
| T+1/T+2 (future) | Queued in `cis_settlement_queue`, processed on settle date |
| Backdated | Allowed (any past date), triggers position recalculation chain |

### Async Processing

- **Architecture:** Queue-based with ThreadPoolExecutor (4 workers)
- **Batch size:** 100 items
- **Poll interval:** 10 seconds
- **Retry:** Max 3 attempts, then dead letter queue
- **SLA:** < 5 minutes from queue to completion

### Multi-Currency Support

- **Local currency:** Security's trading currency
- **Base currency:** Portfolio's base currency
- **FX rate:** Floating (latest rate, not locked to trade date)
- **P&L:** Combined (FX impact included, not separate)

### AVP Validation Rules

| Rule | Implementation |
|------|----------------|
| Trade types | Only BUY and SELL affect position |
| Short selling | Rejected (no overselling) |
| AVP on SELL | Unchanged (uses old average) |
| Settled trade cancel | Not allowed |
| Position status | OPEN or CLOSED |

### AVP Documentation

- `docs/AVP_IMPLEMENTATION_PLAN.md` (657 lines) - Full specifications
- `docs/AVP_USER_GUIDE.md` (549 lines) - User documentation
- `docs/AVP_POSITION_REDESIGN_PLAN.md` (487 lines) - Architecture design
- `docs/AVP_UI_INTEGRATION_GUIDE.md` - UI integration

### AVP Tests

```bash
pytest trade/tests/test_position_service.py      # Phase 1
pytest trade/tests/test_settlement_service.py    # Phase 2
pytest trade/tests/test_position_queue_service.py # Phase 3
pytest trade/tests/test_multicurrency_service.py  # Phase 4
```

## Troubleshooting

**Impala connection fails (Local Docker):**
```bash
# Check if Docker container is running
docker ps | grep kudu

# Start container if stopped
docker start kudu-impala

# Test connection
python manage.py test_hive

# Direct impala-shell test
impala-shell -i localhost:21050 -q "SHOW DATABASES"
```

**Impala connection fails (Cloudera CML):**
- Verify Kerberos ticket: `klist`
- Check IMPALA_HOST points to correct Cloudera coordinator
- Verify IMPALA_AUTH matches your Cloudera auth method (GSSAPI/LDAP)

**Permission denied:**
- Check ACL tables in Kudu (`cis_user`, `cis_user_group`, `cis_group_permissions`)
- Verify user group assignments
- Query: `SELECT * FROM gmp_cis.cis_user WHERE username = 'your-user'`

**Kudu table doesn't exist:**
```bash
# Create tables
python manage.py create_hive_db

# Or run DDL manually
impala-shell -i localhost:21050 -f sql/ddl/cis_trade_kudu.sql
```
