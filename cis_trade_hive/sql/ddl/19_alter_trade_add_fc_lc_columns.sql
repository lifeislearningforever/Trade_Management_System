-- ============================================================================
-- DDL: Add FC/LC columns to cis_trade table
-- Date: 2026-03-27
-- Description: Add total_amount_fc and total_amount_lc columns for multi-currency support
-- ============================================================================

-- Kudu doesn't support ALTER TABLE ADD COLUMN directly
-- Need to recreate the table or use a workaround

-- Option 1: Add columns via Impala (if supported by your Kudu version)
-- Note: This may require Kudu 1.10+ and Impala 3.2+

ALTER TABLE gmp_cis.cis_trade ADD COLUMNS (
    total_amount_fc DECIMAL(20,8) COMMENT 'Total amount in Foreign Currency (Security CCY)',
    total_amount_lc DECIMAL(20,8) COMMENT 'Total amount in Local Currency (Portfolio CCY)'
);

-- ============================================================================
-- If ALTER TABLE ADD COLUMNS fails, run this SELECT to verify current schema:
-- DESCRIBE gmp_cis.cis_trade;
-- ============================================================================

-- ============================================================================
-- Migration Notes:
--
-- 1. total_amount_fc = Total Amount in Security/Foreign Currency
--    - This is the same as the old 'total_amount' field
--    - Formula: gross_amount + commission + sec_fee + other_charges (BUY)
--              gross_amount - commission - sec_fee - other_charges (SELL)
--
-- 2. total_amount_lc = Total Amount in Portfolio/Local Currency
--    - Formula: total_amount_fc * open_fx_rate
--    - This is the LC value at trade time (historical rate)
--
-- 3. Data Migration (populate existing trades):
--    UPDATE gmp_cis.cis_trade
--    SET total_amount_fc = total_amount,
--        total_amount_lc = total_amount * COALESCE(open_fx_rate, 1)
--    WHERE total_amount_fc IS NULL;
-- ============================================================================
