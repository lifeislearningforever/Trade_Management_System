-- ================================================================
-- Alter cis_trade Table - Add Trade Charge Columns
-- Database: gmp_cis
-- Date: 2026-03-02
-- Description: Adds columns to store broker-level charge information
-- Run this in Impala/Kudu
-- ================================================================

-- ================================================================
-- Add Charge-related columns to cis_trade (Kudu table)
-- These columns store the charges applied to each trade
-- ================================================================

ALTER TABLE gmp_cis.cis_trade ADD COLUMNS (
    charge_fee_type STRING COMMENT 'Primary fee type applied to trade (Brokerage Fee, Clearing Fee, etc.)',
    charge_exchange STRING COMMENT 'Exchange code for fee calculation (SGX, NYSE, etc.)',
    charge_country STRING COMMENT 'Country of exchange for fee calculation',
    charge_fee_rule STRING COMMENT 'Fee calculation rule applied (Percent, Flat)',
    charge_fee_value DOUBLE COMMENT 'Base fee value from lookup',
    calculated_commission DOUBLE COMMENT 'Calculated brokerage commission',
    calculated_clearing_fee DOUBLE COMMENT 'Calculated clearing fee',
    calculated_trading_fee DOUBLE COMMENT 'Calculated trading fee',
    calculated_gst DOUBLE COMMENT 'Calculated GST/tax',
    calculated_other_fees DOUBLE COMMENT 'Calculated other fees (FFP/SGX SI FEE, etc.)',
    total_calculated_charges DOUBLE COMMENT 'Total of all calculated charges',
    charges_auto_calculated BOOLEAN COMMENT 'True if charges calculated from lookup table'
);

-- ================================================================
-- Verify column addition
-- ================================================================
DESCRIBE gmp_cis.cis_trade;
