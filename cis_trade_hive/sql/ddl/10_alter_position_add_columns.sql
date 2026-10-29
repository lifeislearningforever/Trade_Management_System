-- ============================================================================
-- ALTER TABLE: Add new columns to cis_trade_position
-- ============================================================================
-- Description: Adds columns for multi-currency position tracking with FX conversion
--              - Security and Portfolio currency tracking
--              - Local (security ccy) and Base (portfolio ccy) value columns
--              - FX rate is NOT stored - it's looked up dynamically from fx_rates table
--
-- Database: gmp_cis
-- Created: 2026-02-09
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- New columns for cis_trade_position table
-- ============================================================================

-- Source system tracking
ALTER TABLE cis_trade_position ADD COLUMNS (src_system STRING);

-- Currency tracking
ALTER TABLE cis_trade_position ADD COLUMNS (security_currency STRING);
ALTER TABLE cis_trade_position ADD COLUMNS (portfolio_currency STRING);

-- Percentage ratio
ALTER TABLE cis_trade_position ADD COLUMNS (pct_ratio DECIMAL(10,6));

-- Security reference
ALTER TABLE cis_trade_position ADD COLUMNS (isin STRING);

-- Classification columns
ALTER TABLE cis_trade_position ADD COLUMNS (country STRING);
ALTER TABLE cis_trade_position ADD COLUMNS (asset_class STRING);
ALTER TABLE cis_trade_position ADD COLUMNS (listing_status STRING);

-- Cost values - Local (security currency) and Base (portfolio currency)
ALTER TABLE cis_trade_position ADD COLUMNS (cost_value_local DECIMAL(20,6));
ALTER TABLE cis_trade_position ADD COLUMNS (cost_value_base DECIMAL(20,6));

-- Market values - Local (security currency) and Base (portfolio currency)
ALTER TABLE cis_trade_position ADD COLUMNS (market_value_local DECIMAL(20,6));
ALTER TABLE cis_trade_position ADD COLUMNS (market_value_base DECIMAL(20,6));

-- Unrealized P&L - Local (security currency) and Base (portfolio currency)
ALTER TABLE cis_trade_position ADD COLUMNS (unrealized_pnl_local DECIMAL(20,6));
ALTER TABLE cis_trade_position ADD COLUMNS (unrealized_pnl_base DECIMAL(20,6));

-- Valuation date
ALTER TABLE cis_trade_position ADD COLUMNS (valuation_date STRING);

-- Market unit price (from equity price)
ALTER TABLE cis_trade_position ADD COLUMNS (market_unit_price DECIMAL(20,6));

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_trade_position;

-- ============================================================================
-- NOTES:
-- ============================================================================
-- FX Rate Calculation Logic (in Python code, not stored):
--   1. Get portfolio currency from cis_portfolio table
--   2. Get security currency from cis_security table
--   3. Build FX pair: {portfolio_ccy}-{security_ccy} (e.g., USD-SGD)
--   4. Lookup rate from gmp_cis_sta_dly_fx_rates table
--   5. Calculate:
--      - cost_value_local = quantity * average_cost (in security ccy)
--      - market_value_local = quantity * current_price (in security ccy)
--      - unrealized_pnl_local = market_value_local - cost_value_local
--      - cost_value_base = cost_value_local * fx_rate (in portfolio ccy)
--      - market_value_base = market_value_local * fx_rate (in portfolio ccy)
--      - unrealized_pnl_base = unrealized_pnl_local * fx_rate (in portfolio ccy)
-- ============================================================================
