-- ================================================================
-- Hive DDL for Portfolio Table - Internal ORC Table
-- Database: cis
-- Storage: ORC format with SNAPPY compression
-- ================================================================

USE cis;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS cis_portfolio;
DROP TABLE IF EXISTS cis_portfolio_stage;

-- ================================================================
-- Table: cis_portfolio (Internal ORC Table)
-- Portfolio master data
-- ================================================================

CREATE TABLE cis_portfolio (
  name                  STRING      COMMENT 'Portfolio identifier/name',
  description           STRING      COMMENT 'Portfolio description',
  currency              STRING      COMMENT 'Base currency (SGD, USD, MYR, etc.)',
  manager               STRING      COMMENT 'Portfolio manager',
  portfolio_client      STRING      COMMENT 'Client name',
  cash_balance_list     STRING      COMMENT 'Cash balance list',
  cash_balance          STRING      COMMENT 'Cash balance',
  `status`              STRING      COMMENT 'Portfolio status (Active/Inactive)',
  cost_centre_code      STRING      COMMENT 'Cost centre code',
  corp_code             STRING      COMMENT 'Corporate code',
  account_group         STRING      COMMENT 'Account group',
  portfolio_group       STRING      COMMENT 'Portfolio group',
  report_group          STRING      COMMENT 'Report group',
  entity_group          STRING      COMMENT 'Entity group',
  revaluation_status    STRING      COMMENT 'Revaluation status (REVALUED/NON-REVALUED)',
  created_at            STRING      COMMENT 'Creation date/time',
  updated_at            STRING      COMMENT 'Last update date/time',
  source_name           STRING      COMMENT 'Source system name',
  branch_code           STRING      COMMENT 'Branch code',
  validation_status     STRING      COMMENT 'Validation status'
)
COMMENT 'Portfolio master data - Internal ORC table'
STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

-- ================================================================
-- Staging Table: cis_portfolio_stage (Text Format for Loading)
-- ================================================================

CREATE TABLE cis_portfolio_stage (
  name                  STRING,
  description           STRING,
  currency              STRING,
  manager               STRING,
  portfolio_client      STRING,
  cash_balance_list     STRING,
  cash_balance          STRING,
  `status`              STRING,
  cost_centre_code      STRING,
  corp_code             STRING,
  account_group         STRING,
  portfolio_group       STRING,
  report_group          STRING,
  entity_group          STRING,
  revaluation_status    STRING,
  created_at            STRING,
  updated_at            STRING
)
COMMENT 'Staging table for portfolio data loading'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

SHOW TABLES;
