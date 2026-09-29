-- Debug: clear out all Test_Prakash / UOBS_IB_AC test data accumulated while
-- debugging the open_fx_rate override propagation bug, so the next test trade
-- starts from a clean slate (no stale historical cost_lc carried forward).
-- Run on server:
--   impala-shell -i <host>:21050 -d gmp_cis -f sql/debug/debug_cleanup_test_prakash_positions.sql
-- ---------------------------------------------------------------------------

-- ── 1. Preview what will be deleted ──────────────────────────────────────────
SELECT 'cis_trade_position' AS tbl, COUNT(*) AS cnt FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
UNION ALL
SELECT 'cis_position', COUNT(*) FROM gmp_cis.cis_position
WHERE portfolio = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
UNION ALL
SELECT 'cis_trade', COUNT(*) FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
UNION ALL
SELECT 'cis_trade_event_queue', COUNT(*) FROM gmp_cis.cis_trade_event_queue
WHERE trade_id IN (
    SELECT trade_id FROM gmp_cis.cis_trade
    WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
)
UNION ALL
SELECT 'cis_position_queue', COUNT(*) FROM gmp_cis.cis_position_queue
WHERE portfolio_id = 'UOBS_IB_AC' AND security_id = 'Test_Prakash';

-- ── 2. Delete, in dependency order ───────────────────────────────────────────
DELETE FROM gmp_cis.cis_position_queue
WHERE portfolio_id = 'UOBS_IB_AC' AND security_id = 'Test_Prakash';

DELETE FROM gmp_cis.cis_trade_event_queue
WHERE trade_id IN (
    SELECT trade_id FROM gmp_cis.cis_trade
    WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
);

DELETE FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash';

DELETE FROM gmp_cis.cis_position
WHERE portfolio = 'UOBS_IB_AC' AND security_label = 'Test_Prakash';

DELETE FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash';

-- ── 3. Verify all clear ───────────────────────────────────────────────────────
SELECT 'cis_trade_position' AS tbl, COUNT(*) AS cnt FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
UNION ALL
SELECT 'cis_position', COUNT(*) FROM gmp_cis.cis_position
WHERE portfolio = 'UOBS_IB_AC' AND security_label = 'Test_Prakash'
UNION ALL
SELECT 'cis_trade', COUNT(*) FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'UOBS_IB_AC' AND security_label = 'Test_Prakash';
-- Expect all zero.
