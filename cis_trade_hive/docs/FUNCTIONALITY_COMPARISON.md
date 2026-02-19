# CIS Trade Hive - Functionality Comparison & Migration Guide

## Branch Comparison: cis_trade_hive → hive-managed-tables

This document provides a comprehensive inventory of all functionality in the `cis_trade_hive` branch and tracks migration status to the `hive-managed-tables` branch.

---

## 1. Executive Summary

### Architecture Migration

| Aspect | cis_trade_hive (Old) | hive-managed-tables (New) |
|--------|----------------------|---------------------------|
| **Database** | Apache Kudu | Apache Hive Managed Tables |
| **Query Engine** | Impala (port 21050) | HiveServer2 (port 10000) |
| **Storage Format** | Kudu native | ORC + SNAPPY compression |
| **Transactions** | Limited (UPSERT only) | Full ACID (INSERT/UPDATE/DELETE) |
| **Connection Manager** | ImpalaConnectionManager | HiveConnectionManager |
| **Write Pattern** | UPSERT | INSERT/UPDATE/DELETE |

### Migration Statistics
- **Files Changed**: 19
- **Lines Added**: 6,319
- **Lines Removed**: 1,744
- **Net New Code**: ~4,575 lines

---

## 2. Django Apps Inventory

| App | Purpose | Migration Status |
|-----|---------|------------------|
| **config** | Django settings, URLs, WSGI | ✅ Migrated |
| **core** | Authentication, ACL, Audit, Help | ✅ Migrated |
| **portfolio** | Portfolio CRUD + Maker-Checker | ✅ Migrated |
| **trade** | Trade execution + Workflow | ✅ Migrated |
| **security** | Security master data | ✅ Migrated |
| **market_data** | FX rates, Equity prices | ✅ Migrated |
| **reference_data** | Currency, Country, Counterparty | ✅ Migrated |
| **udf** | User-Defined Fields | ✅ Migrated |
| **lookup** | Configuration/Lookup tables | ✅ Migrated |
| **hive_poc** | POC for Hive operations | ✅ Present |

---

## 3. Feature Inventory by Module

### 3.1 Core Module (`/core/`)

#### Authentication & Session
| Feature | Description | Status |
|---------|-------------|--------|
| Session-based login | No password validation in dev mode | ✅ |
| User session attributes | user_login, user_id, user_name, user_email, user_group_id | ✅ |
| Login/Logout views | `/login/`, `/logout/` | ✅ |

#### ACL (Access Control Layer)
| Feature | Description | Status |
|---------|-------------|--------|
| User management | cis_user table queries | ✅ |
| Group management | cis_user_group table | ✅ |
| Permission checking | cis_group_permissions | ✅ |
| User-group membership | cis_user_group_membership | ✅ |
| Permission caching | 300s TTL per user | ✅ |

#### Connection Management
| Feature | Description | Status |
|---------|-------------|--------|
| Connection pooling | 20 connections default | ✅ |
| Thread-safe singleton | Lock-protected instance | ✅ |
| Connection validation | Auto-recycle stale connections | ✅ |
| Async write support | ThreadPoolExecutor for audit | ✅ |
| Query caching | TTL-based cache | ✅ |

#### Audit Logging
| Feature | Description | Status |
|---------|-------------|--------|
| Action logging | CREATE, UPDATE, DELETE, APPROVE, REJECT | ✅ |
| Entity tracking | entity_type, entity_id, action | ✅ |
| Value tracking | old_value, new_value as JSON | ✅ |
| User tracking | user_id, username, ip_address, user_agent | ✅ |
| Async logging | Non-blocking audit writes | ✅ |

#### Dashboard & Search
| Feature | Description | Status |
|---------|-------------|--------|
| Main dashboard | `/dashboard/` | ✅ |
| Global search | `/search/` across all entities | ✅ |
| Audit log viewer | View audit trail | ✅ |

---

### 3.2 Portfolio Module (`/portfolio/`)

#### Maker-Checker Workflow
```
DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → INACTIVE → CLOSED
```

| Feature | Description | Status |
|---------|-------------|--------|
| Create portfolio (Maker) | Creates in DRAFT status | ✅ |
| Edit portfolio | Only in DRAFT/REJECTED | ✅ |
| Submit for approval | DRAFT → PENDING_APPROVAL | ✅ |
| Approve (Checker) | PENDING_APPROVAL → APPROVED → ACTIVE | ✅ |
| Reject (Checker) | PENDING_APPROVAL → REJECTED | ✅ |
| Pending approvals view | Checker dashboard | ✅ |
| Portfolio history | Audit trail in cis_portfolio_history | ✅ |

#### CRUD Operations
| Feature | Description | Status |
|---------|-------------|--------|
| List portfolios | With pagination, search, filters | ✅ |
| View portfolio detail | Single portfolio view | ✅ |
| Create portfolio | Form-based creation | ✅ |
| Edit portfolio | Update in editable states | ✅ |
| Delete portfolio | Soft delete | ✅ |
| CSV export | Export list to CSV | ✅ |

#### Portfolio Fields
| Field | Type | Description |
|-------|------|-------------|
| portfolio_id | STRING | Primary key |
| portfolio_short_name | STRING | Short code |
| portfolio_name | STRING | Full name |
| portfolio_type | STRING | EQUITY, FIXED_INCOME, etc. |
| currency | STRING | Trading currency |
| base_currency | STRING | Reporting currency |
| manager_name | STRING | Portfolio manager |
| custodian | STRING | Custodian bank |
| inception_date | DATE | Start date |
| status | STRING | Workflow status |

---

### 3.3 Trade Module (`/trade/`)

#### Trade Types
| Type | Description |
|------|-------------|
| BUY | Purchase securities |
| SELL | Sell securities |
| ADD_LONG | Add to long position |
| DELIVER_LONG | Deliver long position |
| REDUCTION_BASIS | Reduce cost basis |
| INCOME | Dividend/interest income |
| SPLIT_TRANSACTION | Stock split |

#### Maker-Checker Workflow
```
DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → SETTLED/CANCELLED
```

| Feature | Description | Status |
|---------|-------------|--------|
| Create trade | With validation | ✅ |
| Edit trade | Only in DRAFT/REJECTED | ✅ |
| Submit for approval | DRAFT → PENDING_APPROVAL | ✅ |
| Approve/Reject | Checker actions | ✅ |
| Settle trade | Mark as settled | ✅ |
| Cancel trade | Cancel active trade | ✅ |
| Trade history | cis_trade_history table | ✅ |

#### Trade Validation
| Validation | Description | Status |
|------------|-------------|--------|
| Portfolio validation | Check portfolio exists | ✅ |
| Security validation | Check security exists | ✅ |
| Counterparty validation | Check counterparty exists | ✅ |
| Broker validation | Check broker exists | ✅ |

#### Trade Fields
| Field | Type | Description |
|-------|------|-------------|
| trade_id | STRING | Primary key |
| portfolio_id | STRING | FK to portfolio |
| security_id | STRING | FK to security |
| trade_type | STRING | BUY, SELL, etc. |
| trade_action | STRING | Action type |
| quantity | DECIMAL(18,4) | Number of units |
| price | DECIMAL(18,6) | Unit price |
| trade_amount | DECIMAL(18,2) | Total amount |
| currency | STRING | Trade currency |
| trade_date | DATE | Execution date |
| settlement_date | DATE | Settlement date |
| counterparty_id | STRING | FK to counterparty |
| broker_id | STRING | FK to broker |
| commission | DECIMAL(18,4) | Commission amount |
| fees | DECIMAL(18,4) | Other fees |
| status | STRING | Workflow status |

#### Position Management
| Feature | Description | Status |
|---------|-------------|--------|
| Position tracking | cis_trade_position table | ✅ |
| Position calculation | Aggregate by portfolio/security | ✅ |
| Position history | Track position changes | ✅ |

#### Trade Notes
| Feature | Description | Status |
|---------|-------------|--------|
| Add trade notes | cis_trade_note table | ✅ |
| Note types | Comments, instructions | ✅ |

---

### 3.4 Security Module (`/security/`)

#### Maker-Checker Workflow
```
DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → INACTIVE
```

| Feature | Description | Status |
|---------|-------------|--------|
| Create security | Form-based creation | ✅ |
| Edit security | Only in DRAFT/REJECTED | ✅ |
| Approve/Reject | Checker workflow | ✅ |
| Security history | cis_security_history | ✅ |

#### Security Fields
| Field | Type | Description |
|-------|------|-------------|
| security_id | STRING | Primary key |
| security_code | STRING | Internal code |
| security_name | STRING | Full name |
| security_type | STRING | EQUITY, BOND, etc. |
| asset_class | STRING | Asset classification |
| currency | STRING | Trading currency |
| exchange_code | STRING | Exchange |
| country | STRING | Country of issue |
| sector | STRING | Industry sector |
| isin | STRING | ISIN code |
| cusip | STRING | CUSIP code |
| sedol | STRING | SEDOL code |
| ticker | STRING | Ticker symbol |
| issuer | STRING | Issuing entity |

#### Lookup Methods
| Method | Description | Status |
|--------|-------------|--------|
| get_by_isin() | Find by ISIN | ✅ |
| get_by_ticker() | Find by ticker | ✅ |
| get_by_cusip() | Find by CUSIP | ✅ |
| get_by_sedol() | Find by SEDOL | ✅ |

---

### 3.5 Market Data Module (`/market_data/`)

#### Equity Prices
| Feature | Description | Status |
|---------|-------------|--------|
| Price CRUD | Create, read, update, delete | ✅ |
| Latest price lookup | get_latest_price() | ✅ |
| Price history | Date range queries | ✅ |
| Price history table | cis_equity_price_history | ✅ |
| Bulk price import | bulk_create_prices() | ✅ |

#### Equity Price Fields
| Field | Type | Description |
|-------|------|-------------|
| price_id | STRING | Primary key |
| security_id | STRING | FK to security |
| price_date | DATE | Price date |
| open_price | DECIMAL(18,6) | Opening price |
| high_price | DECIMAL(18,6) | High price |
| low_price | DECIMAL(18,6) | Low price |
| close_price | DECIMAL(18,6) | Closing price |
| volume | BIGINT | Trading volume |
| currency | STRING | Price currency |
| source | STRING | Data source |

#### FX Rates
| Feature | Description | Status |
|---------|-------------|--------|
| Rate CRUD | Create, read, update, delete | ✅ |
| Latest rate lookup | get_latest_rate() | ✅ |
| Rate history | Date range queries | ✅ |
| Rate history table | cis_fx_rate_history | ✅ |
| Currency pair queries | get_all_currency_pairs() | ✅ |

#### FX Rate Fields
| Field | Type | Description |
|-------|------|-------------|
| rate_id | STRING | Primary key |
| from_currency | STRING | Source currency |
| to_currency | STRING | Target currency |
| rate_date | DATE | Rate date |
| rate | DECIMAL(18,8) | Exchange rate |
| bid_rate | DECIMAL(18,8) | Bid rate |
| ask_rate | DECIMAL(18,8) | Ask rate |
| source | STRING | Data source |

---

### 3.6 Reference Data Module (`/reference_data/`)

#### Counterparty Management
| Feature | Description | Status |
|---------|-------------|--------|
| Counterparty CRUD | Full CRUD operations | ✅ |
| Counterparty types | BROKER, CUSTODIAN, COUNTERPARTY | ✅ |
| Search and filter | By type, country, status | ✅ |
| CSV export | Export to CSV | ✅ |

#### Counterparty Fields
| Field | Type | Description |
|-------|------|-------------|
| counterparty_id | STRING | Primary key |
| counterparty_code | STRING | Code |
| counterparty_name | STRING | Name |
| counterparty_type | STRING | Type |
| country | STRING | Country |
| address | STRING | Address |
| contact_name | STRING | Contact person |
| contact_email | STRING | Email |
| contact_phone | STRING | Phone |
| status | STRING | Status |

#### Currency Reference
| Feature | Description | Status |
|---------|-------------|--------|
| Currency list | All currencies | ✅ |
| Currency lookup | By code | ✅ |

#### Country Reference
| Feature | Description | Status |
|---------|-------------|--------|
| Country list | All countries | ✅ |
| Country lookup | By code | ✅ |

---

### 3.7 UDF Module (`/udf/`)

#### Field Types Supported
| Type | Description | Status |
|------|-------------|--------|
| TEXT | Free text | ✅ |
| NUMBER | Numeric value | ✅ |
| DATE | Date picker | ✅ |
| DATETIME | Date and time | ✅ |
| BOOLEAN | True/False | ✅ |
| SELECT | Single dropdown | ✅ |
| MULTISELECT | Multiple selection | ✅ |
| CURRENCY | Currency value | ✅ |
| PERCENTAGE | Percentage value | ✅ |

#### Entity Types
| Entity | Description | Status |
|--------|-------------|--------|
| PORTFOLIO | Portfolio UDFs | ✅ |
| TRADE | Trade UDFs | ✅ |
| SECURITY | Security UDFs | ✅ |
| COUNTERPARTY | Counterparty UDFs | ✅ |

#### UDF Features
| Feature | Description | Status |
|---------|-------------|--------|
| Field definitions | cis_udf_field table | ✅ |
| Field values | cis_udf_value table | ✅ |
| Dropdown options | cis_udf_option table | ✅ |
| CSV import/export | Bulk operations | ✅ |

---

### 3.8 Lookup Module (`/lookup/`)

| Feature | Description | Status |
|---------|-------------|--------|
| Lookup tables | Configuration data | ✅ |
| Lookup CRUD | Create, read, update, delete | ✅ |

---

## 4. Database Schema

### 4.1 Core Tables (4)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_user | User accounts | user_id, username, email, full_name, department, is_active, audit fields |
| cis_user_group | User groups | group_id, group_name, description, is_active, audit fields |
| cis_group_permissions | Permissions | permission_id, group_id, resource, action, is_allowed, audit fields |
| cis_user_group_membership | Memberships | membership_id, user_id, group_id, audit fields |

### 4.2 Audit Table (1)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_audit_log | Audit trail | audit_id, entity_type, entity_id, action, old_value, new_value, user_id, username, ip_address, user_agent, created_at |

### 4.3 Portfolio Tables (2)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_portfolio | Portfolio master | 17 columns including workflow status |
| cis_portfolio_history | Portfolio audit | history_id, portfolio_id, action, old_value, new_value, changed_by, changed_at |

### 4.4 Trade Tables (4)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_trade | Trade records | 29 columns including workflow status |
| cis_trade_history | Trade audit | history_id, trade_id, action, old_value, new_value, changed_by, changed_at |
| cis_trade_note | Trade notes | note_id, trade_id, note_type, note_text, audit fields |
| cis_trade_position | Positions | position_id, trade_id, portfolio_id, security_id, position_date, quantity, costs, market values |

### 4.5 Security Tables (2)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_security | Security master | 25 columns including identifiers |
| cis_security_history | Security audit | history_id, security_id, action, old_value, new_value, changed_by, changed_at |

### 4.6 Market Data Tables (4)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_equity_price | Equity prices | price_id, security_id, price_date, OHLC, volume, currency, source, audit fields |
| cis_equity_price_history | Price audit | history_id, price_id, snapshot of price data, change_type, changed_by, changed_at |
| cis_fx_rate | FX rates | rate_id, from_currency, to_currency, rate_date, rate, bid_rate, ask_rate, source, audit fields |
| cis_fx_rate_history | FX rate audit | history_id, rate_id, snapshot of rate data, change_type, changed_by, changed_at |

### 4.7 Reference Data Tables (3)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_counterparty | Counterparties | 15 columns |
| cis_currency | Currencies | currency_id, currency_code, currency_name, symbol, decimal_places |
| cis_country | Countries | country_id, country_code, country_name, region, currency_code |

### 4.8 UDF Tables (2)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_udf_field | Field definitions | field_id, object_type, field_name, field_label, field_type, is_required, default_value, options, display_order |
| cis_udf_value | Field values | value_id, field_id, object_type, object_id, field_value, audit fields |

### 4.9 Helper Tables (2)
| Table | Description | Columns |
|-------|-------------|---------|
| cis_sequence | ID generation | sequence_name, current_value, increment_by |
| cis_help_content | Help docs | help_id, page_key, section_key, title, content, display_order |

**Total: 24 Tables**

---

## 5. API Endpoints

### 5.1 Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| /login/ | GET, POST | Login page |
| /logout/ | GET | Logout |

### 5.2 Dashboard
| Endpoint | Method | Description |
|----------|--------|-------------|
| /dashboard/ | GET | Main dashboard |
| /search/ | GET | Global search |

### 5.3 Portfolio
| Endpoint | Method | Description |
|----------|--------|-------------|
| /portfolio/ | GET | List portfolios |
| /portfolio/create/ | GET, POST | Create portfolio |
| /portfolio/<id>/ | GET | Portfolio detail |
| /portfolio/<id>/edit/ | GET, POST | Edit portfolio |
| /portfolio/<id>/submit/ | POST | Submit for approval |
| /portfolio/<id>/approve/ | POST | Approve portfolio |
| /portfolio/<id>/reject/ | POST | Reject portfolio |
| /portfolio/pending-validation/ | GET | Pending approvals |
| /portfolio/export/csv/ | GET | CSV export |

### 5.4 Trade
| Endpoint | Method | Description |
|----------|--------|-------------|
| /trade/ | GET | List trades |
| /trade/create/ | GET, POST | Create trade |
| /trade/<id>/ | GET | Trade detail |
| /trade/<id>/edit/ | GET, POST | Edit trade |
| /trade/<id>/submit/ | POST | Submit for approval |
| /trade/<id>/settle/ | POST | Settle trade |
| /trade/<id>/cancel/ | POST | Cancel trade |
| /trade/pending-settlement/ | GET | Pending settlement |
| /trade/export/csv/ | GET | CSV export |

### 5.5 Trade API (AJAX)
| Endpoint | Method | Description |
|----------|--------|-------------|
| /trade/api/validate-portfolio/ | GET | Validate portfolio |
| /trade/api/validate-security/ | GET | Validate security |
| /trade/api/validate-counterparty/ | GET | Validate counterparty |
| /trade/api/portfolios/ | GET | List portfolios |
| /trade/api/securities/ | GET | List securities |
| /trade/api/counterparties/ | GET | List counterparties |
| /trade/api/get-position/ | GET | Get position |
| /trade/api/get-equity-price/ | GET | Get equity price |

### 5.6 Security
| Endpoint | Method | Description |
|----------|--------|-------------|
| /security/ | GET | List securities |
| /security/create/ | GET, POST | Create security |
| /security/<id>/ | GET | Security detail |
| /security/<id>/edit/ | GET, POST | Edit security |
| /security/pending-approvals/ | GET | Pending approvals |

### 5.7 Market Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| /market-data/fx-rates/ | GET | FX rates list |
| /market-data/equity-prices/ | GET | Equity prices list |
| /market-data/dashboard/ | GET | Market data dashboard |

### 5.8 Reference Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| /reference-data/currencies/ | GET | Currency list |
| /reference-data/countries/ | GET | Country list |
| /reference-data/counterparties/ | GET | Counterparty list |

### 5.9 UDF
| Endpoint | Method | Description |
|----------|--------|-------------|
| /udf/ | GET | UDF field list |
| /udf/create/ | GET, POST | Create UDF field |
| /udf/<id>/edit/ | GET, POST | Edit UDF field |
| /udf/values/<entity_type>/ | GET | UDF values |

---

## 6. Maker-Checker Workflow

### Workflow Diagram
```
┌─────────┐    Submit     ┌──────────────────┐
│  DRAFT  │──────────────►│ PENDING_APPROVAL │
└─────────┘               └────────┬─────────┘
     ▲                             │
     │                    ┌────────┴────────┐
     │                    ▼                 ▼
     │               ┌─────────┐      ┌──────────┐
     └───────────────│ REJECTED│      │ APPROVED │
         (Edit)      └─────────┘      └────┬─────┘
                                           │
                                           ▼
                                      ┌─────────┐
                                      │  ACTIVE │
                                      └────┬────┘
                                           │
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                         ┌────────┐  ┌─────────┐  ┌────────┐
                         │INACTIVE│  │ SETTLED │  │CANCELLED│
                         └────────┘  └─────────┘  └────────┘
                              │
                              ▼
                         ┌────────┐
                         │ CLOSED │
                         └────────┘
```

### Status Transitions

| Current Status | Allowed Actions | Next Status |
|----------------|-----------------|-------------|
| DRAFT | Submit | PENDING_APPROVAL |
| DRAFT | Edit | DRAFT |
| PENDING_APPROVAL | Approve | APPROVED → ACTIVE |
| PENDING_APPROVAL | Reject | REJECTED |
| REJECTED | Edit | DRAFT |
| ACTIVE | Settle | SETTLED |
| ACTIVE | Cancel | CANCELLED |
| ACTIVE | Deactivate | INACTIVE |
| INACTIVE | Close | CLOSED |

### Role Permissions

| Role | Allowed Actions |
|------|-----------------|
| **Maker** | Create, Edit (DRAFT/REJECTED), Submit, Delete |
| **Checker** | View, Approve, Reject |
| **Admin** | All actions |

---

## 7. Testing Checklist

### 7.1 Core Tests
- [ ] User authentication (login/logout)
- [ ] ACL permission checking
- [ ] Hive connection pooling
- [ ] Audit logging (sync and async)
- [ ] Query caching

### 7.2 Portfolio Tests
- [ ] Create portfolio (DRAFT)
- [ ] Edit portfolio
- [ ] Submit for approval
- [ ] Approve portfolio
- [ ] Reject portfolio
- [ ] Portfolio history tracking
- [ ] CSV export

### 7.3 Trade Tests
- [ ] Create trade (all types)
- [ ] Edit trade
- [ ] Submit for approval
- [ ] Approve/Reject trade
- [ ] Settle trade
- [ ] Cancel trade
- [ ] Position tracking
- [ ] Trade notes
- [ ] Trade history

### 7.4 Security Tests
- [ ] Create security
- [ ] Edit security
- [ ] Approve/Reject security
- [ ] Lookup by ISIN/CUSIP/SEDOL/ticker
- [ ] Security history

### 7.5 Market Data Tests
- [ ] Create equity price
- [ ] Get latest price
- [ ] Price history with history table
- [ ] Create FX rate
- [ ] Get latest rate
- [ ] Rate history with history table

### 7.6 Reference Data Tests
- [ ] Counterparty CRUD
- [ ] Currency lookup
- [ ] Country lookup
- [ ] CSV export

### 7.7 UDF Tests
- [ ] Create UDF field
- [ ] Edit UDF field
- [ ] Delete UDF field
- [ ] Set UDF values
- [ ] CSV import/export

---

## 8. Configuration

### 8.1 Hive Configuration (hive-managed-tables)
```python
HIVE_CONFIG = {
    'HOST': 'localhost',        # or Cloudera host
    'PORT': 10000,              # HiveServer2 port
    'DATABASE': 'gmp_cis',
    'AUTH': 'NONE',             # or LDAP/KERBEROS
    'USERNAME': 'prakashhosalli',
    'PASSWORD': '****',
    'TIMEOUT': 60,
    'POOL_SIZE': 20,
}
```

### 8.2 Required Hive Settings for ACID
```sql
SET hive.support.concurrency=true;
SET hive.enforce.bucketing=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.compactor.initiator.on=true;
SET hive.compactor.worker.threads=1;
SET hive.execution.engine=mr;  -- MapReduce for transactional ops
```

---

## 9. Migration Notes

### 9.1 Breaking Changes
- Port changed from 21050 (Impala) to 10000 (Hive)
- UPSERT replaced with INSERT/UPDATE/DELETE
- Connection manager class renamed

### 9.2 Backward Compatibility
- `impala_manager` alias available for `hive_manager`
- Status mapping provided for old status names

### 9.3 Data Migration
To migrate data from Kudu to Hive:
1. Export data from Kudu tables using Impala
2. Transform data to ORC format
3. Load into Hive managed tables
4. Verify data integrity
5. Update application connection strings

---

## 10. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-19 | Claude Code | Initial comprehensive documentation |
| 1.1 | 2026-02-20 | Claude Code | Added lookup_hive_repository.py, documented Hive ACID limitations |

---

*Last updated: 2026-02-20*
