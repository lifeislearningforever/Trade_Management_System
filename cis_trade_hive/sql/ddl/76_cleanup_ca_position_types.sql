-- ============================================================================
-- Migration 76: Remove stale CA_* position_type rows from cis_position
-- ============================================================================
-- Before the fix (commit 6d36a6a), CA processing wrote new rows into
-- cis_position with position_type = 'CA_CASH_DIVIDEND', 'CA_STOCK_SPLIT' etc.
-- instead of updating the existing INT rows in place.
--
-- These stale rows must be deleted. The correct INT rows already exist
-- (or will be created when CA processing is re-run).
--
-- Only valid position_type values are: INT, EOD, SOD, CORR
--
-- Run with:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     -f 76_cleanup_ca_position_types.sql
-- ============================================================================

-- Preview first (run this SELECT to confirm what will be deleted)
SELECT position_type, COUNT(*) AS cnt, MIN(position_date) AS earliest, MAX(position_date) AS latest
FROM gmp_cis.cis_position
WHERE position_type NOT IN ('INT', 'EOD', 'SOD', 'CORR')
  AND position_type IS NOT NULL
GROUP BY position_type
ORDER BY position_type;

-- Delete all rows with invalid position_type (CA_* and any other non-standard types)
DELETE FROM gmp_cis.cis_position
WHERE position_type NOT IN ('INT', 'EOD', 'SOD', 'CORR')
  AND position_type IS NOT NULL;
