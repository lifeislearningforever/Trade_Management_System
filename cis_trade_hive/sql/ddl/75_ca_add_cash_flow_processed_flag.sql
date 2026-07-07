-- ============================================================================
-- Migration 75: Add cash_flow processing flags to cis_corporate_actions
-- ============================================================================
-- Adds three columns to track whether a CA has been queued and processed
-- into cash flows / position adjustments.
--
-- cash_flow_queued      BOOLEAN  — set true when queue entry inserted (Wave 1)
-- cash_flow_processed   BOOLEAN  — set true when queue entry reaches COMPLETED
-- cash_flow_processed_at STRING  — timestamp (YYYY-MM-DD HH:MM:SS) of completion
--
-- Run with:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     -f 75_ca_add_cash_flow_processed_flag.sql
-- ============================================================================

-- Step 1: Add the new columns
ALTER TABLE gmp_cis.cis_corporate_actions
    ADD COLUMNS (
        cash_flow_queued       BOOLEAN COMMENT 'True when a queue entry has been created for this CA',
        cash_flow_processed    BOOLEAN COMMENT 'True when cash flow processing completed successfully',
        cash_flow_processed_at STRING  COMMENT 'Timestamp when processing completed (YYYY-MM-DD HH:MM:SS)'
    );

-- ============================================================================
-- Step 2: Backfill existing data from cis_ca_cash_flow_queue
-- ============================================================================
-- CA has a COMPLETED queue entry → queued=true, processed=true
-- CA has a queue entry in any other status → queued=true, processed=false
-- CA has no queue entry → queued=false, processed=false (Kudu default NULL)
--
-- Impala does not support UPDATE … FROM / JOIN.
-- Use a subquery in the SET clause instead.
-- Run each UPDATE block separately if needed.
-- ============================================================================

-- 2a: Mark CAs whose queue entry is COMPLETED
UPDATE gmp_cis.cis_corporate_actions ca
SET cash_flow_queued    = true,
    cash_flow_processed = true
WHERE ca.ca_id IN (
    SELECT DISTINCT ca_id
    FROM gmp_cis.cis_ca_cash_flow_queue
    WHERE status = 'COMPLETED'
);

-- 2b: Mark CAs that have a queue entry but NOT completed (PENDING / PROCESSING / FAILED)
UPDATE gmp_cis.cis_corporate_actions ca
SET cash_flow_queued    = true,
    cash_flow_processed = false
WHERE ca.cash_flow_queued IS NULL           -- not already set by 2a
  AND ca.ca_id IN (
    SELECT DISTINCT ca_id
    FROM gmp_cis.cis_ca_cash_flow_queue
    WHERE status IN ('PENDING', 'PROCESSING', 'FAILED')
);

-- 2c: Remaining CAs (no queue entry at all) — set both to false explicitly
UPDATE gmp_cis.cis_corporate_actions
SET cash_flow_queued    = false,
    cash_flow_processed = false
WHERE cash_flow_queued IS NULL;
