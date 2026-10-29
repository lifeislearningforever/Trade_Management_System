-- Debug: SOD vs EOD gap analysis
-- Run to diagnose mismatch between refresh_positions --fill-gaps and
-- create_sod_snapshot --fill-gaps row counts.
--
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_sod_eod_gap_check.sql
-- ---------------------------------------------------------------------------

-- ── 1. All existing SOD rows — which dates and sources ───────────────────────
SELECT
    COUNT(*)        AS cnt,
    src_system,
    position_type,
    position_date
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND is_latest     = true
GROUP BY src_system, position_type, position_date
ORDER BY position_date, src_system;


-- ── 2. All existing EOD rows — which dates and sources ───────────────────────
SELECT
    COUNT(*)        AS cnt,
    src_system,
    position_type,
    position_date
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND is_latest     = true
GROUP BY src_system, position_type, position_date
ORDER BY position_date, src_system;


-- ── 3. EOD rows for 2026-03-02 (source for SOD snapshot) ────────────────────
SELECT
    COUNT(*)        AS cnt,
    src_system,
    position_type,
    position_date
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND is_latest     = true
  AND position_date = '2026-03-02'
GROUP BY src_system, position_type, position_date
ORDER BY src_system;


-- ── 4. SOD rows for 2026-03-03 (target sod_date) ────────────────────────────
SELECT
    COUNT(*)        AS cnt,
    src_system,
    position_type,
    position_date
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND is_latest     = true
  AND position_date = '2026-03-03'
GROUP BY src_system, position_type, position_date
ORDER BY src_system;


-- ── 5. SOD rows for 2026-03-02 (previous sod_date — may be causing confusion)
SELECT
    COUNT(*)        AS cnt,
    src_system,
    position_type,
    position_date
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND is_latest     = true
  AND position_date = '2026-03-02'
GROUP BY src_system, position_type, position_date
ORDER BY src_system;


-- ── 6. What fill-gaps would exclude for sod_date=2026-03-03 ─────────────────
-- Shows which (portfolio, security_label, position_basis) already have a SOD
-- row on 2026-03-03 and would be SKIPPED by --fill-gaps.
SELECT
    COUNT(*)  AS existing_sod_on_20260303
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND is_latest     = true
  AND position_date = '2026-03-03';


-- ── 7. What fill-gaps would return for sod_date=2026-03-03 ──────────────────
-- EOD rows on 2026-03-02 that have NO matching SOD on 2026-03-03.
-- This is what create_sod_snapshot --fill-gaps should process.
SELECT
    COUNT(*)   AS eod_rows_missing_sod,
    p.src_system
FROM gmp_cis.cis_position p
LEFT JOIN (
    SELECT DISTINCT portfolio, security_label, position_basis
    FROM gmp_cis.cis_position
    WHERE position_type = 'SOD'
      AND is_latest     = true
      AND position_date = '2026-03-03'
) existing_sod
  ON p.portfolio      = existing_sod.portfolio
 AND p.security_label = existing_sod.security_label
 AND p.position_basis = existing_sod.position_basis
WHERE p.position_type = 'EOD'
  AND p.is_latest     = true
  AND p.position_date = '2026-03-02'
  AND existing_sod.portfolio IS NULL
GROUP BY p.src_system
ORDER BY p.src_system;


-- ── 8. EOD rows for 2026-03-02 with NO matching EOD on same date ─────────────
-- Cross-check: what refresh_positions --fill-gaps skipped vs processed
SELECT
    COUNT(*)   AS eod_rows_missing_eod,
    p.src_system
FROM gmp_cis.cis_position p
LEFT JOIN (
    SELECT DISTINCT portfolio, security_label, position_basis
    FROM gmp_cis.cis_position
    WHERE position_type = 'EOD'
      AND is_latest     = true
      AND position_date = '2026-03-02'
) existing_eod
  ON p.portfolio      = existing_eod.portfolio
 AND p.security_label = existing_eod.security_label
 AND p.position_basis = existing_eod.position_basis
WHERE p.position_type IN ('INT', 'SOD')
  AND p.is_latest     = true
  AND p.position_date = '2026-03-02'
  AND existing_eod.portfolio IS NULL
GROUP BY p.src_system
ORDER BY p.src_system;


-- ── 9. Full position_type breakdown for 2026-03-02 ───────────────────────────
SELECT
    position_type,
    src_system,
    COUNT(*) AS cnt
FROM gmp_cis.cis_position
WHERE position_date = '2026-03-02'
  AND is_latest     = true
GROUP BY position_type, src_system
ORDER BY position_type, src_system;
