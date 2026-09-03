-- ============================================================================
-- Settlement Queue Table - Future Settlement Processing
-- ============================================================================
-- Description: Queue table for trades with future settlement dates.
--              Trades are queued when settle_date > today and processed
--              by the daily settlement job when settle_date arrives.
--
-- Storage: Hive Managed Table with ORC format and ACID support
-- Database: gmp_cis
-- Created: 2026-03-04
-- Version: 1.0
-- ============================================================================

USE gmp_cis;

-- Set ACID configuration
SET hive.support.concurrency=true;
SET hive.enforce.bucketing=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.compactor.initiator.on=true;
SET hive.compactor.worker.threads=1;
SET hive.execution.engine=mr;

-- ============================================================================
-- TABLE: cis_settlement_queue
-- ============================================================================
-- Stores trades pending future settlement.
-- Daily settlement job processes entries where settle_date <= today.
-- ============================================================================

DROP TABLE IF EXISTS gmp_cis.cis_settlement_queue;

CREATE TABLE gmp_cis.cis_settlement_queue (
    -- Primary Key
    queue_id BIGINT COMMENT 'Unique queue entry ID',

    -- Trade Reference
    trade_id BIGINT COMMENT 'Reference to cis_trade.trade_id',
    portfolio_id STRING COMMENT 'Portfolio short name',
    security_id STRING COMMENT 'Security label',
    trade_type STRING COMMENT 'BUY or SELL',

    -- Trade Values
    quantity DECIMAL(30,8) COMMENT 'Trade quantity',
    price DECIMAL(30,8) COMMENT 'Trade price per unit',
    charges DECIMAL(30,8) COMMENT 'Total charges (commission + fees)',
    settle_date STRING COMMENT 'Settlement date (YYYY-MM-DD)',

    -- Multi-currency (optional)
    security_currency STRING COMMENT 'Security currency code',
    portfolio_currency STRING COMMENT 'Portfolio base currency code',
    isin STRING COMMENT 'ISIN code',
    security_name STRING COMMENT 'Security full name',

    -- Queue Status
    status STRING COMMENT 'PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED',
    retry_count INT COMMENT 'Number of processing attempts',
    error_message STRING COMMENT 'Error message if failed',

    -- Timestamps
    queued_at TIMESTAMP COMMENT 'When trade was queued',
    queued_by STRING COMMENT 'User who queued the trade',
    processed_at TIMESTAMP COMMENT 'When processing completed',
    updated_at TIMESTAMP COMMENT 'Last update timestamp',

    -- Partition Key (stored in table for reference)
    processing_date STRING COMMENT 'Processing date (YYYYMMDD)'
)
CLUSTERED BY (queue_id) INTO 4 BUCKETS
STORED AS ORC
TBLPROPERTIES (
    'transactional' = 'true',
    'orc.compress' = 'SNAPPY'
);


-- ============================================================================
-- Initialize sequence for queue_id
-- ============================================================================
INSERT INTO gmp_cis.cis_sequence (sequence_name, current_value, increment_by)
SELECT 'settlement_queue_id', 1000000, 1
WHERE NOT EXISTS (
    SELECT 1 FROM gmp_cis.cis_sequence WHERE sequence_name = 'settlement_queue_id'
);


-- ============================================================================
-- Sample Queries
-- ============================================================================

-- Get pending settlements for today
-- SELECT * FROM gmp_cis.cis_settlement_queue
-- WHERE settle_date <= CURRENT_DATE()
--   AND status = 'PENDING'
-- ORDER BY queued_at ASC;

-- Get settlement statistics
-- SELECT status, COUNT(*) as count
-- FROM gmp_cis.cis_settlement_queue
-- GROUP BY status;

-- Get failed settlements for retry
-- SELECT * FROM gmp_cis.cis_settlement_queue
-- WHERE status = 'FAILED'
--   AND retry_count < 3
-- ORDER BY queued_at ASC;


-- ============================================================================
-- END OF DDL
-- ============================================================================
