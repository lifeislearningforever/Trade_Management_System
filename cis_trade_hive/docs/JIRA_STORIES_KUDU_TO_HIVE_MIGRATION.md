# Jira Stories: Kudu to Hive Managed Tables Migration

**Epic:** CIS Trade Hive - Kudu to Hive ACID Migration
**Project:** CIS Trade Management System
**Created:** 2026-02-22
**Target Release:** Q1 2026

---

## Executive Summary

Migration of CIS Trade Hive application from Apache Kudu to Hive Managed Tables with ORC format and full ACID transaction support. This migration addresses infrastructure constraints and provides better audit capabilities, true ACID transactions, and simplified operations.

### Migration Scope

| Category | Count | Description |
|----------|-------|-------------|
| **Database Tables** | 24 | Full schema migration |
| **Repository Classes** | 12 | Kudu → Hive repository migration |
| **DDL Scripts** | 30+ | New Hive DDL scripts |
| **Connection Layer** | 2 | HybridConnectionManager + REST Proxy |
| **Django Apps** | 10 | All apps affected |

---

## Epic: CIS-EPIC-001 - Kudu to Hive ACID Migration

**Summary:** Migrate CIS Trade Hive from Kudu/Impala to Hive Managed Tables with ORC + ACID
**Priority:** High
**Labels:** migration, database, infrastructure
**Components:** Core, Portfolio, Trade, Security, Market Data, Reference Data, UDF

---

## Sprint 1: Infrastructure & Foundation (2 weeks)

### Story CIS-101: Set Up Hive ACID Infrastructure

**Summary:** Configure HiveServer2 with ACID transaction support
**Type:** Story
**Priority:** Critical
**Story Points:** 8
**Assignee:** Infrastructure Team

**Description:**
Configure HiveServer2 cluster for full ACID transaction support required by CIS Trade Hive application.

**Acceptance Criteria:**
- [ ] HiveServer2 configured with ACID support enabled
- [ ] Transaction manager set to `DbTxnManager`
- [ ] Compaction initiator and worker threads configured
- [ ] MapReduce execution engine enabled for transactional tables
- [ ] Connection verified from development environment
- [ ] Health check endpoint responding

**Technical Tasks:**
1. Configure hive-site.xml with ACID settings:
   ```sql
   SET hive.support.concurrency=true;
   SET hive.enforce.bucketing=true;
   SET hive.exec.dynamic.partition.mode=nonstrict;
   SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
   SET hive.compactor.initiator.on=true;
   SET hive.compactor.worker.threads=1;
   SET hive.execution.engine=mr;
   ```
2. Verify ACID operations (INSERT, UPDATE, DELETE)
3. Document connection parameters for each environment

---

### Story CIS-102: Create Hive Database and Core Tables DDL

**Summary:** Create DDL scripts for all 24 Hive managed tables
**Type:** Story
**Priority:** Critical
**Story Points:** 5
**Assignee:** Database Team

**Description:**
Create Hive DDL scripts for all tables with ORC format, SNAPPY compression, and ACID transaction support.

**Acceptance Criteria:**
- [ ] All 24 tables created with proper schema
- [ ] Tables use CLUSTERED BY with appropriate bucket counts
- [ ] ORC format with SNAPPY compression configured
- [ ] `transactional=true` property set on all tables
- [ ] Soft delete pattern implemented (deleted_at column)
- [ ] DDL script validated in dev environment

**Tables to Create:**

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

**Linked File:** `sql/hive_ddl/create_all_tables.sql`

---

### Story CIS-103: Implement HiveConnectionManager

**Summary:** Create connection pool manager for Hive with thread-safe singleton pattern
**Type:** Story
**Priority:** Critical
**Story Points:** 8
**Assignee:** Backend Developer

**Description:**
Implement `HiveConnectionManager` class to replace `ImpalaConnectionManager` for Hive ACID operations.

**Acceptance Criteria:**
- [ ] Thread-safe singleton connection pool implemented
- [ ] Connection validation and auto-recycling
- [ ] Support for both NONE auth (dev) and KERBEROS/LDAP (prod)
- [ ] Query timeout configuration
- [ ] Async write support for audit logging
- [ ] Query caching with TTL
- [ ] Environment-based configuration

**Technical Details:**
```python
# Key configuration
HIVE_CONFIG = {
    'HOST': os.environ.get('HIVE_HOST', 'localhost'),
    'PORT': int(os.environ.get('HIVE_PORT', '10000')),
    'DATABASE': 'gmp_cis',
    'AUTH': os.environ.get('HIVE_AUTH', 'NONE'),
    'POOL_SIZE': 20,
    'TIMEOUT': 120,
}
```

**Linked File:** `core/repositories/hive_connection.py`

---

### Story CIS-104: Implement HybridConnectionManager for Read/Write Separation

**Summary:** Create hybrid connection manager that uses Impala for reads and Hive for writes
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Implement a hybrid connection manager that routes:
- **READS** → Impala (fast, sub-second)
- **WRITES** → Hive via REST Proxy (ACID compliant)

**Acceptance Criteria:**
- [ ] Read queries routed to Impala (port 21050)
- [ ] Write queries routed to Hive REST Proxy
- [ ] Fallback mechanism if Impala unavailable
- [ ] Connection mode configurable via environment variable
- [ ] Logging for connection routing decisions

**Linked File:** `core/repositories/hybrid_connection.py`

---

### Story CIS-105: Deploy Hive REST Proxy on Edge Node

**Summary:** Deploy Flask-based REST proxy for Hive ACID operations from CML
**Type:** Story
**Priority:** Critical
**Story Points:** 8
**Assignee:** DevOps Team

**Description:**
Deploy REST proxy service on edge node to enable Hive ACID operations from CML Docker containers (which cannot directly connect to HiveServer2 due to glibc/SASL issues).

**Acceptance Criteria:**
- [ ] Flask REST proxy deployed as systemd service
- [ ] PyHive connection pool configured for performance
- [ ] Tez execution engine configured (faster than MapReduce)
- [ ] API key authentication implemented
- [ ] Health check endpoint working
- [ ] Kerberos ticket auto-renewal configured
- [ ] Gunicorn with 4 workers deployed

**Environments:**

| Environment | Edge Node | Port | API Key |
|-------------|-----------|------|---------|
| PROD | lxmrwpsgv0e1.sg.uobnet.com | 5000 | prod-xxx |
| UAT | lxmrwtsgv0e1.sg.uobnet.com | 5000 | uat-xxx |
| DR | lxmrwdsgv0e1.sg.uobnet.com | 5000 | dr-xxx |

**API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/query` | POST | Execute SELECT |
| `/execute` | POST | Execute INSERT/UPDATE/DELETE |
| `/insert/<table>` | POST | Dynamic INSERT |
| `/update/<table>` | POST | Dynamic UPDATE |
| `/delete/<table>` | POST | Dynamic DELETE |

**Linked Files:** `hive_proxy/app_v2.py`, `hive_proxy/app_v3.py`

---

## Sprint 2: Repository Layer Migration (2 weeks)

### Story CIS-201: Create HiveBaseRepository Abstract Class

**Summary:** Implement abstract base repository for all Hive table operations
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Create abstract base repository class that provides common CRUD operations for Hive ACID tables with soft delete support.

**Acceptance Criteria:**
- [ ] Abstract properties: `table_name`, `primary_key`, `columns`
- [ ] `find_all()` with include_deleted option
- [ ] `find_by_id()` with soft delete filter
- [ ] `create()` with audit field population
- [ ] `update()` with automatic updated_at
- [ ] `soft_delete()` setting deleted_at timestamp
- [ ] `restore()` clearing deleted_at
- [ ] `hard_delete()` for permanent removal
- [ ] Proxy mode support for CML environments

**Linked File:** `core/repositories/hive_base_repository.py` (new), `hive_poc/repositories/hive_base_repository.py` (existing)

---

### Story CIS-202: Migrate Portfolio Repository to Hive

**Summary:** Migrate PortfolioRepository from Kudu to Hive ACID
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Migrate portfolio repository to use Hive managed tables with full CRUD and maker-checker workflow support.

**Acceptance Criteria:**
- [ ] `PortfolioHiveRepository` extends `HiveBaseRepository`
- [ ] CRUD operations working with Hive ACID
- [ ] Maker-checker workflow statuses preserved
- [ ] Portfolio history tracking implemented
- [ ] Search by code, status, type, manager working
- [ ] Dropdown helper methods implemented
- [ ] Unit tests passing

**Methods to Implement:**
- `find_by_code()`
- `find_by_status()`
- `find_by_type()`
- `find_by_manager()`
- `search()`
- `get_portfolio_dropdown()`
- `update_status()`

**Linked Files:**
- Old: `portfolio/repositories/portfolio_kudu_repository.py`
- New: `portfolio/repositories/portfolio_hive_repository.py`

---

### Story CIS-203: Migrate Trade Repository to Hive

**Summary:** Migrate TradeRepository from Kudu to Hive ACID
**Type:** Story
**Priority:** High
**Story Points:** 8
**Assignee:** Backend Developer

**Description:**
Migrate trade repository including trade history, notes, and position tracking.

**Acceptance Criteria:**
- [ ] `TradeHiveRepository` extends `HiveBaseRepository`
- [ ] Trade CRUD operations working
- [ ] Trade workflow (DRAFT → APPROVED → SETTLED)
- [ ] Trade history logging
- [ ] Trade notes CRUD
- [ ] Position tracking integration
- [ ] Validation methods working
- [ ] Unit tests passing

**Tables:**
- cis_trade
- cis_trade_history
- cis_trade_note
- cis_trade_position

**Linked Files:**
- Old: `trade/repositories/trade_kudu_repository.py`
- New: `trade/repositories/trade_hive_repository.py`

---

### Story CIS-204: Migrate Security Repository to Hive

**Summary:** Migrate SecurityRepository from Kudu to Hive ACID
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Migrate security master data repository with identifier lookups.

**Acceptance Criteria:**
- [ ] `SecurityHiveRepository` extends `HiveBaseRepository`
- [ ] Security CRUD operations working
- [ ] Maker-checker workflow supported
- [ ] Security history tracking
- [ ] Lookup by ISIN, CUSIP, SEDOL, Ticker
- [ ] Unit tests passing

**Linked Files:**
- Old: `security/repositories/security_kudu_repository.py`
- New: `security/repositories/security_hive_repository.py`

---

### Story CIS-205: Migrate Market Data Repositories to Hive

**Summary:** Migrate EquityPrice and FXRate repositories from Kudu to Hive ACID
**Type:** Story
**Priority:** Medium
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Migrate market data repositories including equity prices, FX rates, and their history tables.

**Acceptance Criteria:**
- [ ] `EquityPriceHiveRepository` extends `HiveBaseRepository`
- [ ] `FXRateHiveRepository` extends `HiveBaseRepository`
- [ ] Price/Rate CRUD operations working
- [ ] History tables populated on changes
- [ ] Latest price/rate lookup methods
- [ ] Date range queries working
- [ ] Bulk import methods working
- [ ] Unit tests passing

**Tables:**
- cis_equity_price, cis_equity_price_history
- cis_fx_rate, cis_fx_rate_history

**Linked Files:**
- Old: `market_data/repositories/market_data_kudu_repository.py`
- New: `market_data/repositories/equity_price_hive_repository.py`, `market_data/repositories/fx_rate_hive_repository.py`

---

### Story CIS-206: Migrate Reference Data Repository to Hive

**Summary:** Migrate ReferenceDataRepository (Currency, Country, Counterparty) from Kudu to Hive
**Type:** Story
**Priority:** Medium
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Migrate reference data repositories for counterparty, currency, and country tables.

**Acceptance Criteria:**
- [ ] `ReferenceDataHiveRepository` extends `HiveBaseRepository`
- [ ] Counterparty CRUD operations working
- [ ] Currency lookup methods working
- [ ] Country lookup methods working
- [ ] Counterparty type filtering (BROKER, CUSTODIAN, COUNTERPARTY)
- [ ] CSV export working
- [ ] Unit tests passing

**Tables:**
- cis_counterparty
- cis_currency
- cis_country

**Linked File:** `reference_data/repositories/reference_data_hive_repository.py`

---

### Story CIS-207: Migrate UDF Repository to Hive

**Summary:** Migrate UDF (User-Defined Fields) repository from Kudu to Hive
**Type:** Story
**Priority:** Medium
**Story Points:** 3
**Assignee:** Backend Developer

**Description:**
Migrate UDF repository for field definitions and values.

**Acceptance Criteria:**
- [ ] `UDFHiveRepository` extends `HiveBaseRepository`
- [ ] Field definition CRUD working
- [ ] Field value CRUD working
- [ ] Entity type filtering (PORTFOLIO, TRADE, SECURITY, COUNTERPARTY)
- [ ] Field type support (TEXT, NUMBER, DATE, SELECT, etc.)
- [ ] Unit tests passing

**Tables:**
- cis_udf_field
- cis_udf_value

**Linked File:** `udf/repositories/udf_hive_repository.py`

---

### Story CIS-208: Migrate Audit Repository to Hive

**Summary:** Migrate AuditRepository from Kudu to Hive for audit logging
**Type:** Story
**Priority:** High
**Story Points:** 3
**Assignee:** Backend Developer

**Description:**
Migrate audit logging repository with async write support.

**Acceptance Criteria:**
- [ ] `AuditHiveRepository` extends `HiveBaseRepository`
- [ ] Async audit write for non-blocking UI
- [ ] Action types: CREATE, UPDATE, DELETE, APPROVE, REJECT
- [ ] Old/new value tracking as JSON
- [ ] User, IP, timestamp captured
- [ ] High-volume insert handling
- [ ] Unit tests passing

**Linked Files:**
- Old: `core/audit/audit_kudu_repository.py`
- New: `core/audit/audit_hive_repository.py`

---

### Story CIS-209: Migrate Lookup Repository to Hive

**Summary:** Migrate LookupRepository for configuration tables
**Type:** Story
**Priority:** Low
**Story Points:** 2
**Assignee:** Backend Developer

**Description:**
Migrate lookup/configuration repository.

**Acceptance Criteria:**
- [ ] `LookupHiveRepository` extends `HiveBaseRepository`
- [ ] Lookup table CRUD working
- [ ] Configuration caching implemented
- [ ] Unit tests passing

**Linked Files:**
- Old: `lookup/repositories/lookup_kudu_repository.py`
- New: `lookup/repositories/lookup_hive_repository.py`

---

## Sprint 3: Data Migration (1 week)

### Story CIS-301: Export Data from Kudu Tables

**Summary:** Export all existing data from Kudu tables to staging area
**Type:** Story
**Priority:** Critical
**Story Points:** 5
**Assignee:** Data Engineering

**Description:**
Export all data from existing Kudu tables using Impala for the migration.

**Acceptance Criteria:**
- [ ] All 24 tables exported to HDFS staging
- [ ] Data format: Parquet or CSV
- [ ] Row counts documented
- [ ] Data checksums generated for validation
- [ ] Export scripts versioned in git

**Tables to Export:**

| Category | Tables | Est. Rows |
|----------|--------|-----------|
| Core/ACL | 4 tables | ~100 |
| Portfolio | 2 tables | ~500 |
| Trade | 4 tables | ~10,000 |
| Security | 2 tables | ~5,000 |
| Market Data | 4 tables | ~100,000 |
| Reference | 3 tables | ~1,000 |
| UDF | 2 tables | ~200 |
| Helper | 2 tables | ~50 |

---

### Story CIS-302: Transform and Load Data to Hive Tables

**Summary:** Load exported data into Hive managed tables
**Type:** Story
**Priority:** Critical
**Story Points:** 5
**Assignee:** Data Engineering

**Description:**
Transform and load data from staging into Hive ACID tables.

**Acceptance Criteria:**
- [ ] Data transformed to match Hive schema
- [ ] All tables loaded successfully
- [ ] Row count validation passed
- [ ] Data integrity verified (checksums)
- [ ] deleted_at column populated correctly
- [ ] Audit columns preserved

**Load Strategy:**
```sql
-- Use INSERT INTO for ACID tables
INSERT INTO gmp_cis.cis_portfolio
SELECT * FROM staging.portfolio_export;

-- Verify counts
SELECT COUNT(*) FROM gmp_cis.cis_portfolio;
```

---

### Story CIS-303: Validate Data Migration

**Summary:** Validate migrated data integrity and completeness
**Type:** Story
**Priority:** Critical
**Story Points:** 3
**Assignee:** QA Team

**Description:**
Comprehensive validation of migrated data.

**Acceptance Criteria:**
- [ ] Row counts match between Kudu and Hive
- [ ] Sample data comparison passed
- [ ] Soft-deleted records preserved
- [ ] Audit trail intact
- [ ] Referential integrity verified
- [ ] Performance baseline established

**Validation Queries:**
```sql
-- Count comparison
SELECT 'portfolio' AS table_name, COUNT(*) AS hive_count
FROM gmp_cis.cis_portfolio
UNION ALL
SELECT 'trade', COUNT(*) FROM gmp_cis.cis_trade
UNION ALL
SELECT 'security', COUNT(*) FROM gmp_cis.cis_security;

-- Sample data verification
SELECT * FROM gmp_cis.cis_portfolio LIMIT 10;
```

---

## Sprint 4: Integration & Testing (2 weeks)

### Story CIS-401: Update Django Settings for Hive

**Summary:** Update Django configuration for Hive connection
**Type:** Story
**Priority:** High
**Story Points:** 2
**Assignee:** Backend Developer

**Description:**
Update Django settings to use Hive instead of Kudu/Impala.

**Acceptance Criteria:**
- [ ] `config/settings.py` updated with Hive config
- [ ] Environment variables documented
- [ ] Connection string updated to port 10000
- [ ] Backward compatibility aliases provided
- [ ] Settings validated in dev environment

**Environment Variables:**
```bash
# Hive Configuration
HIVE_HOST=localhost
HIVE_PORT=10000
HIVE_DB=gmp_cis
HIVE_AUTH=NONE
HIVE_USERNAME=prakashhosalli
HIVE_PASSWORD=****
HIVE_POOL_SIZE=20
HIVE_TIMEOUT=120

# REST Proxy (for CML)
USE_REST_PROXY=false
HIVE_PROXY_URL=http://edge-node:5000
HIVE_PROXY_API_KEY=xxx
```

---

### Story CIS-402: Update Service Layer for Hive Repositories

**Summary:** Update all service classes to use Hive repositories
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** Backend Developer

**Description:**
Update service layer to import and use Hive repositories instead of Kudu.

**Acceptance Criteria:**
- [ ] PortfolioService using PortfolioHiveRepository
- [ ] TradeService using TradeHiveRepository
- [ ] SecurityService using SecurityHiveRepository
- [ ] MarketDataService using Hive repositories
- [ ] ReferenceDataService using Hive repository
- [ ] UDFService using UDFHiveRepository
- [ ] Backward compatibility imports provided

**Services to Update:**
- `portfolio/services/portfolio_service.py`
- `trade/services/trade_service.py`
- `security/services/security_service.py`
- `market_data/services/market_data_service.py`
- `reference_data/services/reference_data_service.py`
- `udf/services/udf_service.py`

---

### Story CIS-403: Integration Testing - Portfolio Module

**Summary:** Integration tests for Portfolio module with Hive
**Type:** Story
**Priority:** High
**Story Points:** 3
**Assignee:** QA Team

**Description:**
Complete integration testing of Portfolio module with Hive backend.

**Test Cases:**
- [ ] Create portfolio (DRAFT status)
- [ ] Edit portfolio
- [ ] Submit for approval (DRAFT → PENDING_APPROVAL)
- [ ] Approve portfolio (PENDING_APPROVAL → APPROVED → ACTIVE)
- [ ] Reject portfolio (PENDING_APPROVAL → REJECTED)
- [ ] Edit rejected portfolio
- [ ] Soft delete portfolio
- [ ] Restore deleted portfolio
- [ ] Portfolio history tracking
- [ ] Portfolio search
- [ ] CSV export

---

### Story CIS-404: Integration Testing - Trade Module

**Summary:** Integration tests for Trade module with Hive
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** QA Team

**Description:**
Complete integration testing of Trade module with Hive backend.

**Test Cases:**
- [ ] Create trade (all types: BUY, SELL, etc.)
- [ ] Edit trade
- [ ] Submit for approval
- [ ] Approve/Reject trade
- [ ] Settle trade
- [ ] Cancel trade
- [ ] Trade history tracking
- [ ] Trade notes CRUD
- [ ] Position calculation
- [ ] Portfolio validation
- [ ] Security validation
- [ ] Counterparty validation

---

### Story CIS-405: Integration Testing - Security Module

**Summary:** Integration tests for Security module with Hive
**Type:** Story
**Priority:** High
**Story Points:** 3
**Assignee:** QA Team

**Description:**
Complete integration testing of Security module with Hive backend.

**Test Cases:**
- [ ] Create security
- [ ] Edit security
- [ ] Approve/Reject security
- [ ] Lookup by ISIN
- [ ] Lookup by CUSIP
- [ ] Lookup by SEDOL
- [ ] Lookup by Ticker
- [ ] Security history tracking

---

### Story CIS-406: Integration Testing - Market Data Module

**Summary:** Integration tests for Market Data module with Hive
**Type:** Story
**Priority:** Medium
**Story Points:** 3
**Assignee:** QA Team

**Description:**
Complete integration testing of Market Data module with Hive backend.

**Test Cases:**
- [ ] Create equity price
- [ ] Update equity price
- [ ] Get latest price
- [ ] Price history query
- [ ] Create FX rate
- [ ] Update FX rate
- [ ] Get latest rate
- [ ] Rate history query
- [ ] History table population

---

### Story CIS-407: Performance Testing

**Summary:** Performance testing of Hive operations
**Type:** Story
**Priority:** High
**Story Points:** 5
**Assignee:** QA Team

**Description:**
Benchmark performance of Hive ACID operations.

**Performance Targets:**

| Operation | Target | Warning | Critical |
|-----------|--------|---------|----------|
| SELECT (single row) | <500ms | 500-1000ms | >1000ms |
| SELECT (list, 100 rows) | <2s | 2-5s | >5s |
| INSERT (single row) | <10s | 10-20s | >20s |
| UPDATE (single row) | <10s | 10-20s | >20s |
| DELETE (soft) | <10s | 10-20s | >20s |

**Test Scenarios:**
- [ ] Single record CRUD operations
- [ ] Bulk operations (100, 500, 1000 records)
- [ ] Concurrent user simulation (10, 50, 100 users)
- [ ] Peak load testing
- [ ] Connection pool stress test

**Linked File:** `BENCHMARKING.md`, `locustfile.py`

---

## Sprint 5: Deployment & Cutover (1 week)

### Story CIS-501: UAT Environment Deployment

**Summary:** Deploy to UAT environment
**Type:** Story
**Priority:** Critical
**Story Points:** 5
**Assignee:** DevOps Team

**Description:**
Deploy migrated application to UAT environment.

**Acceptance Criteria:**
- [ ] Hive tables created in UAT
- [ ] Data migrated to UAT
- [ ] REST Proxy deployed on UAT edge node
- [ ] Django application deployed
- [ ] Environment variables configured
- [ ] Smoke tests passed
- [ ] UAT sign-off obtained

---

### Story CIS-502: Production Deployment Plan

**Summary:** Create detailed production deployment plan
**Type:** Story
**Priority:** Critical
**Story Points:** 3
**Assignee:** DevOps Team

**Description:**
Document detailed production deployment and rollback plan.

**Deliverables:**
- [ ] Deployment runbook
- [ ] Rollback procedures
- [ ] Monitoring checklist
- [ ] Communication plan
- [ ] Downtime window scheduled
- [ ] Stakeholder approvals

---

### Story CIS-503: Production Deployment

**Summary:** Execute production deployment
**Type:** Story
**Priority:** Critical
**Story Points:** 8
**Assignee:** DevOps Team

**Description:**
Execute production cutover from Kudu to Hive.

**Deployment Steps:**
1. [ ] Announce maintenance window
2. [ ] Take final Kudu data export
3. [ ] Create Hive tables in production
4. [ ] Load data to Hive tables
5. [ ] Deploy REST Proxy to PROD edge node
6. [ ] Deploy updated Django application
7. [ ] Run smoke tests
8. [ ] Verify all modules functional
9. [ ] Monitor for issues
10. [ ] Announce deployment complete

**Rollback Triggers:**
- Data integrity issues
- Performance degradation >50%
- Critical functionality broken
- Error rate >5%

---

### Story CIS-504: Post-Deployment Monitoring

**Summary:** Monitor production after deployment
**Type:** Story
**Priority:** High
**Story Points:** 3
**Assignee:** Operations Team

**Description:**
Monitor production environment for 2 weeks post-deployment.

**Monitoring Checklist:**
- [ ] Query latency metrics
- [ ] Error rates
- [ ] Connection pool utilization
- [ ] Compaction job status
- [ ] Disk space usage
- [ ] User feedback collection

**Metrics Dashboard:**
- Response time p50, p95, p99
- Requests per second
- Error rate percentage
- Active connections
- Queue depth

---

## Sprint 6: Documentation & Cleanup (1 week)

### Story CIS-601: Update Technical Documentation

**Summary:** Update all technical documentation for Hive
**Type:** Story
**Priority:** Medium
**Story Points:** 3
**Assignee:** Tech Writer

**Description:**
Update project documentation to reflect Hive migration.

**Documentation to Update:**
- [ ] CLAUDE.md (main project guide)
- [ ] README.md
- [ ] API documentation
- [ ] Database schema documentation
- [ ] Connection guide
- [ ] Troubleshooting guide

---

### Story CIS-602: Remove Deprecated Kudu Code

**Summary:** Clean up deprecated Kudu-related code
**Type:** Story
**Priority:** Low
**Story Points:** 3
**Assignee:** Backend Developer

**Description:**
Remove deprecated Kudu repositories and DDL scripts after successful migration.

**Files to Archive/Remove:**
- [ ] `*_kudu_repository.py` files
- [ ] `*_kudu.sql` DDL scripts
- [ ] Kudu-specific configuration
- [ ] ImpalaConnectionManager (keep as alias)

**Files to Keep (for reference):**
- Move to `archive/kudu/` directory
- Keep for 6 months before permanent deletion

---

### Story CIS-603: Create Operational Runbook

**Summary:** Create operational runbook for Hive maintenance
**Type:** Story
**Priority:** Medium
**Story Points:** 3
**Assignee:** Operations Team

**Description:**
Document operational procedures for Hive maintenance.

**Runbook Sections:**
- [ ] Daily health checks
- [ ] Compaction scheduling (minor daily, major weekly)
- [ ] Statistics collection
- [ ] Connection pool monitoring
- [ ] Kerberos ticket renewal
- [ ] Backup procedures
- [ ] Recovery procedures
- [ ] Troubleshooting guide

**Maintenance Schedule:**

| Task | Frequency | Command |
|------|-----------|---------|
| Minor compaction | Daily 2AM | `ALTER TABLE x COMPACT 'minor'` |
| Major compaction | Weekly Sunday 2AM | `ALTER TABLE x COMPACT 'major'` |
| Statistics update | Daily 3AM | `ANALYZE TABLE x COMPUTE STATISTICS` |
| Kerberos renewal | Every 4 hours | `kinit -kt keytab principal` |

---

## Summary: Sprint Plan

| Sprint | Duration | Focus | Stories |
|--------|----------|-------|---------|
| Sprint 1 | 2 weeks | Infrastructure & Foundation | CIS-101 to CIS-105 |
| Sprint 2 | 2 weeks | Repository Layer Migration | CIS-201 to CIS-209 |
| Sprint 3 | 1 week | Data Migration | CIS-301 to CIS-303 |
| Sprint 4 | 2 weeks | Integration & Testing | CIS-401 to CIS-407 |
| Sprint 5 | 1 week | Deployment & Cutover | CIS-501 to CIS-504 |
| Sprint 6 | 1 week | Documentation & Cleanup | CIS-601 to CIS-603 |

**Total Duration:** 9 weeks
**Total Story Points:** ~125
**Team Size:** 4-5 engineers + 1 QA + 1 DevOps

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Hive write latency unacceptable | Low | High | PyHive connection pool + Tez engine |
| Data migration issues | Medium | High | Comprehensive validation, rollback plan |
| CML connectivity issues | Medium | High | REST Proxy with HA setup |
| Performance degradation | Medium | Medium | Benchmarking, optimization sprints |
| Kerberos authentication failures | Low | High | Auto-renewal, monitoring alerts |

---

## Definition of Done

- [ ] Code reviewed and approved
- [ ] Unit tests written and passing
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] No critical/high bugs open
- [ ] Performance targets met
- [ ] Deployed to staging environment
- [ ] QA sign-off obtained

---

*Document Version: 1.0*
*Created: 2026-02-22*
*Author: CIS Trade Hive Team*
