-- ================================================================
-- Insert Trade Charge Lookup Data
-- Database: gmp_cis
-- Table: cis_trade_charge_lut
-- Date: 2026-03-02
-- Description: Add all fee types for brokers
-- Run this in Impala
-- ================================================================

-- ================================================================
-- Fee Types:
-- 1. Brokerage Fee - Commission paid to broker (typically % of trade value)
-- 2. Clearing Fee - Fee for clearing the trade (typically % or flat)
-- 3. Trading Fee - Exchange trading fee (typically % or flat)
-- 4. GST - Goods & Services Tax (typically % of brokerage)
-- 5. FFP/SGX SI FEE - Other exchange-specific fees (typically flat)
-- ================================================================

-- First, check existing data
-- SELECT * FROM gmp_cis.cis_trade_charge_lut WHERE broker = 'UOB KAY HIAN PL*';

-- ================================================================
-- Insert additional fee types for UOB KAY HIAN PL*
-- ================================================================

-- Clearing Fee (0.0325% of trade value)
INSERT INTO gmp_cis.cis_trade_charge_lut (fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value)
VALUES ('Clearing Fee', 'UOB KAY HIAN PL*', 'SGX', 'SG', 'Percent', 0.0325);

-- Trading Fee (0.0075% of trade value)
INSERT INTO gmp_cis.cis_trade_charge_lut (fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value)
VALUES ('Trading Fee', 'UOB KAY HIAN PL*', 'SGX', 'SG', 'Percent', 0.0075);

-- GST (9% of brokerage fee - for Singapore)
-- Note: GST is typically calculated on brokerage, but here we apply to trade value
-- If brokerage is 1%, GST at 9% of that = 0.09% of trade value
INSERT INTO gmp_cis.cis_trade_charge_lut (fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value)
VALUES ('GST', 'UOB KAY HIAN PL*', 'SGX', 'SG', 'Percent', 0.09);

-- SGX Access Fee (flat fee per trade)
INSERT INTO gmp_cis.cis_trade_charge_lut (fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value)
VALUES ('FFP/SGX SI FEE', 'UOB KAY HIAN PL*', 'SGX', 'SG', 'Flat', 0.75);

-- ================================================================
-- Verify inserted data
-- ================================================================
SELECT fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value
FROM gmp_cis.cis_trade_charge_lut
WHERE broker = 'UOB KAY HIAN PL*'
ORDER BY fee_type;

-- ================================================================
-- Example: Add charges for another broker (template)
-- ================================================================
-- INSERT INTO gmp_cis.cis_trade_charge_lut (fee_type, broker, exchange, country_of_exchange, fee_rule, fee_value)
-- VALUES ('Brokerage Fee', 'ANOTHER BROKER', 'SGX', 'SG', 'Percent', 0.5);
-- VALUES ('Clearing Fee', 'ANOTHER BROKER', 'SGX', 'SG', 'Percent', 0.0325);
-- VALUES ('Trading Fee', 'ANOTHER BROKER', 'SGX', 'SG', 'Percent', 0.0075);
-- VALUES ('GST', 'ANOTHER BROKER', 'SGX', 'SG', 'Percent', 0.045);
-- VALUES ('FFP/SGX SI FEE', 'ANOTHER BROKER', 'SGX', 'SG', 'Flat', 0.75);
