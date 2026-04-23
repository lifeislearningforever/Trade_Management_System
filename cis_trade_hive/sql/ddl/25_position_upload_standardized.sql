-- ============================================================================
-- Position Upload Standardized Table DDL
-- ============================================================================
-- Description:
--   Single Hive external table that receives all 5 user upload position files
--   after normalization. The ETL (04_position_master_etl_hive.sql) reads from
--   the 5 source tables and inserts into this unified table.
--
--   Replaces: position_master (renamed to position_upload_standardized)
--
-- Partitions: src_id, processing_date
--   src_id          = source system identifier (e.g. USER_UPLOAD_1 .. 5)
--   processing_date = load date YYYYMMDD
--
-- Report Table: position_upload_report
--   Same rows as upload + status (PASS/FAIL) + reason columns.
--   Used for CSV download returned to user.
--
-- Database: gmp_cis
-- Created: 2026-04-23
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. STAGING TABLE: position_upload_standardized
--    Replaces the old position_master table for user upload flow.
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_standardized (
    -- Core identifiers
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,
    ticker                      STRING,

    -- Quantity & holdings
    quantity                    STRING,
    shares_outstanding          STRING,
    shares_issued               STRING,
    pct_holding                 STRING,

    -- Pricing
    market_price                STRING,
    average_cost                STRING,

    -- Cost (FC = Foreign/Security Currency)
    cost_fc                     STRING,
    market_value_fc             STRING,
    net_book_value_fc           STRING,
    unrealized_pnl_fc           STRING,
    provision_fc                STRING,

    -- Cost (LC = Local/Portfolio Currency)
    cost_lc                     STRING,
    market_value_lc             STRING,
    net_book_value_lc           STRING,
    unrealized_pnl_lc           STRING,
    provision_lc                STRING,

    -- Security classification
    product_type                STRING,
    security_type               STRING,
    quoted_unquoted             STRING,
    industry                    STRING,
    fin_nonfin_co               STRING,
    issuer_type                 STRING,
    reits_or_fund_y_n           STRING,

    -- Geography
    exchange_code               STRING,
    country_code                STRING,
    country_of_exchange         STRING,
    country_of_incorporation    STRING,
    country_of_risk             STRING,
    country_of_operation        STRING,
    security_currency           STRING,

    -- Corporate
    corp_code                   STRING,
    branch_code                 STRING,
    cost_centre                 STRING,
    cels                        STRING,
    bwcif_sg                    STRING,
    bwcif_ovs                   STRING,
    mas_6d_code_sg              STRING,
    mas_6d_code_ovs             STRING,

    -- Dates
    position_basis              STRING,
    reporting_date              STRING,
    maturity_date               STRING,

    -- ETL metadata
    src_system                  STRING,
    sub_system                  STRING,
    data_cat                    STRING,
    data_frq                    STRING,
    source_table                STRING,
    etl_insert_ts               STRING,
    etl_batch_id                STRING
)
COMMENT 'Unified position upload staging table — normalised from 5 user upload sources'
PARTITIONED BY (
    src_id          STRING COMMENT 'Source system ID (USER_UPLOAD_1 .. USER_UPLOAD_5)',
    processing_date STRING COMMENT 'Load date YYYYMMDD'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_upload_standardized';


-- ============================================================================
-- 2. REPORT TABLE: position_upload_report
--    Hive external table written after the transform/validation run.
--    Contains every uploaded row + PASS/FAIL status + reason.
--    Partitioned by src_id + processing_date so the Django view can query
--    by upload batch and serve as CSV download.
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_report (
    -- Original upload columns (echo back to user)
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,
    ticker                      STRING,
    quantity                    STRING,
    shares_outstanding          STRING,
    shares_issued               STRING,
    pct_holding                 STRING,
    market_price                STRING,
    average_cost                STRING,
    cost_fc                     STRING,
    market_value_fc             STRING,
    net_book_value_fc           STRING,
    unrealized_pnl_fc           STRING,
    provision_fc                STRING,
    cost_lc                     STRING,
    market_value_lc             STRING,
    net_book_value_lc           STRING,
    unrealized_pnl_lc           STRING,
    provision_lc                STRING,
    product_type                STRING,
    security_type               STRING,
    quoted_unquoted             STRING,
    industry                    STRING,
    fin_nonfin_co               STRING,
    issuer_type                 STRING,
    reits_or_fund_y_n           STRING,
    exchange_code               STRING,
    country_of_exchange         STRING,
    country_of_incorporation    STRING,
    country_of_risk             STRING,
    country_of_operation        STRING,
    security_currency           STRING,
    corp_code                   STRING,
    branch_code                 STRING,
    cost_centre                 STRING,
    cels                        STRING,
    bwcif_sg                    STRING,
    bwcif_ovs                   STRING,
    mas_6d_code_sg              STRING,
    mas_6d_code_ovs             STRING,
    position_basis              STRING,
    reporting_date              STRING,
    maturity_date               STRING,
    src_system                  STRING,
    source_table                STRING,

    -- Validation result columns (extra columns added by transform)
    row_status                  STRING  COMMENT 'PASS or FAIL',
    fail_reason                 STRING  COMMENT 'Null if PASS; detailed reason if FAIL',
    portfolio_status            STRING  COMMENT 'Step 1 portfolio check result',
    security_status             STRING  COMMENT 'Step 2 security match result',
    price_status                STRING  COMMENT 'Step 3 price lookup result',
    quantity_status             STRING  COMMENT 'Step 4 quantity check result',
    exchange_status             STRING  COMMENT 'Step 5 exchange check result',
    matched_security_id         STRING  COMMENT 'Matched security ID (if found)',
    matched_security_name       STRING  COMMENT 'Matched security name (if found)'
)
COMMENT 'Position upload validation report — one row per uploaded row, with PASS/FAIL status'
PARTITIONED BY (
    src_id          STRING COMMENT 'Source system ID, matches position_upload_standardized',
    processing_date STRING COMMENT 'Load date YYYYMMDD'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_upload_report';


-- ============================================================================
-- Partition repair (run after data load)
-- ============================================================================
-- MSCK REPAIR TABLE gmp_cis.position_upload_standardized;
-- MSCK REPAIR TABLE gmp_cis.position_upload_report;
