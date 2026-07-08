-- ============================================================================
-- Migration 78: Rename cash_flow_processed / cash_flow_processed_at
--               to ca_processed / ca_processed_at on cis_corporate_actions
-- ============================================================================
-- Rationale:
--   The old names implied the flag tracked whether the *cash flow* was
--   processed (e.g. whether it updated positions). That meaning belongs to
--   cis_cash_flow.position_updated.
--
--   The CA-level flag only means "the CA queue job ran and generated its cash
--   flows". Renaming to ca_processed makes the two-layer lifecycle explicit:
--
--     cis_corporate_actions.ca_processed     → CA produced its cash flows
--     cis_cash_flow.position_updated         → CF was applied to positions
--
-- Run with:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     -f 78_ca_rename_cash_flow_processed_to_ca_processed.sql
--
-- NOTE: Kudu does not support ALTER COLUMN RENAME. The standard approach is:
--   1. Add new columns.
--   2. Backfill from old columns.
--   3. Drop old columns.
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Step 1: Add new columns
-- ============================================================================
ALTER TABLE gmp_cis.cis_corporate_actions
    ADD COLUMNS (
        ca_processed    BOOLEAN COMMENT 'True when the CA queue job completed — cash flows were generated',
        ca_processed_at STRING  COMMENT 'Timestamp when CA processing completed (YYYY-MM-DD HH:MM:SS)'
    );

-- ============================================================================
-- Step 2: Backfill new columns from old columns
-- ============================================================================
UPDATE gmp_cis.cis_corporate_actions
SET ca_processed    = cash_flow_processed,
    ca_processed_at = cash_flow_processed_at
WHERE cash_flow_processed IS NOT NULL;

UPDATE gmp_cis.cis_corporate_actions
SET ca_processed = false
WHERE cash_flow_processed IS NULL;

-- ============================================================================
-- Step 3: Drop old columns
-- ============================================================================
ALTER TABLE gmp_cis.cis_corporate_actions
    DROP COLUMN cash_flow_processed;

ALTER TABLE gmp_cis.cis_corporate_actions
    DROP COLUMN cash_flow_processed_at;

-- ============================================================================
-- Verification
-- ============================================================================
-- SELECT ca_id, ca_number, cash_flow_queued, ca_processed, ca_processed_at
-- FROM gmp_cis.cis_corporate_actions
-- LIMIT 10;
