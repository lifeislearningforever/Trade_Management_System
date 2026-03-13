-- ============================================================================
-- EOD Settlement Processing - Standalone SQL Script for Impala-Shell
-- ============================================================================
-- Description: Processes pending settlements and creates AVP position records.
--              This script can be run directly with impala-shell.
--
-- USAGE:
--   1. Replace the variables in the CONFIGURATION section below:
--      - SETTLE_DATE:     Settlement date (YYYY-MM-DD)
--      - BATCH_ID:        Unique batch ID (use timestamp, e.g., 1710288000000)
--      - RUN_BY:          User/system running the job
--      - PROCESSING_DATE: Processing date (YYYYMMDD)
--
--   2. Run with impala-shell:
--      impala-shell -i <host>:21050 -d gmp_cis -f eod_settlement_standalone.sql
--
--   3. Or run specific sections:
--      impala-shell -i <host>:21050 -d gmp_cis
--      > source eod_settlement_standalone.sql;
--
-- EXAMPLE:
--   # For settlement date 2026-03-12
--   # Batch ID: 1741788000000 (Unix timestamp in ms)
--   # Replace all occurrences before running
--
-- Created: 2026-03-12
-- Version: 1.0 (Standalone)
-- ============================================================================


-- ============================================================================
-- CONFIGURATION - REPLACE THESE VALUES BEFORE RUNNING
-- ============================================================================
-- Find and replace the following values in this file:
--
--   '2026-03-12'      -> Your settlement date (YYYY-MM-DD)
--   1741788000000     -> Your batch ID (unique BIGINT, use: date +%s%3N)
--   '20260312'        -> Your processing date (YYYYMMDD)
--   'EOD_SYSTEM'      -> Your username or system name
--
-- TIP: Use sed for quick replacement:
--   sed -e "s/'2026-03-12'/'YOUR_DATE'/g" \
--       -e "s/1741788000000/YOUR_BATCH_ID/g" \
--       -e "s/'20260312'/'YOUR_PROC_DATE'/g" \
--       -e "s/'EOD_SYSTEM'/'YOUR_USER'/g" \
--       eod_settlement_standalone.sql > eod_run.sql
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
    CAST(1741788000000 AS BIGINT),
    '2026-03-12',
    '20260312',
    'STARTED',
    CAST(COUNT(*) AS INT),
    CAST(0 AS INT),
    CAST(0 AS INT),
    CAST(0 AS INT),
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'EOD_SYSTEM'
FROM gmp_cis.cis_settlement_queue
WHERE settle_date <= '2026-03-12'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 2: Mark pending records as PROCESSING
-- ============================================================================

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
WHERE settle_date <= '2026-03-12'
  AND status = 'PENDING';


-- ============================================================================
-- STEP 3: Create temp table for position lookup (position BEFORE each trade date)
-- ============================================================================
-- For chain recalculation, we need the position BEFORE each trade's settle_date
-- NOT the global latest position. This ensures backdated trades accumulate correctly.

DROP TABLE IF EXISTS gmp_cis.tmp_current_positions_eod;

-- Get the latest position BEFORE each settle_date for each portfolio/security combo
-- This handles the case where Trade1 on 13th, Trade2 backdated to 6th March
CREATE TABLE gmp_cis.tmp_current_positions_eod
STORED AS PARQUET AS
SELECT
    sq.queue_id,
    sq.portfolio_id,
    sq.security_id,
    sq.settle_date as trade_settle_date,
    p.position_id,
    p.quantity,
    p.average_cost,
    p.total_cost,
    p.realized_pnl,
    p.lots_held,
    p.status,
    p.position_date as base_position_date
FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN (
    -- Get the latest position version BEFORE each settle_date
    SELECT
        p1.portfolio_short_name,
        p1.security_label,
        p1.position_date,
        p1.position_id,
        p1.quantity,
        p1.average_cost,
        p1.total_cost,
        p1.realized_pnl,
        p1.lots_held,
        p1.status,
        p1.version_id
    FROM gmp_cis.cis_trade_position p1
    INNER JOIN (
        -- Get max version_id for each portfolio/security/position_date
        SELECT portfolio_short_name, security_label, position_date, MAX(version_id) as max_version
        FROM gmp_cis.cis_trade_position
        WHERE is_latest = true OR is_latest IS NULL
        GROUP BY portfolio_short_name, security_label, position_date
    ) pv ON p1.portfolio_short_name = pv.portfolio_short_name
        AND p1.security_label = pv.security_label
        AND p1.position_date = pv.position_date
        AND p1.version_id = pv.max_version
) p ON sq.portfolio_id = p.portfolio_short_name
    AND sq.security_id = p.security_label
    AND p.position_date < sq.settle_date  -- BEFORE the trade date, not <=
WHERE sq.settle_date <= '2026-03-12'
  AND sq.status = 'PROCESSING';

-- For each queue item, keep only the most recent position before the trade date
DROP TABLE IF EXISTS gmp_cis.tmp_base_positions_eod;

CREATE TABLE gmp_cis.tmp_base_positions_eod
STORED AS PARQUET AS
SELECT t.*
FROM gmp_cis.tmp_current_positions_eod t
INNER JOIN (
    SELECT queue_id, MAX(base_position_date) as max_date
    FROM gmp_cis.tmp_current_positions_eod
    WHERE position_id IS NOT NULL
    GROUP BY queue_id
) latest ON t.queue_id = latest.queue_id
        AND (t.base_position_date = latest.max_date OR t.position_id IS NULL);

-- Replace the temp table
DROP TABLE IF EXISTS gmp_cis.tmp_current_positions_eod;
ALTER TABLE gmp_cis.tmp_base_positions_eod RENAME TO gmp_cis.tmp_current_positions_eod;

COMPUTE STATS gmp_cis.tmp_current_positions_eod;


-- ============================================================================
-- STEP 4: Identify positions that need is_latest=false
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
WHERE sq.settle_date <= '2026-03-12'
  AND sq.status = 'PROCESSING'
  AND (p.is_latest = true OR p.is_latest IS NULL);


-- ============================================================================
-- STEP 5: Mark old position versions as is_latest=false
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
-- STEP 6: Process settlements and create position records (AVP calculation)
-- ============================================================================
-- AVP Formula:
--   BUY: new_avg_cost = (old_total_cost + buy_value + charges) / (old_qty + buy_qty)
--   SELL: avg_cost unchanged, realized_pnl = sell_qty * (sell_price - avg_cost)
--
-- IMPORTANT: For chain recalculation (backdated trades), we use the position
-- BEFORE each trade's settle_date, NOT the global latest position.
-- The tmp_current_positions_eod now contains one row per queue_id with
-- the correct base position for that specific trade date.

INSERT INTO gmp_cis.cis_trade_position
(version_id, position_id, position_date, portfolio_short_name, security_label,
 quantity, average_cost, total_cost, realized_pnl, current_price, market_value,
 unrealized_pnl, trade_id, trade_type, lots_held, custodian, sub_custodian,
 security_currency, portfolio_currency, fx_rate, average_cost_base,
 total_cost_base, realized_pnl_base, status, is_active, is_latest,
 created_by, created_at, updated_by, updated_at)
SELECT
    -- version_id: unique per record
    CAST(1741788000000 * 1000 + ROW_NUMBER() OVER (ORDER BY sq.settle_date, sq.queue_id) AS BIGINT),
    -- position_id: reuse existing or generate new
    CAST(COALESCE(cp.position_id, 1741788000000 * 100 + ROW_NUMBER() OVER (ORDER BY sq.settle_date, sq.queue_id)) AS BIGINT),
    sq.settle_date,
    sq.portfolio_id,
    sq.security_id,
    -- quantity: add for BUY, subtract for SELL
    -- Use DECIMAL(38,8) internally to avoid precision errors, then cast to DECIMAL(20,8)
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + CAST(sq.quantity AS DECIMAL(38,8))
        WHEN sq.trade_type = 'SELL' THEN COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) - CAST(sq.quantity AS DECIMAL(38,8))
        ELSE COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))
    END AS DECIMAL(20,8)),
    -- average_cost: recalculate for BUY, preserve for SELL
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN
            CASE
                WHEN (COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + CAST(sq.quantity AS DECIMAL(38,8))) > CAST(0 AS DECIMAL(38,8)) THEN
                    (COALESCE(CAST(cp.total_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + (CAST(sq.quantity AS DECIMAL(38,8)) * CAST(sq.price AS DECIMAL(38,8))) + COALESCE(CAST(sq.charges AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))) /
                    (COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + CAST(sq.quantity AS DECIMAL(38,8)))
                ELSE CAST(0 AS DECIMAL(38,8))
            END
        ELSE COALESCE(CAST(cp.average_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))
    END AS DECIMAL(20,8)),
    -- total_cost: add buy value for BUY, reduce proportionally for SELL
    CAST(CASE
        WHEN sq.trade_type = 'BUY' THEN
            COALESCE(CAST(cp.total_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + (CAST(sq.quantity AS DECIMAL(38,8)) * CAST(sq.price AS DECIMAL(38,8))) + COALESCE(CAST(sq.charges AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))
        WHEN sq.trade_type = 'SELL' THEN
            CASE
                WHEN COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) > CAST(0 AS DECIMAL(38,8)) THEN
                    COALESCE(CAST(cp.total_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) * (COALESCE(CAST(cp.quantity AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) - CAST(sq.quantity AS DECIMAL(38,8))) / CAST(cp.quantity AS DECIMAL(38,8))
                ELSE CAST(0 AS DECIMAL(38,8))
            END
        ELSE COALESCE(CAST(cp.total_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))
    END AS DECIMAL(20,8)),
    -- realized_pnl: calculate P&L on SELL
    CAST(CASE
        WHEN sq.trade_type = 'SELL' THEN
            COALESCE(CAST(cp.realized_pnl AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8))) + (CAST(sq.quantity AS DECIMAL(38,8)) * (CAST(sq.price AS DECIMAL(38,8)) - COALESCE(CAST(cp.average_cost AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))))
        ELSE COALESCE(CAST(cp.realized_pnl AS DECIMAL(38,8)), CAST(0 AS DECIMAL(38,8)))
    END AS DECIMAL(20,8)),
    CAST(sq.price AS DECIMAL(20,8)),  -- current_price
    CAST(NULL AS DECIMAL(20,8)),      -- market_value (calculated later)
    CAST(NULL AS DECIMAL(20,8)),      -- unrealized_pnl (calculated later)
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
    -- status: CLOSED if quantity becomes 0 or negative
    CASE
        WHEN sq.trade_type = 'BUY' THEN 'OPEN'
        WHEN sq.trade_type = 'SELL' AND (COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) - sq.quantity) <= CAST(0 AS DECIMAL(20,8)) THEN 'CLOSED'
        ELSE 'OPEN'
    END,
    CAST(true AS BOOLEAN),            -- is_active
    CAST(true AS BOOLEAN),            -- is_latest
    'EOD_SYSTEM',
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    'EOD_SYSTEM',
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss')
FROM gmp_cis.cis_settlement_queue sq
LEFT JOIN gmp_cis.tmp_current_positions_eod cp
    ON sq.queue_id = cp.queue_id  -- Join by queue_id to get correct base position for each trade
WHERE sq.settle_date <= '2026-03-12'
  AND sq.status = 'PROCESSING'
  -- Exclude error cases: SELL without position or insufficient quantity
  AND NOT (sq.trade_type = 'SELL' AND (cp.position_id IS NULL OR COALESCE(cp.quantity, CAST(0 AS DECIMAL(20,8))) < sq.quantity));


-- ============================================================================
-- STEP 7: Log all processed records (SUCCESS and FAILED)
-- ============================================================================

INSERT INTO gmp_cis.cis_eod_settlement_log
(log_id, batch_id, queue_id, trade_id, portfolio_id, security_id, trade_type,
 quantity, price, settle_date, status, error_message, processed_at)
SELECT
    CAST(1741788000000 * 10000 + ROW_NUMBER() OVER (ORDER BY sq.queue_id) AS BIGINT),
    CAST(1741788000000 AS BIGINT),
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
    ON sq.queue_id = cp.queue_id  -- Join by queue_id to match correct base position
WHERE sq.settle_date <= '2026-03-12'
  AND sq.status = 'PROCESSING';


-- ============================================================================
-- STEP 8: Prepare successful queue records for status update
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_queue_success;

CREATE TABLE gmp_cis.tmp_queue_success
STORED AS PARQUET AS
SELECT sq.*
FROM gmp_cis.cis_settlement_queue sq
INNER JOIN gmp_cis.cis_eod_settlement_log l
    ON sq.queue_id = l.queue_id
WHERE l.batch_id = 1741788000000
  AND l.status = 'SUCCESS';


-- ============================================================================
-- STEP 9: Mark successful queue records as COMPLETED
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
-- STEP 10: Prepare failed queue records for status update
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.tmp_queue_failed;

CREATE TABLE gmp_cis.tmp_queue_failed
STORED AS PARQUET AS
SELECT sq.*, l.error_message as new_error_message
FROM gmp_cis.cis_settlement_queue sq
INNER JOIN gmp_cis.cis_eod_settlement_log l
    ON sq.queue_id = l.queue_id
WHERE l.batch_id = 1741788000000
  AND l.status = 'FAILED';


-- ============================================================================
-- STEP 11: Mark failed queue records as FAILED
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
-- STEP 12: Update batch record with final counts
-- ============================================================================

UPSERT INTO gmp_cis.cis_eod_settlement_batch
(batch_id, batch_date, processing_date, status, total_pending, processed_count,
 failed_count, skipped_count, started_at, completed_at, run_by)
SELECT
    CAST(1741788000000 AS BIGINT),
    b.batch_date,
    b.processing_date,
    'COMPLETED',
    b.total_pending,
    CAST((SELECT COUNT(*) FROM gmp_cis.cis_eod_settlement_log WHERE batch_id = 1741788000000 AND status = 'SUCCESS') AS INT),
    CAST((SELECT COUNT(*) FROM gmp_cis.cis_eod_settlement_log WHERE batch_id = 1741788000000 AND status = 'FAILED') AS INT),
    b.skipped_count,
    b.started_at,
    FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss'),
    b.run_by
FROM gmp_cis.cis_eod_settlement_batch b
WHERE b.batch_id = 1741788000000;


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

SELECT '=== EOD SETTLEMENT BATCH SUMMARY ===' as info;

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
WHERE batch_id = 1741788000000;

SELECT '=== SETTLEMENT LOG DETAILS ===' as info;

SELECT
    trade_id,
    portfolio_id,
    security_id,
    trade_type,
    CAST(quantity AS STRING) as quantity,
    CAST(price AS STRING) as price,
    status,
    error_message
FROM gmp_cis.cis_eod_settlement_log
WHERE batch_id = 1741788000000
ORDER BY status DESC, trade_id;


-- ============================================================================
-- END OF SCRIPT
-- ============================================================================
