-- Debug: cis_position has duplicate EOD rows for 2026-03-02 after the FX-rate
-- rerun of refresh_positions. The old row (processing_timestamp IS NULL, from
-- before that column was populated) was not removed by the DELETE-before-INSERT
-- in _batch_upsert_eod, leaving it alongside the newly recomputed row.
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_eod_duplicate_null_timestamp.sql
-- ---------------------------------------------------------------------------

-- ── 1. Find duplicate EOD natural keys for 2026-03-02 ────────────────────────
SELECT portfolio, security_label, position_basis, position_date, COUNT(*) AS cnt
FROM gmp_cis.cis_position
WHERE position_date = '2026-03-02' AND position_type = 'EOD'
GROUP BY portfolio, security_label, position_basis, position_date
HAVING COUNT(*) > 1;

-- ── 2. Inspect the actual duplicate rows (join, not tuple-IN — Impala doesn't
--       support (a,b,c) IN (subquery)) ──────────────────────────────────────
SELECT p.position_id, p.portfolio, p.security_label, p.position_basis, p.position_date,
       p.is_latest, p.processing_timestamp, p.market_value_lc
FROM gmp_cis.cis_position p
JOIN (
    SELECT portfolio, security_label, position_basis
    FROM gmp_cis.cis_position
    WHERE position_date = '2026-03-02' AND position_type = 'EOD'
    GROUP BY portfolio, security_label, position_basis
    HAVING COUNT(*) > 1
) dup
  ON p.portfolio       = dup.portfolio
 AND p.security_label  = dup.security_label
 AND p.position_basis  = dup.position_basis
WHERE p.position_date = '2026-03-02' AND p.position_type = 'EOD'
ORDER BY p.portfolio, p.security_label, p.processing_timestamp;

-- ── 3. Cleanup: delete the stale (NULL processing_timestamp) rows, keeping ──
--       the newly-recomputed ones. Review step 2's output before running this.
DELETE FROM gmp_cis.cis_position
WHERE position_date = '2026-03-02' AND position_type = 'EOD'
  AND processing_timestamp IS NULL;

-- ── 4. Verify no duplicates remain ───────────────────────────────────────────
SELECT portfolio, security_label, position_basis, position_date, COUNT(*) AS cnt
FROM gmp_cis.cis_position
WHERE position_date = '2026-03-02' AND position_type = 'EOD'
GROUP BY portfolio, security_label, position_basis, position_date
HAVING COUNT(*) > 1;
-- Expect zero rows
