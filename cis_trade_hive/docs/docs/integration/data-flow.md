# Data Flow

Data movement and transformations within CisTrade ecosystem.

## Overall Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  GMP System  │────▶│  Hive/Kudu   │◀────│  CisTrade    │
│  (Source)    │     │  (Storage)   │     │  (UI/Logic)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                     │
       │                    │                     │
       ▼                    ▼                     ▼
  Daily ETL         Impala Queries        User Actions
```

## Reference Data Flow

### Source to Hive

**Daily ETL Process**:

1. **GMP Export** (2:00 AM)
   - Currencies → `gmp_cis_sta_dly_currency.csv`
   - Countries → `gmp_cis_sta_dly_country.csv`
   - Calendars → `gmp_cis_sta_dly_calendar.csv`
   - Counterparties → `gmp_cis_sta_dly_counterparty.csv`

2. **File Transfer** (2:30 AM)
   - Files placed in shared directory
   - Permissions set (read-only)

3. **Hive External Tables**
   - Point to file locations
   - No data copy (external)
   - Instant availability

4. **CisTrade Access**
   - Queries via Impala
   - Data served to UI
   - No local caching

**Format**:
```
Source: GMP Database
  ↓ SQL Extract
Format: Pipe-delimited (|)
  ↓ SFTP
Storage: /data/gmp_export/
  ↓ Hive External Table
Access: Impala SELECT queries
  ↓ Python (Impyla)
Display: Django Templates
```

## Portfolio Data Flow

### Write Operations

**Create Portfolio**:

```
1. User Input (Web Form)
   ↓ HTTP POST
2. Django View
   ↓ Validation
3. Portfolio Service
   ↓ Business Logic
4. Portfolio Repository
   ↓ SQL INSERT
5. Kudu Table (cis_portfolio)
   ↓ Confirmation
6. Audit Log (cis_audit_log)
   ↓ Response
7. Success Message to User
```

**Update Portfolio**:

```
1. User Edit (Web Form)
   ↓ HTTP POST
2. Django View
   ↓ Validation
3. Portfolio Service
   ↓ Four-Eyes Check
4. Portfolio Repository
   ↓ SQL UPDATE
5. Kudu Table Update
   ↓ Parallel
6a. Portfolio History (cis_portfolio_history)
6b. Audit Log (cis_audit_log)
   ↓ Response
7. Success Message
```

### Read Operations

**List Portfolios**:

```
1. User Request (Page Load)
   ↓ HTTP GET
2. Django View
   ↓ Permission Check
3. Portfolio Service
   ↓ Filter/Search
4. Portfolio Repository
   ↓ SQL SELECT
5. Impala Query Execution
   ↓ Kudu Scan
6. Kudu Table (cis_portfolio)
   ↓ Results
7. Pagination
   ↓ Template Rendering
8. HTML Response
```

## Audit Log Flow

### Write to Audit

**Every Action**:

```
User Action
  ↓
Django View
  ↓ Extract Context
Audit Repository
  ↓ Build INSERT
Impala Connection
  ↓ Execute
Kudu Table (cis_audit_log)
  ↓ (Async, Non-Blocking)
Continue User Flow
```

### Read from Audit

**Audit Log View**:

```
User Request (/core/audit-log/)
  ↓
Django View
  ↓ Date Range Filter
Audit Repository
  ↓ SQL SELECT with WHERE
Impala Query
  ↓ Kudu Scan
Results
  ↓ Sort by Timestamp DESC
Pagination
  ↓ Template Rendering
Display to User
```

## Market Data Flow

### FX Rate Updates

**Automated Feed**:

```
1. External Provider (Bloomberg/Reuters)
   ↓ API Call (Every 15 min)
2. Market Data Service
   ↓ Parse Response
3. Validation Service
   ↓ Quality Checks
4. Market Data Repository
   ↓ SQL INSERT/UPDATE
5. Kudu Table (cis_fx_rate)
   ↓ Trigger
6. Portfolio Revaluation
   ↓ Affected Portfolios
7. NAV Recalculation
```

**Manual Entry**:

```
User Input (Web Form)
  ↓
Market Data View
  ↓ Validation
Market Data Service
  ↓ Override Checks
Repository
  ↓ INSERT with Manual Flag
Kudu Table
  ↓ Audit
Audit Log (Manual Rate Entry)
```

## UDF Data Flow

### Value Update

```
User Input
  ↓
UDF View
  ↓ Validation (Data Type)
UDF Service
  ↓ Business Logic
Repository Operations:
  ├─ End-Date Previous Value
  └─ Insert New Value
  ↓ Both in Transaction
Kudu Tables:
  ├─ cis_udf_value (current)
  └─ cis_udf_value_history (all)
  ↓ Audit
Audit Log
```

## Data Synchronization

### Ensuring Consistency

**Transactional Writes**:
- Kudu supports row-level transactions
- Multiple tables updated atomically
- Rollback on any failure

**Read Consistency**:
- READ_LATEST snapshot isolation
- Consistent view across queries

## Performance Optimization

### Caching Strategy

**Not Cached** (Always Fresh):
- Portfolio list/detail
- Audit logs
- FX rates (real-time data)

**Cached** (1 hour):
- Help content
- User permissions (session)

**Cached** (1 day):
- Reference data (currencies, countries)
- Calendar data

### Query Optimization

**Partitioning**:
- Portfolio by status
- Audit log by date
- FX rates by currency pair

**Indexes**:
- Portfolio: code (primary key)
- Audit: timestamp
- FX Rate: (base_currency, quote_currency)

## Data Retention

### Policies

**Portfolio Data**:
- Active: Forever
- Closed: 7 years
- Draft/Rejected: 1 year

**Audit Logs**:
- All: 7 years (regulatory)
- Archive to cold storage after 2 years

**Market Data**:
- Current rates: Forever
- Historical rates: 10 years
- Intraday ticks: 3 months

## Related Documentation

- [Business Processes](business-processes.md)
- [Database Schema](../technical/database-schema.md)
- [Integration Points](integrations.md)
