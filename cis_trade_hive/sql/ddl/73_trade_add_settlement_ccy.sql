-- DDL: Add settlement_ccy column to cis_trade
-- Ticket: PORTIARP-7597 (follow-up)
-- Reason: Settlement currency can differ from portfolio base currency.
--         Replaces the unused cash_balance field with a proper settlement CCY selector.
-- Run on: local Docker, SIT, UAT, PROD

ALTER TABLE gmp_cis.cis_trade ADD COLUMNS (settlement_ccy STRING);

-- Verify
DESCRIBE gmp_cis.cis_trade;
