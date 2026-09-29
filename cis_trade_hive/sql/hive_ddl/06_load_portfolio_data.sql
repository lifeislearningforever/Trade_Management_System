-- ================================================================
-- Load Portfolio Data into Hive Tables
-- Database: cis
-- ================================================================

USE cis;

-- ================================================================
-- Step 1: Load data into staging table
-- ================================================================

LOAD DATA LOCAL INPATH '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv/cis_portfolio_data.txt'
OVERWRITE INTO TABLE cis_portfolio_stage;

-- ================================================================
-- Step 2: Insert from staging into ORC table with default values for missing columns
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
  'cis' as source_name,           -- Default value
  NULL as branch_code,             -- Missing in data file
  NULL as validation_status        -- Missing in data file
FROM cis_portfolio_stage;

-- ================================================================
-- Verify data loaded
-- ================================================================

SELECT 'cis_portfolio' as table_name, 'Total rows loaded' as metric, COUNT(*) as value
FROM cis_portfolio;

SELECT 'cis_portfolio' as table_name, 'Sample data' as metric, '' as value;
SELECT * FROM cis_portfolio LIMIT 10;
