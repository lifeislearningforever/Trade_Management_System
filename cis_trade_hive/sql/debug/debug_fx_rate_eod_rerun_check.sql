-- Debug: compare cis_position EOD values before/after refresh_positions rerun
-- following a corrected GMP FX rate load for position_date = 2026-03-02.
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_fx_rate_eod_rerun_check.sql
-- ---------------------------------------------------------------------------

-- ── Step 1: snapshot current (pre-rerun) EOD values ──────────────────────────
-- Run BEFORE `python manage.py refresh_positions --position-date 2026-03-02`
CREATE TABLE gmp_cis.tmp_eod_before_fx_fix AS
SELECT portfolio, security_label, position_basis, position_date,
       market_value_lc, unrealized_pnl_lc, net_book_value_lc,
       average_cost_lc, cost_lc, position_id, version_id
FROM gmp_cis.cis_position
WHERE position_date = '2026-03-02'
  AND position_type = 'EOD'
  AND is_latest = true;

-- ── Step 2: rerun refresh_positions for real (not --dry-run) ────────────────
--   python manage.py refresh_positions --position-date 2026-03-02

-- ── Step 3: diff old snapshot vs new is_latest=true rows ────────────────────
SELECT b.portfolio, b.security_label,
       b.market_value_lc   AS old_mv_lc,   n.market_value_lc   AS new_mv_lc,
       n.market_value_lc - b.market_value_lc AS mv_lc_delta,
       b.unrealized_pnl_lc AS old_upnl_lc, n.unrealized_pnl_lc AS new_upnl_lc,
       b.average_cost_lc   AS old_avg_cost_lc, n.average_cost_lc AS new_avg_cost_lc
FROM gmp_cis.tmp_eod_before_fx_fix b
JOIN gmp_cis.cis_position n
  ON b.portfolio       = n.portfolio
 AND b.security_label  = n.security_label
 AND b.position_basis  = n.position_basis
 AND n.position_date   = '2026-03-02'
 AND n.position_type   = 'EOD'
 AND n.is_latest       = true
WHERE ABS(n.market_value_lc - b.market_value_lc) > 0.00000001
ORDER BY ABS(n.market_value_lc - b.market_value_lc) DESC;

-- ── Step 4: cleanup scratch table once review is complete ───────────────────
-- DROP TABLE IF EXISTS gmp_cis.tmp_eod_before_fx_fix;
