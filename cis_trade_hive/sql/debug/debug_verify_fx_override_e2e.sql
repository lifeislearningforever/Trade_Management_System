-- Debug: verify the open_fx_rate override propagates end-to-end through the
-- real UI -> trade save -> event queue -> worker -> position path (not the
-- shell-direct bypass test). Run AFTER creating one test trade via the UI
-- with portfolio=UOBS_IB_AC, security=Test_Prakash, a manually-overridden
-- open_fx_rate (e.g. 0.5), quantity=10, price=100.
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_verify_fx_override_e2e.sql
-- ---------------------------------------------------------------------------

-- ── 1. Confirm the trade itself stored the right values ─────────────────────
SELECT trade_id, portfolio_short_name, security_label, trade_type, quantity, price,
       currency_code AS security_currency, portfolio_currency,
       open_fx_rate, gross_amount_fc, gross_amount_lc, total_amount_lc, status
FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
ORDER BY created_at DESC
LIMIT 5;

-- ── 2. Confirm the SETTLEMENT event was queued and completed with correct data
SELECT event_id, trade_id, event_type, status, error_message, event_data,
       created_at, processing_started_at, processed_at
FROM gmp_cis.cis_trade_event_queue
WHERE trade_id IN (
    SELECT trade_id FROM gmp_cis.cis_trade
    WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
)
ORDER BY created_at DESC
LIMIT 10;

-- ── 3. The actual result: cis_trade_position (versioned) ─────────────────────
SELECT position_id, position_basis, position_date, is_latest,
       quantity, average_cost_fc, average_cost_lc,
       total_cost_fc, total_cost_lc, trade_id
FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
ORDER BY position_basis;

-- ── 4. The golden-copy result: cis_position (what the Positions UI reads) ───
SELECT position_id, position_type, position_date, is_latest,
       quantity, average_cost_fc, average_cost_lc,
       cost_fc, cost_lc, market_value_fc, market_value_lc
FROM gmp_cis.cis_position
WHERE portfolio = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
ORDER BY position_type;

-- ── Expected result (for qty=10, price=100, override fx=0.5, gross_amount_lc=500) ──
-- average_cost_fc = 100.0
-- average_cost_lc = 50.0   (= gross_amount_lc 500 / quantity 10 — NOT the market rate)
-- total_cost_fc    = 1000.0
-- total_cost_lc    = 500.0
