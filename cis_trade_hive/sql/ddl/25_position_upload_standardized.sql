-- ============================================================================
-- Position Upload Standardized Table DDL
-- ============================================================================
-- Description:
--   Single Hive external table that receives all 5 user upload position files
--   after normalization. The ETL reads from the 5 source tables and inserts
--   into this unified table.
--
-- Partitions: src_id, processing_date
--   src_id          = source system identifier (e.g. cis_user_sta_adhoc_position_1..5)
--   processing_date = load date YYYYMMDD
--
-- IMPORTANT: Column types match the LIVE CML table (verified 2026-05-05).
--   Numeric columns are DECIMAL (not STRING). isin is isin_code. exchange is exchange.
--
-- Database: gmp_cis
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. STAGING TABLE: position_upload_standardized
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_standardized (
    -- Core identifiers
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,
    ticker                      STRING,

    -- Quantity & holdings
    quantity                    DECIMAL(18,4),
    shares_outstanding          DECIMAL(18,4),
    shares_issued               DECIMAL(18,4),
    pct_holding                 DECIMAL(10,6),

    -- Pricing
    market_price                DECIMAL(18,6),
    average_cost                DECIMAL(18,6),

    -- Cost (FC = Foreign/Security Currency)
    cost_fc                     DECIMAL(18,4),
    market_value_fc             DECIMAL(18,4),
    net_book_value_fc           DECIMAL(18,4),
    unrealized_pnl_fc           DECIMAL(18,4),
    provision_fc                DECIMAL(18,4),

    -- Cost (LC = Local/Portfolio Currency)
    cost_lc                     DECIMAL(18,4),
    market_value_lc             DECIMAL(18,4),
    net_book_value_lc           DECIMAL(18,4),
    unrealized_pnl_lc           DECIMAL(18,4),
    provision_lc                DECIMAL(18,4),

    -- Security classification
    product_type                STRING,
    security_type               STRING,
    quoted_unquoted             STRING,
    industry                    STRING,
    fin_nonfin_co               STRING,
    issuer_type                 STRING,
    reits_or_fund_y_n           STRING,

    -- Geography
    exchange                    STRING,
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
    etl_insert_ts               TIMESTAMP,
    etl_batch_id                STRING
)
COMMENT 'Unified position upload staging table — normalised from 5 user upload sources'
PARTITIONED BY (
    src_id          STRING COMMENT 'Source table name (cis_user_sta_adhoc_position_1..5)',
    processing_date STRING COMMENT 'Load date YYYYMMDD'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_upload_standardized';


-- ============================================================================
-- 2. REPORT TABLE: position_upload_report
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_report (
    -- Original upload columns (echo back to user)
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,
    ticker                      STRING,
    quantity                    DECIMAL(18,4),
    shares_outstanding          DECIMAL(18,4),
    shares_issued               DECIMAL(18,4),
    pct_holding                 DECIMAL(10,6),
    market_price                DECIMAL(18,6),
    average_cost                DECIMAL(18,6),
    cost_fc                     DECIMAL(18,4),
    market_value_fc             DECIMAL(18,4),
    net_book_value_fc           DECIMAL(18,4),
    unrealized_pnl_fc           DECIMAL(18,4),
    provision_fc                DECIMAL(18,4),
    cost_lc                     DECIMAL(18,4),
    market_value_lc             DECIMAL(18,4),
    net_book_value_lc           DECIMAL(18,4),
    unrealized_pnl_lc           DECIMAL(18,4),
    provision_lc                DECIMAL(18,4),
    product_type                STRING,
    security_type               STRING,
    quoted_unquoted             STRING,
    industry                    STRING,
    fin_nonfin_co               STRING,
    issuer_type                 STRING,
    reits_or_fund_y_n           STRING,
    exchange                    STRING,
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

    -- Validation result columns
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
    src_id          STRING COMMENT 'Source table name, matches position_upload_standardized',
    processing_date STRING COMMENT 'Load date YYYYMMDD'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_upload_report';


-- ============================================================================
-- Partition repair (run after data load)
-- ============================================================================
-- MSCK REPAIR TABLE gmp_cis.position_upload_standardized;
-- MSCK REPAIR TABLE gmp_cis.position_upload_report;
