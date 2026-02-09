# Position Master ETL Architecture

This document describes the ETL architecture for consolidating position data from 12 different source systems into a unified `cis_position_master` table.

## Overview

The Position Master system consolidates position data from 4 primary source systems (CIS, GMP, AMS, IMS), each with 3 sub-tables (positions, summary, history), totaling 12 source tables. The data flows through staging tables, undergoes security validation, and is loaded into the master position table.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Position Master ETL Flow                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Source Systems          Staging Tables           Target Tables            │
│   ──────────────          ──────────────           ──────────────           │
│                                                                             │
│   ┌─────────┐             ┌──────────────┐                                  │
│   │   CIS   │────────────▶│ stg_cis_*    │                                  │
│   └─────────┘             └──────────────┘                                  │
│                                   │                                         │
│   ┌─────────┐             ┌──────────────┐        ┌────────────────────┐   │
│   │   GMP   │────────────▶│ stg_gmp_*    │───────▶│  Security          │   │
│   └─────────┘             └──────────────┘        │  Validation        │   │
│                                   │               └─────────┬──────────┘   │
│   ┌─────────┐             ┌──────────────┐               │                 │
│   │   AMS   │────────────▶│ stg_ams_*    │               ▼                 │
│   └─────────┘             └──────────────┘        ┌──────────────────┐     │
│                                   │               │ Matched?         │     │
│   ┌─────────┐             ┌──────────────┐        └────────┬─────────┘     │
│   │   IMS   │────────────▶│ stg_ims_*    │                 │               │
│   └─────────┘             └──────────────┘           ┌─────┴─────┐         │
│                                                      ▼           ▼         │
│                                               ┌──────────┐ ┌──────────┐    │
│                                               │ position │ │ position │    │
│                                               │ _master  │ │ _unmatched│   │
│                                               └──────────┘ └──────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Source Systems

| # | System | Description | Sub-Tables |
|---|--------|-------------|------------|
| 1 | **CIS** | Cooperative Investment System (internal trades) | stg_cis_positions, stg_cis_summary, stg_cis_history |
| 2 | **GMP** | Global Markets Platform (external feed) | stg_gmp_positions, stg_gmp_summary, stg_gmp_history |
| 3 | **AMS** | Asset Management System (external feed) | stg_ams_positions, stg_ams_summary, stg_ams_history |
| 4 | **IMS** | Investment Management System (external feed) | stg_ims_positions, stg_ims_summary, stg_ims_history |

## Database Tables

### Master Tables

| Table | Purpose |
|-------|---------|
| `gmp_cis.cis_position_master` | Consolidated positions from all sources |
| `gmp_cis.cis_position_master_history` | Audit trail of position changes |
| `gmp_cis.cis_position_unmatched` | Positions with unmatched securities |

### Staging Tables (12 total)

| Source | Positions | Summary | History |
|--------|-----------|---------|---------|
| CIS | stg_cis_positions | stg_cis_summary | stg_cis_history |
| GMP | stg_gmp_positions | stg_gmp_summary | stg_gmp_history |
| AMS | stg_ams_positions | stg_ams_summary | stg_ams_history |
| IMS | stg_ims_positions | stg_ims_summary | stg_ims_history |

## DDL Files

| File | Description |
|------|-------------|
| `sql/ddl/11_cis_position_master_kudu.sql` | Master position tables DDL |
| `sql/ddl/12_position_staging_tables.sql` | Staging tables DDL (12 tables) |

## ETL Job

### PySpark Job: `merge_position_master.py`

Location: `sql/pyspark/merge_position_master.py`

#### Usage

```bash
# Process all sources (Cloudera/YARN)
spark-submit --master yarn \
  --conf spark.executor.memory=4g \
  --conf spark.executor.cores=2 \
  merge_position_master.py \
  --kudu-master kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051 \
  --source all \
  --valuation-date 2026-02-09 \
  --batch-id BATCH_20260209_001

# Process single source (local Docker)
spark-submit merge_position_master.py \
  --kudu-master localhost:7051 \
  --source gmp \
  --batch-id BATCH_20260209_001

# Dry run (preview without writing)
spark-submit merge_position_master.py \
  --kudu-master localhost:7051 \
  --source all \
  --dry-run
```

#### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--kudu-master` | Yes | - | Kudu master addresses |
| `--source` | No | `all` | Source: cis, gmp, ams, ims, or all |
| `--valuation-date` | No | All | Filter by valuation date (YYYY-MM-DD) |
| `--batch-id` | No | All | Filter by ETL batch ID |
| `--dry-run` | No | False | Preview without writing |
| `--auto-create` | No | False | Auto-create missing securities (PLACEHOLDER) |

## Security Validation

### Matching Logic

Positions are validated against the `cis_security_kudu` master table:

1. **Exact Match**: `security_label` matches `security_name`
   - Result: `is_matched=True`, `match_status='EXACT'`

2. **ISIN Match**: `isin` matches `isin` in security master
   - Result: `is_matched=True`, `match_status='ISIN_MATCH'`

3. **No Match**: Neither security_label nor isin found
   - Result: `is_matched=False`, `match_status='UNMATCHED'`
   - Position written to `cis_position_unmatched` for review

### Unmatched Security Handling

When a position cannot be matched to a security:

1. Record is written to `cis_position_unmatched` table
2. Fields captured for manual review:
   - `security_label`, `isin`, `security_name`
   - `attempted_match_key`
   - `resolution_status` = 'PENDING'

3. Resolution options:
   - **Manual**: Update `cis_security` with the new security, rerun ETL
   - **Auto-create** (future): Set `--auto-create` flag to auto-create securities

### PLACEHOLDER: Auto-Create Securities

The `--auto-create` flag is a placeholder for future implementation. When implemented:

1. Unique unmatched securities will be extracted
2. New `security_id` values will be generated
3. Minimal security records will be created:
   ```
   security_name = security_label from position
   isin = isin from position
   security_type = inferred or 'UNKNOWN'
   currency_code = security_currency from position
   src_system = 'ETL_AUTO_CREATED'
   ```
4. After creation, positions will be re-matched

## Position Master Schema

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `position_master_id` | BIGINT | Primary key (timestamp-based) |
| `portfolio_short_name` | STRING | Portfolio identifier |
| `security_label` | STRING | Security identifier |
| `valuation_date` | STRING | Position as-of date (YYYY-MM-DD) |
| `src_system` | STRING | Source: CIS, GMP, AMS, IMS |

### Natural Key

```
(portfolio_short_name, security_label, valuation_date, src_system)
```

### Multi-Currency Support

| Field | Description |
|-------|-------------|
| `security_currency` | Currency of the security |
| `portfolio_currency` | Base currency of the portfolio |
| `cost_value_local` | Cost in security currency |
| `cost_value_base` | Cost in portfolio currency |
| `market_value_local` | Market value in security currency |
| `market_value_base` | Market value in portfolio currency |
| `unrealized_pnl_local` | P&L in security currency |
| `unrealized_pnl_base` | P&L in portfolio currency |

### Security Matching Fields

| Field | Type | Description |
|-------|------|-------------|
| `security_id` | BIGINT | FK to cis_security (if matched) |
| `is_matched` | BOOLEAN | True if security found in master |
| `match_status` | STRING | EXACT, ISIN_MATCH, UNMATCHED |

## ETL Processing Steps

### Step 1: Load Staging Data

```python
# Read from all source staging tables
stg_df = read_all_staging_positions(spark, kudu_master, sources, valuation_date, batch_id)
```

### Step 2: Load Security Master

```python
# Read active securities for matching
security_df = read_security_master(spark, kudu_master)
```

### Step 3: Validate Securities

```python
# Match positions against security master
matched_df, unmatched_df = validate_securities(stg_df, security_df)
```

### Step 4: Generate IDs

```python
# Generate position_master_id for new records
master_records = generate_position_ids(matched_df, now_ms)
```

### Step 5: Write to Kudu

```python
# UPSERT matched positions to master
master_records.write.format("kudu").option("kudu.operation", "upsert").save()

# UPSERT unmatched to review table
unmatched_records.write.format("kudu").option("kudu.operation", "upsert").save()
```

## Scheduling

### Recommended Schedule

| Frequency | Sources | Notes |
|-----------|---------|-------|
| Hourly | CIS | Internal trades, near real-time |
| Daily | GMP, AMS, IMS | External feeds, end-of-day |
| Weekly | All | Full reconciliation |

### Sample Airflow DAG

```python
from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

with DAG('position_master_etl', schedule_interval='0 6 * * *') as dag:

    merge_gmp = SparkSubmitOperator(
        task_id='merge_gmp_positions',
        application='/path/to/merge_position_master.py',
        application_args=[
            '--kudu-master', 'kudu-master-1:7051',
            '--source', 'gmp',
            '--valuation-date', '{{ ds }}',
        ],
    )

    merge_ams = SparkSubmitOperator(
        task_id='merge_ams_positions',
        application='/path/to/merge_position_master.py',
        application_args=[
            '--kudu-master', 'kudu-master-1:7051',
            '--source', 'ams',
            '--valuation-date', '{{ ds }}',
        ],
    )

    [merge_gmp, merge_ams]
```

## Monitoring

### Key Metrics

| Metric | Query |
|--------|-------|
| Total positions | `SELECT COUNT(*) FROM cis_position_master` |
| By source | `SELECT src_system, COUNT(*) FROM cis_position_master GROUP BY 1` |
| Unmatched | `SELECT COUNT(*) FROM cis_position_unmatched WHERE resolution_status = 'PENDING'` |
| Match rate | `SELECT is_matched, COUNT(*) FROM cis_position_master GROUP BY 1` |

### Health Checks

```sql
-- Check for today's data
SELECT src_system, COUNT(*), MAX(updated_at)
FROM cis_position_master
WHERE valuation_date = CURRENT_DATE()
GROUP BY src_system;

-- Check unmatched queue
SELECT resolution_status, COUNT(*)
FROM cis_position_unmatched
GROUP BY resolution_status;
```

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No data loaded | Wrong batch_id or valuation_date | Check staging tables |
| High unmatched rate | New securities in source | Add securities to master |
| Duplicate positions | Missing natural key constraint | Check staging deduplication |

### Debug Mode

```bash
# Run with dry-run to preview
spark-submit merge_position_master.py \
  --kudu-master localhost:7051 \
  --source gmp \
  --dry-run

# Check Spark UI for job metrics
# http://localhost:4040
```

## Future Enhancements

1. **Auto-create securities**: Implement `--auto-create` flag to automatically create missing securities in `cis_security_kudu`

2. **Fuzzy matching**: Add Levenshtein distance matching for security names

3. **Portfolio validation**: Validate portfolio_short_name against `cis_portfolio`

4. **Currency conversion**: Auto-convert local values to base using FX rates

5. **Real-time streaming**: Replace batch with Spark Structured Streaming

---

Last updated: 2026-02-09
