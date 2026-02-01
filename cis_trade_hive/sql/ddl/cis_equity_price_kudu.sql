-- =====================================================
-- Equity Price Kudu Table DDL (Versioned)
-- =====================================================
-- Purpose: Store daily equity/security closing prices with version history
-- Module: Market Data - Equity Price
-- Author: CisTrade Team
-- Created: 2026-01-04
-- Updated: 2026-01-28 - Changed to composite key (currency_code + security_label)
-- Updated: 2026-01-31 - Added price_date to PK for versioned price history
-- =====================================================
-- Design: Each (currency_code, security_label, price_date) is a unique row.
-- Multiple prices per security are supported (one per date).
-- Latest price = ORDER BY price_date DESC, price_timestamp DESC LIMIT 1
-- CIS-created prices have src_system = 'CIS'
-- =====================================================

-- Drop existing tables if recreating
DROP TABLE IF EXISTS gmp_cis.cis_equity_price;
DROP TABLE IF EXISTS gmp_cis.cis_equity_price_kudu;

-- Create Kudu table with versioned composite primary key
-- PK now includes price_date to allow multiple prices per security (one per date)
CREATE TABLE gmp_cis.cis_equity_price_kudu (
    -- Composite Primary Key fields (currency + security + date)
    currency_code STRING NOT NULL,           -- From gmp_cis_sta_dly_currency.curr_name
    security_label STRING NOT NULL,          -- From cis_security.security_name
    price_date STRING NOT NULL,              -- Date in YYYY-MM-DD format (part of PK)

    -- Business Fields
    isin STRING,                             -- From cis_security.isin
    main_closing_price DECIMAL(18, 6),       -- Main closing price
    price_timestamp BIGINT,                  -- Unix timestamp (milliseconds)
    src_system STRING DEFAULT 'CIS',         -- Source system identifier

    -- Audit Fields
    is_active BOOLEAN DEFAULT true,
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,              -- Unix timestamp (milliseconds)
    updated_by STRING,
    updated_at BIGINT,                       -- Unix timestamp (milliseconds)

    -- Composite Primary Key Constraint (includes price_date for versioning)
    PRIMARY KEY (currency_code, security_label, price_date)
)
PARTITION BY HASH (currency_code, security_label) PARTITIONS 16
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
-- Sample Inserts (versioned - multiple dates per security)
-- =====================================================
-- UPSERT INTO gmp_cis.cis_equity_price VALUES (
--     'USD',                              -- currency_code (PK1)
--     'Apple Inc.',                       -- security_label (PK2)
--     '2026-01-04',                       -- price_date (PK3)
--     'US0378331005',                     -- isin
--     150.25,                             -- main_closing_price
--     1704326400000,                      -- price_timestamp
--     'CIS',                              -- src_system
--     true,                               -- is_active
--     'SYSTEM',                           -- created_by
--     1704326400000,                      -- created_at
--     NULL,                               -- updated_by
--     NULL                                -- updated_at
-- );
--
-- -- Same security, different date = new version
-- UPSERT INTO gmp_cis.cis_equity_price VALUES (
--     'USD',                              -- currency_code (PK1)
--     'Apple Inc.',                       -- security_label (PK2)
--     '2026-01-05',                       -- price_date (PK3) - different date
--     'US0378331005',                     -- isin
--     152.50,                             -- main_closing_price (updated price)
--     1704412800000,                      -- price_timestamp
--     'CIS',                              -- src_system
--     true,                               -- is_active
--     'SYSTEM',                           -- created_by
--     1704412800000,                      -- created_at
--     NULL,                               -- updated_by
--     NULL                                -- updated_at
-- );

-- =====================================================
-- Useful Queries
-- =====================================================
-- Count all equity prices
-- SELECT COUNT(*) as total_prices FROM gmp_cis.cis_equity_price WHERE is_active = true;

-- Get latest price per security (most recent date)
-- SELECT currency_code, security_label, price_date, main_closing_price
-- FROM gmp_cis.cis_equity_price
-- WHERE is_active = true
-- ORDER BY price_date DESC, security_label
-- LIMIT 100;

-- Get latest price for a specific security
-- SELECT * FROM gmp_cis.cis_equity_price
-- WHERE security_label = 'Apple Inc.' AND is_active = true
-- ORDER BY price_date DESC, price_timestamp DESC
-- LIMIT 1;

-- Get price history for a security
-- SELECT * FROM gmp_cis.cis_equity_price
-- WHERE currency_code = 'USD' AND security_label = 'Apple Inc.'
--   AND is_active = true
-- ORDER BY price_date DESC;
