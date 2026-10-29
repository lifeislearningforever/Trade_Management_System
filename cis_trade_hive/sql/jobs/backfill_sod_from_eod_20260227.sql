-- =============================================================================
-- ONE-TIME BACKFILL: Copy EOD 2026-02-27 rows → SOD with contextual_today date
--
-- Purpose : The 26 zero-price trades had no position rows (fixed in commit
--           6194dce). After backfilling cis_trade_position and running EOD
--           refresh, the 2026-02-27 EOD rows now exist. This script promotes
--           them to SOD rows stamped with the current contextual business date.
--
-- Run order:
--   Step 1  — verify business dates (read-only, safe to run anytime)
--   Step 2  — delete any existing SOD rows for contextual_today (idempotent)
--   Step 3  — insert SOD rows
--
-- Replace before running:
--   <YYYY-MM-DD>  →  contextual_today in ISO format  e.g. 2026-06-30
--   <YYYYMMDD>    →  contextual_today as compact date e.g. 20260630
--
-- Usage:
--   impala-shell -i localhost:21050 -f sql/jobs/backfill_sod_from_eod_20260227.sql
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 1 — Verify business dates (run first, confirm contextual_today)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT contextual_today, prev_day
FROM gmp_cis.gmp_cis_sta_dly_alldatesinfo
WHERE src_system   = 'gmp'
  AND sub_system   = 'cis'
  AND data_frq     = 'dly'
  AND record_type  = 'D'
  AND processing_date = (
      SELECT MAX(processing_date)
      FROM gmp_cis.gmp_cis_sta_dly_alldatesinfo
      WHERE src_system  = 'gmp'
        AND sub_system  = 'cis'
        AND data_frq    = 'dly'
        AND record_type = 'D'
  )
LIMIT 1;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 2 — Verify count of source EOD rows before inserting
-- ─────────────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS eod_rows_to_copy, position_basis, src_system
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND position_date = '2026-02-27'
GROUP BY position_basis, src_system
ORDER BY position_basis, src_system;


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 3 — Delete existing SOD rows for contextual_today (idempotent)
--          Replace <YYYY-MM-DD> with contextual_today e.g. 2026-06-30
-- ─────────────────────────────────────────────────────────────────────────────
DELETE FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND position_date = '<YYYY-MM-DD>';


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 4 — Insert EOD 2026-02-27 rows as SOD with contextual_today as date
--          Replace <YYYY-MM-DD>  e.g. 2026-06-30
--          Replace <YYYYMMDD>    e.g. 20260630
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO gmp_cis.cis_position (
    position_id, version_id,
    portfolio, security_label, position_basis, position_date,
    src_system, processing_date,
    quantity,
    average_cost_fc, cost_fc,
    average_cost_lc, cost_lc,
    market_value_fc, market_value_lc,
    net_book_value_fc, net_book_value_lc,
    unrealized_pnl_fc, unrealized_pnl_lc,
    realized_pnl_fc, realized_pnl_lc,
    provision_fc, provision_lc,
    dividend_fc, dividend_lc,
    uncall_fc, uncall_lc,
    pipeline_fc, pipeline_lc,
    position_type, isin, source_table
)
SELECT
    (CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT) + position_id) AS position_id,
    (CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT) + position_id) AS version_id,
    portfolio,
    security_label,
    position_basis,
    '<YYYY-MM-DD>'   AS position_date,
    src_system,
    '<YYYYMMDD>'     AS processing_date,
    quantity,
    average_cost_fc, cost_fc,
    average_cost_lc, cost_lc,
    market_value_fc, market_value_lc,
    net_book_value_fc, net_book_value_lc,
    unrealized_pnl_fc, unrealized_pnl_lc,
    realized_pnl_fc, realized_pnl_lc,
    provision_fc, provision_lc,
    dividend_fc, dividend_lc,
    uncall_fc, uncall_lc,
    pipeline_fc, pipeline_lc,
    'SOD'            AS position_type,
    isin,
    source_table
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND position_date = '2026-02-27';


-- ─────────────────────────────────────────────────────────────────────────────
-- STEP 5 — Verify inserted SOD rows
--          Replace <YYYY-MM-DD> with contextual_today
-- ─────────────────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS sod_rows_inserted, position_basis, src_system
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND position_date = '<YYYY-MM-DD>'
GROUP BY position_basis, src_system
ORDER BY position_basis, src_system;
