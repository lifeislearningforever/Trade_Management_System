-- ============================================================================
-- Position Table Column Rename & Dividend Tracking
-- ============================================================================
-- Description: Rename columns for consistency (FC = Foreign Currency, LC = Local Currency)
--              and add dividend tracking columns.
--
-- Run: impala-shell -i localhost:21050 -f sql/ddl/16_position_column_rename.sql
--
-- Changes:
--   1. average_cost -> average_cost_fc
--   2. average_cost_base -> average_cost_lc
--   3. total_cost -> total_cost_fc
--   4. total_cost_base -> total_cost_lc
--   5. current_price -> market_price
--   6. market_value -> market_value_fc
--   7. last_cash_flow_amount -> last_cash_flow_amount_fc
--   8. Add last_cash_flow_amount_lc
--   9. Add dividend_fc and dividend_lc for accumulated dividends
--  10. Remove legacy columns: unrealized_pnl, realized_pnl, realized_pnl_base
--
-- Created: 2026-03-30
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Step 1: Add new columns with correct naming
-- ============================================================================

-- Cost columns (FC = Foreign Currency = Security Currency)
ALTER TABLE cis_trade_position ADD COLUMNS (average_cost_fc DECIMAL(20,8));
ALTER TABLE cis_trade_position ADD COLUMNS (total_cost_fc DECIMAL(20,8));

-- Cost columns (LC = Local Currency = Portfolio Currency)
ALTER TABLE cis_trade_position ADD COLUMNS (average_cost_lc DECIMAL(20,8));
ALTER TABLE cis_trade_position ADD COLUMNS (total_cost_lc DECIMAL(20,8));

-- Market price (renamed from current_price)
ALTER TABLE cis_trade_position ADD COLUMNS (market_price DECIMAL(20,8));

-- Market value in FC (renamed from market_value)
ALTER TABLE cis_trade_position ADD COLUMNS (market_value_fc DECIMAL(20,8));

-- Cash flow amounts in both currencies
ALTER TABLE cis_trade_position ADD COLUMNS (last_cash_flow_amount_fc DECIMAL(20,8));
ALTER TABLE cis_trade_position ADD COLUMNS (last_cash_flow_amount_lc DECIMAL(20,8));

-- Dividend tracking columns (accumulated dividends from CA)
ALTER TABLE cis_trade_position ADD COLUMNS (dividend_fc DECIMAL(20,8));
ALTER TABLE cis_trade_position ADD COLUMNS (dividend_lc DECIMAL(20,8));

-- ============================================================================
-- Step 2: Copy data from old columns to new columns
-- ============================================================================
-- Note: In Kudu, we cannot UPDATE directly. Use UPSERT with SELECT.
-- This should be done in application code or via a migration script.
--
-- Data migration mapping:
--   average_cost -> average_cost_fc
--   average_cost_base -> average_cost_lc
--   total_cost -> total_cost_fc
--   total_cost_base -> total_cost_lc
--   current_price -> market_price
--   market_value -> market_value_fc
--   last_cash_flow_amount -> last_cash_flow_amount_lc (was in local currency)
--   NEW: dividend_fc = 0 (initialize)
--   NEW: dividend_lc = 0 (initialize)
--
-- Run this in application layer or as separate migration.

-- ============================================================================
-- Verify columns were added
-- ============================================================================
DESCRIBE cis_trade_position;

-- ============================================================================
-- DIVIDEND ACCUMULATION LOGIC (for CA Cash Flow processing)
-- ============================================================================
--
-- When a DIVIDEND corporate action is processed:
--   dividend_fc += foreign_ccy_amt   (from cash flow)
--   dividend_lc += local_ccy_amt     (from cash flow)
--
-- Example:
--   Position for AAPL in portfolio FUND-001
--   CA: DIVIDEND $0.25 per share, 100 shares held
--   Cash Flow: $25.00 FC, SGD$33.75 LC (FX 1.35)
--
--   After processing:
--     dividend_fc = 25.00 (accumulated)
--     dividend_lc = 33.75 (accumulated)
--
-- ============================================================================

-- ============================================================================
-- Sample query to verify new columns
-- ============================================================================
-- SELECT
--     portfolio_short_name,
--     security_label,
--     quantity,
--     average_cost_fc,
--     average_cost_lc,
--     total_cost_fc,
--     total_cost_lc,
--     market_price,
--     market_value_fc,
--     market_value_lc,
--     dividend_fc,
--     dividend_lc
-- FROM cis_trade_position
-- WHERE is_latest = true
-- LIMIT 10;

-- ============================================================================
-- END OF DDL
-- ============================================================================
