-- ============================================================================
-- Migration: Add rounding_method column to cis_trade_charge_lut
-- ============================================================================
-- Purpose:
--   Each fee row in cis_trade_charge_lut can now specify how its calculated
--   fee amount should be rounded before being summed into the trade's total
--   charges: 'Rounding Nearest' | 'Round down' | 'Round up', at currency
--   precision (2 decimal places). Requested by Venkata Narayana Adisetty
--   (Teams, 2026-07-29); precision confirmed as "currency precision" (2dp)
--   on 2026-07-30.
--
-- Kudu supports adding a nullable column online -- no CTAS/rebuild needed.
--
-- Run:
--   impala-shell -i <impala-host>:21050 -f add_rounding_method_to_trade_charge_lut.sql
--
-- Safe to re-run: ALTER TABLE ADD COLUMNS will error if the column already
-- exists -- check first with DESCRIBE if unsure.
-- ============================================================================

ALTER TABLE gmp_cis.cis_trade_charge_lut
ADD COLUMNS (rounding_method STRING COMMENT 'Rounding Nearest | Round down | Round up -- applied at currency precision (2dp) before summing into total_charges');

-- ============================================================================
-- Backfill existing UOB KAY HIAN PL* / SGX / SG rows
-- ============================================================================

UPDATE gmp_cis.cis_trade_charge_lut
SET rounding_method = 'Rounding Nearest'
WHERE fee_type = 'Brokerage Fee' AND broker = 'UOB KAY HIAN PL*' AND exchange = 'SGX';

UPDATE gmp_cis.cis_trade_charge_lut
SET rounding_method = 'Round down'
WHERE fee_type = 'Clearing Fee' AND broker = 'UOB KAY HIAN PL*' AND exchange = 'SGX';

UPDATE gmp_cis.cis_trade_charge_lut
SET rounding_method = 'Round up'
WHERE fee_type = 'FFP/SGX SI FEE' AND broker = 'UOB KAY HIAN PL*' AND exchange = 'SGX';

UPDATE gmp_cis.cis_trade_charge_lut
SET rounding_method = 'Rounding Nearest'
WHERE fee_type = 'GST' AND broker = 'UOB KAY HIAN PL*' AND exchange = 'SGX';

UPDATE gmp_cis.cis_trade_charge_lut
SET rounding_method = 'Round up'
WHERE fee_type = 'Trading Fee' AND broker = 'UOB KAY HIAN PL*' AND exchange = 'SGX';

-- ============================================================================
-- Verify
-- ============================================================================
-- SELECT fee_type, broker, exchange, fee_rule, fee_value, rounding_method
-- FROM gmp_cis.cis_trade_charge_lut
-- ORDER BY broker, fee_type;
