-- ============================================================================
-- Add src_system Column to Portfolio and Security Tables
-- ============================================================================
-- Description: Adds src_system column to track the source system
--              - CIS: Records created via CIS UI
--              - GMP: Records loaded via ETL from GMP
-- Created: 2026-01-10
-- Database: gmp_cis
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- NOTE: Kudu tables don't support ALTER TABLE ADD COLUMN directly.
-- This script provides the approach to migrate the tables with new columns.
-- ============================================================================

-- ============================================================================
-- PORTFOLIO TABLE MIGRATION
-- ============================================================================

-- Step 1: Create new portfolio table with src_system column
DROP TABLE IF EXISTS cis_portfolio_v2;

CREATE TABLE cis_portfolio_v2 (
  name STRING NOT NULL,
  description STRING,
  currency STRING,
  manager STRING,
  portfolio_client STRING,
  cash_balance STRING,
  status STRING,
  is_active BOOLEAN,
  cost_centre_code STRING,
  corp_code STRING,
  account_group STRING,
  portfolio_group STRING,
  report_group STRING,
  entity_group STRING,
  revaluation_status STRING,
  src_system STRING,    -- Source system: CIS (UI created) or GMP (ETL loaded)
  created_at STRING,
  updated_by STRING,
  updated_at STRING,
  PRIMARY KEY (name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Step 2: Migrate data from old table to new table
-- Existing records are from ETL, so set src_system = 'GMP'
-- INSERT INTO cis_portfolio_v2
-- SELECT
--     name,
--     description,
--     currency,
--     manager,
--     portfolio_client,
--     cash_balance,
--     status,
--     is_active,
--     cost_centre_code,
--     corp_code,
--     account_group,
--     portfolio_group,
--     report_group,
--     entity_group,
--     revaluation_status,
--     'GMP' as src_system,   -- Existing ETL records are from GMP
--     created_at,
--     updated_by,
--     updated_at
-- FROM cis_portfolio;

-- Step 3: Swap tables (backup old, rename new)
-- ALTER TABLE cis_portfolio RENAME TO cis_portfolio_backup;
-- ALTER TABLE cis_portfolio_v2 RENAME TO cis_portfolio;


-- ============================================================================
-- SECURITY TABLE MIGRATION
-- ============================================================================

-- Step 1: Create new security table with src_system column
DROP TABLE IF EXISTS cis_security_v3;

CREATE TABLE cis_security_v3 (
    security_id BIGINT NOT NULL,
    security_name STRING NOT NULL,
    isin STRING,
    security_description STRING,
    issuer STRING,
    ticker STRING,
    industry STRING,
    security_type STRING,
    investment_type STRING,
    issuer_type STRING,
    quoted_unquoted STRING,
    country_of_incorporation STRING,
    country_of_exchange STRING,
    country_of_issue STRING,
    country_of_primary_exchange STRING,
    exchange_code STRING,
    currency_code STRING,
    price DECIMAL(20, 4),
    price_date STRING,
    price_source STRING,
    shares_outstanding BIGINT,
    beta DECIMAL(10, 4),
    par_value DECIMAL(20, 6),
    shareholding_entity_1 DECIMAL(10, 4),
    shareholding_entity_2 DECIMAL(10, 4),
    shareholding_entity_3 DECIMAL(10, 4),
    shareholding_aggregated DECIMAL(10, 4),
    substantial_10_pct STRING,
    bwciif BIGINT,
    bwciif_others BIGINT,
    cels STRING,
    approved_s32 STRING,
    basel_iv_fund STRING,
    mas_643_entity_type STRING,
    mas_6d_code STRING,
    fin_nonfin_ind STRING,
    business_unit_head STRING,
    person_in_charge STRING,
    core_noncore STRING,
    fund_index_fund STRING,
    management_limit_classification STRING,
    relative_index STRING,
    status STRING,
    submitted_for_approval_at BIGINT,
    submitted_by STRING,
    reviewed_at BIGINT,
    reviewed_by STRING,
    review_comments STRING,
    src_system STRING,    -- Source system: CIS (UI created) or GMP (ETL loaded)
    is_active BOOLEAN DEFAULT true,
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,
    updated_by STRING NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (security_id)
)
PARTITION BY HASH (security_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES(
    'kudu.num_tablet_replicas' = '3'
);

-- Step 2: Migrate data from old table to new table
-- Existing records are from ETL, so set src_system = 'GMP'
-- INSERT INTO cis_security_v3
-- SELECT
--     security_id,
--     security_name,
--     isin,
--     security_description,
--     issuer,
--     ticker,
--     industry,
--     security_type,
--     investment_type,
--     issuer_type,
--     quoted_unquoted,
--     country_of_incorporation,
--     country_of_exchange,
--     country_of_issue,
--     country_of_primary_exchange,
--     exchange_code,
--     currency_code,
--     price,
--     price_date,
--     price_source,
--     shares_outstanding,
--     beta,
--     par_value,
--     shareholding_entity_1,
--     shareholding_entity_2,
--     shareholding_entity_3,
--     shareholding_aggregated,
--     substantial_10_pct,
--     bwciif,
--     bwciif_others,
--     cels,
--     approved_s32,
--     basel_iv_fund,
--     mas_643_entity_type,
--     mas_6d_code,
--     fin_nonfin_ind,
--     business_unit_head,
--     person_in_charge,
--     core_noncore,
--     fund_index_fund,
--     management_limit_classification,
--     relative_index,
--     status,
--     submitted_for_approval_at,
--     submitted_by,
--     reviewed_at,
--     reviewed_by,
--     review_comments,
--     'GMP' as src_system,   -- Existing ETL records are from GMP
--     is_active,
--     created_by,
--     created_at,
--     updated_by,
--     updated_at
-- FROM cis_security;

-- Step 3: Swap tables (backup old, rename new)
-- ALTER TABLE cis_security RENAME TO cis_security_backup;
-- ALTER TABLE cis_security_v3 RENAME TO cis_security;


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check new table structures
DESCRIBE cis_portfolio_v2;
DESCRIBE cis_security_v3;

-- After migration, verify src_system column exists
-- SELECT src_system, COUNT(*) FROM cis_portfolio GROUP BY src_system;
-- SELECT src_system, COUNT(*) FROM cis_security GROUP BY src_system;
