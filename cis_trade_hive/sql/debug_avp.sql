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
-- LC/FC POSITION DEBUG (NON-REVAL cost_lc investigation)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q_LC1: Trade vs Position join — shows exactly what was stored in cis_trade
--        (total_amount_lc, gross_amount_lc, open_fx_rate) vs what landed in
--        cis_position (cost_fc, cost_lc, average_cost_fc, average_cost_lc).
--
--        Replace portfolio_short_name / security_label values as needed.
--
--        Key columns to check:
--          t.gross_amount_fc   = qty × price (FC, no charges)  — should equal cost_fc for first BUY
--          t.gross_amount_lc   = gross_fc × fx_rate at entry   — may be stale if user edited LC
--          t.total_amount_lc   = user-entered LC amount (always correct)
--          t.open_fx_rate      = FX rate stored on the trade
--          implied_rate        = total_amount_lc / total_amount_fc (what rate the user implied)
--          p.cost_fc           = position cost in security currency
--          p.cost_lc           = position cost in portfolio currency  ← THIS is what we're checking
--          p.average_cost_fc   = avg cost per unit in FC
--          p.average_cost_lc   = avg cost per unit in LC
-- -----------------------------------------------------------------------------
SELECT
    t.trade_id,
    t.deal_number,
    t.trade_type,
    t.trade_date,
    t.settle_date,
    t.currency_code                                         AS security_ccy,
    pf.currency                                             AS portfolio_ccy,
    pf.revaluation_status,

    -- Trade FC/LC amounts
    t.quantity,
    t.price,
    t.quantity * t.price                                    AS gross_fc_calc,
    t.gross_amount_fc                                       AS gross_amount_fc_stored,
    t.gross_amount_lc                                       AS gross_amount_lc_stored,
    t.total_amount_fc,
    t.total_amount_lc,
    t.open_fx_rate,

    -- Implied FX rate from trade (gross_amount_lc / gross_amount_fc, matching position_service logic)
    CASE
        WHEN t.gross_amount_fc IS NOT NULL AND t.gross_amount_fc != 0
             AND t.gross_amount_lc IS NOT NULL AND t.gross_amount_lc != 0
        THEN t.gross_amount_lc / t.gross_amount_fc
        ELSE NULL
    END                                                     AS implied_fx_rate,

    -- Position result
    p.position_basis,
    p.position_date,
    p.src_system,
    p.cost_fc,
    p.cost_lc,
    p.average_cost_fc,
    p.average_cost_lc,
    p.market_value_fc,
    p.market_value_lc,
    p.processing_timestamp

FROM gmp_cis.cis_trade t
JOIN gmp_cis.cis_portfolio pf
    ON t.portfolio_short_name = pf.name
LEFT JOIN gmp_cis.cis_position p
    ON  p.portfolio      = t.portfolio_short_name
    AND p.security_label = t.security_label
    AND p.src_system     = 'CIS'

WHERE t.portfolio_short_name = 'UOBP INV_CRE_SUB'
  AND t.security_label       = 'Test_Prakash'
  AND (t.is_deleted = false OR t.is_deleted IS NULL)

ORDER BY t.trade_date ASC, t.trade_id ASC, p.position_basis, p.position_date
;


-- -----------------------------------------------------------------------------
-- Q_LC2: FX rate table lookup — what rate the position service would have used
--        for a given currency pair and position date.
--
--        Replace ccy pair and date as needed.
--        spot_rate_d is the direct pair rate (security_ccy → portfolio_ccy).
-- -----------------------------------------------------------------------------
SELECT
    ref_quot_ccy,
    date,
    spot_rate_d
FROM gmp_cis.gmp_cis_sta_dly_fx_rates
WHERE ref_quot_ccy IN ('AOA-SGD', 'SGD-AOA', 'AOA-USD', 'USD-SGD', 'USD-AOA', 'SGD-USD')
  AND date <= '2026-03-02'
ORDER BY ref_quot_ccy, date DESC
LIMIT 30
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


-- =============================================================================
-- EQUITY PRICE CURRENCY DEBUG
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q_EP1: Equity price vs security master — check currency resolution
--        Shows current stored currency_code, what security master has, and
--        what resolved_currency WILL BE after next sync run.
--
--        Replace '%YNSMK%' with the security name you are investigating.
--        resolved_currency = 'MISSING' means security is not in master yet.
-- -----------------------------------------------------------------------------
SELECT
    ep.currency_code,
    ep.security_label,
    ep.isin,
    ep.price_date,
    ep.main_closing_price,
    ep.src_system,
    ep.is_active,
    s.security_name        AS sec_name_match,
    s.currency_code        AS sec_currency_code,
    COALESCE(
        CASE WHEN ep.currency_code IS NOT NULL AND TRIM(ep.currency_code) != ''
             THEN ep.currency_code ELSE NULL END,
        s.currency_code,
        'MISSING'
    )                      AS resolved_currency
FROM gmp_cis.cis_equity_price ep
LEFT JOIN gmp_cis.cis_security_kudu s
    ON ep.security_label = s.security_name
WHERE ep.security_label LIKE '%YNSMK%'
  AND (ep.is_active = true OR ep.is_active IS NULL)
ORDER BY ep.security_label, ep.price_date DESC
;


-- -----------------------------------------------------------------------------
-- Q_EP2: Security master name lookup — confirm exact security_name stored
--        so the equity price join will match correctly.
--
--        If sec_name_match is NULL in Q_EP1, run this to find the correct name.
--        Replace '%YNSMK%' with your security search term.
-- -----------------------------------------------------------------------------
SELECT
    security_name,
    security_description,
    currency_code,
    isin,
    src_system
FROM gmp_cis.cis_security_kudu
WHERE UPPER(security_name) LIKE '%YNSMK%'
   OR UPPER(security_description) LIKE '%YNSMK%'
ORDER BY security_name
;


-- -----------------------------------------------------------------------------
-- Q_EP3: Manual UPSERT — load equity price from GMP staging into cis_equity_price
--        with correct currency_code enriched from cis_security_kudu.
--
--        Use this when:
--          - cis_equity_price has blank currency_code (staging SQL joined wrong column)
--          - You want to fix it immediately without waiting for next PySpark sync
--
--        Source: gmp_cis_sta_dly_equity_prices (GMP staging)
--                joined to cis_security_kudu on security_name = security full name
--
--        Steps:
--          1. Run Q_EP2 to confirm the correct currency_code and security_name
--          2. Replace processing_date and security names below
--          3. Run — UPSERT will update existing blank-currency rows by PK match
--
--        Replace:
--          '20260302'             → target processing_date (YYYYMMDD)
--          'YNSMK 7 1/2 PERP'    → actual security name(s) from GMP staging
-- -----------------------------------------------------------------------------
UPSERT INTO gmp_cis.cis_equity_price (
    currency_code,
    security_label,
    price_date,
    isin,
    main_closing_price,
    price_timestamp,
    src_system,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    COALESCE(s.currency_code, '')                       AS currency_code,
    eq.security                                         AS security_label,
    FROM_UNIXTIME(
        UNIX_TIMESTAMP(CAST(eq.`date` AS STRING), 'yyyyMMdd'),
        'yyyy-MM-dd'
    )                                                   AS price_date,
    seu.isin                                            AS isin,
    CAST(eq.main_closing_price AS DECIMAL(18,6))        AS main_closing_price,
    FROM_UNIXTIME(UNIX_TIMESTAMP())                     AS price_timestamp,
    'GMP'                                               AS src_system,
    TRUE                                                AS is_active,
    'MANUAL_FIX'                                        AS created_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())                     AS created_at,
    'MANUAL_FIX'                                        AS updated_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())                     AS updated_at
FROM gmp_cis.gmp_cis_sta_dly_equity_prices eq
LEFT JOIN gmp_cis.gmp_cis_sta_dly_security seu
    ON  eq.security          = seu.security_label
    AND eq.processing_date   = seu.processing_date   -- prevent fan-out across dates
LEFT JOIN gmp_cis.cis_security_kudu s
    ON eq.security = s.security_name                 -- join on full name to get currency
WHERE eq.processing_date = '20260302'
  AND eq.security NOT LIKE '%LOG DEL%'
  AND eq.security IN ('YNSMK 7 1/2 PERP', 'YNSMK 7.5 050673')
;


-- =============================================================================
-- Settlement Queue Debug Queries (2026-03-02)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q_SQ1: All trades with settle_date = 2026-03-02 and their queue status
--        Use this to identify which trades are missing from the settlement queue
-- -----------------------------------------------------------------------------
SELECT
    t.trade_id,
    t.trade_type,
    t.deal_number,
    t.portfolio_short_name,
    t.security_label,
    t.status          AS trade_status,
    t.quantity,
    t.price,
    t.settle_date,
    q.queue_id,
    q.status          AS queue_status
FROM gmp_cis.cis_trade t
LEFT JOIN gmp_cis.cis_settlement_queue q
    ON q.trade_id = t.trade_id
   AND q.position_basis = 'SETTLED'
WHERE t.settle_date = '2026-03-02'
  AND t.trade_type IN ('BUY', 'SELL')
  AND (t.is_deleted = false OR t.is_deleted IS NULL)
ORDER BY t.status, t.portfolio_short_name, t.trade_id
;


-- -----------------------------------------------------------------------------
-- Q_SQ2: Trades missing from settlement queue (excludes CANCELLED)
--        These are the ones --backfill-queue will insert
-- -----------------------------------------------------------------------------
SELECT
    t.trade_id,
    t.trade_type,
    t.deal_number,
    t.portfolio_short_name,
    t.security_label,
    t.status,
    t.quantity,
    t.price,
    t.settle_date
FROM gmp_cis.cis_trade t
WHERE t.trade_type IN ('BUY', 'SELL')
  AND t.status IN ('SETTLED', 'VALIDATED')
  AND t.settle_date = '2026-03-02'
  AND (t.is_deleted = false OR t.is_deleted IS NULL)
  AND NOT EXISTS (
      SELECT 1 FROM gmp_cis.cis_settlement_queue q
      WHERE q.trade_id      = t.trade_id
        AND q.position_basis = 'SETTLED'
  )
ORDER BY t.portfolio_short_name, t.trade_id
;


-- -----------------------------------------------------------------------------
-- Q_SQ3: Settlement queue entries for 2026-03-02 (all statuses)
-- -----------------------------------------------------------------------------
SELECT
    q.queue_id,
    q.trade_id,
    q.portfolio_id,
    q.security_id,
    q.trade_type,
    q.quantity,
    q.price,
    q.settle_date,
    q.status,
    q.queued_at,
    q.processed_at
FROM gmp_cis.cis_settlement_queue q
WHERE q.settle_date = '2026-03-02'
ORDER BY q.status, q.queued_at
;


-- -----------------------------------------------------------------------------
-- Q_SQ4: Cancelled trades for 2026-03-02 — confirm these are excluded
-- -----------------------------------------------------------------------------
SELECT
    t.trade_id,
    t.trade_type,
    t.deal_number,
    t.portfolio_short_name,
    t.security_label,
    t.status,
    t.settle_date
FROM gmp_cis.cis_trade t
WHERE t.settle_date = '2026-03-02'
  AND t.status = 'CANCELLED'
  AND (t.is_deleted = false OR t.is_deleted IS NULL)
ORDER BY t.portfolio_short_name
;
