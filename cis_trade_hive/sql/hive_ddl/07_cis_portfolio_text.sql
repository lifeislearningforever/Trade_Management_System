-- ================================================================
-- Hive DDL for Portfolio Table - TEXT Format (Workaround for ORC issues)
-- Database: cis
-- Storage: TEXT format with pipe delimiter
-- ================================================================

USE cis;

-- Drop ORC table and recreate as TEXT
DROP TABLE IF EXISTS cis_portfolio;

-- ================================================================
-- Table: cis_portfolio (TEXT Format)
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
COMMENT 'Portfolio master data - TEXT format'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- ================================================================
-- Insert data from staging table
-- ================================================================

INSERT INTO TABLE cis_portfolio
SELECT
  name,
  description,
  currency,
  manager,
  portfolio_client,
  cash_balance_list,
  cash_balance,
  `status`,
  cost_centre_code,
  corp_code,
  account_group,
  portfolio_group,
  report_group,
  entity_group,
  revaluation_status,
  created_at,
  updated_at,
  'cis' as source_name,
  NULL as branch_code,
  NULL as validation_status
FROM cis_portfolio_stage;

-- ================================================================
-- Verify data loaded
-- ================================================================

SELECT 'Total rows loaded:' as info, COUNT(*) as count FROM cis_portfolio;
SELECT * FROM cis_portfolio LIMIT 10;
