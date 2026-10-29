-- Portfolio Kudu Tables for Close/Reactivate Functionality
-- Database: gmp_cis
-- Created: 2025-12-27
--
-- Usage:
--   impala-shell -f portfolio_kudu_tables.sql
--

USE gmp_cis;

-- ============================================================================
-- TABLE: cis_portfolio
-- ============================================================================
-- Check if cis_portfolio table exists and has required columns
-- If columns don't exist, you may need to recreate or add them manually

-- Expected columns for close/reactivate functionality:
-- - code (or use name as code/primary key)
-- - status (should already exist)
-- - is_active (needed for soft delete)
-- - updated_by (track who made changes)
-- - updated_at (should already exist)

-- Note: Kudu doesn't support ALTER TABLE ADD COLUMN for nullable columns easily
-- If columns are missing, you may need to:
-- 1. Create new table with updated schema
-- 2. Copy data from old table
-- 3. Drop old table and rename new table

-- Check current table structure:
DESCRIBE cis_portfolio;

-- If is_active and updated_by columns don't exist, create updated table:
DROP TABLE IF EXISTS cis_portfolio_new;

CREATE TABLE IF NOT EXISTS cis_portfolio_new (
  code STRING NOT NULL,
  name STRING,
  description STRING,
  currency STRING,
  manager STRING,
  portfolio_client STRING,
  cash_balance_list STRING,
  cash_balance DECIMAL(20,2),
  status STRING,
  is_active BOOLEAN,
  cost_centre_code STRING,
  corp_code STRING,
  account_group STRING,
  portfolio_group STRING,
  report_group STRING,
  entity_group STRING,
  revaluation_status STRING,
  created_by STRING,
  created_at STRING,
  updated_by STRING,
  updated_at STRING,
  PRIMARY KEY (code)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Migrate data if needed (uncomment after table creation):
-- INSERT INTO cis_portfolio_new
-- SELECT
--   name as code,  -- or use existing code column
--   name,
--   description,
--   currency,
--   manager,
--   portfolio_client,
--   cash_balance_list,
--   CAST(cash_balance AS DECIMAL(20,2)),
--   COALESCE(status, 'ACTIVE'),
--   CAST(true AS BOOLEAN) as is_active,  -- default to active
--   cost_centre_code,
--   corp_code,
--   account_group,
--   portfolio_group,
--   report_group,
--   entity_group,
--   revaluation_status,
--   'system' as created_by,
--   created_at,
--   'system' as updated_by,
--   updated_at
-- FROM cis_portfolio;

-- Then swap tables:
-- DROP TABLE cis_portfolio;
-- ALTER TABLE cis_portfolio_new RENAME TO cis_portfolio;


-- ============================================================================
-- TABLE: cis_portfolio_history
-- ============================================================================
-- Track all changes to portfolios (close, reactivate, update, etc.)

DROP TABLE IF EXISTS cis_portfolio_history;

CREATE TABLE IF NOT EXISTS cis_portfolio_history (
  history_id BIGINT NOT NULL,
  portfolio_code STRING,
  action STRING,
  status STRING,
  changes STRING,
  comments STRING,
  performed_by STRING,
  created_at STRING,
  PRIMARY KEY (history_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Verify tables created
SHOW TABLES LIKE 'cis_portfolio*';

-- Check table structures
DESCRIBE cis_portfolio;
DESCRIBE cis_portfolio_history;
