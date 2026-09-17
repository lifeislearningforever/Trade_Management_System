-- =============================================================================
-- ONE-TIME FIX: Set is_latest for cis_position on position_date = 2026-02-03
--
-- Goal: exactly one is_latest=true row per natural key
--       (portfolio, security_label, position_basis, src_system) for this date,
--       preferring INT over SOD:
--   - If an INT row exists for the key -> INT is_latest=true, all other rows
--     for that key (SOD/EOD/CORR) on this date -> is_latest=false.
--   - If no INT row exists but an SOD row does -> SOD is_latest=true.
--
-- Note: cis_position's is_latest is normally tracked PER position_type
-- independently (see sql/ddl/66_cis_position_add_is_latest.sql) — this script
-- deliberately overrides that for this one date to make INT win over SOD
-- wherever both exist, per one-off request.
--
-- Impala does not support subqueries in UPDATE ... SET (see CLAUDE.md), so
-- this uses UPDATE ... WHERE ... NOT IN (subquery), same pattern as
-- sql/jobs/fix_duplicate_eod_positions.sql.
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/set_is_latest_int_or_sod_2026_02_03.sql
-- =============================================================================

USE gmp_cis;

-- STEP 0 — Preview: how many keys have INT vs SOD-only on this date
SELECT
    COUNT(DISTINCT CASE WHEN position_type = 'INT' THEN portfolio || '|' || security_label || '|' || position_basis || '|' || src_system END) AS keys_with_int,
    COUNT(DISTINCT CASE WHEN position_type = 'SOD' THEN portfolio || '|' || security_label || '|' || position_basis || '|' || src_system END) AS keys_with_sod
FROM cis_position
WHERE position_date = '2026-02-03';


-- STEP 1 — Clean baseline: demote every row for this date to is_latest=false
UPDATE cis_position
SET is_latest = false
WHERE position_date = '2026-02-03';


-- STEP 2 — INT wins: set is_latest=true for the INT row per key
--          (MAX(position_id) as tiebreaker if more than one INT row exists
--           for the same key on this date — mirrors fix_duplicate_eod_positions.sql)
UPDATE cis_position
SET is_latest = true
WHERE position_date = '2026-02-03'
  AND position_type = 'INT'
  AND position_id IN (
      SELECT MAX(position_id)
      FROM cis_position
      WHERE position_date = '2026-02-03'
        AND position_type = 'INT'
      GROUP BY portfolio, security_label, position_basis, src_system
  );


-- STEP 3 — SOD wins only where no INT row exists for that key on this date
UPDATE cis_position
SET is_latest = true
WHERE position_date = '2026-02-03'
  AND position_type = 'SOD'
  AND position_id IN (
      SELECT MAX(position_id)
      FROM cis_position
      WHERE position_date = '2026-02-03'
        AND position_type = 'SOD'
      GROUP BY portfolio, security_label, position_basis, src_system
  )
  AND (portfolio || '|' || security_label || '|' || position_basis || '|' || src_system) NOT IN (
      SELECT portfolio || '|' || security_label || '|' || position_basis || '|' || src_system
      FROM cis_position
      WHERE position_date = '2026-02-03'
        AND position_type = 'INT'
  );


-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Every key should have exactly one is_latest=true row (INT if present, else SOD)
SELECT
    portfolio, security_label, position_basis, src_system,
    SUM(CASE WHEN is_latest = true THEN 1 ELSE 0 END) AS latest_count
FROM cis_position
WHERE position_date = '2026-02-03'
GROUP BY portfolio, security_label, position_basis, src_system
HAVING SUM(CASE WHEN is_latest = true THEN 1 ELSE 0 END) <> 1
ORDER BY portfolio, security_label;

-- Breakdown by type
SELECT
    position_type,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN is_latest = true THEN 1 ELSE 0 END) AS is_latest_true
FROM cis_position
WHERE position_date = '2026-02-03'
GROUP BY position_type
ORDER BY position_type;
