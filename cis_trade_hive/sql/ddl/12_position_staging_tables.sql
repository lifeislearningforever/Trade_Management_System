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
-- Database: gmp_cis
-- Created: 2026-02-09
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STAGING TABLE TEMPLATE
-- ============================================================================
-- All staging tables share a common schema for consistent processing.
-- Fields map to cis_position_master with source-specific extensions.
-- ============================================================================


-- ============================================================================
-- SOURCE 1: CIS (Cooperative Investment System)
-- ============================================================================
-- Internal positions from CIS trades. Already in cis_trade_position.
-- This staging table captures any external CIS position feeds.
-- ============================================================================

-- 1.1 CIS Positions
DROP TABLE IF EXISTS gmp_cis.stg_cis_positions_kudu;

CREATE TABLE gmp_cis.stg_cis_positions_kudu (
    stg_id BIGINT NOT NULL,

    -- Position Identity
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,

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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_cis_positions
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_cis_positions_kudu');

-- 1.2 CIS Summary
DROP TABLE IF EXISTS gmp_cis.stg_cis_summary_kudu;

CREATE TABLE gmp_cis.stg_cis_summary_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    valuation_date STRING NOT NULL,

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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 2
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_cis_summary
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_cis_summary_kudu');

-- 1.3 CIS History
DROP TABLE IF EXISTS gmp_cis.stg_cis_history_kudu;

CREATE TABLE gmp_cis.stg_cis_history_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,
    version_number INT,

    -- Snapshot Data
    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    -- Change Info
    change_type STRING,  -- BUY, SELL, ADJUSTMENT, PRICE_UPDATE
    change_amount DECIMAL(20,6),

    -- ETL Metadata
    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_cis_history
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_cis_history_kudu');


-- ============================================================================
-- SOURCE 2: GMP (Global Markets Platform)
-- ============================================================================

-- 2.1 GMP Positions
DROP TABLE IF EXISTS gmp_cis.stg_gmp_positions_kudu;

CREATE TABLE gmp_cis.stg_gmp_positions_kudu (
    stg_id BIGINT NOT NULL,

    -- Position Identity
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    cusip STRING,               -- GMP-specific
    sedol STRING,               -- GMP-specific

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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_gmp_positions
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_gmp_positions_kudu');

-- 2.2 GMP Summary
DROP TABLE IF EXISTS gmp_cis.stg_gmp_summary_kudu;

CREATE TABLE gmp_cis.stg_gmp_summary_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    valuation_date STRING NOT NULL,
    gmp_book_id STRING,

    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    currency_breakdown STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 2
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_gmp_summary
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_gmp_summary_kudu');

-- 2.3 GMP History
DROP TABLE IF EXISTS gmp_cis.stg_gmp_history_kudu;

CREATE TABLE gmp_cis.stg_gmp_history_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    gmp_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_gmp_history
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_gmp_history_kudu');


-- ============================================================================
-- SOURCE 3: AMS (Asset Management System)
-- ============================================================================

-- 3.1 AMS Positions
DROP TABLE IF EXISTS gmp_cis.stg_ams_positions_kudu;

CREATE TABLE gmp_cis.stg_ams_positions_kudu (
    stg_id BIGINT NOT NULL,

    -- Position Identity
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    ams_security_id STRING,     -- AMS-specific

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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ams_positions
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ams_positions_kudu');

-- 3.2 AMS Summary
DROP TABLE IF EXISTS gmp_cis.stg_ams_summary_kudu;

CREATE TABLE gmp_cis.stg_ams_summary_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    valuation_date STRING NOT NULL,
    ams_fund_code STRING,

    total_positions INT,
    total_market_value DECIMAL(20,6),
    total_cost_value DECIMAL(20,6),
    total_unrealized_pnl DECIMAL(20,6),
    total_realized_pnl DECIMAL(20,6),

    nav DECIMAL(20,6),              -- Net Asset Value
    nav_per_unit DECIMAL(20,6),

    currency_breakdown STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 2
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ams_summary
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ams_summary_kudu');

-- 3.3 AMS History
DROP TABLE IF EXISTS gmp_cis.stg_ams_history_kudu;

CREATE TABLE gmp_cis.stg_ams_history_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    ams_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ams_history
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ams_history_kudu');


-- ============================================================================
-- SOURCE 4: IMS (Investment Management System)
-- ============================================================================

-- 4.1 IMS Positions
DROP TABLE IF EXISTS gmp_cis.stg_ims_positions_kudu;

CREATE TABLE gmp_cis.stg_ims_positions_kudu (
    stg_id BIGINT NOT NULL,

    -- Position Identity
    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,

    -- Security Reference
    isin STRING,
    security_name STRING,
    security_type STRING,
    ticker STRING,
    ims_instrument_id STRING,   -- IMS-specific

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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ims_positions
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ims_positions_kudu');

-- 4.2 IMS Summary
DROP TABLE IF EXISTS gmp_cis.stg_ims_summary_kudu;

CREATE TABLE gmp_cis.stg_ims_summary_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    valuation_date STRING NOT NULL,
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
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 2
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ims_summary
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ims_summary_kudu');

-- 4.3 IMS History
DROP TABLE IF EXISTS gmp_cis.stg_ims_history_kudu;

CREATE TABLE gmp_cis.stg_ims_history_kudu (
    stg_id BIGINT NOT NULL,

    portfolio_short_name STRING NOT NULL,
    security_label STRING NOT NULL,
    valuation_date STRING NOT NULL,
    version_number INT,

    quantity DECIMAL(20,6),
    market_value DECIMAL(20,6),
    cost_value DECIMAL(20,6),
    unrealized_pnl DECIMAL(20,6),

    change_type STRING,
    change_amount DECIMAL(20,6),
    ims_trade_id STRING,

    etl_batch_id STRING,
    etl_load_timestamp BIGINT,

    PRIMARY KEY (stg_id)
)
PARTITION BY HASH (stg_id) PARTITIONS 4
STORED AS KUDU;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.stg_ims_history
STORED AS KUDU
TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.stg_ims_history_kudu');


-- ============================================================================
-- SEQUENCE INITIALIZATION
-- ============================================================================

-- Add sequences for staging tables
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
-- END OF DDL
-- ============================================================================
