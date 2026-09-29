-- ============================================================================
-- Migration: Reorder columns in position_upload_report
-- ============================================================================
-- Purpose:
--   Move validation/status columns (row_status, fail_reason, portfolio_status,
--   security_status, price_status, quantity_status, exchange_status,
--   matched_security_id, matched_security_name) to appear immediately after
--   the isin column, before ticker. This makes the report easier to read.
--
-- Strategy: CTAS (Create Table As Select) — safe for Hive external tables.
--   1. Rename existing table to _old
--   2. Create new table at a new LOCATION with the new column order
--   3. Copy all data from old → new (INSERT INTO ... SELECT with explicit mapping)
--   4. Verify row counts match
--   5. Drop old table (data files at old LOCATION are preserved as external)
--
-- Run on UAT:
--   impala-shell -i <impala-host>:21050 -f migrate_position_upload_report_reorder_cols.sql
--
-- Safe to re-run: step 2 uses CREATE EXTERNAL TABLE IF NOT EXISTS.
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- STEP 1: Rename existing table to _old
-- ============================================================================
ALTER TABLE gmp_cis.position_upload_report
    RENAME TO gmp_cis.position_upload_report_old;


-- ============================================================================
-- STEP 2: Create new table with status columns after isin
-- ============================================================================
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_upload_report (
    -- Core identifiers
    portfolio                   STRING,
    security_full_name          STRING,
    security_short_name         STRING,
    isin                        STRING,

    -- Validation result columns (immediately after isin for quick review)
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


-- ============================================================================
-- STEP 3: Copy all data from old table to new (explicit column mapping)
--         Reads old columns by NAME, writes into new column order.
-- ============================================================================
SET hive.exec.dynamic.partition.mode=nonstrict;

INSERT INTO gmp_cis.position_upload_report
PARTITION (processing_date, src_id)
SELECT
    -- Core identifiers
    portfolio,
    security_full_name,
    security_short_name,
    isin,
    -- Status columns (pulled from end of old table, placed after isin)
    row_status,
    fail_reason,
    portfolio_status,
    security_status,
    price_status,
    quantity_status,
    exchange_status,
    matched_security_id,
    matched_security_name,
    -- Data columns
    ticker,
    quantity,
    shares_outstanding,
    shares_issued,
    pct_holding,
    market_price,
    average_cost,
    cost_fc,
    market_value_fc,
    net_book_value_fc,
    unrealized_pnl_fc,
    provision_fc,
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    provision_lc,
    product_type,
    security_type,
    quoted_unquoted,
    industry,
    fin_nonfin_co,
    issuer_type,
    reits_or_fund_y_n,
    exchange,
    country_of_exchange,
    country_of_incorporation,
    country_of_risk,
    country_of_operation,
    security_currency,
    corp_code,
    branch_code,
    cost_centre,
    cels,
    bwcif_sg,
    bwcif_ovs,
    mas_6d_code_sg,
    mas_6d_code_ovs,
    position_basis,
    reporting_date,
    maturity_date,
    src_system,
    source_table,
    -- Partition columns last
    processing_date,
    src_id
FROM gmp_cis.position_upload_report_old;

-- Repair partitions on new table
MSCK REPAIR TABLE gmp_cis.position_upload_report;


-- ============================================================================
-- STEP 4: Verify row counts match before dropping old table
--         Run this manually and confirm counts are equal before step 5.
-- ============================================================================
SELECT 'OLD' AS tbl, COUNT(*) AS row_count FROM gmp_cis.position_upload_report_old
UNION ALL
SELECT 'NEW' AS tbl, COUNT(*) AS row_count FROM gmp_cis.position_upload_report;


-- ============================================================================
-- STEP 5: Drop old table (external table — data files at old LOCATION are safe)
--         Only run after confirming row counts match in step 4.
-- ============================================================================
-- DROP TABLE IF EXISTS gmp_cis.position_upload_report_old;
