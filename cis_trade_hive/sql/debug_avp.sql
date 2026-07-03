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
