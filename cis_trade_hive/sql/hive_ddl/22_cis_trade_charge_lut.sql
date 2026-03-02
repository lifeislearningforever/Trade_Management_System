-- ================================================================
-- Trade Charge Lookup Table DDL
-- Database: gmp_cis
-- Date: 2026-03-02
-- Description: Lookup table for broker-level trade charges
-- Used to calculate fees based on broker, exchange, and country
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
-- Drop existing table if exists
-- ================================================================
DROP TABLE IF EXISTS cis_trade_charge_lut;

-- ================================================================
-- Create Trade Charge Lookup Table
-- ================================================================
CREATE TABLE cis_trade_charge_lut (
    charge_id           BIGINT COMMENT 'Primary key - unique charge ID',
    broker              STRING COMMENT 'Broker short name (from cis_party)',
    fee_type            STRING COMMENT 'Type of fee: COMMISSION, STAMP_DUTY, CLEARING_FEE, EXCHANGE_FEE, TAX, OTHER',
    exchange            STRING COMMENT 'Exchange code (e.g., SGX, NYSE, LSE)',
    country_of_exchange STRING COMMENT 'Country where exchange is located',
    fee_rule            STRING COMMENT 'Fee calculation rule: PERCENTAGE, FLAT, PER_SHARE, TIERED',
    fee_value           DECIMAL(20,6) COMMENT 'Fee value (percentage as decimal e.g., 0.001 for 0.1%, or flat amount)',
    min_fee             DECIMAL(20,6) COMMENT 'Minimum fee amount (for PERCENTAGE rule)',
    max_fee             DECIMAL(20,6) COMMENT 'Maximum fee amount (for PERCENTAGE rule)',
    currency            STRING COMMENT 'Currency for flat fees',
    effective_from      STRING COMMENT 'Date from which this charge is effective (YYYY-MM-DD)',
    effective_to        STRING COMMENT 'Date until which this charge is effective (YYYY-MM-DD)',
    is_active           BOOLEAN COMMENT 'Whether this charge rule is active',
    display_order       INT COMMENT 'Order for display purposes',
    description         STRING COMMENT 'Description of the charge',
    created_by          STRING COMMENT 'User who created the record',
    created_at          STRING COMMENT 'Creation timestamp',
    updated_by          STRING COMMENT 'User who last updated the record',
    updated_at          STRING COMMENT 'Last update timestamp'
)
COMMENT 'Lookup table for broker-level trade charges and fees'
CLUSTERED BY (charge_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ================================================================
-- Insert sample charge data for common brokers
-- ================================================================

-- Goldman Sachs charges
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 1 AS BIGINT),
    'GS', 'COMMISSION', 'NYSE', 'USA', 'PERCENTAGE', 0.0010, 10.00, 500.00, 'USD',
    '2024-01-01', '2099-12-31', true, 1,
    'Goldman Sachs standard commission - 0.1%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 2 AS BIGINT),
    'GS', 'SEC_FEE', 'NYSE', 'USA', 'PERCENTAGE', 0.0000278, 0.01, 100.00, 'USD',
    '2024-01-01', '2099-12-31', true, 2,
    'SEC Transaction Fee - $27.80 per million',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- Morgan Stanley charges
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 3 AS BIGINT),
    'MS', 'COMMISSION', 'NYSE', 'USA', 'PERCENTAGE', 0.0012, 15.00, 600.00, 'USD',
    '2024-01-01', '2099-12-31', true, 1,
    'Morgan Stanley standard commission - 0.12%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- DBS Bank charges (Singapore)
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 4 AS BIGINT),
    'DBS', 'COMMISSION', 'SGX', 'SG', 'PERCENTAGE', 0.0018, 25.00, 1000.00, 'SGD',
    '2024-01-01', '2099-12-31', true, 1,
    'DBS Vickers standard commission - 0.18%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 5 AS BIGINT),
    'DBS', 'CLEARING_FEE', 'SGX', 'SG', 'PERCENTAGE', 0.000325, 0.00, 1000.00, 'SGD',
    '2024-01-01', '2099-12-31', true, 2,
    'SGX Clearing Fee - 0.0325%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 6 AS BIGINT),
    'DBS', 'STAMP_DUTY', 'SGX', 'SG', 'PERCENTAGE', 0.002, 0.00, 0.00, 'SGD',
    '2024-01-01', '2099-12-31', true, 3,
    'Singapore Stamp Duty - 0.2% (buy only)',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- UBS charges
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 7 AS BIGINT),
    'UBS', 'COMMISSION', 'LSE', 'UK', 'PERCENTAGE', 0.0015, 20.00, 750.00, 'GBP',
    '2024-01-01', '2099-12-31', true, 1,
    'UBS standard commission - 0.15%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 8 AS BIGINT),
    'UBS', 'STAMP_DUTY', 'LSE', 'UK', 'PERCENTAGE', 0.005, 0.00, 0.00, 'GBP',
    '2024-01-01', '2099-12-31', true, 2,
    'UK Stamp Duty - 0.5% (buy only)',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- JP Morgan charges
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 9 AS BIGINT),
    'JPM', 'COMMISSION', 'NYSE', 'USA', 'PER_SHARE', 0.005, 1.00, 100.00, 'USD',
    '2024-01-01', '2099-12-31', true, 1,
    'JP Morgan per share commission - $0.005/share',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- Citibank charges
INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 10 AS BIGINT),
    'CITI', 'COMMISSION', 'HKEX', 'HK', 'PERCENTAGE', 0.0025, 50.00, 2000.00, 'HKD',
    '2024-01-01', '2099-12-31', true, 1,
    'Citibank HK standard commission - 0.25%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 11 AS BIGINT),
    'CITI', 'STAMP_DUTY', 'HKEX', 'HK', 'PERCENTAGE', 0.001, 0.00, 0.00, 'HKD',
    '2024-01-01', '2099-12-31', true, 2,
    'Hong Kong Stamp Duty - 0.1%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

INSERT INTO cis_trade_charge_lut VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 + 12 AS BIGINT),
    'CITI', 'EXCHANGE_FEE', 'HKEX', 'HK', 'PERCENTAGE', 0.00005, 0.01, 100.00, 'HKD',
    '2024-01-01', '2099-12-31', true, 3,
    'HKEX Trading Fee - 0.005%',
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'SYSTEM', FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
);

-- ================================================================
-- Verify inserted data
-- ================================================================
SELECT broker, fee_type, exchange, country_of_exchange, fee_rule, fee_value, is_active
FROM cis_trade_charge_lut
WHERE is_active = true
ORDER BY broker, display_order;
