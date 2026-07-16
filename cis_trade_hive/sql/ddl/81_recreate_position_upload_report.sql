-- DDL Migration 81: Recreate position_upload_report with correct column order.
--
-- The table was originally created with validation status columns (row_status,
-- fail_reason, etc.) AFTER the upload data columns.  The ETL Step 7B SELECT
-- now emits them immediately after isin, so Parquet column positions no longer
-- match — Impala raises:
--   AnalysisException: Expression 'b.quantity' (type: DECIMAL(30,8))
--   is not compatible with column 'fail_reason' (type: STRING)
--
-- Fix: drop the external table (does NOT delete Parquet data on HDFS) and
-- recreate it with the corrected DDL from 25_position_upload_standardized.sql.
--
-- Run on server:
--   impala-shell -i <host>:21050 -f 81_recreate_position_upload_report.sql
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS gmp_cis.position_upload_report;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_report (
    -- Core identifiers
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,

    -- Validation result columns (immediately after ISIN for quick review)
    row_status                  STRING  COMMENT 'PASS or FAIL',
    fail_reason                 STRING  COMMENT 'Null if PASS; detailed reason if FAIL',
    portfolio_status            STRING  COMMENT 'Step 1 portfolio check result',
    security_status             STRING  COMMENT 'Step 2 security match result',
    price_status                STRING  COMMENT 'Step 3 price lookup result',
    quantity_status             STRING  COMMENT 'Step 4 quantity check result',
    exchange_status             STRING  COMMENT 'Step 5 exchange check result',
    matched_security_id         STRING  COMMENT 'Matched security ID (if found)',
    matched_security_name       STRING  COMMENT 'Matched security name (if found)',

    -- Original upload columns (echo back to user)
    ticker                      STRING,
    quantity                    DECIMAL(30,8),
    shares_outstanding          DECIMAL(30,8),
    shares_issued               DECIMAL(30,8),
    pct_holding                 DECIMAL(10,6),
    market_price                DECIMAL(30,8),
    average_cost                DECIMAL(30,8),
    cost_fc                     DECIMAL(30,8),
    market_value_fc             DECIMAL(30,8),
    net_book_value_fc           DECIMAL(30,8),
    unrealized_pnl_fc           DECIMAL(30,8),
    provision_fc                DECIMAL(30,8),
    cost_lc                     DECIMAL(30,8),
    market_value_lc             DECIMAL(30,8),
    net_book_value_lc           DECIMAL(30,8),
    unrealized_pnl_lc           DECIMAL(30,8),
    provision_lc                DECIMAL(30,8),
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
    source_table                STRING
)
COMMENT 'Position upload validation report — one row per uploaded row, with PASS/FAIL status'
PARTITIONED BY (
    processing_date STRING COMMENT 'Load date YYYYMMDD',
    src_id          STRING COMMENT 'Source table name, matches position_upload_standardized'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_upload_report';

-- Reload partitions from existing Parquet files (if any historical data should
-- be preserved — otherwise the table starts empty and Step 7B will repopulate
-- it on the next ETL run).
-- MSCK REPAIR TABLE gmp_cis.position_upload_report;
