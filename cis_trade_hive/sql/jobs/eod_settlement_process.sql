-- ============================================================================
-- EOD Settlement Processing Job - Impala/Kudu SQL Script
-- ============================================================================
-- Description: Processes pending settlements and creates position records.
--              This script is called by eod_settlement_process.sh
--
-- IMPORTANT: This script uses shell variable substitution (not impala-shell --var)
--            Variables are substituted by the shell script before execution.
--
-- Input Parameters (substituted by shell before execution):
--   SETTLE_DATE     - Settlement date to process (YYYY-MM-DD), default: today
--   BATCH_ID        - Unique batch ID for this run (BIGINT)
--   RUN_BY          - User/system running the job
--   PROCESSING_DATE - Processing date (YYYYMMDD)
--
-- Usage:
--   # Variables are substituted by eod_settlement_process.sh
--   # The shell script generates a temp SQL file with values substituted
--
-- Created: 2026-03-06
-- Updated: 2026-03-11 (Impala/Kudu compatibility fixes)
-- Version: 2.0
-- ============================================================================

-- Refresh metadata to ensure we have latest table state
INVALIDATE METADATA gmp_cis.cis_settlement_queue;
INVALIDATE METADATA gmp_cis.cis_trade_position;
INVALIDATE METADATA gmp_cis.cis_eod_settlement_batch;
INVALIDATE METADATA gmp_cis.cis_eod_settlement_log;


-- ============================================================================
-- STEP 1: Create batch record
-- ============================================================================

UPSERT INTO gmp_cis.cis_eod_settlement_batch
(batch_id, batch_date, processing_date, status, total_pending, processed_count,
 failed_count, skipped_count, started_at, run_by)
SELECT
    CAST(__BATCH_ID__ AS BIGINT),
    '__SETTLE_DATE__',
    '__PROCESSING_DATE__',
    'STARTED',
    CAST(COUNT(*) AS INT),
    CAST(0 AS INT),
    CAST(0 AS INT),
    CAST(0 AS INT),
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    '__RUN_BY__'
FROM gmp_cis.cis_settlement_queue
WHERE settle_date <= '__SETTLE_DATE__'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 2: Mark pending records as PROCESSING using UPSERT
-- ============================================================================
-- Kudu requires UPSERT with full primary key for updates

UPSERT INTO gmp_cis.cis_settlement_queue
(queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
 charges, settle_date, security_currency, portfolio_currency, isin, security_name,
 status, retry_count, error_message, queued_at, queued_by, processed_at, updated_at,
 processing_date, custodian, sub_custodian)
SELECT
    queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
    charges, settle_date, security_currency, portfolio_currency, isin, security_name,
    'PROCESSING',
    retry_count, error_message, queued_at, queued_by, processed_at,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    processing_date, custodian, sub_custodian
FROM gmp_cis.cis_settlement_queue
WHERE settle_date <= '__SETTLE_DATE__'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 3: Create temp table for current positions
-- ============================================================================
-- Using temp table instead of view for better Impala compatibility

DROP TABLE IF EXISTS gmp_cis.tmp_current_positions_eod;

CREATE TABLE gmp_cis.tmp_current_positions_eod
STORED AS PARQUET AS
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
INNER JOIN (
    SELECT portfolio_short_name, security_label, MAX(version_id) as max_version
    FROM gmp_cis.cis_trade_position
    WHERE is_latest = true OR is_latest IS NULL
    GROUP BY portfolio_short_name, security_label
) latest
ON p.portfolio_short_name = latest.portfolio_short_name
   AND p.security_label = latest.security_label
   AND p.version_id = latest.max_version;

-- Compute stats for better query performance
COMPUTE STATS gmp_cis.tmp_current_positions_eod;


-- ============================================================================
-- STEP 4: Create temp table to track which positions need is_latest=false
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_positions_to_update;

CREATE TABLE gmp_cis.tmp_positions_to_update
STORED AS PARQUET AS
SELECT DISTINCT p.version_id, p.position_id, p.position_date,
       p.portfolio_short_name, p.security_label, p.quantity, p.average_cost,
       p.total_cost, p.realized_pnl, p.current_price, p.market_value,
       p.unrealized_pnl, p.trade_id, p.trade_type, p.lots_held, p.custodian,
       p.sub_custodian, p.security_currency, p.portfolio_currency, p.fx_rate,
       p.average_cost_base, p.total_cost_base, p.realized_pnl_base,
       p.status, p.is_active, p.created_by, p.created_at, p.updated_by
FROM gmp_cis.cis_trade_position p
INNER JOIN gmp_cis.cis_settlement_queue sq
    ON p.portfolio_short_name = sq.portfolio_id
    AND p.security_label = sq.security_id
WHERE sq.settle_date <= '__SETTLE_DATE__'
  AND sq.status = 'PROCESSING'
  AND (p.is_latest = true OR p.is_latest IS NULL);


-- ============================================================================
-- STEP 5: Mark old position versions as is_latest=false using UPSERT
-- ============================================================================

UPSERT INTO gmp_cis.cis_trade_position
(version_id, position_id, position_date, portfolio_short_name, security_label,
 quantity, average_cost, total_cost, realized_pnl, current_price, market_value,
 unrealized_pnl, trade_id, trade_type, lots_held, custodian, sub_custodian,
 security_currency, portfolio_currency, fx_rate, average_cost_base,
 total_cost_base, realized_pnl_base, status, is_active, is_latest,
 created_by, created_at, updated_by, updated_at)
SELECT
    version_id, position_id, position_date, portfolio_short_name, security_label,
    quantity, average_cost, total_cost, realized_pnl, current_price, market_value,
    unrealized_pnl, trade_id, trade_type, lots_held, custodian, sub_custodian,
    security_currency, portfolio_currency, fx_rate, average_cost_base,
    total_cost_base, realized_pnl_base, status, is_active,
    CAST(false AS BOOLEAN) AS is_latest,
    created_by, created_at, updated_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS updated_at
FROM gmp_cis.tmp_positions_to_update;


-- ============================================================================
-- STEP 6: Process settlements and create position records
-- ============================================================================
-- Only insert for valid cases (BUY, or SELL with sufficient quantity)

INSERT INTO gmp_cis.cis_trade_position
(version_id, position_id, position_date, portfolio_short_name, security_label,
 quantity, average_cost, total_cost, realized_pnl, current_price, market_value,
 unrealized_pnl, trade_id, trade_type, lots_held, custodian, sub_custodian,
 security_currency, portfolio_currency, fx_rate, average_cost_base,
 total_cost_base, realized_pnl_base, status, is_active, is_latest,
 created_by, created_at, updated_by, updated_at)
SELECT
    CAST(__BATCH_ID__ * 1000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS BIGINT),
    CAST(COALESCE(cp.position_id, __BATCH_ID__ * 100 + ROW_NUMBER() OVER (ORDER BY sq.queue_id)) AS BIGINT),
    sq.settle_date,
    sq.portfolio_id,
    sq.security_id,
    -- quantity
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity
        WHEN sq.trade_type = 'SELL' THEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity
        ELSE COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8)))
    END AS DECIMAL(20,8)),
    -- average_cost (AVP formula)
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN
            CASE
                WHEN (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity) > CAST(0 AS DECIMAL(20,8)) THEN
                    (COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * sq.price) + COALESCE(sq.charges, CAST(0 AS DECIMAL(20,8)))) /
                    (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) + sq.quantity)
                ELSE CAST(0 AS DECIMAL(20,8))
            END
        ELSE COALESCE(cp.average_cost, CAST(0 AS DECIMAL(20,8)))
    END AS DECIMAL(20,8)),
    -- total_cost
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN
            COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * sq.price) + COALESCE(sq.charges, CAST(0 AS DECIMAL(20,8)))
        WHEN sq.trade_type = 'SELL' THEN
            CASE
                WHEN COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) > CAST(0 AS DECIMAL(20,8)) THEN
                    COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8))) * (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity) / cp.quantity
                ELSE CAST(0 AS DECIMAL(20,8))
            END
        ELSE COALESCE(cp.total_cost, CAST(0 AS DECIMAL(20,8)))
    END AS DECIMAL(20,8)),
    -- realized_pnl
    CAST(CASE
        WHEN sq.trade_type = 'SELL' THEN
            COALESCE(cp.realized_pnl, CAST(0 AS DECIMAL(20,8))) + (sq.quantity * (sq.price - COALESCE(cp.average_cost, CAST(0 AS DECIMAL(20,8)))))
        ELSE COALESCE(cp.realized_pnl, CAST(0 AS DECIMAL(20,8)))
    END AS DECIMAL(20,8)),
    CAST(sq.price AS DECIMAL(20,8)),  -- current_price
    CAST(NULL AS DECIMAL(20,8)),      -- market_value
    CAST(NULL AS DECIMAL(20,8)),      -- unrealized_pnl
    sq.trade_id,
    sq.trade_type,
    CAST(CASE WHEN sq.trade_type = 'BUY' THEN COALESCE(cp.lots_held, 0) + 1 ELSE COALESCE(cp.lots_held, 0) END AS INT),
    sq.custodian,
    sq.sub_custodian,
    sq.security_currency,
    sq.portfolio_currency,
    CAST(NULL AS DECIMAL(20,8)),      -- fx_rate
    CAST(NULL AS DECIMAL(20,8)),      -- average_cost_base
    CAST(NULL AS DECIMAL(20,8)),      -- total_cost_base
    CAST(NULL AS DECIMAL(20,8)),      -- realized_pnl_base
    CASE
        WHEN sq.trade_type = 'BUY' THEN 'OPEN'
        WHEN sq.trade_type = 'SELL' AND (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity) <= CAST(0 AS DECIMAL(20,8)) THEN 'CLOSED'
        ELSE 'OPEN'
    END,
    CAST(true AS BOOLEAN),            -- is_active
    CAST(true AS BOOLEAN),            -- is_latest
    '__RUN_BY__',
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    '__RUN_BY__',
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN gmp_cis.tmp_current_positions_eod cp
    ON sq.portfolio_id = cp.portfolio_short_name
    AND sq.security_id = cp.security_label
WHERE sq.settle_date <= '__SETTLE_DATE__'
  AND sq.status = 'PROCESSING'
  -- Exclude error cases
  AND NOT (sq.trade_type = 'SELL' AND (cp.position_id IS NULL OR COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) < sq.quantity));


-- ============================================================================
-- STEP 7: Log all processed records (SUCCESS and FAILED)
-- ============================================================================

INSERT INTO gmp_cis.cis_eod_settlement_log
(log_id, batch_id, queue_id, trade_id, portfolio_id, security_id, trade_type,
 quantity, price, settle_date, status, error_message, processed_at)
SELECT
    CAST(__BATCH_ID__ * 10000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS BIGINT),
    CAST(__BATCH_ID__ AS BIGINT),
    sq.queue_id,
    sq.trade_id,
    sq.portfolio_id,
    sq.security_id,
    sq.trade_type,
    sq.quantity,
    sq.price,
    sq.settle_date,
    CASE
        WHEN sq.trade_type = 'SELL' AND cp.position_id IS NULL THEN 'FAILED'
        WHEN sq.trade_type = 'SELL' AND COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) < sq.quantity THEN 'FAILED'
        ELSE 'SUCCESS'
    END,
    CASE
        WHEN sq.trade_type = 'SELL' AND cp.position_id IS NULL THEN
            CONCAT('No position found for ', sq.security_id, ' in portfolio ', sq.portfolio_id)
        WHEN sq.trade_type = 'SELL' AND COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) < sq.quantity THEN
            CONCAT('Insufficient quantity. Available: ', CAST(COALESCE(cp.quantity, 0) AS STRING), ', Requested: ', CAST(sq.quantity AS STRING))
        ELSE NULL
    END,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN gmp_cis.tmp_current_positions_eod cp
    ON sq.portfolio_id = cp.portfolio_short_name
    AND sq.security_id = cp.security_label
WHERE sq.settle_date <= '__SETTLE_DATE__'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 8: Create temp table for successful queue updates
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_queue_success;

CREATE TABLE gmp_cis.tmp_queue_success
STORED AS PARQUET AS
SELECT sq.*
FROM gmp_cis.cis_settlement_queue sq
INNER JOIN gmp_cis.cis_eod_settlement_log l
    ON sq.queue_id = l.queue_id
WHERE l.batch_id = __BATCH_ID__
  AND l.status = 'SUCCESS';


-- ============================================================================
-- STEP 9: Mark successful queue records as COMPLETED using UPSERT
-- ============================================================================

UPSERT INTO gmp_cis.cis_settlement_queue
(queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
 charges, settle_date, security_currency, portfolio_currency, isin, security_name,
 status, retry_count, error_message, queued_at, queued_by, processed_at, updated_at,
 processing_date, custodian, sub_custodian)
SELECT
    queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
    charges, settle_date, security_currency, portfolio_currency, isin, security_name,
    'COMPLETED',
    retry_count, error_message, queued_at, queued_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    processing_date, custodian, sub_custodian
FROM gmp_cis.tmp_queue_success;


-- ============================================================================
-- STEP 10: Create temp table for failed queue updates
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_queue_failed;

CREATE TABLE gmp_cis.tmp_queue_failed
STORED AS PARQUET AS
SELECT sq.*, l.error_message as new_error_message
FROM gmp_cis.cis_settlement_queue sq
INNER JOIN gmp_cis.cis_eod_settlement_log l
    ON sq.queue_id = l.queue_id
WHERE l.batch_id = __BATCH_ID__
  AND l.status = 'FAILED';


-- ============================================================================
-- STEP 11: Mark failed queue records as FAILED using UPSERT
-- ============================================================================

UPSERT INTO gmp_cis.cis_settlement_queue
(queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
 charges, settle_date, security_currency, portfolio_currency, isin, security_name,
 status, retry_count, error_message, queued_at, queued_by, processed_at, updated_at,
 processing_date, custodian, sub_custodian)
SELECT
    queue_id, trade_id, portfolio_id, security_id, trade_type, quantity, price,
    charges, settle_date, security_currency, portfolio_currency, isin, security_name,
    'FAILED',
    retry_count, new_error_message, queued_at, queued_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    processing_date, custodian, sub_custodian
FROM gmp_cis.tmp_queue_failed;


-- ============================================================================
-- STEP 12: Update batch record with final counts using UPSERT
-- ============================================================================

UPSERT INTO gmp_cis.cis_eod_settlement_batch
(batch_id, batch_date, processing_date, status, total_pending, processed_count,
 failed_count, skipped_count, started_at, completed_at, run_by)
SELECT
    CAST(__BATCH_ID__ AS BIGINT),
    b.batch_date,
    b.processing_date,
    'COMPLETED',
    b.total_pending,
    CAST((SELECT COUNT(*) FROM gmp_cis.cis_eod_settlement_log WHERE batch_id = __BATCH_ID__ AND status = 'SUCCESS') AS INT),
    CAST((SELECT COUNT(*) FROM gmp_cis.cis_eod_settlement_log WHERE batch_id = __BATCH_ID__ AND status = 'FAILED') AS INT),
    b.skipped_count,
    b.started_at,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    b.run_by
FROM gmp_cis.cis_eod_settlement_batch b
WHERE b.batch_id = __BATCH_ID__;


-- ============================================================================
-- STEP 13: Cleanup temp tables
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_current_positions_eod;
DROP TABLE IF EXISTS gmp_cis.tmp_positions_to_update;
DROP TABLE IF EXISTS gmp_cis.tmp_queue_success;
DROP TABLE IF EXISTS gmp_cis.tmp_queue_failed;


-- ============================================================================
-- STEP 14: Show summary
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
WHERE batch_id = __BATCH_ID__;


-- ============================================================================
-- END OF SCRIPT
-- ============================================================================
