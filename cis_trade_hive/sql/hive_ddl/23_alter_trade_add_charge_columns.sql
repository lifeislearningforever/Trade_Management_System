-- ================================================================
-- Alter cis_trade Table - Add Trade Charge Columns
-- Database: gmp_cis
-- Date: 2026-03-02
-- Description: Adds columns to store broker-level charge information
-- ================================================================

USE gmp_cis;

-- ================================================================
-- Set Hive ACID properties for transactional support
-- ================================================================
SET hive.support.concurrency=true;
SET hive.enforce.bucketing=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.compactor.initiator.on=true;
SET hive.compactor.worker.threads=1;
SET hive.execution.engine=mr;

-- ================================================================
-- Add Charge-related columns to cis_trade
-- These columns store the charges applied to each trade
-- ================================================================

-- Trade charge fee type (COMMISSION, STAMP_DUTY, CLEARING_FEE, etc.)
ALTER TABLE cis_trade ADD COLUMNS (
    charge_fee_type     STRING COMMENT 'Primary fee type applied to trade'
);

-- Exchange where trade is executed
ALTER TABLE cis_trade ADD COLUMNS (
    charge_exchange     STRING COMMENT 'Exchange code for fee calculation'
);

-- Country of exchange for regulatory fees
ALTER TABLE cis_trade ADD COLUMNS (
    charge_country      STRING COMMENT 'Country of exchange for fee calculation'
);

-- Fee calculation rule used (PERCENTAGE, FLAT, PER_SHARE, TIERED)
ALTER TABLE cis_trade ADD COLUMNS (
    charge_fee_rule     STRING COMMENT 'Fee calculation rule applied'
);

-- Base fee value from lookup table
ALTER TABLE cis_trade ADD COLUMNS (
    charge_fee_value    DECIMAL(20,6) COMMENT 'Base fee value from lookup'
);

-- Calculated commission amount
ALTER TABLE cis_trade ADD COLUMNS (
    calculated_commission DECIMAL(20,6) COMMENT 'Calculated commission from broker charge'
);

-- Calculated stamp duty amount
ALTER TABLE cis_trade ADD COLUMNS (
    calculated_stamp_duty DECIMAL(20,6) COMMENT 'Calculated stamp duty'
);

-- Calculated clearing fee amount
ALTER TABLE cis_trade ADD COLUMNS (
    calculated_clearing_fee DECIMAL(20,6) COMMENT 'Calculated clearing fee'
);

-- Calculated exchange fee amount
ALTER TABLE cis_trade ADD COLUMNS (
    calculated_exchange_fee DECIMAL(20,6) COMMENT 'Calculated exchange fee'
);

-- Total calculated charges (sum of all fee types)
ALTER TABLE cis_trade ADD COLUMNS (
    total_calculated_charges DECIMAL(20,6) COMMENT 'Total of all calculated charges'
);

-- Flag indicating if charges were auto-calculated from lookup
ALTER TABLE cis_trade ADD COLUMNS (
    charges_auto_calculated BOOLEAN COMMENT 'True if charges calculated from lookup table'
);

-- ================================================================
-- Verify column addition
-- ================================================================
DESCRIBE cis_trade;
