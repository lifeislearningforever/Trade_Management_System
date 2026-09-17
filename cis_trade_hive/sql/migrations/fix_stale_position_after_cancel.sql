-- ============================================================================
-- Migration: Fix stale is_latest position rows after trade cancellation
-- ============================================================================
-- Problem:
--   When a trade is cancelled and another trade still exists for the same
--   portfolio/security, the cancelled trade's settle_date position row
--   (is_latest=true, non-zero qty) is left behind in cis_position and
--   cis_trade_position because chain recalc only writes dates covered by
--   remaining active trades.
--
-- Example:
--   Trade 1: BUY 500, trade_date=2026-03-02, settle_date=2026-03-04 (SETTLED, active)
--   Trade 2: BUY 400, trade_date=2026-03-02, settle_date=2026-03-02 (CANCELLED)
--   → SETTLED position @ 2026-03-02 with qty=400 stays visible — should be 0.
--
-- Fix:
--   Retire the stale is_latest=true row for the cancelled trade's settle_date
--   by setting is_latest=false and quantity=0 in both cis_position and
--   cis_trade_position.
--
-- Instructions:
--   1. Replace PORTFOLIO_SHORT_NAME, SECURITY_LABEL, and SETTLE_DATE below
--      with your actual values before running.
--   2. Run Step 1 (check) first and confirm the stale row is visible.
--   3. Run Steps 2 and 3 to retire the stale rows.
--   4. Run Step 4 to verify only the correct active rows remain.
--
-- Run on UAT:
--   impala-shell -i <impala-host>:21050 -d gmp_cis \
--     -f sql/migrations/fix_stale_position_after_cancel.sql
-- ============================================================================

-- ============================================================================
-- CONFIGURATION — update these values before running
-- ============================================================================
-- PORTFOLIO_SHORT_NAME : 'UOBS_SHF_SUB'
-- SECURITY_LABEL       : 'UOI SP'
-- SETTLE_DATE          : '2026-03-02'   (the cancelled trade's settle_date)
-- POSITION_BASIS       : 'SETTLED'
-- ============================================================================


-- ============================================================================
-- STEP 1: Check — confirm stale rows exist before making any changes
-- ============================================================================
SELECT
    position_id,
    portfolio,
    security_label,
    position_date,
    position_basis,
    quantity,
    is_latest
FROM gmp_cis.cis_position
WHERE portfolio      = 'UOBS_SHF_SUB'
  AND security_label = 'UOI SP'
  AND is_latest      = true
ORDER BY position_date, position_basis;


-- ============================================================================
-- STEP 2: Retire stale row in cis_position (gold/summary table)
-- ============================================================================
UPDATE gmp_cis.cis_position
SET is_latest = false,
    quantity  = CAST(0 AS DECIMAL(30,8))
WHERE portfolio      = 'UOBS_SHF_SUB'
  AND security_label = 'UOI SP'
  AND position_date  = '2026-03-02'
  AND position_basis = 'SETTLED'
  AND is_latest      = true;


-- ============================================================================
-- STEP 3: Retire stale row in cis_trade_position (detail/AVP table)
-- ============================================================================
UPDATE gmp_cis.cis_trade_position
SET is_latest = false,
    quantity  = CAST(0 AS DECIMAL(30,8))
WHERE portfolio_short_name = 'UOBS_SHF_SUB'
  AND security_label       = 'UOI SP'
  AND position_date        = '2026-03-02'
  AND position_basis       = 'SETTLED'
  AND is_latest            = true;


-- ============================================================================
-- STEP 4: Verify — should show only TRADED 500 qty row remaining
-- ============================================================================
SELECT
    position_id,
    portfolio,
    security_label,
    position_date,
    position_basis,
    quantity,
    average_cost_fc,
    is_latest
FROM gmp_cis.cis_position
WHERE portfolio      = 'UOBS_SHF_SUB'
  AND security_label = 'UOI SP'
  AND is_latest      = true
ORDER BY position_date, position_basis;
