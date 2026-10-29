-- DDL: Rename cash_balance → settlement_ccy in gmp_cis.cis_portfolio
-- Kudu does not support ALTER TABLE RENAME COLUMN, so:
--   Step 1: Add new column settlement_ccy
--   Step 2: Copy existing data across
--   Step 3: Drop old column cash_balance
--
-- Run on: local Docker → SIT → UAT → PROD (in order)
-- Ticket: PORTIARP-7597 follow-up

-- Step 1: Add new column
ALTER TABLE gmp_cis.cis_portfolio ADD COLUMNS (settlement_ccy STRING);

-- Step 2: Copy data (cash_balance stored currency codes like 'SGD', 'USD')
UPDATE gmp_cis.cis_portfolio SET settlement_ccy = CAST(cash_balance AS STRING);

-- Step 3: Drop old column
ALTER TABLE gmp_cis.cis_portfolio DROP COLUMN cash_balance;

-- Verify
DESCRIBE gmp_cis.cis_portfolio;
SELECT name, currency, settlement_ccy FROM gmp_cis.cis_portfolio LIMIT 10;
