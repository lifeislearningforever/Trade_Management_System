-- ============================================================================
-- Position Staging Tables - 12 Source Position Tables
-- ============================================================================
-- Description: Staging tables for position data from 4 source systems,
--              each with 3 sub-tables (positions, summary, history).
--
-- Source Systems:
--   1. CIS  - Cooperative Investment System (internal trades via cis_trade_position)
--   2. GMP  - Global Markets Platform (external feed)
--   3. AMS  - Asset Management System (external feed)
--   4. IMS  - Investment Management System (external feed)
--
-- Sub-Tables per Source (3 each = 12 total):
--   - _positions: Current position holdings
--   - _summary:   Aggregated portfolio-level summary
--   - _history:   Historical position snapshots
--
-- Data Flow:
--   Source -> Staging Table -> Transform -> cis_position_master
--
-- Storage: Hive External Tables with Parquet format
-- Database: gmp_cis
-- Created: 2026-02-09
-- Updated: 2026-02-10 (Converted from Kudu to Hive/Parquet)
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- HDFS DIRECTORY SETUP (run via hdfs dfs commands before creating tables)
-- ============================================================================
-- # CIS staging tables
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_cis_positions
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_cis_summary
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_cis_history
--
-- # GMP staging tables
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_gmp_positions
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_gmp_summary
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_gmp_history
--
-- # AMS staging tables
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ams_positions
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ams_summary
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ams_history
--
-- # IMS staging tables
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ims_positions
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ims_summary
-- hdfs dfs -mkdir -p /data/gmp_cis/staging/stg_ims_history
--
-- # Set permissions
-- hdfs dfs -chmod -R 777 /data/gmp_cis/staging
-- ============================================================================


-- ============================================================================
-- STAGING TABLE TEMPLATE
-- ============================================================================
-- All staging tables share a common schema for consistent processing.
-- Fields map to cis_position_master with source-specific extensions.
-- Storage: External Hive tables with Parquet format
-- ============================================================================


-- ============================================================================
-- SOURCE 1: CIS (Cooperative Investment System)
-- ============================================================================
-- Internal positions from CIS trades. Already in cis_trade_position.
-- This staging table captures any external CIS position feeds.
-- ============================================================================

-- 1.1 CIS Positions
DROP TABLE IF EXISTS gmp_cis.stg_cis_positions;

CREATE EXTERNAL TABLE gmp_cis.stg_cis_positions (
    stg_id BIGINT,

    -- Position Identity
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,

    -- Currency
    security_currency STRING,
    portfolio_currency STRING,

    -- Holdings
    quantity DECIMAL(20,6),
    face_value DECIMAL(20,6),
    lots_held INT,

    -- Cost
    average_cost DECIMAL(20,6),
    total_cost DECIMAL(20,6),
    cost_value_local DECIMAL(20,6),
    cost_value_base DECIMAL(20,6),

    -- Market Value
    market_unit_price DECIMAL(20,6),
    market_value DECIMAL(20,6),
    market_value_local DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- P&L
    unrealized_pnl DECIMAL(20,6),
    unrealized_pnl_local DECIMAL(20,6),
    unrealized_pnl_base DECIMAL(20,6),
    realized_pnl DECIMAL(20,6),

    -- Classification
    pct_ratio DECIMAL(10,6),
    country STRING,
    asset_class STRING,
    listing_status STRING,

    -- Custodian
    custodian STRING,
    sub_custodian STRING,

    -- Status
    status STRING,

    -- ETL Metadata
    src_position_id STRING,
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_cis_positions'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 1.2 CIS Summary
DROP TABLE IF EXISTS gmp_cis.stg_cis_summary;

CREATE EXTERNAL TABLE gmp_cis.stg_cis_summary (
    stg_id BIGINT,

    portfolio_short_name STRING,
    valuation_date STRING,

    -- Aggregate Metrics
    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    -- Currency Breakdown (JSON)
    currency_breakdown STRING,

    -- ETL Metadata
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_cis_summary'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 1.3 CIS History
DROP TABLE IF EXISTS gmp_cis.stg_cis_history;

CREATE EXTERNAL TABLE gmp_cis.stg_cis_history (
    stg_id BIGINT,

    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    version_number INT,

    -- Snapshot Data
    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    -- Change Info
    change_type STRING,                       -- BUY, SELL, ADJUSTMENT, PRICE_UPDATE
    change_amount DECIMAL(20,6),

    -- ETL Metadata
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_cis_history'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');


-- ============================================================================
-- SOURCE 2: GMP (Global Markets Platform)
-- ============================================================================

-- 2.1 GMP Positions
DROP TABLE IF EXISTS gmp_cis.stg_gmp_positions;

CREATE EXTERNAL TABLE gmp_cis.stg_gmp_positions (
    stg_id BIGINT,

    -- Position Identity
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    cusip STRING,                             -- GMP-specific
    sedol STRING,                             -- GMP-specific

    -- Currency
    security_currency STRING,
    portfolio_currency STRING,

    -- Holdings
    quantity DECIMAL(20,6),
    face_value DECIMAL(20,6),
    lots_held INT,

    -- Cost
    average_cost DECIMAL(20,6),
    total_cost DECIMAL(20,6),
    cost_value_local DECIMAL(20,6),
    cost_value_base DECIMAL(20,6),

    -- Market Value
    market_unit_price DECIMAL(20,6),
    market_value DECIMAL(20,6),
    market_value_local DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- P&L
    unrealized_pnl DECIMAL(20,6),
    unrealized_pnl_local DECIMAL(20,6),
    unrealized_pnl_base DECIMAL(20,6),
    realized_pnl DECIMAL(20,6),

    -- GMP-specific fields
    gmp_position_id STRING,
    gmp_book_id STRING,
    gmp_desk_id STRING,

    -- Classification
    pct_ratio DECIMAL(10,6),
    country STRING,
    asset_class STRING,
    listing_status STRING,

    -- Custodian
    custodian STRING,
    sub_custodian STRING,

    -- Status
    status STRING,

    -- ETL Metadata
    src_position_id STRING,
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_gmp_positions'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 2.2 GMP Summary
DROP TABLE IF EXISTS gmp_cis.stg_gmp_summary;

CREATE EXTERNAL TABLE gmp_cis.stg_gmp_summary (
    stg_id BIGINT,

    portfolio_short_name STRING,
    valuation_date STRING,
    gmp_book_id STRING,

    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    currency_breakdown STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_gmp_summary'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 2.3 GMP History
DROP TABLE IF EXISTS gmp_cis.stg_gmp_history;

CREATE EXTERNAL TABLE gmp_cis.stg_gmp_history (
    stg_id BIGINT,

    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    gmp_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_gmp_history'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');


-- ============================================================================
-- SOURCE 3: AMS (Asset Management System)
-- ============================================================================

-- 3.1 AMS Positions
DROP TABLE IF EXISTS gmp_cis.stg_ams_positions;

CREATE EXTERNAL TABLE gmp_cis.stg_ams_positions (
    stg_id BIGINT,

    -- Position Identity
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    ams_security_id STRING,                   -- AMS-specific

    -- Currency
    security_currency STRING,
    portfolio_currency STRING,

    -- Holdings
    quantity DECIMAL(20,6),
    face_value DECIMAL(20,6),
    lots_held INT,

    -- Cost
    average_cost DECIMAL(20,6),
    total_cost DECIMAL(20,6),
    cost_value_local DECIMAL(20,6),
    cost_value_base DECIMAL(20,6),

    -- Market Value
    market_unit_price DECIMAL(20,6),
    market_value DECIMAL(20,6),
    market_value_local DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- P&L
    unrealized_pnl DECIMAL(20,6),
    unrealized_pnl_local DECIMAL(20,6),
    unrealized_pnl_base DECIMAL(20,6),
    realized_pnl DECIMAL(20,6),

    -- AMS-specific fields
    ams_position_id STRING,
    ams_fund_code STRING,
    ams_mandate_id STRING,

    -- Classification
    pct_ratio DECIMAL(10,6),
    country STRING,
    asset_class STRING,
    listing_status STRING,
    industry STRING,
    sector STRING,

    -- Custodian
    custodian STRING,
    sub_custodian STRING,

    -- Status
    status STRING,

    -- ETL Metadata
    src_position_id STRING,
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ams_positions'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 3.2 AMS Summary
DROP TABLE IF EXISTS gmp_cis.stg_ams_summary;

CREATE EXTERNAL TABLE gmp_cis.stg_ams_summary (
    stg_id BIGINT,

    portfolio_short_name STRING,
    valuation_date STRING,
    ams_fund_code STRING,

    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    nav DECIMAL(20,6),                        -- Net Asset Value
    nav_per_unit DECIMAL(20,6),

    currency_breakdown STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ams_summary'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 3.3 AMS History
DROP TABLE IF EXISTS gmp_cis.stg_ams_history;

CREATE EXTERNAL TABLE gmp_cis.stg_ams_history (
    stg_id BIGINT,

    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    ams_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ams_history'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');


-- ============================================================================
-- SOURCE 4: IMS (Investment Management System)
-- ============================================================================

-- 4.1 IMS Positions
DROP TABLE IF EXISTS gmp_cis.stg_ims_positions;

CREATE EXTERNAL TABLE gmp_cis.stg_ims_positions (
    stg_id BIGINT,

    -- Position Identity
    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    ims_instrument_id STRING,                 -- IMS-specific

    -- Currency
    security_currency STRING,
    portfolio_currency STRING,

    -- Holdings
    quantity DECIMAL(20,6),
    face_value DECIMAL(20,6),
    lots_held INT,

    -- Cost
    average_cost DECIMAL(20,6),
    total_cost DECIMAL(20,6),
    cost_value_local DECIMAL(20,6),
    cost_value_base DECIMAL(20,6),

    -- Market Value
    market_unit_price DECIMAL(20,6),
    market_value DECIMAL(20,6),
    market_value_local DECIMAL(20,6),
    market_value_base DECIMAL(20,6),

    -- P&L
    unrealized_pnl DECIMAL(20,6),
    unrealized_pnl_local DECIMAL(20,6),
    unrealized_pnl_base DECIMAL(20,6),
    realized_pnl DECIMAL(20,6),

    -- IMS-specific fields
    ims_position_id STRING,
    ims_account_id STRING,
    ims_strategy_id STRING,
    benchmark_weight DECIMAL(10,6),
    active_weight DECIMAL(10,6),

    -- Classification
    pct_ratio DECIMAL(10,6),
    country STRING,
    asset_class STRING,
    listing_status STRING,
    industry STRING,
    sector STRING,

    -- Custodian
    custodian STRING,
    sub_custodian STRING,

    -- Status
    status STRING,

    -- ETL Metadata
    src_position_id STRING,
    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ims_positions'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 4.2 IMS Summary
DROP TABLE IF EXISTS gmp_cis.stg_ims_summary;

CREATE EXTERNAL TABLE gmp_cis.stg_ims_summary (
    stg_id BIGINT,

    portfolio_short_name STRING,
    valuation_date STRING,
    ims_account_id STRING,

    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    benchmark_return DECIMAL(10,6),
    portfolio_return DECIMAL(10,6),
    tracking_error DECIMAL(10,6),

    currency_breakdown STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ims_summary'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- 4.3 IMS History
DROP TABLE IF EXISTS gmp_cis.stg_ims_history;

CREATE EXTERNAL TABLE gmp_cis.stg_ims_history (
    stg_id BIGINT,

    portfolio_short_name STRING,
    security_label STRING,
    valuation_date STRING,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    ims_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/staging/stg_ims_history'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');


-- ============================================================================
-- SEQUENCE INITIALIZATION (for Kudu-based sequence table)
-- ============================================================================

-- Add sequences for staging tables (sequences still use Kudu for atomic increments)
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_cis_positions_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_cis_summary_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_cis_history_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_gmp_positions_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_gmp_summary_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_gmp_history_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ams_positions_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ams_summary_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ams_history_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ims_positions_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ims_summary_id', 1000000, 1);
UPSERT INTO gmp_cis.cis_sequence VALUES ('stg_ims_history_id', 1000000, 1);


-- ============================================================================
-- VERIFICATION
-- ============================================================================

SHOW TABLES LIKE 'stg_%_positions';
SHOW TABLES LIKE 'stg_%_summary';
SHOW TABLES LIKE 'stg_%_history';


-- ============================================================================
-- NOTES ON HIVE/PARQUET STAGING TABLES
-- ============================================================================
-- 1. Staging tables are designed for bulk loading from source systems.
--
-- 2. Load pattern:
--    - Clear staging table (DROP/CREATE or TRUNCATE)
--    - Load new data via INSERT INTO or Spark DataFrame write
--    - Run merge_position_master.py to process staging data
--
-- 3. For incremental loads, use valuation_date and etl_batch_id for filtering.
--
-- 4. Parquet advantages for staging:
--    - Fast columnar reads for analytics queries
--    - Efficient compression reduces storage
--    - Schema enforcement at write time
--    - Compatible with Spark, Hive, Impala
-- ============================================================================


-- ============================================================================
-- END OF DDL
-- ============================================================================
