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
-- Target Table Types (from DDL):
--   cis_eod_settlement_batch:
--     batch_id BIGINT, batch_date STRING, processing_date STRING, status STRING,
--     total_pending INT, processed_count INT, failed_count INT, skipped_count INT,
--     started_at STRING, completed_at STRING, duration_seconds INT, error_summary STRING,
--     run_by STRING
--
--   cis_trade_position:
--     version_id BIGINT, position_id BIGINT, position_date STRING,
--     portfolio_short_name STRING, security_label STRING,
--     quantity DECIMAL(20,8), average_cost DECIMAL(20,8), total_cost DECIMAL(20,8),
--     realized_pnl DECIMAL(20,8), current_price DECIMAL(20,8), market_value DECIMAL(20,8),
--     unrealized_pnl DECIMAL(20,8), trade_id BIGINT, trade_type STRING,
--     lots_held INT, custodian STRING, sub_custodian STRING,
--     security_currency STRING, portfolio_currency STRING, fx_rate DECIMAL(20,8),
--     average_cost_base DECIMAL(20,8), total_cost_base DECIMAL(20,8),
--     realized_pnl_base DECIMAL(20,8), status STRING, is_active BOOLEAN,
--     created_by STRING, created_at STRING, updated_by STRING, updated_at STRING,
--     is_latest BOOLEAN
--
--   cis_eod_settlement_log:
--     log_id BIGINT, batch_id BIGINT, queue_id BIGINT, trade_id BIGINT,
--     portfolio_id STRING, security_id STRING, trade_type STRING,
--     quantity DECIMAL(20,8), price DECIMAL(20,8), settle_date STRING,
--     status STRING, error_message STRING, position_id BIGINT, version_id BIGINT,
--     average_cost DECIMAL(20,8), total_cost DECIMAL(20,8), realized_pnl DECIMAL(20,8),
--     processed_at STRING, duration_ms INT
--
-- Created: 2026-03-06
-- Updated: 2026-03-11 (Type safety fixes)
-- Version: 1.1
-- ============================================================================

-- Refresh metadata to ensure we have latest table state
INVALIDATE METADATA gmp_cis.cis_settlement_queue;
INVALIDATE METADATA gmp_cis.cis_trade_position;


-- ============================================================================
-- STEP 1: Create batch record
-- ============================================================================
-- Target: cis_eod_settlement_batch
-- Types: batch_id BIGINT, batch_date STRING, processing_date STRING, status STRING,
--        total_pending INT, processed_count INT, failed_count INT, skipped_count INT,
--        started_at STRING, run_by STRING

INSERT INTO gmp_cis.cis_eod_settlement_batch
(batch_id, batch_date, processing_date, status, total_pending, processed_count,
 failed_count, skipped_count, started_at, run_by)
SELECT
    CAST(${var:BATCH_ID} AS BIGINT) AS batch_id,
    CAST('${var:SETTLE_DATE}' AS STRING) AS batch_date,
    CAST('${var:PROCESSING_DATE}' AS STRING) AS processing_date,
    CAST('STARTED' AS STRING) AS status,
    CAST(COUNT(*) AS INT) AS total_pending,
    CAST(0 AS INT) AS processed_count,
    CAST(0 AS INT) AS failed_count,
    CAST(0 AS INT) AS skipped_count,
    CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS STRING) AS started_at,
    CAST('${var:RUN_BY}' AS STRING) AS run_by
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

-- Create temp view of latest positions (is_latest=true or highest version_id)
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
    p.lots_held,
    p.status
FROM gmp_cis.cis_trade_position p
WHERE (p.is_latest = true OR p.is_latest IS NULL)
  AND p.version_id = (
      SELECT MAX(version_id)
      FROM gmp_cis.cis_trade_position p2
      WHERE p2.portfolio_short_name = p.portfolio_short_name
        AND p2.security_label = p.security_label
        AND (p2.is_latest = true OR p2.is_latest IS NULL)
  );


-- ============================================================================
-- STEP 4: Mark old position versions as is_latest=false
-- ============================================================================
-- Before inserting new positions, mark existing positions for these
-- portfolio+security combinations as not latest

UPDATE gmp_cis.cis_trade_position
SET is_latest = false,
    updated_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE (portfolio_short_name, security_label) IN (
    SELECT DISTINCT portfolio_id, security_id
    FROM gmp_cis.cis_settlement_queue
    WHERE settle_date <= '${var:SETTLE_DATE}'
      AND status = 'PROCESSING'
)
AND (is_latest = true OR is_latest IS NULL);


-- ============================================================================
-- STEP 5: Process settlements and create position records
-- ============================================================================
-- Target: cis_trade_position
-- All values must be properly CAST to match table column types

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
    is_latest,
    created_by,
    created_at,
    updated_by,
    updated_at
)
SELECT
    -- version_id: BIGINT - Generate unique version_id
    CAST(${var:BATCH_ID} * 1000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS BIGINT) AS version_id,

    -- position_id: BIGINT - Use existing or generate new
    CAST(COALESCE(cp.position_id, ${var:BATCH_ID} * 100 + ROW_NUMBER() OVER (ORDER BY sq.queue_id)) AS BIGINT) AS position_id,

    -- position_date: STRING
    CAST(sq.settle_date AS STRING) AS position_date,

    -- portfolio_short_name: STRING
    CAST(sq.portfolio_id AS STRING) AS portfolio_short_name,

    -- security_label: STRING
    CAST(sq.security_id AS STRING) AS security_label,

    -- quantity: DECIMAL(20,8)
    CAST(
        CASE
            WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity
            WHEN sq.trade_type = 'SELL' THEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity
            ELSE COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8)))
        END
    AS DECIMAL(20,8)) AS quantity,

    -- average_cost: DECIMAL(20,8) - AVP formula
    CAST(
        CASE
            WHEN sq.trade_type = 'BUY' THEN
                CASE
                    WHEN (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity) > CAST(0 AS DECIMAL(20,8)) THEN
                        (COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * sq.price) + COALESCE(sq.charges, CAST(0 AS DECIMAL(20,8)))) /
                        (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity)
                    ELSE CAST(0 AS DECIMAL(20,8))
                END
            WHEN sq.trade_type = 'SELL' THEN
                COALESCE(cp.average_cost, CAST(0 AS DECIMAL(20,8)))
            ELSE COALESCE(cp.average_cost, CAST(0 AS DECIMAL(20,8)))
        END
    AS DECIMAL(20,8)) AS average_cost,

    -- total_cost: DECIMAL(20,8)
    CAST(
        CASE
            WHEN sq.trade_type = 'BUY' THEN
                COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * sq.price) + COALESCE(sq.charges, CAST(0 AS DECIMAL(20,8)))
            WHEN sq.trade_type = 'SELL' THEN
                CASE
                    WHEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) > CAST(0 AS DECIMAL(20,8)) THEN
                        COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) * (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity) / cp.quantity
                    ELSE CAST(0 AS DECIMAL(20,8))
                END
            ELSE COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8)))
        END
    AS DECIMAL(20,8)) AS total_cost,

    -- realized_pnl: DECIMAL(20,8)
    CAST(
        CASE
            WHEN sq.trade_type = 'SELL' THEN
                COALESCE(cp.realized_pnl, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * (sq.price - COALESCE(cp.average_cost, CAST(0 AS DECIMAL(20,8)))))
            ELSE COALESCE(cp.realized_pnl, CAST(0 AS DECIMAL(20,8)))
        END
    AS DECIMAL(20,8)) AS realized_pnl,

    -- current_price: DECIMAL(20,8)
    CAST(sq.price AS DECIMAL(20,8)) AS current_price,

    -- market_value: DECIMAL(20,8) - NULL for now, updated later
    CAST(NULL AS DECIMAL(20,8)) AS market_value,

    -- unrealized_pnl: DECIMAL(20,8) - NULL for now, updated later
    CAST(NULL AS DECIMAL(20,8)) AS unrealized_pnl,

    -- trade_id: BIGINT
    CAST(sq.trade_id AS BIGINT) AS trade_id,

    -- trade_type: STRING
    CAST(sq.trade_type AS STRING) AS trade_type,

    -- lots_held: INT
    CAST(
        CASE
            WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.lots_held, 0) + 1
            ELSE COALESCE(cp.lots_held, 0)
        END
    AS INT) AS lots_held,

    -- custodian: STRING
    CAST(sq.custodian AS STRING) AS custodian,

    -- sub_custodian: STRING
    CAST(sq.sub_custodian AS STRING) AS sub_custodian,

    -- security_currency: STRING
    CAST(sq.security_currency AS STRING) AS security_currency,

    -- portfolio_currency: STRING
    CAST(sq.portfolio_currency AS STRING) AS portfolio_currency,

    -- fx_rate: DECIMAL(20,8) - NULL for now
    CAST(NULL AS DECIMAL(20,8)) AS fx_rate,

    -- average_cost_base: DECIMAL(20,8) - NULL for now
    CAST(NULL AS DECIMAL(20,8)) AS average_cost_base,

    -- total_cost_base: DECIMAL(20,8) - NULL for now
    CAST(NULL AS DECIMAL(20,8)) AS total_cost_base,

    -- realized_pnl_base: DECIMAL(20,8) - NULL for now
    CAST(NULL AS DECIMAL(20,8)) AS realized_pnl_base,

    -- status: STRING
    CAST(
        CASE
            WHEN sq.trade_type = 'BUY' THEN 'OPEN'
            WHEN sq.trade_type = 'SELL' AND (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity) <= CAST(0 AS DECIMAL(20,8)) THEN 'CLOSED'
            ELSE 'OPEN'
        END
    AS STRING) AS status,

    -- is_active: BOOLEAN
    CAST(TRUE AS BOOLEAN) AS is_active,

    -- is_latest: BOOLEAN
    CAST(TRUE AS BOOLEAN) AS is_latest,

    -- created_by: STRING
    CAST('${var:RUN_BY}' AS STRING) AS created_by,

    -- created_at: STRING
    CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS STRING) AS created_at,

    -- updated_by: STRING
    CAST('${var:RUN_BY}' AS STRING) AS updated_by,

    -- updated_at: STRING
    CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS STRING) AS updated_at

FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN gmp_cis.v_current_positions_temp cp
    ON sq.portfolio_id = cp.portfolio_short_name
    AND sq.security_id = cp.security_label
WHERE sq.settle_date <= '${var:SETTLE_DATE}'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 6: Log processed records
-- ============================================================================
-- Target: cis_eod_settlement_log
-- Types: log_id BIGINT, batch_id BIGINT, queue_id BIGINT, trade_id BIGINT,
--        portfolio_id STRING, security_id STRING, trade_type STRING,
--        quantity DECIMAL(20,8), price DECIMAL(20,8), settle_date STRING,
--        status STRING, processed_at STRING

INSERT INTO gmp_cis.cis_eod_settlement_log
(log_id, batch_id, queue_id, trade_id, portfolio_id, security_id, trade_type,
 quantity, price, settle_date, status, processed_at)
SELECT
    CAST(${var:BATCH_ID} * 10000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS BIGINT) AS log_id,
    CAST(${var:BATCH_ID} AS BIGINT) AS batch_id,
    CAST(sq.queue_id AS BIGINT) AS queue_id,
    CAST(sq.trade_id AS BIGINT) AS trade_id,
    CAST(sq.portfolio_id AS STRING) AS portfolio_id,
    CAST(sq.security_id AS STRING) AS security_id,
    CAST(sq.trade_type AS STRING) AS trade_type,
    CAST(sq.quantity AS DECIMAL(20,8)) AS quantity,
    CAST(sq.price AS DECIMAL(20,8)) AS price,
    CAST(sq.settle_date AS STRING) AS settle_date,
    CAST('SUCCESS' AS STRING) AS status,
    CAST(FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS STRING) AS processed_at
FROM gmp_cis.cis_settlement_queue sq
WHERE sq.settle_date <= '${var:SETTLE_DATE}'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 7: Mark settlement queue records as COMPLETED
-- ============================================================================

UPDATE gmp_cis.cis_settlement_queue
SET status = 'COMPLETED',
    processed_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    updated_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE settle_date <= '${var:SETTLE_DATE}'
  AND status = 'PROCESSING';


-- ============================================================================
-- STEP 8: Update batch record with final counts
-- ============================================================================

UPDATE gmp_cis.cis_eod_settlement_batch
SET status = 'COMPLETED',
    processed_count = (
        SELECT CAST(COUNT(*) AS INT)
        FROM gmp_cis.cis_eod_settlement_log
        WHERE batch_id = ${var:BATCH_ID} AND status = 'SUCCESS'
    ),
    failed_count = (
        SELECT CAST(COUNT(*) AS INT)
        FROM gmp_cis.cis_eod_settlement_log
        WHERE batch_id = ${var:BATCH_ID} AND status = 'FAILED'
    ),
    completed_at = FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
WHERE batch_id = ${var:BATCH_ID};


-- ============================================================================
-- STEP 9: Sync to external position_master table (if exists)
-- ============================================================================

-- Uncomment if position_master external table exists
-- INSERT INTO gmp_cis.position_master
-- SELECT ... FROM gmp_cis.cis_trade_position WHERE ...;


-- ============================================================================
-- STEP 10: Cleanup temp view
-- ============================================================================

DROP VIEW IF EXISTS gmp_cis.v_current_positions_temp;


-- ============================================================================
-- STEP 11: Show summary
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
