# Cloudera Kudu Data/Metadata Sync Strategy
## Production, UAT, and DR Environment Synchronization

**Document Version:** 1.0
**Date:** 2026-01-21
**Domain:** Banking / Trade Management System
**Author:** CIS Trade Hive Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [Sync Strategy Options](#3-sync-strategy-options)
4. [Recommended Native Kudu Sync Approach](#4-recommended-native-kudu-sync-approach)
5. [Implementation Plan](#5-implementation-plan)
6. [Table Uplift Strategy](#6-table-uplift-strategy)
7. [Data Masking for Non-Prod Environments](#7-data-masking-for-non-prod-environments)
8. [Monitoring and Validation](#8-monitoring-and-validation)
9. [Disaster Recovery Procedures](#9-disaster-recovery-procedures)
10. [Appendix: Scripts and Commands](#10-appendix-scripts-and-commands)

---

## 1. Executive Summary

This document outlines the native Cloudera Kudu synchronization strategy for maintaining data consistency across Production (PROD), User Acceptance Testing (UAT), and Disaster Recovery (DR) environments in our banking trade management system.

### Key Objectives:
- **Zero data loss** for DR failover scenarios
- **Consistent test data** for UAT environment
- **Minimal latency** for real-time sync to DR
- **Data security compliance** with banking regulations
- **Automated sync processes** with monitoring

### Environment Matrix:

| Environment | Purpose | Sync Direction | Sync Type | Frequency |
|-------------|---------|----------------|-----------|-----------|
| PROD | Live operations | Source | - | - |
| DR | Disaster Recovery | PROD → DR | Real-time | Continuous |
| UAT | Testing | PROD → UAT | Batch | Daily/On-demand |

---

## 2. Current Architecture Overview

### 2.1 Existing Cloudera Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION CLUSTER                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Kudu Master │  │ Kudu Master │  │ Kudu Master │   (HA)       │
│  │   Node 1    │  │   Node 2    │  │   Node 3    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│         │                │                │                      │
│  ┌──────┴────────────────┴────────────────┴──────┐              │
│  │              Kudu Tablet Servers              │              │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐         │              │
│  │  │ TServer │ │ TServer │ │ TServer │  (N)    │              │
│  │  └─────────┘ └─────────┘ └─────────┘         │              │
│  └───────────────────────────────────────────────┘              │
│                          │                                       │
│  ┌───────────────────────┴───────────────────────┐              │
│  │              Impala Daemons                   │              │
│  │  (Query Engine for Kudu Tables)               │              │
│  └───────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Database Schema (gmp_cis)

**Core Tables:**
| Table Name | Type | Records (Est.) | Sync Priority |
|------------|------|----------------|---------------|
| cis_portfolio | Kudu | 10K+ | HIGH |
| cis_trade | Kudu | 1M+ | HIGH |
| cis_security | Kudu | 50K+ | HIGH |
| cis_audit_log | Kudu | 10M+ | MEDIUM |
| cis_udf_field | Kudu | 1K | HIGH |
| cis_counterparty | Kudu | 5K | MEDIUM |
| gmp_cis_sta_dly_currency | Hive/Kudu | 500 | LOW |
| gmp_cis_sta_dly_country | Hive/Kudu | 300 | LOW |

---

## 3. Sync Strategy Options

### 3.1 Option Comparison Matrix

| Option | Complexity | Latency | Data Loss Risk | Cost | Recommended For |
|--------|------------|---------|----------------|------|-----------------|
| **Kudu Native Replication** | Medium | Low (<1s) | Minimal | Low | DR |
| **Impala CTAS + INSERT** | Low | High (batch) | Batch window | Low | UAT |
| **Spark Streaming** | High | Low | Minimal | Medium | Real-time DR |
| **Cloudera Replication Manager** | Low | Medium | Configurable | License | All |
| **Custom CDC Pipeline** | High | Low | Minimal | High | Complex scenarios |

### 3.2 Recommended Hybrid Approach

```
┌──────────────────────────────────────────────────────────────────┐
│                     SYNC ARCHITECTURE                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   PROD ─────────┬─────────────────────────────────────► DR       │
│                 │     Kudu Native Replication                     │
│                 │     (Real-time, <1 second latency)              │
│                 │                                                 │
│                 └─────────────────────────────────────► UAT      │
│                       Batch Sync (Impala CTAS)                    │
│                       (Daily at 02:00 UTC)                        │
│                       + Data Masking                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Recommended Native Kudu Sync Approach

### 4.1 DR Sync: Kudu Cross-Cluster Replication

**Architecture:**
```
PROD Cluster                          DR Cluster
┌─────────────┐                      ┌─────────────┐
│ Kudu Master │◄────────────────────►│ Kudu Master │
│   (Leader)  │   Raft Consensus     │  (Follower) │
└─────────────┘                      └─────────────┘
      │                                    │
      ▼                                    ▼
┌─────────────┐                      ┌─────────────┐
│   Tablet    │────── WAL Logs ─────►│   Tablet    │
│   Server    │     Replication      │   Server    │
└─────────────┘                      └─────────────┘
```

**Configuration (kudu-master.conf):**

```properties
# PROD Master Configuration
--master_addresses=prod-kudu-master-1:7051,prod-kudu-master-2:7051,prod-kudu-master-3:7051

# Enable cross-datacenter replication
--enable_leader_failure_detection=true
--leader_failure_max_missed_heartbeat_periods=3.0
--raft_heartbeat_interval_ms=500

# Replication to DR
--remote_bootstrap_begin_session_timeout_ms=30000
--remote_bootstrap_end_session_timeout_ms=180000
```

### 4.2 UAT Sync: Batch Replication via Impala

**Daily Sync Process:**

```sql
-- Step 1: Create staging tables in UAT
CREATE TABLE IF NOT EXISTS gmp_cis_uat.cis_portfolio_staging
LIKE gmp_cis.cis_portfolio
STORED AS KUDU;

-- Step 2: Truncate and reload
TRUNCATE TABLE gmp_cis_uat.cis_portfolio_staging;

-- Step 3: Insert with data masking
INSERT INTO gmp_cis_uat.cis_portfolio_staging
SELECT
    name,
    description,
    currency,
    CONCAT('UAT_MGR_', SUBSTR(MD5(manager), 1, 8)) as manager,  -- Masked
    CONCAT('UAT_CLIENT_', SUBSTR(MD5(portfolio_client), 1, 8)) as portfolio_client,  -- Masked
    cash_balance * 0.01 as cash_balance,  -- Scaled down
    status,
    cost_centre_code,
    corp_code,
    account_group,
    portfolio_group,
    report_group,
    entity_group,
    revaluation_status,
    is_active,
    created_at,
    updated_at,
    'UAT_SYNC' as updated_by,
    src_system,
    submitted_by,
    submitted_at,
    validated_by,
    validated_at,
    settled_by,
    settled_at,
    cancelled_by,
    cancelled_at,
    cancel_reason
FROM gmp_cis.cis_portfolio
WHERE is_active = true;

-- Step 4: Swap tables
ALTER TABLE gmp_cis_uat.cis_portfolio RENAME TO gmp_cis_uat.cis_portfolio_old;
ALTER TABLE gmp_cis_uat.cis_portfolio_staging RENAME TO gmp_cis_uat.cis_portfolio;
DROP TABLE IF EXISTS gmp_cis_uat.cis_portfolio_old;
```

---

## 5. Implementation Plan

### 5.1 Phase 1: DR Setup (Week 1-2)

| Task | Description | Owner | Duration |
|------|-------------|-------|----------|
| 1.1 | Configure Kudu master replication | Infra Team | 2 days |
| 1.2 | Set up tablet server sync | Infra Team | 2 days |
| 1.3 | Configure network connectivity (VPN/Direct Connect) | Network Team | 3 days |
| 1.4 | Initial full sync | DBA Team | 2 days |
| 1.5 | Validation and testing | QA Team | 3 days |

### 5.2 Phase 2: UAT Sync Pipeline (Week 3-4)

| Task | Description | Owner | Duration |
|------|-------------|-------|----------|
| 2.1 | Create UAT database schema | DBA Team | 1 day |
| 2.2 | Develop sync scripts with masking | Dev Team | 3 days |
| 2.3 | Set up Oozie/Airflow scheduling | Dev Team | 2 days |
| 2.4 | Configure data masking rules | Security Team | 2 days |
| 2.5 | End-to-end testing | QA Team | 3 days |

### 5.3 Phase 3: Monitoring & Automation (Week 5-6)

| Task | Description | Owner | Duration |
|------|-------------|-------|----------|
| 3.1 | Set up Cloudera Manager alerts | Infra Team | 1 day |
| 3.2 | Create sync monitoring dashboard | Dev Team | 2 days |
| 3.3 | Implement automated validation | Dev Team | 2 days |
| 3.4 | Documentation and runbooks | All Teams | 2 days |
| 3.5 | DR failover drill | All Teams | 1 day |

---

## 6. Table Uplift Strategy

### 6.1 Hive to Kudu Migration

For tables currently in Hive that need to be uplifted to Kudu:

```sql
-- Step 1: Create Kudu table with proper schema
CREATE TABLE gmp_cis.cis_portfolio_kudu (
    name STRING NOT NULL,
    description STRING,
    currency STRING,
    manager STRING,
    portfolio_client STRING,
    cash_balance DECIMAL(18,4),
    status STRING,
    cost_centre_code STRING,
    corp_code STRING,
    account_group STRING,
    portfolio_group STRING,
    report_group STRING,
    entity_group STRING,
    revaluation_status STRING,
    is_active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    updated_by STRING,
    src_system STRING,
    submitted_by STRING,
    submitted_at TIMESTAMP,
    validated_by STRING,
    validated_at TIMESTAMP,
    settled_by STRING,
    settled_at TIMESTAMP,
    cancelled_by STRING,
    cancelled_at TIMESTAMP,
    cancel_reason STRING,
    PRIMARY KEY (name)
)
PARTITION BY HASH (name) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051',
    'kudu.num_tablet_replicas' = '3'
);

-- Step 2: Migrate data
INSERT INTO gmp_cis.cis_portfolio_kudu
SELECT * FROM gmp_cis.cis_portfolio_hive;

-- Step 3: Validate row counts
SELECT
    (SELECT COUNT(*) FROM gmp_cis.cis_portfolio_hive) as hive_count,
    (SELECT COUNT(*) FROM gmp_cis.cis_portfolio_kudu) as kudu_count;

-- Step 4: Rename tables (after validation)
ALTER TABLE gmp_cis.cis_portfolio_hive RENAME TO gmp_cis.cis_portfolio_hive_backup;
ALTER TABLE gmp_cis.cis_portfolio_kudu RENAME TO gmp_cis.cis_portfolio;
```

### 6.2 Schema Evolution Guidelines

**Adding New Columns:**
```sql
-- Kudu supports adding nullable columns
ALTER TABLE gmp_cis.cis_portfolio ADD COLUMNS (
    accounting_section STRING
);
```

**Primary Key Considerations:**
- Kudu requires a primary key
- Choose columns with high cardinality
- Consider composite keys for uniqueness
- Primary key columns cannot be changed after table creation

### 6.3 Partitioning Strategy

```sql
-- Range partitioning for time-series data (trades, audit logs)
CREATE TABLE gmp_cis.cis_trade (
    trade_id BIGINT NOT NULL,
    trade_date DATE NOT NULL,
    ...
    PRIMARY KEY (trade_id, trade_date)
)
PARTITION BY HASH (trade_id) PARTITIONS 32,
             RANGE (trade_date) (
                PARTITION VALUES < '2025-01-01',
                PARTITION '2025-01-01' <= VALUES < '2026-01-01',
                PARTITION '2026-01-01' <= VALUES < '2027-01-01',
                PARTITION VALUES >= '2027-01-01'
             )
STORED AS KUDU;
```

---

## 7. Data Masking for Non-Prod Environments

### 7.1 Masking Rules (Banking Compliance)

| Field Type | Masking Rule | Example |
|------------|--------------|---------|
| Customer Name | Hash + Prefix | `UAT_CUST_a1b2c3d4` |
| Account Number | Partial mask | `****1234` |
| Email | Domain replace | `user@uat.masked.com` |
| Phone | Randomize | `+65-XXXX-XXXX` |
| Financial Amount | Scale factor | `amount * 0.01` |
| Address | Anonymize | `123 UAT Street, Test City` |

### 7.2 Masking Function Library

```sql
-- Create masking UDFs in Impala
CREATE FUNCTION gmp_cis.mask_name(STRING)
RETURNS STRING
LOCATION '/user/hive/udfs/mask_functions.jar'
SYMBOL='com.bank.udf.MaskName';

CREATE FUNCTION gmp_cis.mask_account(STRING)
RETURNS STRING
LOCATION '/user/hive/udfs/mask_functions.jar'
SYMBOL='com.bank.udf.MaskAccount';

CREATE FUNCTION gmp_cis.scale_amount(DECIMAL(18,4), DOUBLE)
RETURNS DECIMAL(18,4)
LOCATION '/user/hive/udfs/mask_functions.jar'
SYMBOL='com.bank.udf.ScaleAmount';
```

### 7.3 Masked Sync View Example

```sql
-- Create view for UAT sync with all masking applied
CREATE VIEW gmp_cis.v_portfolio_masked AS
SELECT
    name,
    CONCAT('UAT Portfolio - ', SUBSTR(name, 1, 10)) as description,
    currency,
    gmp_cis.mask_name(manager) as manager,
    gmp_cis.mask_name(portfolio_client) as portfolio_client,
    gmp_cis.scale_amount(cash_balance, 0.01) as cash_balance,
    status,
    cost_centre_code,
    corp_code,
    account_group,
    portfolio_group,
    report_group,
    entity_group,
    revaluation_status,
    is_active,
    created_at,
    updated_at,
    'MASKED' as updated_by,
    'UAT' as src_system,
    submitted_by,
    submitted_at,
    validated_by,
    validated_at,
    settled_by,
    settled_at,
    cancelled_by,
    cancelled_at,
    cancel_reason
FROM gmp_cis.cis_portfolio;
```

---

## 8. Monitoring and Validation

### 8.1 Sync Monitoring Metrics

| Metric | Threshold | Alert Level |
|--------|-----------|-------------|
| Replication Lag (DR) | > 5 seconds | CRITICAL |
| Sync Job Duration | > 2 hours | WARNING |
| Row Count Mismatch | > 0.1% | WARNING |
| Failed Sync Jobs | Any | CRITICAL |
| Tablet Server Health | < 100% | WARNING |

### 8.2 Validation Queries

```sql
-- Daily validation script
-- Run after each sync to ensure data integrity

-- 1. Row count comparison
SELECT
    'cis_portfolio' as table_name,
    (SELECT COUNT(*) FROM gmp_cis.cis_portfolio) as prod_count,
    (SELECT COUNT(*) FROM gmp_cis_dr.cis_portfolio) as dr_count,
    (SELECT COUNT(*) FROM gmp_cis_uat.cis_portfolio) as uat_count;

-- 2. Latest record timestamp check
SELECT
    'PROD' as env, MAX(updated_at) as latest_update
FROM gmp_cis.cis_portfolio
UNION ALL
SELECT
    'DR' as env, MAX(updated_at) as latest_update
FROM gmp_cis_dr.cis_portfolio
UNION ALL
SELECT
    'UAT' as env, MAX(updated_at) as latest_update
FROM gmp_cis_uat.cis_portfolio;

-- 3. Checksum validation (sample)
SELECT
    'PROD' as env,
    COUNT(*) as row_count,
    SUM(CAST(HASH(name, status, currency) AS BIGINT)) as checksum
FROM gmp_cis.cis_portfolio
WHERE updated_at >= DATE_SUB(NOW(), INTERVAL 1 DAY);
```

### 8.3 Cloudera Manager Alerts Configuration

```json
{
  "alertRules": [
    {
      "name": "Kudu Replication Lag Alert",
      "condition": "kudu_tablet_server_replication_lag_ms > 5000",
      "severity": "CRITICAL",
      "notification": ["ops-team@bank.com", "sms:+65-XXXX-XXXX"]
    },
    {
      "name": "Kudu Tablet Server Down",
      "condition": "kudu_tablet_server_status != 'RUNNING'",
      "severity": "CRITICAL",
      "notification": ["ops-team@bank.com", "pagerduty"]
    },
    {
      "name": "Sync Job Failure",
      "condition": "oozie_job_status == 'KILLED' OR oozie_job_status == 'FAILED'",
      "severity": "WARNING",
      "notification": ["dev-team@bank.com"]
    }
  ]
}
```

---

## 9. Disaster Recovery Procedures

### 9.1 DR Failover Runbook

```
┌─────────────────────────────────────────────────────────────────┐
│                  DR FAILOVER PROCEDURE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Assess Situation (5 min)                               │
│  ├── Verify PROD cluster is unreachable                         │
│  ├── Check Cloudera Manager alerts                              │
│  └── Confirm with Infrastructure team                           │
│                                                                  │
│  Step 2: Initiate Failover (10 min)                             │
│  ├── Update DNS to point to DR cluster                          │
│  ├── Promote DR Kudu masters to primary                         │
│  └── Restart Impala daemons on DR                               │
│                                                                  │
│  Step 3: Validate DR Environment (15 min)                       │
│  ├── Run health check queries                                   │
│  ├── Verify application connectivity                            │
│  └── Test critical workflows                                    │
│                                                                  │
│  Step 4: Notify Stakeholders (5 min)                            │
│  ├── Send incident notification                                 │
│  └── Update status page                                         │
│                                                                  │
│  Total RTO Target: 35 minutes                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Failover Commands

```bash
#!/bin/bash
# dr_failover.sh - Execute DR Failover

set -e

echo "=== CIS Trade Hive DR Failover ==="
echo "Timestamp: $(date)"

# Step 1: Promote DR masters
echo "Step 1: Promoting DR Kudu masters..."
for master in dr-kudu-master-{1,2,3}; do
    ssh $master "sudo systemctl restart kudu-master"
done

# Step 2: Update configuration
echo "Step 2: Updating Impala configuration..."
for daemon in dr-impala-daemon-{1,2,3,4,5}; do
    ssh $daemon "sudo sed -i 's/prod-kudu-master/dr-kudu-master/g' /etc/impala/conf/impalad.conf"
    ssh $daemon "sudo systemctl restart impala-server"
done

# Step 3: Update DNS
echo "Step 3: Updating DNS records..."
# This would typically call your DNS API
# aws route53 change-resource-record-sets --hosted-zone-id XXXXX --change-batch file://dr-dns-update.json

# Step 4: Validate
echo "Step 4: Running validation..."
impala-shell -i dr-impala-daemon-1:21050 -q "SELECT COUNT(*) FROM gmp_cis.cis_portfolio;"

echo "=== Failover Complete ==="
```

### 9.3 Failback Procedure

```bash
#!/bin/bash
# dr_failback.sh - Execute DR Failback to PROD

set -e

echo "=== CIS Trade Hive DR Failback ==="
echo "Timestamp: $(date)"

# Step 1: Verify PROD is healthy
echo "Step 1: Verifying PROD cluster health..."
for master in prod-kudu-master-{1,2,3}; do
    ssh $master "kudu cluster ksck prod-kudu-master-1:7051"
done

# Step 2: Sync any DR changes back to PROD
echo "Step 2: Syncing DR changes to PROD..."
impala-shell -i dr-impala-daemon-1:21050 -f /opt/scripts/sync_dr_to_prod.sql

# Step 3: Update DNS back to PROD
echo "Step 3: Reverting DNS to PROD..."
# aws route53 change-resource-record-sets --hosted-zone-id XXXXX --change-batch file://prod-dns-update.json

# Step 4: Restart DR as replica
echo "Step 4: Reconfiguring DR as replica..."
for master in dr-kudu-master-{1,2,3}; do
    ssh $master "sudo systemctl restart kudu-master"
done

echo "=== Failback Complete ==="
```

---

## 10. Appendix: Scripts and Commands

### 10.1 Full Sync Script (UAT)

```bash
#!/bin/bash
# sync_prod_to_uat.sh
# Schedule: Daily at 02:00 UTC via Oozie/Airflow

set -e

LOG_FILE="/var/log/kudu_sync/uat_sync_$(date +%Y%m%d).log"
IMPALA_HOST="uat-impala-daemon-1:21050"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== UAT Sync Started: $(date) ==="

# List of tables to sync
TABLES=(
    "cis_portfolio"
    "cis_trade"
    "cis_security"
    "cis_counterparty"
    "cis_udf_field"
    "cis_audit_log"
)

for table in "${TABLES[@]}"; do
    echo "Syncing table: $table"

    # Create staging table
    impala-shell -i $IMPALA_HOST -q "
        DROP TABLE IF EXISTS gmp_cis_uat.${table}_staging;
        CREATE TABLE gmp_cis_uat.${table}_staging
        LIKE gmp_cis_uat.${table} STORED AS KUDU;
    "

    # Sync with masking (using the masked view)
    impala-shell -i $IMPALA_HOST -q "
        INSERT INTO gmp_cis_uat.${table}_staging
        SELECT * FROM gmp_cis.v_${table}_masked;
    "

    # Swap tables
    impala-shell -i $IMPALA_HOST -q "
        ALTER TABLE gmp_cis_uat.${table} RENAME TO gmp_cis_uat.${table}_old;
        ALTER TABLE gmp_cis_uat.${table}_staging RENAME TO gmp_cis_uat.${table};
        DROP TABLE IF EXISTS gmp_cis_uat.${table}_old;
    "

    echo "Completed: $table"
done

# Validation
echo "Running validation..."
impala-shell -i $IMPALA_HOST -f /opt/scripts/validate_sync.sql

echo "=== UAT Sync Completed: $(date) ==="
```

### 10.2 Kudu Health Check Script

```bash
#!/bin/bash
# kudu_health_check.sh

KUDU_MASTER="kudu-master-1:7051"

echo "=== Kudu Cluster Health Check ==="
echo "Timestamp: $(date)"
echo ""

# Cluster health
echo "1. Cluster Health Status:"
kudu cluster ksck $KUDU_MASTER

# Table list
echo ""
echo "2. Tables in gmp_cis database:"
kudu table list $KUDU_MASTER | grep gmp_cis

# Tablet server status
echo ""
echo "3. Tablet Server Status:"
kudu tserver list $KUDU_MASTER

# Replication status
echo ""
echo "4. Under-replicated Tablets:"
kudu cluster ksck $KUDU_MASTER 2>&1 | grep -i "under-replicated"

echo ""
echo "=== Health Check Complete ==="
```

### 10.3 Impala Table Creation Template

```sql
-- Template for creating Kudu-backed tables via Impala
-- Replace placeholders with actual values

CREATE TABLE IF NOT EXISTS gmp_cis.{TABLE_NAME} (
    -- Primary key columns (required, non-nullable)
    {PK_COLUMN} {PK_TYPE} NOT NULL,

    -- Regular columns
    {COLUMN_1} {TYPE_1},
    {COLUMN_2} {TYPE_2},
    ...

    -- Audit columns (recommended)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    updated_by STRING,
    src_system STRING DEFAULT 'CIS',
    is_active BOOLEAN DEFAULT TRUE,

    -- Define primary key
    PRIMARY KEY ({PK_COLUMN})
)
-- Partitioning strategy
PARTITION BY HASH ({PK_COLUMN}) PARTITIONS {NUM_PARTITIONS}
-- Optional: Range partitioning for time-series
-- PARTITION BY RANGE ({DATE_COLUMN}) (
--     PARTITION VALUES < '2025-01-01',
--     PARTITION '2025-01-01' <= VALUES < '2026-01-01'
-- )
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = '{KUDU_MASTERS}',
    'kudu.num_tablet_replicas' = '3'
);

-- Add table comment
COMMENT ON TABLE gmp_cis.{TABLE_NAME} IS '{TABLE_DESCRIPTION}';
```

### 10.4 Oozie Workflow for Scheduled Sync

```xml
<!-- oozie_sync_workflow.xml -->
<workflow-app name="kudu-uat-sync" xmlns="uri:oozie:workflow:0.5">
    <start to="sync-tables"/>

    <action name="sync-tables">
        <shell xmlns="uri:oozie:shell-action:0.3">
            <job-tracker>${jobTracker}</job-tracker>
            <name-node>${nameNode}</name-node>
            <exec>/opt/scripts/sync_prod_to_uat.sh</exec>
            <capture-output/>
        </shell>
        <ok to="validate-sync"/>
        <error to="send-failure-alert"/>
    </action>

    <action name="validate-sync">
        <shell xmlns="uri:oozie:shell-action:0.3">
            <job-tracker>${jobTracker}</job-tracker>
            <name-node>${nameNode}</name-node>
            <exec>/opt/scripts/validate_sync.sh</exec>
        </shell>
        <ok to="send-success-alert"/>
        <error to="send-failure-alert"/>
    </action>

    <action name="send-success-alert">
        <email xmlns="uri:oozie:email-action:0.2">
            <to>ops-team@bank.com</to>
            <subject>UAT Sync Completed Successfully</subject>
            <body>The daily UAT sync job completed at ${wf:lastModifiedTime()}</body>
        </email>
        <ok to="end"/>
        <error to="end"/>
    </action>

    <action name="send-failure-alert">
        <email xmlns="uri:oozie:email-action:0.2">
            <to>ops-team@bank.com,dev-team@bank.com</to>
            <subject>ALERT: UAT Sync Failed</subject>
            <body>The UAT sync job failed. Error: ${wf:errorMessage(wf:lastErrorNode())}</body>
        </email>
        <ok to="kill"/>
        <error to="kill"/>
    </action>

    <kill name="kill">
        <message>Workflow killed: ${wf:errorMessage(wf:lastErrorNode())}</message>
    </kill>

    <end name="end"/>
</workflow-app>
```

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-21 | CIS Trade Hive Team | Initial version |

---

## Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technical Lead | | | |
| DBA Lead | | | |
| Security Officer | | | |
| Project Manager | | | |
