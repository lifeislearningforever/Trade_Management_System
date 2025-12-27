# Integration Points

External system integrations and APIs.

## GMP System Integration

### Overview

**Purpose**: Source of truth for reference data

**Type**: Batch ETL

**Frequency**: Daily (2:00 AM)

**Data Flow**: GMP → CSV Files → Hive External Tables → CisTrade

### Integrated Data

**1. Currencies**
- Table: `gmp_cis_sta_dly_currency`
- Records: ~180 currencies
- Update: Daily
- Format: Pipe-delimited (|)

**2. Countries**
- Table: `gmp_cis_sta_dly_country`
- Records: ~250 countries
- Update: Daily
- Format: Pipe-delimited (|)

**3. Calendars**
- Table: `gmp_cis_sta_dly_calendar`
- Records: ~100,000 holidays
- Update: Daily
- Format: Pipe-delimited (|)

**4. Counterparties**
- Table: `gmp_cis_sta_dly_counterparty`
- Records: ~7,000 entities
- Update: Daily
- Format: Pipe-delimited (|)

### ETL Process

```
┌─────────────┐
│ GMP System  │
└──────┬──────┘
       │ 2:00 AM - Extract
       ▼
┌─────────────┐
│  CSV Files  │
└──────┬──────┘
       │ 2:30 AM - Transfer
       ▼
┌─────────────┐
│ Shared Dir  │
└──────┬──────┘
       │ 3:00 AM - Hive Refresh
       ▼
┌─────────────┐
│ Hive Tables │ (External)
└──────┬──────┘
       │ Real-time - Query
       ▼
┌─────────────┐
│  CisTrade   │
└─────────────┘
```

### Monitoring

**Health Checks**:
- File arrival monitoring
- Row count validation
- Data quality checks
- Timestamp verification

**Alerts**:
- Missing file (> 1 hour late)
- Empty file
- Significant row count change (±10%)
- Format errors

## ACL Integration

### Overview

**Purpose**: Authentication and authorization

**Type**: Real-time queries

**Source**: Hive tables (gmp_cis ACL tables)

**Authentication Flow**:

```
User Login
  ↓
Query ACL User Table
  ↓ (User found?)
Query ACL Group
  ↓
Query ACL Permissions
  ↓
Build Permission Map
  ↓
Create Session
```

### ACL Tables

**1. cis_acl_user**
- User credentials
- Group membership
- Status (enabled/disabled)

**2. cis_acl_group**
- Group definitions
- Group hierarchy

**3. cis_acl_permission**
- Permission definitions
- Access levels (READ/WRITE/READ_WRITE)

**4. cis_acl_user_group**
- User-to-group mappings

### Session Management

**Session Data**:
```python
{
    'user_login': 'jsmith',
    'user_id': '12345',
    'user_name': 'John Smith',
    'user_email': 'jsmith@company.com',
    'user_group_id': '1',
    'user_group_name': 'Checkers',
    'user_permissions': {
        'cis-portfolio': 'READ_WRITE',
        'cis-udf': 'READ',
        'cis-audit': 'READ'
    }
}
```

**Session Timeout**: 8 hours

## Market Data Feeds

### Bloomberg Integration

**Type**: API (Real-time)

**Frequency**: Every 15 minutes

**Coverage**: 150+ currency pairs

**Endpoint**: Bloomberg API

**Data Retrieved**:
- Bid rate
- Ask rate
- Mid rate (used for valuation)
- Timestamp
- Source identifier

**Authentication**: API key

**Error Handling**:
- Retry 3 times on failure
- Fall back to Reuters if unavailable
- Alert market data team

### Reuters Integration

**Type**: API (Real-time)

**Frequency**: Every 30 minutes

**Coverage**: 120+ currency pairs

**Purpose**: Backup to Bloomberg

**Process**: Same as Bloomberg

## Kudu Storage

### Overview

**Purpose**: Transactional data storage

**Type**: Direct connection via Impala

**Tables**: 6 main tables
- cis_portfolio
- cis_portfolio_history
- cis_audit_log
- cis_udf_master
- cis_udf_value
- cis_fx_rate

### Connection Configuration

```python
IMPALA_CONFIG = {
    'host': 'impala-host.company.com',
    'port': 21050,
    'database': 'gmp_cis',
    'auth_mechanism': 'PLAIN',
    'use_ssl': True,
    'timeout': 60
}
```

### Query Optimization

**Partitioning**: By status, date
**Caching**: Impala query cache
**Batch Operations**: Bulk inserts when possible

## Email Notifications

### SMTP Integration

**Purpose**: User notifications

**Events**:
- Portfolio submitted for approval
- Portfolio approved
- Portfolio rejected
- System alerts

**SMTP Configuration**:
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.company.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
```

**Email Templates**:
- Approval request
- Approval confirmation
- Rejection notification
- Alert notification

## Reporting Integration

### Export Formats

**CSV**: Comma-separated values
**Excel**: XLSX format using openpyxl
**PDF**: HTML to PDF using WeasyPrint

### Scheduled Reports

**Delivery**: Email
**Frequency**: Daily, Weekly, Monthly
**Recipients**: Configurable per report

## Future Integrations

### Planned

**1. SSO Integration**
- SAML 2.0
- Azure AD
- Timeline: Q2 2026

**2. Risk Engine**
- Real-time risk calculations
- VaR, stress testing
- Timeline: Q3 2026

**3. Trade Booking System**
- Auto-populate from trades
- Straight-through processing
- Timeline: Q4 2026

## API Endpoints (Future)

### REST API

**Planned Features**:
- Portfolio CRUD via API
- Audit log queries
- Reference data access

**Authentication**: OAuth 2.0

**Documentation**: OpenAPI/Swagger

**Timeline**: 2027

## Integration Monitoring

### Dashboards

**Metrics**:
- GMP ETL status
- ACL query latency
- Market data feed health
- Kudu connection pool
- Email delivery rate

**Tools**:
- Grafana dashboards
- Prometheus metrics
- ELK stack for logs

## Related Documentation

- [Business Processes](business-processes.md)
- [Data Flow](data-flow.md)
- [Architecture](../technical/architecture.md)
