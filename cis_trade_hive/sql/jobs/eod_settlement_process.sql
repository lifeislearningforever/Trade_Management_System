-- ============================================================================
-- EOD Settlement Processing Job - Impala SQL Script
-- ============================================================================
-- Description: Processes pending settlements and creates position records.
--              This script is called by eod_settlement_process.sh
--
-- Input Parameters (via shell variable substitution):
--   ${SETTLE_DATE}     - Settlement date to process (YYYY-MM-DD), default: today
--   ${BATCH_ID}        - Unique batch ID for this run
--   ${RUN_BY}          - User/system running the job
--   ${PROCESSING_DATE} - Processing date (YYYYMMDD)
--
-- Usage:
--   impala-shell -i <host>:21050 -d gmp_cis \
--     --var=SETTLE_DATE=2026-03-06 \
--     --var=BATCH_ID=1709740800000 \
--     --var=RUN_BY=SYSTEM \
--     --var=PROCESSING_DATE=20260306 \
--     -f eod_settlement_process.sql
--
-- Created: 2026-03-06
-- Version: 1.0
-- ============================================================================

-- Refresh metadata to ensure we have latest table state
INVALIDATE METADATA gmp_cis.cis_settlement_queue;
INVALIDATE METADATA gmp_cis.cis_trade_position;


-- ============================================================================
-- STEP 1: Create batch record
-- ============================================================================

INSERT INTO gmp_cis.cis_eod_settlement_batch
(batch_id, batch_date, processing_date, status, total_pending, processed_count,
 failed_count, skipped_count, started_at, run_by)
SELECT
    ${var:BATCH_ID},
    '${var:SETTLE_DATE}',
    '${var:PROCESSING_DATE}',
    'STARTED',
    COUNT(*),
    0,
    0,
    0,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    '${var:RUN_BY}'
FROM gmp_cis.cis_settlement_queue
WHERE settle_date <= '${var:SETTLE_DATE}'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 2: Mark pending records as PROCESSING
-- ============================================================================

UPDATE gmp_cis.cis_settlement_queue
SET status = 'PROCESSING',
    updated_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE settle_date <= '${var:SETTLE_DATE}'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 3: Get current positions for portfolio+security combinations
-- ============================================================================
-- This is used to calculate the new AVP when processing each settlement

-- Create temp view of latest positions
DROP VIEW IF EXISTS gmp_cis.v_current_positions_temp;

CREATE VIEW gmp_cis.v_current_positions_temp AS
SELECT
    p.portfolio_short_name,
    p.security_label,
    p.position_id,
    p.quantity,
    p.average_cost,
    p.total_cost,
    p.realized_pnl,
    p.status
FROM gmp_cis.cis_trade_position p
INNER JOIN (
    SELECT portfolio_short_name, security_label, MAX(version_id) as max_version
    FROM gmp_cis.cis_trade_position
    GROUP BY portfolio_short_name, security_label
) latest
ON p.portfolio_short_name = latest.portfolio_short_name
   AND p.security_label = latest.security_label
   AND p.version_id = latest.max_version;


-- ============================================================================
-- STEP 4: Process settlements and create position records
-- ============================================================================
-- This inserts new position versions for each settlement

-- Generate unique version IDs using timestamp + row number
INSERT INTO gmp_cis.cis_trade_position
(
    version_id,
    position_id,
    position_date,
    portfolio_short_name,
    security_label,
    quantity,
    average_cost,
    total_cost,
    realized_pnl,
    current_price,
    market_value,
    unrealized_pnl,
    trade_id,
    trade_type,
    lots_held,
    custodian,
    sub_custodian,
    security_currency,
    portfolio_currency,
    fx_rate,
    average_cost_base,
    total_cost_base,
    realized_pnl_base,
    status,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    -- Generate unique version_id: batch_id * 1000 + row_number
    ${var:BATCH_ID} * 1000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS version_id,

    -- Use existing position_id or generate new one
    COALESCE(cp.position_id, ${var:BATCH_ID} * 100 + ROW_NUMBER() OVER (ORDER BY sq.queue_id)) AS position_id,

    -- Position date = settle date
    sq.settle_date AS position_date,

    -- Portfolio and Security
    sq.portfolio_id AS portfolio_short_name,
    sq.security_id AS security_label,

    -- Calculate new quantity
    CASE
        WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.quantity, 0) + sq.quantity
        WHEN sq.trade_type = 'SELL' THEN COALESCE(cp.quantity, 0) - sq.quantity
        ELSE COALESCE(cp.quantity, 0)
    END AS quantity,

    -- Calculate new average cost (AVP formula)
    CASE
        WHEN sq.trade_type = 'BUY' THEN
            -- BUY: new_avg = (old_total_cost + new_cost) / new_qty
            CASE
                WHEN (COALESCE(cp.quantity, 0) + sq.quantity) > 0 THEN
                    (COALESCE(cp.total_cost, 0) + (sq.quantity * sq.price) + COALESCE(sq.charges, 0)) /
                    (COALESCE(cp.quantity, 0) + sq.quantity)
                ELSE 0
            END
        WHEN sq.trade_type = 'SELL' THEN
            -- SELL: avg cost unchanged
            COALESCE(cp.average_cost, 0)
        ELSE COALESCE(cp.average_cost, 0)
    END AS average_cost,

    -- Calculate new total cost
    CASE
        WHEN sq.trade_type = 'BUY' THEN
            COALESCE(cp.total_cost, 0) + (sq.quantity * sq.price) + COALESCE(sq.charges, 0)
        WHEN sq.trade_type = 'SELL' THEN
            -- Reduce total cost proportionally
            CASE
                WHEN COALESCE(cp.quantity, 0) > 0 THEN
                    COALESCE(cp.total_cost, 0) * (COALESCE(cp.quantity, 0) - sq.quantity) / COALESCE(cp.quantity, 0)
                ELSE 0
            END
        ELSE COALESCE(cp.total_cost, 0)
    END AS total_cost,

    -- Calculate realized P&L (only for SELL)
    CASE
        WHEN sq.trade_type = 'SELL' THEN
            COALESCE(cp.realized_pnl, 0) + (sq.quantity * (sq.price - COALESCE(cp.average_cost, 0)))
        ELSE COALESCE(cp.realized_pnl, 0)
    END AS realized_pnl,

    -- Market data (to be updated later)
    sq.price AS current_price,
    NULL AS market_value,
    NULL AS unrealized_pnl,

    -- Trade reference
    sq.trade_id,
    sq.trade_type,

    -- Lots (increment for BUY, keep for SELL)
    CASE
        WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.lots_held, 0) + 1
        ELSE COALESCE(cp.lots_held, 0)
    END AS lots_held,

    -- Custodian info
    sq.custodian,
    sq.sub_custodian,

    -- Multi-currency
    sq.security_currency,
    sq.portfolio_currency,
    NULL AS fx_rate,
    NULL AS average_cost_base,
    NULL AS total_cost_base,
    NULL AS realized_pnl_base,

    -- Status
    CASE
        WHEN sq.trade_type = 'BUY' THEN 'OPEN'
        WHEN sq.trade_type = 'SELL' AND (COALESCE(cp.quantity, 0) - sq.quantity) <= 0 THEN 'CLOSED'
        ELSE 'OPEN'
    END AS status,

    TRUE AS is_active,

    -- Audit
    '${var:RUN_BY}' AS created_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS created_at,
    '${var:RUN_BY}' AS updated_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS updated_at

FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN gmp_cis.v_current_positions_temp cp
    ON sq.portfolio_id = cp.portfolio_short_name
    AND sq.security_id = cp.security_label
WHERE sq.settle_date <= '${var:SETTLE_DATE}'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 5: Log processed records
-- ============================================================================

INSERT INTO gmp_cis.cis_eod_settlement_log
(log_id, batch_id, queue_id, trade_id, portfolio_id, security_id, trade_type,
 quantity, price, settle_date, status, processed_at)
SELECT
    ${var:BATCH_ID} * 10000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS log_id,
    ${var:BATCH_ID} AS batch_id,
    sq.queue_id,
    sq.trade_id,
    sq.portfolio_id,
    sq.security_id,
    sq.trade_type,
    sq.quantity,
    sq.price,
    sq.settle_date,
    'SUCCESS' AS status,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS processed_at
FROM gmp_cis.cis_settlement_queue sq
WHERE sq.settle_date <= '${var:SETTLE_DATE}'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 6: Mark settlement queue records as COMPLETED
-- ============================================================================

UPDATE gmp_cis.cis_settlement_queue
SET status = 'COMPLETED',
    processed_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    updated_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE settle_date <= '${var:SETTLE_DATE}'
  AND status = 'PROCESSING';


-- ============================================================================
-- STEP 7: Update batch record with final counts
-- ============================================================================

UPDATE gmp_cis.cis_eod_settlement_batch
SET status = 'COMPLETED',
    processed_count = (
        SELECT COUNT(*)
        FROM gmp_cis.cis_eod_settlement_log
        WHERE batch_id = ${var:BATCH_ID} AND status = 'SUCCESS'
    ),
    failed_count = (
        SELECT COUNT(*)
        FROM gmp_cis.cis_eod_settlement_log
        WHERE batch_id = ${var:BATCH_ID} AND status = 'FAILED'
    ),
    completed_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE batch_id = ${var:BATCH_ID};


-- ============================================================================
-- STEP 8: Sync to external position_master table (if exists)
-- ============================================================================

-- Uncomment if position_master external table exists
-- INSERT INTO gmp_cis.position_master
-- SELECT ... FROM gmp_cis.cis_trade_position WHERE ...;


-- ============================================================================
-- STEP 9: Cleanup temp view
-- ============================================================================

DROP VIEW IF EXISTS gmp_cis.v_current_positions_temp;


-- ============================================================================
-- STEP 10: Show summary
-- ============================================================================

SELECT
    batch_id,
    batch_date,
    status,
    total_pending,
    processed_count,
    failed_count,
    started_at,
    completed_at
FROM gmp_cis.cis_eod_settlement_batch
WHERE batch_id = ${var:BATCH_ID};


-- ============================================================================
-- END OF SCRIPT
-- ============================================================================
