-- ============================================================================
-- Trade Lookup/Reference Tables - Kudu DDL
-- ============================================================================
-- Description: Lookup tables for Trade module dropdown fields
--              All dropdown options stored in Kudu for consistency
--
-- Database: gmp_cis
-- Created: 2026-01-12
-- Version: 1.0
--
-- Tables Created:
--   1. cis_trade_status_lookup      - Trade status options
--   2. cis_broker_lookup            - Broker list
--   3. cis_gl_fund_type_lookup      - GL fund types
--   4. cis_gl_cost_centre_lookup    - GL cost centres
--   5. cis_gl_account_code_lookup   - GL account codes
--   6. cis_selling_rule_lookup      - Selling rules (FIFO, LIFO, etc.)
--   7. cis_custodian_lookup         - Custodian list
--   8. cis_sub_custodian_lookup     - Sub-custodian list
--   9. cis_fund_type_lookup         - Fund type (UDF)
--   10. cis_income_exp_type_lookup  - Income/Expense types (UDF)
--   11. cis_uobn_lookup             - UOBN/UOBN-HK options (UDF)
--   12. cis_extension_lookup        - Extension options
--   13. cis_delivery_type_lookup    - Delivery type options
--   14. cis_income_type_lookup      - Income types (Dividend, Interest, etc.)
--   15. cis_split_type_lookup       - Split types
--   16. cis_reduction_type_lookup   - Reduction basis types
--
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- 1. Trade Status Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_trade_status_lookup;

CREATE TABLE cis_trade_status_lookup (
    status_code STRING NOT NULL,
    status_name STRING,
    description STRING,
    display_order INT,
    is_active BOOLEAN,
    PRIMARY KEY (status_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_trade_status_lookup VALUES ('PENDING', 'Pending', 'Trade is pending execution', 1, true);
INSERT INTO cis_trade_status_lookup VALUES ('CONFIRMED', 'Confirmed', 'Trade is confirmed', 2, true);
INSERT INTO cis_trade_status_lookup VALUES ('MATCHED', 'Matched', 'Trade matched with counterparty', 3, true);
INSERT INTO cis_trade_status_lookup VALUES ('SETTLED', 'Settled', 'Trade is settled', 4, true);
INSERT INTO cis_trade_status_lookup VALUES ('FAILED', 'Failed', 'Trade failed', 5, true);
INSERT INTO cis_trade_status_lookup VALUES ('CANCELLED', 'Cancelled', 'Trade cancelled', 6, true);

-- ============================================================================
-- 2. Broker Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_broker_lookup;

CREATE TABLE cis_broker_lookup (
    broker_code STRING NOT NULL,
    broker_name STRING,
    broker_type STRING,           -- PRIME, EXECUTING, CLEARING
    country STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (broker_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_broker_lookup VALUES ('GS', 'Goldman Sachs', 'PRIME', 'US', true, 1);
INSERT INTO cis_broker_lookup VALUES ('MS', 'Morgan Stanley', 'PRIME', 'US', true, 2);
INSERT INTO cis_broker_lookup VALUES ('JPM', 'JP Morgan', 'PRIME', 'US', true, 3);
INSERT INTO cis_broker_lookup VALUES ('UBS', 'UBS', 'PRIME', 'CH', true, 4);
INSERT INTO cis_broker_lookup VALUES ('CS', 'Credit Suisse', 'PRIME', 'CH', true, 5);
INSERT INTO cis_broker_lookup VALUES ('BARC', 'Barclays', 'PRIME', 'UK', true, 6);
INSERT INTO cis_broker_lookup VALUES ('DB', 'Deutsche Bank', 'PRIME', 'DE', true, 7);
INSERT INTO cis_broker_lookup VALUES ('HSBC', 'HSBC', 'PRIME', 'UK', true, 8);
INSERT INTO cis_broker_lookup VALUES ('CITI', 'Citibank', 'PRIME', 'US', true, 9);
INSERT INTO cis_broker_lookup VALUES ('BOFA', 'BofA Securities', 'PRIME', 'US', true, 10);
INSERT INTO cis_broker_lookup VALUES ('DBS', 'DBS Bank', 'EXECUTING', 'SG', true, 11);
INSERT INTO cis_broker_lookup VALUES ('OCBC', 'OCBC Bank', 'EXECUTING', 'SG', true, 12);
INSERT INTO cis_broker_lookup VALUES ('UOB', 'UOB Bank', 'EXECUTING', 'SG', true, 13);

-- ============================================================================
-- 3. GL Fund Type Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_gl_fund_type_lookup;

CREATE TABLE cis_gl_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_gl_fund_type_lookup VALUES ('TRADING', 'Trading Book', 'Trading book positions', true, 1);
INSERT INTO cis_gl_fund_type_lookup VALUES ('BANKING', 'Banking Book', 'Banking book positions', true, 2);
INSERT INTO cis_gl_fund_type_lookup VALUES ('INVESTMENT', 'Investment Book', 'Investment portfolio', true, 3);
INSERT INTO cis_gl_fund_type_lookup VALUES ('HEDGE', 'Hedge Book', 'Hedging positions', true, 4);
INSERT INTO cis_gl_fund_type_lookup VALUES ('OTHER', 'Other', 'Other fund types', true, 5);

-- ============================================================================
-- 4. GL Cost Centre Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_gl_cost_centre_lookup;

CREATE TABLE cis_gl_cost_centre_lookup (
    cost_centre_code STRING NOT NULL,
    cost_centre_name STRING,
    department STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (cost_centre_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_gl_cost_centre_lookup VALUES ('CC-001', 'Treasury', 'Treasury Department', true, 1);
INSERT INTO cis_gl_cost_centre_lookup VALUES ('CC-002', 'Investment Management', 'Investment Mgmt', true, 2);
INSERT INTO cis_gl_cost_centre_lookup VALUES ('CC-003', 'Trading Desk', 'Trading Operations', true, 3);
INSERT INTO cis_gl_cost_centre_lookup VALUES ('CC-004', 'Risk Management', 'Risk Mgmt', true, 4);
INSERT INTO cis_gl_cost_centre_lookup VALUES ('CC-005', 'Operations', 'Back Office Operations', true, 5);

-- ============================================================================
-- 5. GL Account Code Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_gl_account_code_lookup;

CREATE TABLE cis_gl_account_code_lookup (
    account_code STRING NOT NULL,
    account_name STRING,
    account_type STRING,          -- ASSET, LIABILITY, EQUITY, INCOME, EXPENSE
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (account_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-1001', 'Trading Securities', 'ASSET', 'Trading securities account', true, 1);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-1002', 'Available for Sale', 'ASSET', 'AFS securities', true, 2);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-1003', 'Held to Maturity', 'ASSET', 'HTM securities', true, 3);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-2001', 'Realized Gains', 'INCOME', 'Realized P&L', true, 4);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-2002', 'Unrealized Gains', 'INCOME', 'Unrealized P&L', true, 5);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-3001', 'Commission Expense', 'EXPENSE', 'Broker commissions', true, 6);
INSERT INTO cis_gl_account_code_lookup VALUES ('ACC-3002', 'Trading Fees', 'EXPENSE', 'Exchange fees', true, 7);

-- ============================================================================
-- 6. Selling Rule Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_selling_rule_lookup;

CREATE TABLE cis_selling_rule_lookup (
    rule_code STRING NOT NULL,
    rule_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (rule_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_selling_rule_lookup VALUES ('FIFO', 'First In First Out', 'Sell oldest lots first', true, 1);
INSERT INTO cis_selling_rule_lookup VALUES ('LIFO', 'Last In First Out', 'Sell newest lots first', true, 2);
INSERT INTO cis_selling_rule_lookup VALUES ('WAVG', 'Weighted Average', 'Use weighted average cost', true, 3);
INSERT INTO cis_selling_rule_lookup VALUES ('SPEC', 'Specific Identification', 'Specify which lots to sell', true, 4);
INSERT INTO cis_selling_rule_lookup VALUES ('HIFO', 'Highest In First Out', 'Sell highest cost lots first', true, 5);

-- ============================================================================
-- 7. Custodian Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_custodian_lookup;

CREATE TABLE cis_custodian_lookup (
    custodian_code STRING NOT NULL,
    custodian_name STRING,
    country STRING,
    custodian_type STRING,        -- GLOBAL, LOCAL
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (custodian_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_custodian_lookup VALUES ('DBS', 'DBS Bank', 'SG', 'LOCAL', true, 1);
INSERT INTO cis_custodian_lookup VALUES ('SCB', 'Standard Chartered', 'SG', 'GLOBAL', true, 2);
INSERT INTO cis_custodian_lookup VALUES ('CITI', 'Citibank', 'US', 'GLOBAL', true, 3);
INSERT INTO cis_custodian_lookup VALUES ('HSBC', 'HSBC', 'HK', 'GLOBAL', true, 4);
INSERT INTO cis_custodian_lookup VALUES ('BNP', 'BNP Paribas', 'FR', 'GLOBAL', true, 5);
INSERT INTO cis_custodian_lookup VALUES ('SSB', 'State Street Bank', 'US', 'GLOBAL', true, 6);
INSERT INTO cis_custodian_lookup VALUES ('NTRS', 'Northern Trust', 'US', 'GLOBAL', true, 7);

-- ============================================================================
-- 8. Sub-Custodian Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_sub_custodian_lookup;

CREATE TABLE cis_sub_custodian_lookup (
    sub_custodian_code STRING NOT NULL,
    sub_custodian_name STRING,
    parent_custodian STRING,      -- FK to cis_custodian_lookup
    country STRING,
    market STRING,                -- Market/Exchange
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (sub_custodian_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_sub_custodian_lookup VALUES ('DBS-SG', 'DBS Bank Singapore', 'DBS', 'SG', 'SGX', true, 1);
INSERT INTO cis_sub_custodian_lookup VALUES ('SCB-SG', 'Standard Chartered SG', 'SCB', 'SG', 'SGX', true, 2);
INSERT INTO cis_sub_custodian_lookup VALUES ('CITI-SG', 'Citibank Singapore', 'CITI', 'SG', 'SGX', true, 3);
INSERT INTO cis_sub_custodian_lookup VALUES ('HSBC-HK', 'HSBC Hong Kong', 'HSBC', 'HK', 'HKEX', true, 4);
INSERT INTO cis_sub_custodian_lookup VALUES ('BNP-HK', 'BNP Paribas HK', 'BNP', 'HK', 'HKEX', true, 5);
INSERT INTO cis_sub_custodian_lookup VALUES ('CITI-US', 'Citibank USA', 'CITI', 'US', 'NYSE', true, 6);
INSERT INTO cis_sub_custodian_lookup VALUES ('SSB-US', 'State Street USA', 'SSB', 'US', 'NYSE', true, 7);

-- ============================================================================
-- 9. Fund Type Lookup (UDF)
-- ============================================================================
DROP TABLE IF EXISTS cis_fund_type_lookup;

CREATE TABLE cis_fund_type_lookup (
    fund_type_code STRING NOT NULL,
    fund_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (fund_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_fund_type_lookup VALUES ('EQUITY', 'Equity', 'Equity/Stock investments', true, 1);
INSERT INTO cis_fund_type_lookup VALUES ('FIXED_INCOME', 'Fixed Income', 'Bonds and fixed income', true, 2);
INSERT INTO cis_fund_type_lookup VALUES ('MONEY_MARKET', 'Money Market', 'Short-term instruments', true, 3);
INSERT INTO cis_fund_type_lookup VALUES ('BALANCED', 'Balanced', 'Mixed asset class', true, 4);
INSERT INTO cis_fund_type_lookup VALUES ('ALTERNATIVE', 'Alternative', 'Alternative investments', true, 5);
INSERT INTO cis_fund_type_lookup VALUES ('REAL_ESTATE', 'Real Estate', 'Property investments', true, 6);
INSERT INTO cis_fund_type_lookup VALUES ('COMMODITY', 'Commodity', 'Commodity investments', true, 7);
INSERT INTO cis_fund_type_lookup VALUES ('OTHER', 'Other', 'Other fund types', true, 8);

-- ============================================================================
-- 10. Income/Expense Type Lookup (UDF)
-- ============================================================================
DROP TABLE IF EXISTS cis_income_exp_type_lookup;

CREATE TABLE cis_income_exp_type_lookup (
    type_code STRING NOT NULL,
    type_name STRING,
    category STRING,              -- INCOME, EXPENSE
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_income_exp_type_lookup VALUES ('TRADING', 'Trading', 'INCOME', 'Trading income', true, 1);
INSERT INTO cis_income_exp_type_lookup VALUES ('INVESTMENT', 'Investment', 'INCOME', 'Investment income', true, 2);
INSERT INTO cis_income_exp_type_lookup VALUES ('DIVIDEND', 'Dividend', 'INCOME', 'Dividend income', true, 3);
INSERT INTO cis_income_exp_type_lookup VALUES ('INTEREST', 'Interest', 'INCOME', 'Interest income', true, 4);
INSERT INTO cis_income_exp_type_lookup VALUES ('CAPITAL_GAIN', 'Capital Gain', 'INCOME', 'Capital gains', true, 5);
INSERT INTO cis_income_exp_type_lookup VALUES ('FEE', 'Fee', 'EXPENSE', 'Fee expense', true, 6);
INSERT INTO cis_income_exp_type_lookup VALUES ('COMMISSION', 'Commission', 'EXPENSE', 'Commission expense', true, 7);
INSERT INTO cis_income_exp_type_lookup VALUES ('TAX', 'Tax', 'EXPENSE', 'Tax expense', true, 8);
INSERT INTO cis_income_exp_type_lookup VALUES ('OTHER', 'Other', 'INCOME', 'Other', true, 9);

-- ============================================================================
-- 11. UOBN Lookup (UDF)
-- ============================================================================
DROP TABLE IF EXISTS cis_uobn_lookup;

CREATE TABLE cis_uobn_lookup (
    uobn_code STRING NOT NULL,
    uobn_name STRING,
    region STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (uobn_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_uobn_lookup VALUES ('UOBN-SG', 'UOBN Singapore', 'SEA', 'Singapore booking', true, 1);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-HK', 'UOBN Hong Kong', 'NEA', 'Hong Kong booking', true, 2);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-MY', 'UOBN Malaysia', 'SEA', 'Malaysia booking', true, 3);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-TH', 'UOBN Thailand', 'SEA', 'Thailand booking', true, 4);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-ID', 'UOBN Indonesia', 'SEA', 'Indonesia booking', true, 5);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-CN', 'UOBN China', 'NEA', 'China booking', true, 6);
INSERT INTO cis_uobn_lookup VALUES ('UOBN-OTHER', 'Other', 'OTHER', 'Other booking', true, 7);

-- ============================================================================
-- 12. Extension Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_extension_lookup;

CREATE TABLE cis_extension_lookup (
    extension_code STRING NOT NULL,
    extension_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (extension_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_extension_lookup VALUES ('NONE', 'None', 'No extension', true, 1);
INSERT INTO cis_extension_lookup VALUES ('EXT-1D', '1 Day Extension', 'Extend settlement by 1 day', true, 2);
INSERT INTO cis_extension_lookup VALUES ('EXT-2D', '2 Day Extension', 'Extend settlement by 2 days', true, 3);
INSERT INTO cis_extension_lookup VALUES ('EXT-1W', '1 Week Extension', 'Extend settlement by 1 week', true, 4);
INSERT INTO cis_extension_lookup VALUES ('EXT-CUSTOM', 'Custom Extension', 'Custom extension period', true, 5);

-- ============================================================================
-- 13. Delivery Type Lookup (for Deliver Long)
-- ============================================================================
DROP TABLE IF EXISTS cis_delivery_type_lookup;

CREATE TABLE cis_delivery_type_lookup (
    delivery_type_code STRING NOT NULL,
    delivery_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (delivery_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_delivery_type_lookup VALUES ('TRANSFER', 'Transfer', 'Portfolio to portfolio transfer', true, 1);
INSERT INTO cis_delivery_type_lookup VALUES ('CORP_ACTION', 'Corporate Action', 'Due to corporate action', true, 2);
INSERT INTO cis_delivery_type_lookup VALUES ('SETTLEMENT', 'Settlement', 'Settlement delivery', true, 3);
INSERT INTO cis_delivery_type_lookup VALUES ('REDEMPTION', 'Redemption', 'Fund redemption', true, 4);
INSERT INTO cis_delivery_type_lookup VALUES ('PLEDGE', 'Pledge', 'Collateral pledge', true, 5);
INSERT INTO cis_delivery_type_lookup VALUES ('OTHER', 'Other', 'Other delivery type', true, 6);

-- ============================================================================
-- 14. Income Type Lookup (for Income tab)
-- ============================================================================
DROP TABLE IF EXISTS cis_income_type_lookup;

CREATE TABLE cis_income_type_lookup (
    income_type_code STRING NOT NULL,
    income_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (income_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_income_type_lookup VALUES ('DIVIDEND', 'Dividend', 'Cash dividend', true, 1);
INSERT INTO cis_income_type_lookup VALUES ('STOCK_DIV', 'Stock Dividend', 'Stock dividend', true, 2);
INSERT INTO cis_income_type_lookup VALUES ('INTEREST', 'Interest', 'Bond interest/coupon', true, 3);
INSERT INTO cis_income_type_lookup VALUES ('PREMIUM', 'Premium', 'Option premium', true, 4);
INSERT INTO cis_income_type_lookup VALUES ('DISTRIBUTION', 'Distribution', 'Fund distribution', true, 5);
INSERT INTO cis_income_type_lookup VALUES ('RENTAL', 'Rental', 'Rental income', true, 6);
INSERT INTO cis_income_type_lookup VALUES ('OTHER', 'Other', 'Other income', true, 7);

-- ============================================================================
-- 15. Split Type Lookup (for Split Transaction)
-- ============================================================================
DROP TABLE IF EXISTS cis_split_type_lookup;

CREATE TABLE cis_split_type_lookup (
    split_type_code STRING NOT NULL,
    split_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (split_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_split_type_lookup VALUES ('STOCK_SPLIT', 'Stock Split', 'Forward stock split (e.g., 2:1)', true, 1);
INSERT INTO cis_split_type_lookup VALUES ('REVERSE_SPLIT', 'Reverse Split', 'Reverse stock split (e.g., 1:2)', true, 2);
INSERT INTO cis_split_type_lookup VALUES ('LOT_SPLIT', 'Lot Split', 'Split position into lots', true, 3);
INSERT INTO cis_split_type_lookup VALUES ('BONUS_ISSUE', 'Bonus Issue', 'Bonus share issue', true, 4);

-- ============================================================================
-- 16. Reduction Type Lookup (for Reduction Basis)
-- ============================================================================
DROP TABLE IF EXISTS cis_reduction_type_lookup;

CREATE TABLE cis_reduction_type_lookup (
    reduction_type_code STRING NOT NULL,
    reduction_type_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (reduction_type_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_reduction_type_lookup VALUES ('RETURN_CAPITAL', 'Return of Capital', 'Return of capital distribution', true, 1);
INSERT INTO cis_reduction_type_lookup VALUES ('AMORTIZATION', 'Amortization', 'Bond premium amortization', true, 2);
INSERT INTO cis_reduction_type_lookup VALUES ('WRITEDOWN', 'Write-down', 'Impairment write-down', true, 3);
INSERT INTO cis_reduction_type_lookup VALUES ('PARTIAL_REDEMP', 'Partial Redemption', 'Partial redemption', true, 4);
INSERT INTO cis_reduction_type_lookup VALUES ('OTHER', 'Other', 'Other reduction', true, 5);

-- ============================================================================
-- 17. Section 31/26 Lookup (UDF Regulatory)
-- ============================================================================
DROP TABLE IF EXISTS cis_section_lookup;

CREATE TABLE cis_section_lookup (
    section_code STRING NOT NULL,
    section_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (section_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_section_lookup VALUES ('SEC_31', 'Section 31', 'Section 31 applicable', true, 1);
INSERT INTO cis_section_lookup VALUES ('SEC_26', 'Section 26', 'Section 26 applicable', true, 2);
INSERT INTO cis_section_lookup VALUES ('BOTH', 'Both', 'Both sections applicable', true, 3);
INSERT INTO cis_section_lookup VALUES ('NA', 'N/A', 'Not applicable', true, 4);

-- ============================================================================
-- 18. Revision Code Lookup (UDF)
-- ============================================================================
DROP TABLE IF EXISTS cis_revision_code_lookup;

CREATE TABLE cis_revision_code_lookup (
    revision_code STRING NOT NULL,
    revision_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (revision_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_revision_code_lookup VALUES ('REV-001', 'Revision 001', 'First revision code', true, 1);
INSERT INTO cis_revision_code_lookup VALUES ('REV-002', 'Revision 002', 'Second revision code', true, 2);
INSERT INTO cis_revision_code_lookup VALUES ('REV-003', 'Revision 003', 'Third revision code', true, 3);
INSERT INTO cis_revision_code_lookup VALUES ('NA', 'N/A', 'Not applicable', true, 4);

-- ============================================================================
-- 19. Open/Close Position Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_open_close_lookup;

CREATE TABLE cis_open_close_lookup (
    position_code STRING NOT NULL,
    position_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (position_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_open_close_lookup VALUES ('OPEN', 'Open', 'Opening new position', true, 1);
INSERT INTO cis_open_close_lookup VALUES ('CLOSE', 'Close', 'Closing existing position', true, 2);

-- ============================================================================
-- 20. Amortisation Method Lookup
-- ============================================================================
DROP TABLE IF EXISTS cis_amor_method_lookup;

CREATE TABLE cis_amor_method_lookup (
    method_code STRING NOT NULL,
    method_name STRING,
    description STRING,
    is_active BOOLEAN,
    display_order INT,
    PRIMARY KEY (method_code)
)
PARTITION BY HASH PARTITIONS 2
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Seed data
INSERT INTO cis_amor_method_lookup VALUES ('STD', 'Standard', 'Standard method', true, 1);
INSERT INTO cis_amor_method_lookup VALUES ('EFF_INT', 'Effective Interest', 'Effective interest method', true, 2);
INSERT INTO cis_amor_method_lookup VALUES ('STRAIGHT', 'Straight Line', 'Straight line method', true, 3);
INSERT INTO cis_amor_method_lookup VALUES ('NONE', 'None', 'No amortisation', true, 4);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all lookup tables
SHOW TABLES LIKE 'cis_%_lookup';

-- Check row counts
SELECT 'cis_trade_status_lookup' as table_name, COUNT(*) as row_count FROM cis_trade_status_lookup
UNION ALL
SELECT 'cis_broker_lookup', COUNT(*) FROM cis_broker_lookup
UNION ALL
SELECT 'cis_gl_fund_type_lookup', COUNT(*) FROM cis_gl_fund_type_lookup
UNION ALL
SELECT 'cis_selling_rule_lookup', COUNT(*) FROM cis_selling_rule_lookup
UNION ALL
SELECT 'cis_custodian_lookup', COUNT(*) FROM cis_custodian_lookup
UNION ALL
SELECT 'cis_fund_type_lookup', COUNT(*) FROM cis_fund_type_lookup;

-- ============================================================================
-- END OF LOOKUP TABLES DDL
-- ============================================================================
