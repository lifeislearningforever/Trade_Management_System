-- ============================================================================
-- ALTER TABLE: Add portfolio_currency to cis_trade
-- ============================================================================
-- Description: Add portfolio_currency column to store the portfolio's base
--              currency separate from the security's trading currency.
--
-- Currency Definitions:
--   - currency_code: Security's trading currency (Foreign Currency / FC)
--   - portfolio_currency: Portfolio's base currency (Local Currency / LC)
--
-- Example:
--   Portfolio SGD-FUND has currency SGD (portfolio_currency = 'SGD')
--   Security AAPL trades in USD (currency_code = 'USD')
--   FX conversion needed: USD -> SGD
--
-- Created: 2026-03-25
-- ============================================================================

USE gmp_cis;

-- Add portfolio_currency column to cis_trade
ALTER TABLE cis_trade ADD COLUMNS (portfolio_currency STRING);

-- Verify the column was added
-- DESCRIBE cis_trade;

-- ============================================================================
-- Data Migration: Populate portfolio_currency from cis_portfolio
-- ============================================================================
-- Run this after the ALTER TABLE to backfill existing data

-- UPDATE cis_trade t
-- SET portfolio_currency = (
--     SELECT currency
--     FROM cis_portfolio p
--     WHERE p.name = t.portfolio_short_name
--     LIMIT 1
-- )
-- WHERE portfolio_currency IS NULL;

-- Note: Kudu doesn't support subquery in UPDATE SET clause.
-- Use the following approach instead:

-- Step 1: Create temp table with the mapping
-- CREATE TABLE temp_trade_portfolio_ccy AS
-- SELECT t.trade_id, p.currency AS portfolio_currency
-- FROM cis_trade t
-- JOIN cis_portfolio p ON t.portfolio_short_name = p.name;

-- Step 2: Update using UPSERT from temp table
-- For each row, you'd need to do individual updates or use Impala's MERGE
-- This is best done via Python script for bulk updates.

-- ============================================================================
-- END OF DDL
-- ============================================================================
