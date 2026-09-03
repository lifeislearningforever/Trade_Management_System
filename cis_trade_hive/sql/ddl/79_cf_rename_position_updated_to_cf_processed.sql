-- ============================================================================
-- Migration 79: Rename position_updated → cf_processed on cis_cash_flow
-- ============================================================================
-- Rationale:
--   position_updated was named from the perspective of the position table
--   ("did the position get updated?"). The flag actually lives on the cash
--   flow record and means "this cash flow has been processed and applied to
--   positions". Renaming to cf_processed makes the two-layer lifecycle explicit:
--
--     cis_corporate_actions.ca_processed  → CA produced its cash flows (migration 78)
--     cis_cash_flow.cf_processed          → CF was applied to positions  ← this migration
--
-- Run with:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     -f 79_cf_rename_position_updated_to_cf_processed.sql
--
-- NOTE: Kudu does not support ALTER COLUMN RENAME. Standard approach:
--   1. Add new column.
--   2. Backfill from old column.
--   3. Drop old column.
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Step 1: Add new column
-- ============================================================================
ALTER TABLE gmp_cis.cis_cash_flow
    ADD COLUMNS (
        cf_processed BOOLEAN COMMENT 'True when this CF has been applied to positions by process_approved_cashflows'
    );

-- ============================================================================
-- Step 2: Backfill new column from old column
-- ============================================================================
UPDATE gmp_cis.cis_cash_flow
SET cf_processed = position_updated
WHERE position_updated IS NOT NULL;

UPDATE gmp_cis.cis_cash_flow
SET cf_processed = false
WHERE position_updated IS NULL;

-- ============================================================================
-- Step 3: Drop old column
-- ============================================================================
ALTER TABLE gmp_cis.cis_cash_flow
    DROP COLUMN position_updated;

-- ============================================================================
-- Verification
-- ============================================================================
-- SELECT cash_flow_id, cash_flow_number, status, cf_processed
-- FROM gmp_cis.cis_cash_flow
-- ORDER BY created_at DESC
-- LIMIT 10;
