# Position Master ETL

ETL pipeline to transform 10 source Hive external tables into a unified `position_master` table.

## Overview

| Component | Description |
|-----------|-------------|
| **Source Tables** | 10 Hive external tables (Parquet format) |
| **Target Table** | `gmp_cis.position_master` |
| **Format** | Parquet with SNAPPY compression |
| **Partitions** | `src_id`, `processing_date` |

## Source Systems

### USER_UPLOAD (src_system='USER_UPLOAD')

| Table | Description | Key Mappings |
|-------|-------------|--------------|
| `user_upload_1` | Basic Position Data | Portfolio, ISIN, Quantity, Exchange |
| `user_upload_2` | Holdings with Country | Portfolio, Security, Country, Holdings % |
| `user_upload_3` | Account Position | Account/Portfolio, ISIN, Quantity |
| `user_upload_4` | Position with Valuation | Full security details, Cost FC/LC, P&L |
| `user_upload_5` | Complete Position | All fields including MAS codes, BWCIF |

### AMS_STREET (src_system='AMS_STREET')

| Table | Description | Key Mappings |
|-------|-------------|--------------|
| `ams_street_1` | Multi Discretionary Fund | Portfolio, Security, Price, Units |
| `ams_street_2` | Multiple Holdings Daily | Portfolio, Security, Quantity |
| `ams_street_3` | ICEQ Month End (v1) | Full valuation with P&L |
| `ams_street_4` | ICEQ Month End (v2) | Full valuation with P&L |
| `ams_street_5` | S31 UOI | Portfolio, Cost, Market Value, MAS codes |

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

# Create source tables
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

## Field Mapping Summary

### Position Master Target Schema

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

### Source to Target Mapping (Key Fields)

| Master Field | USER_UPLOAD Sources | AMS_STREET Sources |
|--------------|--------------------|--------------------|
| `portfolio` | Portfolio, Portfolio_Name, Account_name | Portfolio, Portfolio_Code |
| `isin` | ISIN_Code, ISIN | ISIN |
| `quantity` | Quantity_Today, Qty_Held, Shares_outstanding_total | Units, Quantity, Quantity_Units |
| `market_price` | Market_Price_unit_FC | Price, Market_Unit_Price_Local, Market_Price |
| `cost_fc` | COST_FC | Cost_Value_Local, Total_Cost_FC |
| `cost_lc` | COST_LC | Cost_Value_Base, Total_Cost_SGD |
| `position_basis` | trade_date, settled_date | trade_date, settled_date |

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

-- Sample data
SELECT portfolio, isin, quantity, market_price, cost_fc, src_system, source_table
FROM gmp_cis.position_master
WHERE processing_date = '03032026'
LIMIT 10;
```

## Notes

1. **Yellow-highlighted fields** in the mapping images indicate fields that are NOT mapped to the master table (reserved/unused fields).
2. The `position_basis` field captures either `trade_date` or `settled_date` depending on the source.
3. All decimal fields use appropriate precision for financial calculations.
4. ETL supports both append and overwrite modes for flexibility.
