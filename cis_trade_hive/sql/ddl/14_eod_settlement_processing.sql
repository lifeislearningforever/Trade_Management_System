-- ============================================================================
-- EOD Settlement Processing - Hive Managed Tables and Processing Logic
-- ============================================================================
-- Description: End-of-Day settlement processing for AVP position calculation.
--              Processes pending settlements from cis_settlement_queue and
--              creates positions in cis_trade_position table.
--
-- Tables:
--   1. cis_eod_settlement_batch - Batch tracking for EOD runs
--   2. cis_eod_settlement_log - Detailed processing log
--
-- Usage:
--   Run via: scripts/eod_settlement_process.sh
--   Schedule: Daily at EOD (e.g., 18:00 SGT)
--
-- Created: 2026-03-06
-- Version: 1.0
-- ============================================================================


-- ============================================================================
-- TABLE 1: cis_eod_settlement_batch
-- ============================================================================
-- Tracks each EOD settlement batch run for audit and monitoring.
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_eod_settlement_batch;

CREATE TABLE gmp_cis.cis_eod_settlement_batch (
    -- Primary Key
    batch_id BIGINT NOT NULL,

    -- Batch Info
    batch_date STRING NOT NULL,           -- Settlement date being processed (YYYY-MM-DD)
    processing_date STRING NOT NULL,      -- Date batch was run (YYYYMMDD)

    -- Status: STARTED, PROCESSING, COMPLETED, FAILED
    status STRING,

    -- Counts
    total_pending INT,                    -- Total records to process
    processed_count INT,                  -- Successfully processed
    failed_count INT,                     -- Failed records
    skipped_count INT,                    -- Skipped records

    -- Timing
    started_at STRING,
    completed_at STRING,
    duration_seconds INT,

    -- Error Summary
    error_summary STRING,

    -- Audit
    run_by STRING,                        -- User/system that triggered the run

    PRIMARY KEY (batch_id)
)
PARTITION BY HASH (batch_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051'
);


-- ============================================================================
-- TABLE 2: cis_eod_settlement_log
-- ============================================================================
-- Detailed log of each settlement record processed in a batch.
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_eod_settlement_log;

CREATE TABLE gmp_cis.cis_eod_settlement_log (
    -- Primary Key
    log_id BIGINT NOT NULL,

    -- Batch Reference
    batch_id BIGINT,

    -- Settlement Queue Reference
    queue_id BIGINT,
    trade_id BIGINT,

    -- Trade Info
    portfolio_id STRING,
    security_id STRING,
    trade_type STRING,
    quantity DECIMAL(30,8),
    price DECIMAL(30,8),
    settle_date STRING,

    -- Processing Result
    status STRING,                        -- SUCCESS, FAILED, SKIPPED
    error_message STRING,

    -- Position Result (if successful)
    position_id BIGINT,
    version_id BIGINT,
    average_cost DECIMAL(30,8),
    total_cost DECIMAL(30,8),
    realized_pnl DECIMAL(30,8),

    -- Timing
    processed_at STRING,
    duration_ms INT,

    PRIMARY KEY (log_id)
)
PARTITION BY HASH (log_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7051,kudu-master-3:7051'
);


-- ============================================================================
-- VIEW: v_pending_settlements_today
-- ============================================================================
-- View to get all pending settlements ready for processing today.
-- ============================================================================

DROP VIEW IF EXISTS gmp_cis.v_pending_settlements_today;

CREATE VIEW gmp_cis.v_pending_settlements_today AS
SELECT
    sq.queue_id,
    sq.trade_id,
    sq.portfolio_id,
    sq.security_id,
    sq.trade_type,
    sq.quantity,
    sq.price,
    sq.charges,
    sq.settle_date,
    sq.security_currency,
    sq.portfolio_currency,
    sq.isin,
    sq.security_name,
    sq.custodian,
    sq.sub_custodian,
    sq.queued_at,
    sq.queued_by
FROM gmp_cis.cis_settlement_queue sq
WHERE sq.settle_date <= CAST(CURRENT_DATE() AS STRING)
  AND sq.status = 'PENDING'
ORDER BY sq.settle_date ASC, sq.queued_at ASC;


-- ============================================================================
-- VIEW: v_settlement_queue_summary
-- ============================================================================
-- Summary view for monitoring settlement queue status.
-- ============================================================================

DROP VIEW IF EXISTS gmp_cis.v_settlement_queue_summary;

CREATE VIEW gmp_cis.v_settlement_queue_summary AS
SELECT
    settle_date,
    status,
    COUNT(*) as record_count,
    SUM(CAST(quantity AS DOUBLE) * CAST(price AS DOUBLE)) as total_value
FROM gmp_cis.cis_settlement_queue
GROUP BY settle_date, status
ORDER BY settle_date DESC, status;


-- ============================================================================
-- VIEW: v_eod_batch_summary
-- ============================================================================
-- Summary of recent EOD batch runs for monitoring.
-- ============================================================================

DROP VIEW IF EXISTS gmp_cis.v_eod_batch_summary;

CREATE VIEW gmp_cis.v_eod_batch_summary AS
SELECT
    batch_id,
    batch_date,
    status,
    total_pending,
    processed_count,
    failed_count,
    duration_seconds,
    started_at,
    completed_at,
    run_by
FROM gmp_cis.cis_eod_settlement_batch
ORDER BY batch_id DESC
LIMIT 30;


-- ============================================================================
-- MONITORING QUERIES
-- ============================================================================

-- Check pending settlements for today
-- SELECT * FROM gmp_cis.v_pending_settlements_today;

-- Check settlement queue summary
-- SELECT * FROM gmp_cis.v_settlement_queue_summary WHERE settle_date >= '2026-03-01';

-- Check recent EOD batch runs
-- SELECT * FROM gmp_cis.v_eod_batch_summary;

-- Get failed settlements from last batch
-- SELECT l.*
-- FROM gmp_cis.cis_eod_settlement_log l
-- JOIN (SELECT MAX(batch_id) as max_batch FROM gmp_cis.cis_eod_settlement_batch) b
-- ON l.batch_id = b.max_batch
-- WHERE l.status = 'FAILED';


-- ============================================================================
-- END OF DDL
-- ============================================================================
