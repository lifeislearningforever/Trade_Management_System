# Kudu Tables Generated from Hive

## Summary

Successfully generated Kudu table definitions for **15 tables** from the `cis` Hive database.

**Generated File**: `cis_hive_to_kudu_tables.sql` (368 lines)

---

## Tables Generated

| # | Hive Table | Kudu Table | Primary Key | Columns |
|---|------------|------------|-------------|---------|
| 1 | cis_audit_log | cis_audit_log_kudu | log_id | 30 |
| 2 | cis_group_permissions | cis_group_permissions_kudu | group_name, permission_id | 7 |
| 3 | cis_permission | cis_permission_kudu | permission_id | 6 |
| 4 | cis_portfolio | cis_portfolio_kudu | name | 17 |
| 5 | cis_udf_definition | cis_udf_definition_kudu | entity_type, field_name | 23 |
| 6 | cis_udf_option | cis_udf_option_kudu | entity_type, field_name, option_value | 8 |
| 7 | cis_udf_value | cis_udf_value_kudu | entity_id, entity_type, field_name | 14 |
| 8 | cis_udf_value_multi | cis_udf_value_multi_kudu | entity_id, entity_type, field_name, value | 10 |
| 9 | cis_user | cis_user_kudu | username | 14 |
| 10 | cis_user_group | cis_user_group_kudu | username, group_name | 7 |
| 11 | gmp_cis_sta_dly_calendar | gmp_cis_sta_dly_calendar_kudu | event_date, event_name | 3 |
| 12 | gmp_cis_sta_dly_counterparty | gmp_cis_sta_dly_counterparty_kudu | counterparty_code | 20 |
| 13 | gmp_cis_sta_dly_country | gmp_cis_sta_dly_country_kudu | country_code | 2 |
| 14 | gmp_cis_sta_dly_currency | gmp_cis_sta_dly_currency_kudu | currency_code | 8 |
| 15 | test_insert_simple | test_insert_simple_kudu | id | 2 |

**Total Columns Across All Tables**: 171

---

## What Was Generated

### Auto-Generated Features

1. **Type Conversion**: Automatically converted Hive data types to Kudu equivalents
   - `string` → `STRING`
   - `int` → `INT32`
   - `bigint` → `INT64`
   - `double` → `DOUBLE`
   - `timestamp` → `UNIXTIME_MICROS`

2. **Primary Keys**: Defined for each table based on business logic
   - Single column PKs for most tables
   - Composite PKs for junction/relationship tables

3. **NOT NULL Constraints**: Automatically added to all primary key columns

4. **Partitioning**: All tables use `PARTITION BY HASH PARTITIONS 4` for distributed performance

5. **Kudu Properties**: Configured with:
   - `kudu.master_addresses = localhost:7051`
   - Unique Kudu table names with `_kudu` suffix

---

## How to Use

### Prerequisites

- Apache Kudu running on `localhost:7051`
- Impala installed and configured to work with Kudu
- Access to `cis` database

### Create All Tables

```bash
# Using Impala Shell (Recommended)
impala-shell -f cis_hive_to_kudu_tables.sql

# Or using Beeline with Impala JDBC
beeline -u "jdbc:impala://localhost:21050/cis" -f cis_hive_to_kudu_tables.sql
```

### Verify Tables Created

```sql
USE cis;
SHOW TABLES LIKE '*_kudu';

-- Check a specific table
DESCRIBE cis_portfolio_kudu;
```

---

## Data Migration

After creating the Kudu tables, you can migrate data from Hive:

```sql
-- Example: Migrate portfolio data
INSERT INTO cis_portfolio_kudu
SELECT * FROM cis_portfolio;

-- Verify
SELECT COUNT(*) FROM cis_portfolio_kudu;
```

---

## Key Differences: Hive vs Kudu

| Feature | Hive | Kudu |
|---------|------|------|
| Storage | HDFS files | Kudu storage |
| Updates | Not optimized | Fast updates |
| Primary Keys | Not required | Required |
| Random Access | Slow (full scans) | Fast (indexed) |
| Use Case | Batch analytics | Real-time updates |

---

## Generator Script

The tables were generated using: `generate_kudu_from_hive.py`

**Features**:
- Automatically queries Hive for all tables in `cis` database
- Extracts schema for each table
- Converts to Kudu-compatible DDL
- Defines appropriate primary keys
- Handles type conversion

**Re-generate**:
```bash
cd sql/ddl
python3 generate_kudu_from_hive.py
```

---

## Next Steps

1. **Start Kudu** (if not running):
   ```bash
   kudu-master &
   kudu-tserver &
   ```

2. **Create Tables**:
   ```bash
   impala-shell -f cis_hive_to_kudu_tables.sql
   ```

3. **Migrate Data**: Choose tables to migrate from Hive to Kudu

4. **Update Application**: Point application to use Kudu tables for better performance

---

## Notes

- **Read-Only View**: Hive tables remain for read-only analytics
- **Real-Time Updates**: Use Kudu tables for CRUD operations
- **Hybrid Approach**: Can use both Hive and Kudu for different purposes
- **Performance**: Kudu provides 10-100x faster random access than Hive

---

Generated: 2025-12-25 23:20:53
