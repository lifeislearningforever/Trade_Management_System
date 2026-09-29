-- =============================================================================
-- ONE-TIME FIX: Remove duplicate EOD rows in cis_position
--
-- Root cause: refresh_positions DELETE was scoped to position_date, so when a
-- prior run left EOD rows with a different date, the new INSERT created a second
-- row instead of replacing the first.
--
-- Fix: Keep only the row with the highest position_id per
--      (portfolio, security_label, position_basis) for position_type='EOD'.
--      Delete all others.
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/fix_duplicate_eod_positions.sql
-- =============================================================================


-- STEP 1 — Check how many duplicates exist
SELECT portfolio, security_label, position_basis, COUNT(*) AS cnt
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
GROUP BY portfolio, security_label, position_basis
HAVING COUNT(*) > 1
ORDER BY cnt DESC;


-- STEP 2 — Delete duplicate EOD rows, keeping only the latest (MAX position_id)
DELETE FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND position_id NOT IN (
      SELECT MAX(position_id)
      FROM gmp_cis.cis_position
      WHERE position_type = 'EOD'
      GROUP BY portfolio, security_label, position_basis
  );


-- STEP 3 — Verify no duplicates remain
SELECT portfolio, security_label, position_basis, COUNT(*) AS cnt
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
GROUP BY portfolio, security_label, position_basis
HAVING COUNT(*) > 1;
