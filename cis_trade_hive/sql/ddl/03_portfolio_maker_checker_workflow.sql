-- ============================================================================
-- Portfolio Maker-Checker Workflow DDL
-- ============================================================================
-- Description: Adds workflow columns to cis_portfolio table for full
--              Maker-Checker workflow support
-- Database: gmp_cis
-- Created: 2026-01-10
--
-- Workflow Statuses:
--   MAKER Side:
--     - INITIAL: New portfolio created (not yet submitted)
--     - MODIFIED: Portfolio edited (after rejection or before submit)
--     - CANCELLED: Portfolio cancelled by maker
--
--   CHECKER Side:
--     - PENDING_VALIDATION: Submitted for validation (awaiting checker)
--     - VALIDATED: Approved by checker (ready for settlement)
--     - SETTLED: Final active state (settlement complete)
--
-- Status Flow:
--   Create    -> INITIAL
--   Edit      -> MODIFIED
--   Cancel    -> CANCELLED
--   Submit    -> PENDING_VALIDATION
--   Validate  -> VALIDATED (or CANCELLED if rejected)
--   Settle    -> SETTLED
--
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- NOTE: Kudu tables don't support ALTER TABLE ADD COLUMN directly.
-- This script creates a new table with the updated schema for migration.
-- ============================================================================

-- ============================================================================
-- TABLE: cis_portfolio_v2 (with Maker-Checker workflow columns)
-- ============================================================================

DROP TABLE IF EXISTS cis_portfolio_v2;

CREATE TABLE cis_portfolio_v2 (
  -- Primary Key
  name STRING NOT NULL,

  -- Basic Portfolio Info
  description STRING,
  currency STRING,
  manager STRING,
  portfolio_client STRING,
  cash_balance STRING,

  -- Classification
  cost_centre_code STRING,
  corp_code STRING,
  account_group STRING,
  portfolio_group STRING,
  report_group STRING,
  entity_group STRING,
  revaluation_status STRING,

  -- Source System (CIS = UI created, GMP = ETL loaded)
  src_system STRING,

  -- Workflow Status
  -- Values: INITIAL, MODIFIED, PENDING_VALIDATION, VALIDATED, CANCELLED, SETTLED
  status STRING,
  is_active BOOLEAN,

  -- Maker Info (who created/modified)
  created_by STRING,
  created_at STRING,
  updated_by STRING,
  updated_at STRING,

  -- Submission Info (Maker submits for validation)
  submitted_by STRING,
  submitted_at STRING,

  -- Validation Info (Checker validates)
  validated_by STRING,
  validated_at STRING,
  validation_comments STRING,

  -- Settlement Info (Checker settles/activates)
  settled_by STRING,
  settled_at STRING,
  settlement_comments STRING,

  -- Cancellation Info
  cancelled_by STRING,
  cancelled_at STRING,
  cancel_reason STRING,

  PRIMARY KEY (name)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
  'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);


-- ============================================================================
-- DATA MIGRATION from existing cis_portfolio
-- ============================================================================
-- Uncomment and run after creating the new table

/*
INSERT INTO cis_portfolio_v2
SELECT
    name,
    description,
    currency,
    manager,
    portfolio_client,
    cash_balance,
    cost_centre_code,
    corp_code,
    account_group,
    portfolio_group,
    report_group,
    entity_group,
    revaluation_status,
    COALESCE(src_system, 'GMP') as src_system,  -- Existing records default to GMP
    -- Map existing statuses to new workflow statuses
    CASE
        WHEN status = 'DRAFT' THEN 'INITIAL'
        WHEN status = 'PENDING_APPROVAL' THEN 'PENDING_VALIDATION'
        WHEN status = 'APPROVED' THEN 'VALIDATED'
        WHEN status = 'REJECTED' THEN 'CANCELLED'
        WHEN status = 'Active' THEN 'SETTLED'
        WHEN status = 'Inactive' THEN 'CANCELLED'
        ELSE 'SETTLED'  -- Default existing active records to SETTLED
    END as status,
    CASE
        WHEN status IN ('Active', 'APPROVED') THEN true
        ELSE false
    END as is_active,
    created_by,
    created_at,
    updated_by,
    updated_at,
    NULL as submitted_by,
    NULL as submitted_at,
    NULL as validated_by,
    NULL as validated_at,
    NULL as validation_comments,
    NULL as settled_by,
    NULL as settled_at,
    NULL as settlement_comments,
    NULL as cancelled_by,
    NULL as cancelled_at,
    NULL as cancel_reason
FROM cis_portfolio;
*/


-- ============================================================================
-- TABLE SWAP (after verifying migration)
-- ============================================================================
-- Uncomment and run after verifying data migration

/*
-- Backup original table
ALTER TABLE cis_portfolio RENAME TO cis_portfolio_backup_20260110;

-- Rename new table to original name
ALTER TABLE cis_portfolio_v2 RENAME TO cis_portfolio;

-- Verify
DESCRIBE cis_portfolio;
SELECT status, COUNT(*) FROM cis_portfolio GROUP BY status;
*/


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check new table structure
DESCRIBE cis_portfolio_v2;

-- After migration, verify status distribution
-- SELECT status, COUNT(*) FROM cis_portfolio GROUP BY status;

-- Check workflow columns exist
-- SELECT name, status, submitted_by, submitted_at, validated_by, validated_at,
--        settled_by, settled_at FROM cis_portfolio LIMIT 5;
