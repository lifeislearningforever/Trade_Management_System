# Trade Data Ingestion - PySpark Jobs

## Overview

PySpark jobs to ingest trade data from Hive source tables into Kudu target tables.
Handles 250,000+ records with NULL values gracefully.

## Files

| File | Description |
|------|-------------|
| `ingest_trade_hive_to_kudu.py` | Full-featured ingestion with Kudu Spark connector |
| `ingest_trade_simple.py` | Simple version using Impala SQL INSERT (recommended) |
| `run_trade_ingestion.sh` | Shell script to run the ingestion |

## Quick Start

### 1. Test with limited records (Local)

```bash
spark-submit ingest_trade_simple.py \
    --source-db gmp_cis \
    --source-table cis_trade_hive \
    --target-db gmp_cis \
    --target-table cis_trade \
    --limit 1000
```

### 2. Full load (Cloudera CML / YARN)

```bash
./run_trade_ingestion.sh
```

### 3. Custom configuration

```bash
./run_trade_ingestion.sh \
    --source-db gmp_source \
    --source-table trade_raw \
    --target-db gmp_cis \
    --target-table cis_trade \
    --batch-size 5000
```

## NULL Handling

The ingestion handles NULL values for all columns:

| Column Type | NULL Handling |
|-------------|---------------|
| String | Empty string `''` |
| Decimal | `0` |
| Boolean | `False` |
| Integer/Long | `NULL` (preserved) |
| trade_id | Auto-generated (timestamp + row number) |

### Required Fields with Defaults

| Column | Default Value |
|--------|---------------|
| `trade_type` | `'UNKNOWN'` |
| `trade_date` | `'1900-01-01'` |
| `status` | `'SETTLED'` |
| `src_system` | `'GMP'` |
| `is_active` | `True` |
| `is_deleted` | `False` |
| `created_by` | `'ETL_SYSTEM'` |
| `updated_by` | `'ETL_SYSTEM'` |

## Source Table Requirements

The source Hive table can have any of these columns (all optional except noted):

```
trade_type, deal_number, portfolio_short_name, portfolio_full_name,
security_label, security_full_name, security_type, trade_status,
trade_date, settle_date, quantity, price, commission, ...
```

Missing columns will be filled with defaults.

## Target Table Schema

Target: `gmp_cis.cis_trade` (Kudu)

See `sql/ddl/06_trade_tables_kudu.sql` for full DDL.

## Performance

| Records | Estimated Time | Batch Size |
|---------|---------------|------------|
| 10,000 | ~30 sec | 10,000 |
| 100,000 | ~3 min | 10,000 |
| 250,000 | ~8 min | 10,000 |
| 1,000,000 | ~30 min | 10,000 |

### Tuning Parameters

```bash
# Environment variables
export BATCH_SIZE=5000          # Smaller for slow Kudu
export NUM_EXECUTORS=8          # More for larger datasets
export EXECUTOR_MEMORY=8g       # Increase for complex transforms
```

## Spark Configuration

For Cloudera CML:

```bash
spark-submit \
    --master yarn \
    --deploy-mode cluster \
    --executor-memory 4g \
    --driver-memory 2g \
    --num-executors 4 \
    --conf spark.sql.shuffle.partitions=200 \
    --conf spark.dynamicAllocation.enabled=true \
    ingest_trade_simple.py
```

## Troubleshooting

### Error: Table not found

```bash
# Check if tables exist
impala-shell -q "SHOW TABLES IN gmp_cis LIKE '*trade*'"
```

### Error: Kudu write timeout

Increase batch size or check Kudu cluster health:

```bash
# Reduce batch size
--batch-size 1000

# Check Kudu health
kudu cluster ksck kudu-master-1:7051
```

### Error: Out of memory

```bash
# Increase executor memory
--executor-memory 8g

# Or reduce parallelism
--conf spark.sql.shuffle.partitions=50
```

## Logging

Logs are written to:
- YARN: Application logs in HDFS
- Local: stdout/stderr

## Author

Claude Code - 2026-01-16
