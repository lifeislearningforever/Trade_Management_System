-- DDL/DML 83: Backfill cis_position_rep from cis_position (EOD rows)
--
-- Use this to populate cis_position_rep for dates that existed before
-- the automated publish step was added to refresh_positions.
--
-- Run on server:
--   impala-shell -i <host>:21050 -f sql/ddl/83_backfill_cis_position_rep.sql
-- ---------------------------------------------------------------------------

-- ── Option A: Single date ───────────────────────────────────────────────────
-- Replace '2026-03-02' with the target date.

INSERT OVERWRITE gmp_cis.cis_position_rep
PARTITION (position_date = '2026-03-02')
SELECT
    position_id,
    version_id,
    portfolio,
    security_label,
    position_basis,
    src_system,
    processing_date,
    processing_timestamp,
    isin,
    source_table,
    quantity,
    average_cost_fc,
    cost_fc,
    market_value_fc,
    net_book_value_fc,
    unrealized_pnl_fc,
    realized_pnl_fc,
    provision_fc,
    dividend_fc,
    uncall_fc,
    pipeline_fc,
    average_cost_lc,
    cost_lc,
    market_value_lc,
    net_book_value_lc,
    unrealized_pnl_lc,
    realized_pnl_lc,
    provision_lc,
    dividend_lc,
    uncall_lc,
    pipeline_lc
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND is_latest     = true
  AND position_date = '2026-03-02';


-- ── Option B: All dates (dynamic partition backfill) ────────────────────────
-- Populates every position_date in one pass.
-- Uncomment and run instead of Option A when backfilling the full history.

-- SET hive.exec.dynamic.partition=true;
-- SET hive.exec.dynamic.partition.mode=nonstrict;
--
-- INSERT OVERWRITE gmp_cis.cis_position_rep
-- PARTITION (position_date)
-- SELECT
--     position_id, version_id,
--     portfolio, security_label, position_basis,
--     src_system, processing_date, processing_timestamp,
--     isin, source_table,
--     quantity,
--     average_cost_fc, cost_fc,
--     market_value_fc, net_book_value_fc,
--     unrealized_pnl_fc, realized_pnl_fc,
--     provision_fc, dividend_fc, uncall_fc, pipeline_fc,
--     average_cost_lc, cost_lc,
--     market_value_lc, net_book_value_lc,
--     unrealized_pnl_lc, realized_pnl_lc,
--     provision_lc, dividend_lc, uncall_lc, pipeline_lc,
--     position_date          -- must be LAST: maps to the partition column
-- FROM gmp_cis.cis_position
-- WHERE position_type = 'EOD'
--   AND is_latest     = true;


-- ── Verify ──────────────────────────────────────────────────────────────────
SELECT COUNT(*) AS row_count, src_system, position_date
FROM gmp_cis.cis_position_rep
WHERE position_date = '2026-03-02'
GROUP BY src_system, position_date
ORDER BY src_system;
