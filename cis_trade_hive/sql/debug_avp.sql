-- =============================================================================
-- AVP Debug Queries
-- Added to as debugging progresses — replace 'Test_Prakash_ccy' / 'AAPL'
-- with the portfolio/security under investigation.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1: All live trades for a portfolio/security (what chain recalc sees)
-- -----------------------------------------------------------------------------
SELECT trade_id, deal_number, trade_type, quantity, price,
       trade_date, settle_date, status, is_deleted, updated_at
FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'AAPL'
  AND (is_deleted = false OR is_deleted IS NULL)
ORDER BY trade_date ASC, trade_id ASC
;


-- -----------------------------------------------------------------------------
-- Q2: Authoritative current positions (is_latest = true only)
-- -----------------------------------------------------------------------------
SELECT position_id, trade_id, position_basis, position_date,
       quantity, average_cost_fc, total_cost_fc, is_latest, created_at
FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'AAPL'
  AND is_latest = true
ORDER BY position_basis, position_date
;


-- -----------------------------------------------------------------------------
-- Q3: Exactly what chain recalc reads from cis_trade (mirror the service query)
-- Update from_date and today's date as needed.
-- -----------------------------------------------------------------------------
SELECT trade_id, deal_number, trade_type, quantity, price,
       COALESCE(commission,0) + COALESCE(sec_fee,0) + COALESCE(other_charges,0) AS charges,
       trade_date, settle_date, status, trade_status, is_deleted, updated_at
FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'AAPL'
  AND (trade_date >= '2026-03-02' OR settle_date >= '2026-03-02')
  AND settle_date <= '2026-07-03'
  AND (trade_status IN ('INITIAL','MODIFIED','VALIDATED','SETTLED')
       OR status IN ('INITIAL','MODIFIED','VALIDATED','SETTLED'))
  AND (is_deleted = false OR is_deleted IS NULL)
ORDER BY trade_date ASC, settle_date ASC, trade_id ASC
;


-- -----------------------------------------------------------------------------
-- Q4: All position rows (not just is_latest) — shows full version history
-- -----------------------------------------------------------------------------
SELECT version_id, position_id, trade_id, position_basis, position_date,
       quantity, average_cost_fc, total_cost_fc, is_latest, created_at
FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'Test_Prakash'
ORDER BY position_basis, created_at DESC
;


-- -----------------------------------------------------------------------------
-- Q6: Full position history with realized_pnl — to see SELL impact per version
-- -----------------------------------------------------------------------------
SELECT version_id, trade_id, position_basis, position_date,
       quantity, average_cost_fc, realized_pnl_fc, total_cost_fc,
       is_latest, created_at
FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'Test_Prakash'
ORDER BY position_basis, position_date, created_at DESC
;


-- -----------------------------------------------------------------------------
-- Q5: Position queue — pending/failed items that may still fire chain recalc
-- -----------------------------------------------------------------------------
SELECT queue_id, trade_id, portfolio_id, security_id, trade_type,
       quantity, price, status, error_message, created_at, updated_at
FROM gmp_cis.cis_position_queue
WHERE portfolio_id = 'Test_Prakash_ccy'
ORDER BY created_at DESC
LIMIT 20
;
