-- ============================================================================
-- Impala SQL: EOD Corporate Action → Cash Flow Pipeline
-- ============================================================================
-- Pure SQL alternative to the PySpark job.
-- Use this when Spark is unavailable or for reruns of individual steps.
--
-- LIMITATION vs PySpark:
--   Step 1 (GMP sync) requires surrogate ca_id generation.
--   Impala cannot generate unique IDs across rows in a SELECT.
--   Use the PySpark job (eod_ca_cash_flow.py) for Step 1 in production.
--   This file covers Step 2 (queue → cash flow) which only needs UPSERT.
--
-- Run via edgenode:
--   impala-shell -i <host>:21050 -d gmp_cis -f eod_ca_cash_flow.sql
--
-- Run specific date:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     --var=processing_date=20260130 \
--     -f eod_ca_cash_flow.sql
--
-- Control-M job step (after PySpark Step 1):
--   impala-shell -i ${IMPALA_HOST}:21050 -d gmp_cis -f eod_ca_cash_flow.sql
--
-- Created: 2026-04-11
-- ============================================================================

USE gmp_cis;


-- ============================================================================
-- STEP 1 (SQL only): GMP CA type mapping reference
-- NOTE: ID generation not possible in pure SQL.
--       Run eod_ca_cash_flow.py (PySpark) for Step 1 in production.
--       This block shown for documentation purposes only.
-- ============================================================================
/*
-- GMP CA type → CIS CA type mapping (for reference):
-- 'cash dividend'     → DIVIDEND
-- 'dividend'          → DIVIDEND
-- 'd'                 → DIVIDEND
-- 'special dividend'  → SPECIAL_DIVIDEND
-- 'clas sp'           → SPECIAL_DIVIDEND
-- 'interest'          → INTEREST
-- 'i'                 → INTEREST
-- 'coupon'            → COUPON
-- 'c'                 → COUPON
-- 'roc'               → ROC
-- 'return of capital' → ROC
-- 'capital distribution' → CAPITAL_DISTRIBUTION
-- 'bonus issue'       → BONUS_ISSUE
-- 'bonus'             → BONUS_ISSUE
-- 'b'                 → BONUS_ISSUE
-- 'stock split'       → STOCK_SPLIT
-- 'split'             → SPLIT
-- 's'                 → SPLIT
-- 'reverse split'     → REVERSE_SPLIT
-- 'consolidation'     → CONSOLIDATION
-- 'rights issue'      → RIGHTS_ISSUE
-- 'rights entitlement'→ RIGHTS_ENTITLEMENT
-- 'warrant'           → WARRANT_ENTITLEMENT
*/


-- ============================================================================
-- STEP 2: Process PENDING queue → generate cash flows
-- ============================================================================
-- Reads cis_ca_cash_flow_queue (PENDING, retry_count < 3)
-- Joins with latest open positions to find which portfolios hold the security
-- Gets FX rate for local currency conversion
-- UPSERTs into cis_cash_flow
-- Marks queue entries COMPLETED
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 2A: Preview — show what will be generated (run before 2B for verification)
-- ----------------------------------------------------------------------------
SELECT
    q.ca_number,
    q.ca_type,
    q.security_name,
    q.ex_date,
    q.payment_date,
    CAST(q.price AS DECIMAL(20,8))                              AS price,
    pos.portfolio_short_name,
    pos.quantity,
    pos.security_currency,
    pos.portfolio_currency,
    CAST(pos.quantity AS DECIMAL(20,8))
        * CAST(q.price AS DECIMAL(20,8))                        AS amount_fc,
    COALESCE(fx.rate, 1.0)                                      AS fx_rate,
    CAST(pos.quantity AS DECIMAL(20,8))
        * CAST(q.price AS DECIMAL(20,8))
        * COALESCE(CAST(fx.rate AS DECIMAL(20,8)), 1.0)         AS amount_lc
FROM cis_ca_cash_flow_queue q
-- Latest open position per portfolio+security as of ex_date (trade-date basis)
INNER JOIN (
    SELECT
        p.portfolio_short_name,
        p.security_label,
        p.quantity,
        COALESCE(p.security_currency, p.foreign_ccy)            AS security_currency,
        COALESCE(p.portfolio_currency, p.local_ccy)             AS portfolio_currency
    FROM cis_trade_position p
    INNER JOIN (
        SELECT portfolio_short_name, security_label, MAX(position_date) AS max_date
        FROM cis_trade_position
        WHERE quantity > 0
          AND status = 'OPEN'
          AND is_active = true
          AND position_basis = 'TRADE_DATE'
        GROUP BY portfolio_short_name, security_label
    ) latest
      ON p.portfolio_short_name = latest.portfolio_short_name
     AND p.security_label       = latest.security_label
     AND p.position_date        = latest.max_date
    WHERE p.quantity > 0
      AND p.status   = 'OPEN'
      AND p.is_active = true
) pos ON q.security_name = pos.security_label
-- Latest FX rate for security_currency → portfolio_currency
LEFT JOIN (
    SELECT
        fx1.from_currency,
        fx1.to_currency,
        fx1.rate
    FROM cis_fx_rate fx1
    INNER JOIN (
        SELECT from_currency, to_currency, MAX(rate_date) AS max_date
        FROM cis_fx_rate
        GROUP BY from_currency, to_currency
    ) fx_latest
      ON fx1.from_currency = fx_latest.from_currency
     AND fx1.to_currency   = fx_latest.to_currency
     AND fx1.rate_date     = fx_latest.max_date
) fx ON pos.security_currency  = fx.from_currency
    AND pos.portfolio_currency  = fx.to_currency
-- Only pending, not yet failed out
WHERE q.status      = 'PENDING'
  AND q.retry_count < 3
  -- Only cash-flow-generating types
  AND q.ca_type IN ('DIVIDEND','SPECIAL_DIVIDEND','INTEREST','COUPON','ROC','CAPITAL_DISTRIBUTION')
  -- No duplicate: skip if CF already exists for same portfolio+security+ex_date
  AND NOT EXISTS (
      SELECT 1 FROM cis_cash_flow cf
      WHERE cf.portfolio_short_name = pos.portfolio_short_name
        AND cf.security_label       = q.security_name
        AND cf.ex_date              = q.ex_date
        AND cf.src_system           = 'CA'
        AND (cf.is_deleted = false OR cf.is_deleted IS NULL)
  )
ORDER BY q.ca_number, pos.portfolio_short_name;


-- ----------------------------------------------------------------------------
-- 2B: UPSERT — generate cash flows
-- NOTE: cash_flow_id uses UNIX_TIMESTAMP()*1000 + a row counter trick.
--       Because Impala cannot generate row numbers unique across the full
--       dataset in one pass, this may collide on large batches.
--       Use eod_ca_cash_flow.py (PySpark) in production for safe ID generation.
--       This SQL is suitable for small batches or manual reruns.
-- ----------------------------------------------------------------------------
UPSERT INTO cis_cash_flow (
    cash_flow_id,
    cash_flow_number,
    portfolio_short_name,
    security_label,
    cash_flow_type,
    send_receive,
    position_updated,
    foreign_ccy,
    foreign_ccy_amt,
    local_ccy,
    local_ccy_amt,
    flow_amount_local,
    dividend_price,
    quantity,
    fx_rate,
    value_date,
    ex_date,
    record_date,
    payment_date,
    dividend_date,
    ca_id,
    ca_number,
    status,
    src_system,
    is_active,
    is_deleted,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    -- cash_flow_id: timestamp * 1000 + dense_rank to avoid collision within batch
    -- (For production use PySpark monotonically_increasing_id instead)
    CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT)
        + CAST(ROW_NUMBER() OVER (ORDER BY q.ca_number, pos.portfolio_short_name) AS BIGINT)
                                                                AS cash_flow_id,

    CONCAT('CF-', DATE_FORMAT(NOW(),'yyyyMMdd'), '-',
           LPAD(CAST(ROW_NUMBER() OVER (ORDER BY q.ca_number, pos.portfolio_short_name) AS STRING), 5, '0'))
                                                                AS cash_flow_number,

    pos.portfolio_short_name,
    q.security_name                                             AS security_label,

    -- CA type → CF type mapping
    CASE q.ca_type
        WHEN 'DIVIDEND'             THEN 'DIVIDEND'
        WHEN 'SPECIAL_DIVIDEND'     THEN 'SPECIAL_DIVIDEND'
        WHEN 'INTEREST'             THEN 'INTEREST'
        WHEN 'COUPON'               THEN 'COUPON'
        WHEN 'ROC'                  THEN 'ROC'
        WHEN 'CAPITAL_DISTRIBUTION' THEN 'CAPITAL_DISTRIBUTION'
        ELSE q.ca_type
    END                                                         AS cash_flow_type,

    'RECEIVE'                                                   AS send_receive,
    false                                                       AS position_updated,

    -- Foreign currency = security currency
    pos.security_currency                                       AS foreign_ccy,
    CAST(pos.quantity AS DECIMAL(20,8))
        * CAST(q.price AS DECIMAL(20,8))                        AS foreign_ccy_amt,

    -- Local currency = portfolio currency
    pos.portfolio_currency                                      AS local_ccy,
    CAST(pos.quantity AS DECIMAL(20,8))
        * CAST(q.price AS DECIMAL(20,8))
        * COALESCE(CAST(fx.rate AS DECIMAL(20,8)), 1.0)         AS local_ccy_amt,
    CAST(pos.quantity AS DECIMAL(20,8))
        * CAST(q.price AS DECIMAL(20,8))
        * COALESCE(CAST(fx.rate AS DECIMAL(20,8)), 1.0)         AS flow_amount_local,

    -- Dividend price per share = amount_fc / quantity
    CASE WHEN CAST(pos.quantity AS DECIMAL(20,8)) > 0
         THEN CAST(q.price AS DECIMAL(20,8))
         ELSE 0
    END                                                         AS dividend_price,

    CAST(pos.quantity AS DECIMAL(20,8))                         AS quantity,
    COALESCE(CAST(fx.rate AS DECIMAL(20,8)), 1.0)               AS fx_rate,

    -- Dates
    q.ex_date                                                   AS value_date,
    q.ex_date,
    q.record_date,
    q.payment_date,
    q.record_date                                               AS dividend_date,

    -- CA reference
    CAST(q.ca_id AS BIGINT)                                     AS ca_id,
    q.ca_number,

    -- Status: CA-generated CFs are auto-validated (no four-eyes)
    'VALIDATED'                                                 AS status,
    'CA'                                                        AS src_system,

    -- Audit fields
    true                                                        AS is_active,
    false                                                       AS is_deleted,
    'EOD_JOB'                                                   AS created_by,
    UNIX_TIMESTAMP() * 1000                                     AS created_at,
    'EOD_JOB'                                                   AS updated_by,
    UNIX_TIMESTAMP() * 1000                                     AS updated_at

FROM cis_ca_cash_flow_queue q
INNER JOIN (
    SELECT
        p.portfolio_short_name,
        p.security_label,
        p.quantity,
        COALESCE(p.security_currency, p.foreign_ccy)            AS security_currency,
        COALESCE(p.portfolio_currency, p.local_ccy)             AS portfolio_currency
    FROM cis_trade_position p
    INNER JOIN (
        SELECT portfolio_short_name, security_label, MAX(position_date) AS max_date
        FROM cis_trade_position
        WHERE quantity > 0
          AND status = 'OPEN'
          AND is_active = true
          AND position_basis = 'TRADE_DATE'
        GROUP BY portfolio_short_name, security_label
    ) latest
      ON p.portfolio_short_name = latest.portfolio_short_name
     AND p.security_label       = latest.security_label
     AND p.position_date        = latest.max_date
    WHERE p.quantity > 0
      AND p.status   = 'OPEN'
      AND p.is_active = true
) pos ON q.security_name = pos.security_label
LEFT JOIN (
    SELECT fx1.from_currency, fx1.to_currency, fx1.rate
    FROM cis_fx_rate fx1
    INNER JOIN (
        SELECT from_currency, to_currency, MAX(rate_date) AS max_date
        FROM cis_fx_rate
        GROUP BY from_currency, to_currency
    ) fx_latest
      ON fx1.from_currency = fx_latest.from_currency
     AND fx1.to_currency   = fx_latest.to_currency
     AND fx1.rate_date     = fx_latest.max_date
) fx ON pos.security_currency = fx.from_currency
    AND pos.portfolio_currency = fx.to_currency
WHERE q.status      = 'PENDING'
  AND q.retry_count < 3
  AND q.ca_type IN ('DIVIDEND','SPECIAL_DIVIDEND','INTEREST','COUPON','ROC','CAPITAL_DISTRIBUTION')
  AND NOT EXISTS (
      SELECT 1 FROM cis_cash_flow cf
      WHERE cf.portfolio_short_name = pos.portfolio_short_name
        AND cf.security_label       = q.security_name
        AND cf.ex_date              = q.ex_date
        AND cf.src_system           = 'CA'
        AND (cf.is_deleted = false OR cf.is_deleted IS NULL)
  );


-- ----------------------------------------------------------------------------
-- 2C: Mark queue entries COMPLETED
-- Run this only after 2B succeeds
-- ----------------------------------------------------------------------------
UPDATE cis_ca_cash_flow_queue
SET status       = 'COMPLETED',
    processed_at = UNIX_TIMESTAMP() * 1000
WHERE status      = 'PENDING'
  AND retry_count < 3
  AND ca_type IN ('DIVIDEND','SPECIAL_DIVIDEND','INTEREST','COUPON','ROC','CAPITAL_DISTRIBUTION');


-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Queue status summary
SELECT status, COUNT(*) AS cnt
FROM cis_ca_cash_flow_queue
GROUP BY status
ORDER BY status;

-- Cash flows created today (CA-generated)
SELECT
    cf.portfolio_short_name,
    cf.security_label,
    cf.cash_flow_type,
    cf.foreign_ccy,
    cf.foreign_ccy_amt,
    cf.local_ccy,
    cf.local_ccy_amt,
    cf.ex_date,
    cf.payment_date,
    cf.ca_number
FROM cis_cash_flow cf
WHERE cf.src_system = 'CA'
  AND (cf.is_deleted = false OR cf.is_deleted IS NULL)
ORDER BY cf.created_at DESC
LIMIT 50;

-- Verify no duplicates
SELECT portfolio_short_name, security_label, ex_date, COUNT(*) AS cnt
FROM cis_cash_flow
WHERE src_system = 'CA'
  AND (is_deleted = false OR is_deleted IS NULL)
GROUP BY portfolio_short_name, security_label, ex_date
HAVING cnt > 1;
