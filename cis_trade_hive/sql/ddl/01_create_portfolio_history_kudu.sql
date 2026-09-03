-- Create Portfolio History Table in Kudu
-- Database: gmp_cis
-- Purpose: Track close/reactivate and all portfolio changes
--
-- Usage:
--   impala-shell -f 01_create_portfolio_history_kudu.sql
--

USE gmp_cis;

-- Drop table if exists (for clean recreation)
DROP TABLE IF EXISTS cis_portfolio_history;

-- Create portfolio history table
CREATE TABLE cis_portfolio_history (
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

-- Verify table created
SHOW TABLES LIKE 'cis_portfolio_history';
DESCRIBE cis_portfolio_history;

SELECT 'Portfolio history table created successfully' as status;
