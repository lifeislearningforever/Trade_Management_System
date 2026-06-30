-- =============================================================================
-- ONE-TIME FIX: Deduplicate EOD rows in cis_position
--
-- For each (portfolio, security_label, position_basis, position_date)
-- with multiple EOD rows:
--   - MAX(position_id)   → position_type = 'EOD'  (latest — keep as EOD)
--   - All others         → position_type = 'INT'   (older rows relabelled)
--   - Nothing is deleted
--
-- Handles 2, 3, or N duplicate EOD rows correctly.
--
-- Run order:
--   Step 1 — verify duplicates (read-only)
--   Step 2 — relabel all non-MAX rows from EOD → INT
--   Step 3 — verify result (no combination should have more than 1 EOD)
--   Step 4 — spot check UOBAM_TW_DFUND / CLAR SP
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
    p.position_date,
    COUNT(*)           AS total_eod_rows,
    MAX(p.position_id) AS latest_position_id,
    MIN(p.position_id) AS oldest_position_id
FROM gmp_cis.cis_position p
INNER JOIN (
    SELECT portfolio, security_label, position_basis, position_date
    FROM gmp_cis.cis_position
    WHERE position_type = 'EOD'
    GROUP BY portfolio, security_label, position_basis, position_date
    HAVING COUNT(*) > 1
) dups
  ON p.portfolio      = dups.portfolio
 AND p.security_label = dups.security_label
 AND p.position_basis = dups.position_basis
 AND p.position_date  = dups.position_date
WHERE p.position_type = 'EOD'
GROUP BY p.portfolio, p.security_label, p.position_basis, p.position_date
ORDER BY total_eod_rows DESC, p.portfolio, p.security_label, p.position_date;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — Relabel all non-MAX(position_id) EOD rows → INT
--          MAX(position_id) per (portfolio, security_label, position_basis,
--          position_date) stays as EOD. Everything else becomes INT.
--          Nothing is deleted.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE gmp_cis.cis_position
SET position_type = 'INT'
WHERE position_type = 'EOD'
  AND position_id NOT IN (
      SELECT MAX(position_id)
      FROM gmp_cis.cis_position
      WHERE position_type = 'EOD'
      GROUP BY portfolio, security_label, position_basis, position_date
  );


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3 — Verify: each (portfolio, security_label, position_basis, position_date)
--          should have exactly 1 EOD row. INT rows can be many.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.portfolio,
    p.security_label,
    p.position_basis,
    p.position_date,
    COUNT(*)                                                    AS total_rows,
    SUM(CASE WHEN p.position_type = 'EOD' THEN 1 ELSE 0 END)   AS eod_count,
    SUM(CASE WHEN p.position_type = 'INT' THEN 1 ELSE 0 END)   AS int_count
FROM gmp_cis.cis_position p
INNER JOIN (
    SELECT portfolio, security_label, position_basis, position_date
    FROM gmp_cis.cis_position
    WHERE position_type IN ('INT', 'EOD')
    GROUP BY portfolio, security_label, position_basis, position_date
    HAVING COUNT(*) > 1
) combos
  ON p.portfolio      = combos.portfolio
 AND p.security_label = combos.security_label
 AND p.position_basis = combos.position_basis
 AND p.position_date  = combos.position_date
GROUP BY p.portfolio, p.security_label, p.position_basis, p.position_date
ORDER BY p.portfolio, p.security_label, p.position_basis, p.position_date;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 4 — Spot check UOBAM_TW_DFUND / CLAR SP
-- ─────────────────────────────────────────────────────────────────────────────
SELECT position_id, version_id, portfolio, security_label,
       position_basis, position_type, position_date
FROM gmp_cis.cis_position
WHERE portfolio      = 'UOBAM_TW_DFUND'
  AND security_label = 'CLAR SP'
ORDER BY position_date, position_id;
