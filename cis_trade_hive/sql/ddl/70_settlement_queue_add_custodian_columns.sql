-- ============================================================================
-- DDL 70: Add custodian columns to cis_settlement_queue
-- ============================================================================
-- Problem: INSERT into cis_settlement_queue references custodian and
--          sub_custodian columns that were never added to the table.
--          settlement_service.py reads them back to pass to calculate_position.
--
-- Fix: ADD COLUMNS custodian STRING and sub_custodian STRING.
--
-- Run on: SIT, UAT, PROD
-- Safe to re-run: ALTER TABLE ADD COLUMNS is idempotent in Impala
--                 (will error if column already exists — verify first with DESCRIBE)
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Step 1: Add missing columns to cis_settlement_queue
-- ============================================================================

ALTER TABLE cis_settlement_queue ADD COLUMNS (custodian STRING);
ALTER TABLE cis_settlement_queue ADD COLUMNS (sub_custodian STRING);

-- ============================================================================
-- Step 2: Verify
-- ============================================================================

DESCRIBE cis_settlement_queue;

-- Expected: custodian and sub_custodian appear in the column list.
-- Existing PENDING rows will have NULL for these two columns (acceptable —
-- the settlement worker uses item.get('custodian') which defaults to None).

-- ============================================================================
-- END
-- ============================================================================
