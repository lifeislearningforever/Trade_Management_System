-- ============================================================================
-- Hive POC - Managed Tables with ORC Format and ACID Support
-- Database: gmp_cis
-- Table Prefix: _hive (portfolio_hive, trade_hive)
-- ============================================================================

-- Create database
CREATE DATABASE IF NOT EXISTS gmp_cis
COMMENT 'GMP CIS Trade Management - Hive POC';

USE gmp_cis;

-- ============================================================================
-- 1. Portfolio Hive Managed Table (ORC with ACID)
-- ============================================================================
DROP TABLE IF EXISTS portfolio_hive;

CREATE TABLE portfolio_hive (
    portfolio_id STRING COMMENT 'Primary key - UUID',
    portfolio_name STRING COMMENT 'Portfolio name',
    portfolio_code STRING COMMENT 'Short code for the portfolio',
    portfolio_type STRING COMMENT 'Type: EQUITY, FIXED_INCOME, BALANCED, etc.',
    currency STRING COMMENT 'Base currency code (e.g., USD, EUR, SGD)',
    manager_name STRING COMMENT 'Portfolio manager name',
    description STRING COMMENT 'Portfolio description',
    status STRING COMMENT 'Status: ACTIVE, INACTIVE, DRAFT',
    created_at TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_at TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    deleted_at TIMESTAMP COMMENT 'Soft delete timestamp - NULL means not deleted'
)
CLUSTERED BY (portfolio_id) INTO 2 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- 2. Trade Hive Managed Table (ORC with ACID)
-- ============================================================================
DROP TABLE IF EXISTS trade_hive;

CREATE TABLE trade_hive (
    trade_id STRING COMMENT 'Primary key - UUID',
    portfolio_id STRING COMMENT 'Foreign key to portfolio_hive',
    security_id STRING COMMENT 'Security identifier (ISIN, CUSIP, etc.)',
    security_name STRING COMMENT 'Security name',
    trade_type STRING COMMENT 'Type: BUY, SELL',
    quantity DECIMAL(18,4) COMMENT 'Number of units traded',
    price DECIMAL(18,6) COMMENT 'Trade price per unit',
    trade_amount DECIMAL(18,2) COMMENT 'Total trade amount (quantity * price)',
    currency STRING COMMENT 'Trade currency',
    trade_date DATE COMMENT 'Date of trade execution',
    settlement_date DATE COMMENT 'Expected settlement date',
    status STRING COMMENT 'Status: PENDING, EXECUTED, SETTLED, CANCELLED',
    broker STRING COMMENT 'Broker/counterparty name',
    notes STRING COMMENT 'Additional trade notes',
    created_at TIMESTAMP COMMENT 'Record creation timestamp',
    created_by STRING COMMENT 'User who created the record',
    updated_at TIMESTAMP COMMENT 'Last update timestamp',
    updated_by STRING COMMENT 'User who last updated the record',
    deleted_at TIMESTAMP COMMENT 'Soft delete timestamp - NULL means not deleted'
)
CLUSTERED BY (trade_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);

-- ============================================================================
-- Sample Data - Portfolios
-- ============================================================================
INSERT INTO portfolio_hive VALUES
    ('PF001', 'Global Equity Fund', 'GEF', 'EQUITY', 'USD', 'John Smith',
     'Global equity portfolio focused on developed markets', 'ACTIVE',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

INSERT INTO portfolio_hive VALUES
    ('PF002', 'Asia Fixed Income', 'AFI', 'FIXED_INCOME', 'SGD', 'Jane Doe',
     'Asian fixed income portfolio with focus on investment grade bonds', 'ACTIVE',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

INSERT INTO portfolio_hive VALUES
    ('PF003', 'Balanced Growth Fund', 'BGF', 'BALANCED', 'EUR', 'Robert Chen',
     'Balanced portfolio with 60% equity and 40% fixed income', 'ACTIVE',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

-- ============================================================================
-- Sample Data - Trades
-- ============================================================================
INSERT INTO trade_hive VALUES
    ('TR001', 'PF001', 'US0378331005', 'Apple Inc', 'BUY', 100.0000, 175.500000, 17550.00, 'USD',
     '2024-01-15', '2024-01-17', 'SETTLED', 'Goldman Sachs', 'Initial position',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

INSERT INTO trade_hive VALUES
    ('TR002', 'PF001', 'US5949181045', 'Microsoft Corp', 'BUY', 50.0000, 380.250000, 19012.50, 'USD',
     '2024-01-16', '2024-01-18', 'SETTLED', 'Morgan Stanley', 'Tech exposure',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

INSERT INTO trade_hive VALUES
    ('TR003', 'PF002', 'SG1234567890', 'Singapore Govt Bond 3.5%', 'BUY', 1000000.0000, 1.020000, 1020000.00, 'SGD',
     '2024-01-20', '2024-01-22', 'SETTLED', 'DBS', 'Government bond allocation',
     CURRENT_TIMESTAMP(), 'system', CURRENT_TIMESTAMP(), 'system', NULL);

-- ============================================================================
-- Verify Tables
-- ============================================================================
SHOW TABLES IN gmp_cis;
SELECT * FROM portfolio_hive WHERE deleted_at IS NULL;
SELECT * FROM trade_hive WHERE deleted_at IS NULL;
