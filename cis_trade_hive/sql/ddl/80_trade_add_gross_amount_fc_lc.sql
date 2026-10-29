-- ============================================================================
-- Migration 80: Add gross_amount_fc / gross_amount_lc to cis_trade
-- ============================================================================
-- Rationale (PORTIARP-8206):
--   Trade should carry both gross (qty × price, no charges) and total
--   (gross + charges) amounts in both currencies.
--
--   gross_amount_fc = qty × price              (security/foreign currency)
--   gross_amount_lc = gross_amount_fc × fx_rate (portfolio/local currency)
--   total_amount_fc = gross_amount_fc + charges (existing, unchanged)
--   total_amount_lc = total_fc × fx_rate        (existing, unchanged)
--
--   AVP position cost basis uses gross amounts only.
--
-- Run with:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     -f 80_trade_add_gross_amount_fc_lc.sql
-- ============================================================================

USE gmp_cis;

-- Step 1: Add new columns
ALTER TABLE gmp_cis.cis_trade
    ADD COLUMNS (
        gross_amount_fc DECIMAL(30,8) COMMENT 'Gross amount FC: qty x price (no charges) — AVP cost basis',
        gross_amount_lc DECIMAL(30,8) COMMENT 'Gross amount LC: gross_fc x fx_rate (no charges)'
    );

-- ============================================================================
-- Step 2: Backfill from existing data
-- gross_amount_fc = total_amount_fc - (commission + sec_fee + other_charges)
-- gross_amount_lc = total_amount_lc × (gross_fc / total_fc)  where total_fc != 0
--                   else gross_amount_fc (same currency, rate = 1)
-- ============================================================================
UPDATE gmp_cis.cis_trade
SET gross_amount_fc = CAST(
        total_amount_fc
        - COALESCE(commission, 0)
        - COALESCE(sec_fee, 0)
        - COALESCE(other_charges, 0)
    AS DECIMAL(30,8))
WHERE total_amount_fc IS NOT NULL AND total_amount_fc != 0;

-- gross_amount_lc: scale total_amount_lc by (gross_fc / total_fc)
UPDATE gmp_cis.cis_trade
SET gross_amount_lc = CAST(
        total_amount_lc * (
            (total_amount_fc - COALESCE(commission, 0) - COALESCE(sec_fee, 0) - COALESCE(other_charges, 0))
            / total_amount_fc
        )
    AS DECIMAL(30,8))
WHERE total_amount_fc IS NOT NULL AND total_amount_fc != 0
  AND total_amount_lc IS NOT NULL AND total_amount_lc != 0;

-- Fallback: no charges or zero total — gross = total
UPDATE gmp_cis.cis_trade
SET gross_amount_fc = total_amount_fc,
    gross_amount_lc = total_amount_lc
WHERE gross_amount_fc IS NULL
  AND total_amount_fc IS NOT NULL;

-- ============================================================================
-- Verification
-- ============================================================================
-- SELECT trade_id, quantity, price,
--        commission, sec_fee, other_charges,
--        gross_amount_fc, total_amount_fc,
--        gross_amount_lc, total_amount_lc
-- FROM gmp_cis.cis_trade
-- ORDER BY created_at DESC
-- LIMIT 10;
