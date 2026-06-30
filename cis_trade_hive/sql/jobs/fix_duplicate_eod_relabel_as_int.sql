-- =============================================================================
-- ONE-TIME FIX: Deduplicate EOD rows in cis_position
--
-- For each (portfolio, security_label, position_basis) with multiple EOD rows:
--   - MAX(position_id)            → position_type = 'INT'  (latest/live)
--   - Second highest position_id  → position_type = 'EOD'  (keep one EOD)
--   - All others (3rd, 4th ...)   → DELETE
--
-- Handles 2, 3, or N duplicate EOD rows correctly.
--
-- Run order:
--   Step 1 — verify duplicates (read-only)
--   Step 2 — delete all excess rows beyond top 2
--   Step 3 — relabel MAX(position_id) to INT
--   Step 4 — verify result
--   Step 5 — spot check UOBAM_TW_DFUND / CLAR SP
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/fix_duplicate_eod_relabel_as_int.sql
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1 — Show all duplicate EOD combinations and counts (read-only)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.portfolio,
    p.security_label,
    p.position_basis,
    COUNT(*)           AS total_eod_rows,
    MAX(p.position_id) AS max_position_id,
    MIN(p.position_id) AS min_position_id
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
GROUP BY p.portfolio, p.security_label, p.position_basis
ORDER BY total_eod_rows DESC, p.portfolio, p.security_label;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — Delete all EOD rows beyond the top 2 per combination
--          (3rd highest, 4th highest, etc.)
--          Top 2 = MAX and second-highest position_id — these are kept.
-- ─────────────────────────────────────────────────────────────────────────────
DELETE FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND position_id NOT IN (
      -- Keep MAX per combination
      SELECT MAX(position_id)
      FROM gmp_cis.cis_position
      WHERE position_type = 'EOD'
      GROUP BY portfolio, security_label, position_basis
  )
  AND position_id NOT IN (
      -- Keep second-highest per combination
      SELECT MAX(position_id)
      FROM gmp_cis.cis_position
      WHERE position_type = 'EOD'
        AND position_id NOT IN (
            SELECT MAX(position_id)
            FROM gmp_cis.cis_position
            WHERE position_type = 'EOD'
            GROUP BY portfolio, security_label, position_basis
        )
      GROUP BY portfolio, security_label, position_basis
  );


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3 — Relabel MAX(position_id) per combination from EOD → INT
--          The remaining lower position_id stays as EOD
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
-- STEP 4 — Verify: no combination should have more than 1 EOD row
--          and INT+EOD counts should each be 1 for affected combinations
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.portfolio,
    p.security_label,
    p.position_basis,
    COUNT(*)                                                    AS total_rows,
    SUM(CASE WHEN p.position_type = 'INT' THEN 1 ELSE 0 END)   AS int_count,
    SUM(CASE WHEN p.position_type = 'EOD' THEN 1 ELSE 0 END)   AS eod_count
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
-- STEP 5 — Spot check UOBAM_TW_DFUND / CLAR SP
-- ─────────────────────────────────────────────────────────────────────────────
SELECT position_id, version_id, portfolio, security_label,
       position_basis, position_type, position_date
FROM gmp_cis.cis_position
WHERE portfolio     = 'UOBAM_TW_DFUND'
  AND security_label = 'CLAR SP'
ORDER BY position_id;
