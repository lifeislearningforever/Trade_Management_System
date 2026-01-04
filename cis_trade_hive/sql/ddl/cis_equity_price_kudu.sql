-- =====================================================
-- Equity Price Kudu Table DDL
-- =====================================================
-- Purpose: Store daily equity/security closing prices
-- Module: Market Data - Equity Price
-- Author: CisTrade Team
-- Created: 2026-01-04
-- =====================================================

-- Drop existing tables if recreating
DROP TABLE IF EXISTS gmp_cis.cis_equity_price;
DROP TABLE IF EXISTS gmp_cis.cis_equity_price_kudu;

-- Create Kudu table
CREATE TABLE gmp_cis.cis_equity_price_kudu (
    -- Primary Key
    equity_price_id BIGINT NOT NULL,

    -- Business Fields
    currency_code STRING NOT NULL,           -- From gmp_cis_sta_dly_currency.curr_name
    security_label STRING NOT NULL,          -- From cis_security.security_name
    isin STRING,                             -- From cis_security.isin
    price_date STRING NOT NULL,              -- Date in YYYY-MM-DD format
    main_closing_price DECIMAL(18, 6),       -- Main closing price
    market STRING,                           -- From UDF (e.g., NYSE, SGX, LSE)
    price_timestamp BIGINT,                  -- Unix timestamp (milliseconds)
    group_name STRING,                       -- Group classification

    -- Audit Fields
    is_active BOOLEAN DEFAULT true,
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,              -- Unix timestamp (milliseconds)
    updated_by STRING,
    updated_at BIGINT,                       -- Unix timestamp (milliseconds)

    -- Primary Key Constraint
    PRIMARY KEY (equity_price_id)
)
PARTITION BY HASH (equity_price_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3',
    'kudu.table_name' = 'impala::gmp_cis.cis_equity_price_kudu'
);

-- Create Impala external table pointing to Kudu
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_equity_price
STORED AS KUDU
TBLPROPERTIES(
    'kudu.table_name' = 'impala::gmp_cis.cis_equity_price_kudu'
);

-- =====================================================
-- Sample Insert (for testing)
-- =====================================================
-- INSERT INTO gmp_cis.cis_equity_price_kudu VALUES (
--     1,                                  -- equity_price_id
--     'USD',                              -- currency_code
--     'Apple Inc.',                       -- security_label
--     'US0378331005',                     -- isin
--     '2026-01-04',                       -- price_date
--     150.25,                             -- main_closing_price
--     'NASDAQ',                           -- market
--     1704326400000,                      -- price_timestamp
--     'Technology',                       -- group_name
--     true,                               -- is_active
--     'SYSTEM',                           -- created_by
--     1704326400000,                      -- created_at
--     NULL,                               -- updated_by
--     NULL                                -- updated_at
-- );

-- =====================================================
-- Useful Queries
-- =====================================================
-- Count all equity prices
-- SELECT COUNT(*) as total_prices FROM gmp_cis.cis_equity_price WHERE is_active = true;

-- Get latest prices per security
-- SELECT security_label, currency_code, price_date, main_closing_price, market
-- FROM gmp_cis.cis_equity_price
-- WHERE is_active = true
-- ORDER BY price_date DESC, security_label
-- LIMIT 100;

-- Get price history for a specific security
-- SELECT price_date, main_closing_price, market
-- FROM gmp_cis.cis_equity_price
-- WHERE security_label = 'Apple Inc.'
--   AND is_active = true
-- ORDER BY price_date DESC
-- LIMIT 30;
