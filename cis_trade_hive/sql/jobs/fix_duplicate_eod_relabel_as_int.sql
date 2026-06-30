-- =============================================================================
-- ONE-TIME FIX: Relabel duplicate EOD rows — bigger position_id → INT, smaller → EOD
--
-- Context : refresh_positions created duplicate EOD rows for some positions.
--           Rather than deleting, we keep both and assign correct position_type:
--             - MAX(position_id) per (portfolio, security_label, position_basis) → INT
--             - MIN(position_id) (the older row)                                 → EOD
--
-- Run order: Step 1 verify → Step 2 update INT → Step 3 verify
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/fix_duplicate_eod_relabel_as_int.sql
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1 — Show all duplicate EOD combinations before update
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.position_id,
    p.version_id,
    p.portfolio,
    p.security_label,
    p.position_basis,
    p.position_type,
    p.position_date
FROM gmp_cis.cis_position p
INNER JOIN (
    SELECT portfolio, security_label, position_basis
    FROM gmp_cis.cis_position
    WHERE position_type = 'EOD'
    GROUP BY portfolio, security_label, position_basis
    HAVING COUNT(*) > 1
) dups
  ON p.portfolio      = dups.portfolio
 AND p.security_label = dups.security_label
 AND p.position_basis = dups.position_basis
WHERE p.position_type = 'EOD'
ORDER BY p.portfolio, p.security_label, p.position_basis, p.position_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — Set the bigger position_id (latest row) to INT
--          The smaller position_id row stays as EOD
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE gmp_cis.cis_position
SET position_type = 'INT'
WHERE position_type = 'EOD'
  AND position_id IN (
      SELECT MAX(position_id)
      FROM gmp_cis.cis_position
      WHERE position_type = 'EOD'
      GROUP BY portfolio, security_label, position_basis
      HAVING COUNT(*) > 1
  );


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3 — Verify: each combination should now have one INT and one EOD
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.portfolio,
    p.security_label,
    p.position_basis,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN p.position_type = 'INT' THEN 1 ELSE 0 END) AS int_count,
    SUM(CASE WHEN p.position_type = 'EOD' THEN 1 ELSE 0 END) AS eod_count
FROM gmp_cis.cis_position p
INNER JOIN (
    SELECT portfolio, security_label, position_basis
    FROM gmp_cis.cis_position
    WHERE position_type IN ('INT', 'EOD')
    GROUP BY portfolio, security_label, position_basis
    HAVING COUNT(*) > 1
) combos
  ON p.portfolio      = combos.portfolio
 AND p.security_label = combos.security_label
 AND p.position_basis = combos.position_basis
GROUP BY p.portfolio, p.security_label, p.position_basis
ORDER BY p.portfolio, p.security_label, p.position_basis;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 4 — Spot check UOBAM_TW_DFUND / CLAR SP
-- ─────────────────────────────────────────────────────────────────────────────
SELECT position_id, version_id, portfolio, security_label,
       position_basis, position_type, position_date
FROM gmp_cis.cis_position
WHERE portfolio = 'UOBAM_TW_DFUND'
  AND security_label = 'CLAR SP'
ORDER BY position_id;
