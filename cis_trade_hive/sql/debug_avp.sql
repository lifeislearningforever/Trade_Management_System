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
-- Q3b: ALL trades including cancelled — to see full picture of what existed
-- -----------------------------------------------------------------------------
SELECT trade_id, deal_number, trade_type, quantity, price,
       trade_date, settle_date, status, is_deleted, updated_at
FROM gmp_cis.cis_trade
WHERE portfolio_short_name = 'Test_Prakash_ccy'
  AND security_label = 'AAPL'
  AND (trade_date >= '2026-03-02' OR settle_date >= '2026-03-02')
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
-- Q7: Portfolio list — all portfolios (mirrors portfolio list page query)
-- Replace status/currency filters as needed; remove WHERE clause to see all.
-- -----------------------------------------------------------------------------
SELECT name, description, currency, manager, portfolio_client,
       settlement_ccy, status, revaluation_status, is_active,
       src_system, account_group, portfolio_group, report_group, entity_group,
       entity, business_line, investment_type, branch_code,
       desk_head, portfolio_owner, country,
       created_at, updated_at, updated_by
FROM gmp_cis.cis_portfolio
WHERE 1=1
  -- AND status = 'SETTLED'          -- uncomment to filter active/settled only
  -- AND currency = 'USD'            -- uncomment to filter by base currency
  -- AND LOWER(name) LIKE '%test%'   -- uncomment to search by name
ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, name
LIMIT 1000
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


-- -----------------------------------------------------------------------------
-- Q8: Cash flow list — mirrors cash flow list page (check cash_flow_number is set)
-- -----------------------------------------------------------------------------
SELECT cash_flow_id, cash_flow_number, portfolio_short_name, security_label,
       cash_flow_type, send_receive, value_date, payment_date,
       local_ccy, local_ccy_amt, foreign_ccy, foreign_ccy_amt,
       status, src_system, ca_number,
       is_deleted, created_by, created_at, updated_at
FROM gmp_cis.cis_cash_flow
WHERE (is_deleted = false OR is_deleted IS NULL)
  -- AND portfolio_short_name = 'UOBS_VMS_AC'   -- uncomment to filter by portfolio
ORDER BY created_at DESC
LIMIT 50
;


-- -----------------------------------------------------------------------------
-- Q8b: Cash flow detail by cash_flow_id — mirrors get_by_id query
-- Replace 123 with the actual cash_flow_id from the URL.
-- -----------------------------------------------------------------------------
SELECT cash_flow_id, cash_flow_number, portfolio_short_name, security_label,
       cash_flow_type, send_receive, value_date, status,
       src_system, ca_number, created_at, updated_at
FROM gmp_cis.cis_cash_flow
WHERE cash_flow_id = 123
;


-- =============================================================================
-- CA QUEUE DEBUG / MANUAL OPERATIONS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q9: Check if a CA has a queue entry
-- Replace ca_id value as needed.
-- -----------------------------------------------------------------------------
SELECT queue_id, ca_id, ca_number, ca_type, security_name,
       ex_date, record_date, payment_date,
       price, currency, status, retry_count, error_message,
       cash_flows_created, total_amount, processed_at, created_at
FROM gmp_cis.cis_ca_cash_flow_queue
WHERE ca_id = 1780908537778
;


-- -----------------------------------------------------------------------------
-- Q10: Check cis_position for stale CA_* position_type rows (should be none)
-- -----------------------------------------------------------------------------
SELECT position_type, COUNT(*) AS cnt,
       MIN(position_date) AS earliest, MAX(position_date) AS latest
FROM gmp_cis.cis_position
WHERE position_type NOT IN ('INT', 'EOD', 'SOD', 'CORR')
  AND position_type IS NOT NULL
GROUP BY position_type
ORDER BY position_type
;


-- -----------------------------------------------------------------------------
-- Q11: Manually insert a queue entry for a CA that was never queued.
-- Use when: CA is VALIDATED but cis_ca_cash_flow_queue has no row for it
-- and --correction fails with "No queue entries found".
--
-- Replace all placeholder values before running.
-- After insert, run: python manage.py process_corporate_actions --ca-id <ca_id>
-- -----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_ca_cash_flow_queue (
    queue_id,
    ca_id,
    ca_number,
    ca_type,
    security_name,
    ex_date,
    record_date,
    payment_date,
    price,
    currency,
    status,
    retry_count,
    cash_flows_created,
    total_amount,
    created_at,
    created_by
) VALUES (
    CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT),  -- queue_id  (auto timestamp)
    1780908537778,                             -- ca_id
    'CA-20260608-00002',                       -- ca_number
    'STOCK_SPLIT',                             -- ca_type   (e.g. STOCK_SPLIT, DIVIDEND, CASH_DIVIDEND)
    'UQ-UOB-102 CH',                          -- security_name
    '2026-02-27',                              -- ex_date
    '2026-02-27',                              -- record_date
    '2026-03-02',                              -- payment_date
    2.000000,                                  -- price (split ratio / dividend rate)
    'GBP',                                     -- currency
    'PENDING',                                 -- status
    CAST(0 AS BIGINT),                         -- retry_count
    CAST(0 AS BIGINT),                         -- cash_flows_created
    NULL,                                      -- total_amount
    CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT),  -- created_at
    'SYSTEM'                                   -- created_by
)
;
