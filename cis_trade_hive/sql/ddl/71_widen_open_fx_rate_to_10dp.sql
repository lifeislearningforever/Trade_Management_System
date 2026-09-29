-- DDL 71: Widen open_fx_rate in cis_trade from DECIMAL(20,6) to DECIMAL(20,10)
-- Reason: FX rates can require up to 10 decimal places for cross-currency precision.
-- Run on: all environments (local, SIT, UAT, PROD)

ALTER TABLE gmp_cis.cis_trade
    ALTER COLUMN open_fx_rate SET DATA TYPE DECIMAL(20,10);
