# Hive vs Kudu: Production Decision Guide

## Executive Summary

This document provides a comprehensive analysis comparing **Hive Managed Tables (ORC + ACID)** and **Apache Kudu** for the CIS Trade Management System. Based on infrastructure constraints and use case requirements, **Hive with ORC + ACID** is the recommended approach.

| Decision Factor | Recommendation |
|-----------------|----------------|
| **Infrastructure** | Hive (already available) |
| **Use Case Fit** | Hive (trade management doesn't need sub-second writes) |
| **Cost** | Hive (no additional infrastructure) |
| **Complexity** | Hive (standard Hadoop ecosystem) |

---

## Table of Contents

1. [Current Situation](#current-situation)
2. [Technology Comparison](#technology-comparison)
3. [Hive (ORC + ACID) Analysis](#hive-orc--acid-analysis)
4. [Kudu Analysis](#kudu-analysis)
5. [Production Architecture](#production-architecture)
6. [Implementation Guidelines](#implementation-guidelines)
7. [Performance Optimization](#performance-optimization)
8. [Migration Strategy](#migration-strategy)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Decision Matrix](#decision-matrix)

---

## Current Situation

### Infrastructure Status
- **Hive:** Already deployed and operational
- **Kudu:** Infrastructure not suitable / not available
- **HiveServer2:** Running on `localhost:10000`
- **Database:** `gmp_cis`

### Application Requirements
- Trade Management System (Portfolio, Trade, Security data)
- CRUD operations with soft delete support
- Audit trail and historical data retention
- Reporting and analytics capabilities
- Moderate write volume (not high-frequency trading)

---

## Technology Comparison

### Feature Matrix

| Feature | Hive (ORC + ACID) | Kudu |
|---------|-------------------|------|
| **Write Latency** | 3-5 seconds | Sub-second |
| **Read Latency** | Good (columnar) | Excellent |
| **UPDATE Support** | Yes (ACID) | Native |
| **DELETE Support** | Yes (ACID) | Native |
| **Concurrency** | Limited (~10-20 writes) | High (1000s) |
| **Storage Format** | ORC on HDFS | Own engine |
| **Compression** | SNAPPY, ZLIB, LZO | LZ4, ZLIB |
| **Partitioning** | Yes | Yes (hash/range) |
| **Primary Key** | No (clustered buckets) | Yes (native) |
| **Schema Evolution** | Add columns | Add/drop columns |
| **Transactions** | Single table ACID | Row-level |
| **Integration** | Spark, Impala, Presto | Impala, Spark |

### Use Case Suitability

| Use Case | Hive | Kudu | Winner |
|----------|------|------|--------|
| Batch ETL | Excellent | Good | Hive |
| Real-time Ingest | Poor | Excellent | Kudu |
| Analytics/Reporting | Excellent | Good | Hive |
| OLTP Workloads | Poor | Good | Kudu |
| Historical Data | Excellent | Good | Hive |
| Time-series Data | Good | Excellent | Kudu |
| Data Warehousing | Excellent | Good | Hive |

---

## Hive (ORC + ACID) Analysis

### Advantages

| # | Advantage | Business Impact |
|---|-----------|-----------------|
| 1 | **Already Available** | Zero infrastructure cost, immediate deployment |
| 2 | **Mature Ecosystem** | 10+ years production stability, extensive documentation |
| 3 | **SQL Compatibility** | Standard HiveQL, minimal learning curve |
| 4 | **Cost Effective** | No additional hardware, licensing, or training |
| 5 | **ORC Efficiency** | 70-90% compression ratio, fast columnar reads |
| 6 | **Wide Integration** | Works with Spark, Impala, Presto, Python |
| 7 | **ACID Transactions** | Full support in Hive 3.x+ for INSERT/UPDATE/DELETE |
| 8 | **Schema Evolution** | Add columns without rewriting data |
| 9 | **Partitioning** | Efficient data organization by date/category |
| 10 | **Backup/Recovery** | Standard HDFS snapshot and replication tools |

### Disadvantages

| # | Disadvantage | Impact Level | Mitigation Strategy |
|---|--------------|--------------|---------------------|
| 1 | **Slow Writes** | Medium | Batch inserts (100-1000 records) |
| 2 | **UPDATE Latency** | Medium | Off-peak batch updates |
| 3 | **No Real-time** | Low* | Hybrid with Redis cache |
| 4 | **Compaction Required** | Low | Scheduled maintenance |
| 5 | **Limited Concurrency** | Medium | Connection pooling, queuing |
| 6 | **MapReduce Dependency** | Low | Accept latency trade-off |
| 7 | **No Multi-table TX** | Low | Application-level handling |
| 8 | **Lock Contention** | Medium | Partition-level design |

*Low impact because trade management doesn't require real-time (<1s) writes

### Verified Capabilities (POC Results)

```
Operation       | Status    | Latency
----------------|-----------|----------
INSERT          | Working   | 3-4 seconds
UPDATE          | Working   | 3-4 seconds
DELETE (soft)   | Working   | 3-4 seconds
SELECT          | Working   | <1 second
JOIN            | Working   | 1-2 seconds
Soft Delete     | Working   | 3-4 seconds
Restore         | Working   | 3-4 seconds
```

---

## Kudu Analysis

### Advantages

| # | Advantage | Details |
|---|-----------|---------|
| 1 | **Fast Writes** | Sub-second INSERT/UPDATE/DELETE |
| 2 | **Real-time Analytics** | Combines OLTP + OLAP in one system |
| 3 | **High Concurrency** | Handles thousands of concurrent operations |
| 4 | **No Manual Compaction** | Automatic background maintenance |
| 5 | **Primary Key Support** | Native enforcement, fast lookups |
| 6 | **Impala Integration** | Direct queries without data movement |

### Disadvantages

| # | Disadvantage | Impact |
|---|--------------|--------|
| 1 | **Infrastructure Required** | Need dedicated Kudu tablet servers |
| 2 | **Additional Complexity** | Another distributed system to manage |
| 3 | **Cost** | Hardware, potential licensing, training |
| 4 | **Limited Ecosystem** | Primarily Impala for optimal queries |
| 5 | **Not Available** | Current infrastructure doesn't support it |
| 6 | **Operational Overhead** | Tablet server management, rebalancing |

---

## Production Architecture

### Recommended: Hybrid Architecture with Hive

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                               │
│                      Django Web Application                              │
│                    (Bootstrap 5 + REST APIs)                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          SERVICE LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │ PortfolioService│  │  TradeService   │  │   ReportingService      │  │
│  │   (CRUD + BL)   │  │  (CRUD + BL)    │  │   (Analytics)           │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        REPOSITORY LAYER                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │ HiveRepository  │  │  CacheRepository│  │   BatchWriteQueue       │  │
│  │ (PyHive/JDBC)   │  │  (Redis)        │  │   (Async Processing)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │    Redis     │ │  PostgreSQL  │ │     Hive     │
           │    Cache     │ │   Metadata   │ │  (ORC+ACID)  │
           │              │ │              │ │              │
           │ - Hot data   │ │ - Users      │ │ - Portfolios │
           │ - Sessions   │ │ - Configs    │ │ - Trades     │
           │ - Recent     │ │ - Lookups    │ │ - History    │
           │   trades     │ │ - ACL        │ │ - Audit logs │
           └──────────────┘ └──────────────┘ └──────────────┘
```

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           WRITE PATH                                     │
│                                                                          │
│   User Request ──► Django View ──► Service Layer ──► Batch Queue        │
│                                          │               │               │
│                                          ▼               ▼               │
│                                    Redis Cache     Hive (Async)          │
│                                   (Immediate)     (Batched)              │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           READ PATH                                      │
│                                                                          │
│   User Request ──► Django View ──► Service Layer                        │
│                                          │                               │
│                          ┌───────────────┼───────────────┐               │
│                          ▼               ▼               ▼               │
│                    Redis Cache     PostgreSQL         Hive               │
│                    (Cache Hit)     (Metadata)     (Cache Miss)           │
│                          │               │               │               │
│                          └───────────────┴───────────────┘               │
│                                          │                               │
│                                          ▼                               │
│                                    Response to User                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Technology | Responsibility | Latency Target |
|-------|------------|----------------|----------------|
| **Hot Cache** | Redis | Active sessions, recent data | <10ms |
| **Metadata** | PostgreSQL | Users, configs, lookups | <50ms |
| **Data Store** | Hive (ORC) | All business data | <5s write, <1s read |
| **Archive** | Hive Partitions | Historical data (>1 year) | <5s read |

---

## Implementation Guidelines

### 1. Table Design

```sql
-- Portfolio Table with Partitioning
CREATE TABLE gmp_cis.portfolio_hive (
    portfolio_id     STRING,
    portfolio_name   STRING,
    portfolio_code   STRING,
    portfolio_type   STRING,
    currency         STRING,
    manager_name     STRING,
    description      STRING,
    status           STRING,
    created_at       TIMESTAMP,
    created_by       STRING,
    updated_at       TIMESTAMP,
    updated_by       STRING,
    deleted_at       TIMESTAMP
)
CLUSTERED BY (portfolio_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- Trade Table with Date Partitioning
CREATE TABLE gmp_cis.trade_hive (
    trade_id         STRING,
    portfolio_id     STRING,
    security_id      STRING,
    security_name    STRING,
    trade_type       STRING,
    quantity         DECIMAL(18,4),
    price            DECIMAL(18,6),
    trade_amount     DECIMAL(18,2),
    currency         STRING,
    settlement_date  DATE,
    status           STRING,
    broker           STRING,
    notes            STRING,
    created_at       TIMESTAMP,
    created_by       STRING,
    updated_at       TIMESTAMP,
    updated_by       STRING,
    deleted_at       TIMESTAMP
)
PARTITIONED BY (trade_date DATE)
CLUSTERED BY (trade_id) INTO 8 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);
```

### 2. Connection Management

```python
# hive_connection.py - Production Configuration
HIVE_PRODUCTION_CONFIG = {
    'HOST': os.environ.get('HIVE_HOST', 'hiveserver2.company.com'),
    'PORT': int(os.environ.get('HIVE_PORT', '10000')),
    'DATABASE': os.environ.get('HIVE_DB', 'gmp_cis'),
    'AUTH': os.environ.get('HIVE_AUTH', 'KERBEROS'),  # Production auth
    'KERBEROS_SERVICE_NAME': 'hive',
    'POOL_SIZE': 10,
    'POOL_TIMEOUT': 30,
    'QUERY_TIMEOUT': 300,
}

class HiveConnectionPool:
    """Production-grade connection pool for Hive."""

    def __init__(self, config=HIVE_PRODUCTION_CONFIG):
        self.config = config
        self._pool = Queue(maxsize=config['POOL_SIZE'])
        self._lock = threading.Lock()

    def get_connection(self):
        """Get connection from pool with timeout."""
        try:
            return self._pool.get(timeout=self.config['POOL_TIMEOUT'])
        except Empty:
            return self._create_connection()

    def return_connection(self, conn):
        """Return connection to pool."""
        try:
            self._pool.put_nowait(conn)
        except Full:
            conn.close()
```

### 3. Batch Write Implementation

```python
# batch_writer.py - Efficient batch inserts
class HiveBatchWriter:
    """
    Batch writer for efficient Hive inserts.
    Collects records and flushes in batches.
    """

    def __init__(self, table_name, batch_size=100, flush_interval=30):
        self.table_name = table_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.batch = []
        self.last_flush = time.time()
        self._lock = threading.Lock()

    def add(self, record: dict):
        """Add record to batch."""
        with self._lock:
            self.batch.append(record)

            if self._should_flush():
                self.flush()

    def _should_flush(self):
        """Check if batch should be flushed."""
        return (
            len(self.batch) >= self.batch_size or
            time.time() - self.last_flush >= self.flush_interval
        )

    def flush(self):
        """Flush batch to Hive."""
        if not self.batch:
            return

        records = self.batch
        self.batch = []
        self.last_flush = time.time()

        # Build multi-row INSERT
        columns = list(records[0].keys())
        values_list = []

        for record in records:
            values = [self._format_value(record[col]) for col in columns]
            values_list.append(f"({', '.join(values)})")

        query = f"""
            INSERT INTO {self.table_name} ({', '.join(columns)})
            VALUES {', '.join(values_list)}
        """

        # Execute with retry
        self._execute_with_retry(query)

    def _execute_with_retry(self, query, max_retries=3):
        """Execute query with retry logic."""
        for attempt in range(max_retries):
            try:
                conn_manager.execute_write(query)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
```

### 4. Soft Delete Pattern

```python
# Repository base class soft delete implementation
class HiveBaseRepository:

    def soft_delete(self, record_id: str, deleted_by: str = 'system') -> bool:
        """
        Soft delete - sets deleted_at timestamp instead of removing.

        Benefits:
        - Full audit trail maintained
        - Easy restore capability
        - No data loss risk
        - Compliance friendly
        """
        now = datetime.now()
        query = f"""
            UPDATE {self.full_table_name}
            SET
                deleted_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_by = '{deleted_by}'
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NULL
        """
        return self._execute_acid_write(query)

    def restore(self, record_id: str, restored_by: str = 'system') -> bool:
        """Restore a soft-deleted record."""
        now = datetime.now()
        query = f"""
            UPDATE {self.full_table_name}
            SET
                deleted_at = NULL,
                updated_at = '{now.strftime('%Y-%m-%d %H:%M:%S')}',
                updated_by = '{restored_by}'
            WHERE {self.primary_key} = '{record_id}'
            AND deleted_at IS NOT NULL
        """
        return self._execute_acid_write(query)

    def find_all(self, include_deleted: bool = False):
        """Find all records, optionally including deleted."""
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        query = f"SELECT * FROM {self.full_table_name} {where}"
        return self.conn_manager.execute_query(query)
```

---

## Performance Optimization

### 1. Query Optimization

```sql
-- Use partition pruning
SELECT * FROM trade_hive
WHERE trade_date BETWEEN '2024-01-01' AND '2024-01-31'
AND deleted_at IS NULL;

-- Avoid SELECT * in production
SELECT trade_id, security_name, quantity, price, status
FROM trade_hive
WHERE portfolio_id = 'PF001'
AND deleted_at IS NULL;

-- Use LIMIT for pagination
SELECT * FROM trade_hive
WHERE deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 100 OFFSET 0;
```

### 2. Compaction Schedule

```sql
-- Minor compaction (daily) - consolidates delta files
ALTER TABLE trade_hive COMPACT 'minor';

-- Major compaction (weekly) - full table rewrite
ALTER TABLE trade_hive COMPACT 'major';

-- Check compaction status
SHOW COMPACTIONS;
```

### 3. Statistics Collection

```sql
-- Collect table statistics for query optimization
ANALYZE TABLE portfolio_hive COMPUTE STATISTICS;
ANALYZE TABLE trade_hive COMPUTE STATISTICS;

-- Collect column statistics
ANALYZE TABLE trade_hive COMPUTE STATISTICS FOR COLUMNS
    trade_id, portfolio_id, status, trade_date;
```

### 4. Caching Strategy

```python
# Redis cache integration
class CachedHiveRepository:
    """Repository with Redis caching layer."""

    def __init__(self, base_repo, cache_ttl=300):
        self.repo = base_repo
        self.cache = redis.Redis(host='localhost', port=6379)
        self.ttl = cache_ttl

    def find_by_id(self, record_id: str):
        """Find with cache-aside pattern."""
        cache_key = f"{self.repo.table_name}:{record_id}"

        # Try cache first
        cached = self.cache.get(cache_key)
        if cached:
            return json.loads(cached)

        # Cache miss - query Hive
        record = self.repo.find_by_id(record_id)

        if record:
            self.cache.setex(
                cache_key,
                self.ttl,
                json.dumps(record, default=str)
            )

        return record

    def invalidate(self, record_id: str):
        """Invalidate cache on update/delete."""
        cache_key = f"{self.repo.table_name}:{record_id}"
        self.cache.delete(cache_key)
```

---

## Migration Strategy

### Phase 1: POC Validation (Completed)
- [x] Create hive_poc Django app
- [x] Implement CRUD with soft delete
- [x] Verify ACID operations work
- [x] Test UPDATE and DELETE
- [x] Create sample data

### Phase 2: Production Preparation
- [ ] Set up production HiveServer2 connection
- [ ] Implement connection pooling
- [ ] Add retry logic and error handling
- [ ] Set up monitoring and alerting
- [ ] Create compaction schedules

### Phase 3: Data Migration
- [ ] Export existing Kudu/Impala data
- [ ] Transform to Hive table format
- [ ] Load historical data
- [ ] Verify data integrity

### Phase 4: Application Cutover
- [ ] Update repository configurations
- [ ] Deploy to staging environment
- [ ] Run integration tests
- [ ] Performance testing
- [ ] Production deployment

### Phase 5: Post-Migration
- [ ] Monitor performance metrics
- [ ] Tune compaction schedules
- [ ] Optimize slow queries
- [ ] Document operational procedures

---

## Monitoring & Maintenance

### Key Metrics to Monitor

| Metric | Threshold | Alert Level |
|--------|-----------|-------------|
| Query latency (p95) | > 5s | Warning |
| Query latency (p99) | > 10s | Critical |
| Failed queries | > 1% | Warning |
| Connection pool usage | > 80% | Warning |
| Delta files per table | > 100 | Warning |
| Compaction queue | > 10 | Warning |

### Maintenance Tasks

| Task | Frequency | Command/Action |
|------|-----------|----------------|
| Minor compaction | Daily (off-peak) | `ALTER TABLE x COMPACT 'minor'` |
| Major compaction | Weekly | `ALTER TABLE x COMPACT 'major'` |
| Statistics update | Daily | `ANALYZE TABLE x COMPUTE STATISTICS` |
| Connection pool health | Continuous | Monitor pool utilization |
| Query performance | Continuous | Log slow queries (>5s) |

### Operational Runbook

```bash
# Check HiveServer2 status
beeline -u "jdbc:hive2://localhost:10000" -e "SELECT 1"

# View active sessions
beeline -u "jdbc:hive2://localhost:10000" -e "SHOW SESSIONS"

# Check compaction status
beeline -u "jdbc:hive2://localhost:10000" -e "SHOW COMPACTIONS"

# View table statistics
beeline -u "jdbc:hive2://localhost:10000" -e "DESCRIBE FORMATTED trade_hive"

# Monitor query performance
tail -f /var/log/hive/hiveserver2.log | grep -i "completed"
```

---

## Decision Matrix

### Final Recommendation: Hive (ORC + ACID)

| Criteria | Weight | Hive Score | Kudu Score | Hive Weighted | Kudu Weighted |
|----------|--------|------------|------------|---------------|---------------|
| Infrastructure Available | 30% | 10 | 0 | 3.0 | 0.0 |
| Use Case Fit | 25% | 8 | 9 | 2.0 | 2.25 |
| Operational Complexity | 20% | 8 | 5 | 1.6 | 1.0 |
| Cost | 15% | 10 | 3 | 1.5 | 0.45 |
| Performance | 10% | 6 | 9 | 0.6 | 0.9 |
| **TOTAL** | **100%** | | | **8.7** | **4.6** |

### Decision: **HIVE (ORC + ACID)**

**Rationale:**
1. Infrastructure is already in place - zero additional cost
2. ACID transactions verified working in POC
3. Soft delete pattern works perfectly
4. Write latency (3-5s) acceptable for trade management
5. Excellent read performance with ORC columnar format
6. Standard ecosystem - Spark, Impala, Presto compatible

---

## Appendix

### A. POC Verification Results

```
Test                          | Result  | Notes
------------------------------|---------|----------------------------------
INSERT single record          | PASS    | 3.5s average
INSERT batch (100 records)    | PASS    | 8s average
UPDATE single record          | PASS    | 3.5s average
Soft DELETE                   | PASS    | 3.5s average
Restore deleted record        | PASS    | 3.5s average
SELECT all records            | PASS    | <1s
SELECT with WHERE             | PASS    | <1s
PyHive connection             | PASS    | auth='NONE' for local
Django integration            | PASS    | Full CRUD working
```

### B. Configuration Reference

```python
# Production Hive Configuration
HIVE_PRODUCTION_CONFIG = {
    'HOST': 'hiveserver2.production.company.com',
    'PORT': 10000,
    'DATABASE': 'gmp_cis',
    'AUTH': 'KERBEROS',
    'KERBEROS_SERVICE_NAME': 'hive',
    'POOL_SIZE': 20,
    'QUERY_TIMEOUT': 300,
}

# Development Hive Configuration
HIVE_DEV_CONFIG = {
    'HOST': 'localhost',
    'PORT': 10000,
    'DATABASE': 'gmp_cis',
    'AUTH': 'NONE',
    'POOL_SIZE': 5,
    'QUERY_TIMEOUT': 60,
}
```

### C. Related Documentation

- [Hive POC README](../README.md)
- [Table DDL Scripts](../sql/create_hive_tables.sql)
- [Docker Setup Guide](../docker/README.md)
- [API Documentation](./API.md)

---

*Document Version: 1.0*
*Last Updated: February 2026*
*Author: CIS Trade Hive Team*
