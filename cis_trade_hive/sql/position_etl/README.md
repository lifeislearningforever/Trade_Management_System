# Position Master ETL

ETL pipeline to transform 10 source Hive external tables into a unified `position_master` table.

## Overview

| Component | Description |
|-----------|-------------|
| **Source Tables** | 10 Hive external tables (Parquet format, STRING datatypes) |
| **Target Table** | `gmp_cis.position_master` |
| **Format** | Parquet with SNAPPY compression |
| **Partitions** | `src_id`, `processing_date` |

## Source Tables

### USER_UPLOAD (src_system='USER_UPLOAD')

| Table Name | position_basis | Description |
|------------|----------------|-------------|
| `cis_user_sta_adhoc_position_1` | **trade_date** | Basic Position Data |
| `cis_user_sta_adhoc_position_2` | **trade_date** | Holdings with Country |
| `cis_user_sta_adhoc_position_3` | **trade_date** | Account Position |
| `cis_user_sta_adhoc_position_4` | **settled_date** | Position with Valuation |
| `cis_user_sta_adhoc_position_5` | **settled_date** | Complete Position (most comprehensive) |

### AMS_STREET (src_system='AMS_STREET')

| Table Name | position_basis | Description |
|------------|----------------|-------------|
| `gmp_cis_sta_dly_ams_multi_dis_cif` | **trade_date** | Multi Discretionary Fund |
| `gmp_cis_sta_dly_ams_multi_hold` | **trade_date** | Multiple Holdings Daily |
| `gmp_cis_sta_dly_stat_street_ams_daily_limit` | **trade_date** | S31 UOI Daily Limit |
| `gmp_cis_sta_dly_stat_street_ams_iceq` | **trade_date** | ICEQ Daily |
| `gmp_cis_sta_mthly_stat_street_ams_iceq_end` | **settled_date** | ICEQ Month End |

## Position Basis Mapping

The `position_basis` column in `position_master` is populated from either `trade_date` or `settled_date` depending on the source table:

| Source | position_basis Source Field |
|--------|----------------------------|
| cis_user_sta_adhoc_position_1 | trade_date |
| cis_user_sta_adhoc_position_2 | trade_date |
| cis_user_sta_adhoc_position_3 | trade_date |
| cis_user_sta_adhoc_position_4 | settled_date |
| cis_user_sta_adhoc_position_5 | settled_date |
| gmp_cis_sta_dly_ams_multi_dis_cif | trade_date |
| gmp_cis_sta_dly_ams_multi_hold | trade_date |
| gmp_cis_sta_dly_stat_street_ams_daily_limit | trade_date |
| gmp_cis_sta_dly_stat_street_ams_iceq | trade_date |
| gmp_cis_sta_mthly_stat_street_ams_iceq_end | settled_date |

## Files

```
sql/position_etl/
├── 01_position_master_ddl.sql      # Target table DDL
├── 02_user_upload_source_ddl.sql   # USER_UPLOAD source DDLs
├── 03_ams_street_source_ddl.sql    # AMS_STREET source DDLs
├── 04_position_master_etl_hive.sql # Hive SQL ETL
├── position_master_etl.py          # PySpark ETL
├── run_etl.sh                      # Runner script
└── README.md                       # This file
```

## Quick Start

### 1. Create Tables

```bash
# Create target table
beeline -u "jdbc:hive2://localhost:10000" -n user \
  -f sql/position_etl/01_position_master_ddl.sql

# Create source tables (if not exists)
beeline -u "jdbc:hive2://localhost:10000" -n user \
  -f sql/position_etl/02_user_upload_source_ddl.sql

beeline -u "jdbc:hive2://localhost:10000" -n user \
  -f sql/position_etl/03_ams_street_source_ddl.sql
```

### 2. Run ETL

#### Using Shell Script (Recommended)

```bash
# PySpark (default)
./sql/position_etl/run_etl.sh 03032026

# PySpark with overwrite mode
./sql/position_etl/run_etl.sh 03032026 overwrite

# Hive SQL
./sql/position_etl/run_etl.sh 03032026 append hive
```

#### Using PySpark Directly

```bash
spark-submit \
  --master yarn \
  --deploy-mode client \
  sql/position_etl/position_master_etl.py \
  --processing-date 03032026 \
  --mode append
```

#### Using Hive Directly

```bash
beeline -u "jdbc:hive2://localhost:10000" -n user \
  --hivevar processing_date=03032026 \
  --hivevar batch_id=batch_001 \
  -f sql/position_etl/04_position_master_etl_hive.sql
```

## Position Master Target Schema

| Category | Fields |
|----------|--------|
| **Identifiers** | portfolio, security_full_name, security_short_name, isin, ticker |
| **Quantity** | quantity, shares_outstanding, shares_issued, pct_holding |
| **Pricing** | market_price, average_cost |
| **Cost FC** | cost_fc, market_value_fc, net_book_value_fc, unrealized_pnl_fc |
| **Cost LC** | cost_lc, market_value_lc, net_book_value_lc, unrealized_pnl_lc, provision_lc |
| **Classification** | product_type, security_type, quoted_unquoted, industry, fin_nonfin_co |
| **Geography** | exchange, country_code, country_of_exchange, country_of_incorporation |
| **Corporate** | corp_code, branch_code, cost_centre, cels |
| **MAS/BWCIF** | bwcif_sg, bwcif_ovs, mas_6d_code_sg, mas_6d_code_ovs |
| **Dates** | position_basis, reporting_date, maturity_date |
| **Metadata** | src_system, sub_system, data_cat, data_frq, source_table |
| **ETL** | etl_insert_ts, etl_batch_id |
| **Partitions** | src_id, processing_date |

## Source to Target Mapping (Key Fields)

| Master Field | USER_UPLOAD Sources | AMS_STREET Sources |
|--------------|--------------------|--------------------|
| `portfolio` | portfolio, portfolio_name, account_name | portfolio, portfolio_code |
| `isin` | isin_code, isin | isin |
| `quantity` | quantity_today, qty_held, shares_outstanding_total, quantity | units, quantity, quantity_units |
| `market_price` | market_price_unit_fc | price, market_unit_price_local, market_price |
| `cost_fc` | cost_fc | cost_value_local, total_cost_fc |
| `cost_lc` | cost_lc | cost_value_base, total_cost_sgd |
| `position_basis` | trade_date OR settled_date | trade_date OR settled_date |

## Partition Strategy

- **src_id**: Source identifier (granular tracking)
- **processing_date**: Date in DDMMYYYY format

This enables:
- Efficient date-based queries
- Incremental data loads
- Easy data retention management

## Verification Queries

```sql
-- Check record counts by source
SELECT src_system, source_table, COUNT(*) AS cnt
FROM gmp_cis.position_master
WHERE processing_date = '03032026'
GROUP BY src_system, source_table;

-- Check latest batch
SELECT etl_batch_id, COUNT(*) AS records, MIN(etl_insert_ts), MAX(etl_insert_ts)
FROM gmp_cis.position_master
GROUP BY etl_batch_id
ORDER BY MIN(etl_insert_ts) DESC
LIMIT 5;

-- Sample data with position_basis
SELECT portfolio, isin, quantity, position_basis, src_system, source_table
FROM gmp_cis.position_master
WHERE processing_date = '03032026'
LIMIT 10;

-- Check position_basis distribution
SELECT source_table, position_basis, COUNT(*) AS cnt
FROM gmp_cis.position_master
WHERE processing_date = '03032026'
GROUP BY source_table, position_basis
ORDER BY source_table;
```

## Notes

1. **All source table columns are STRING datatype** - ingestion uses STRING for all fields.
2. The `position_basis` field captures either `trade_date` or `settled_date` depending on the source table (see mapping table above).
3. ETL supports both append and overwrite modes for flexibility.
4. The PySpark ETL uses a configuration-driven approach for easy maintenance.
