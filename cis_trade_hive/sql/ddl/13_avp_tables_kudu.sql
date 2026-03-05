-- ============================================================================
-- AVP (Average Price Position) Tables - Kudu
-- ============================================================================
-- Description: Tables required for AVP position calculation system.
--              Uses Kudu storage to match cis_trade table.
--
-- Tables:
--   1. cis_trade_position - Position tracking with AVP calculations
--   2. cis_position_queue - Async processing queue for positions
--   3. cis_settlement_queue - Queue for future settlement dates (T+1, T+2)
--
-- Created: 2026-03-05
-- Version: 1.0
-- ============================================================================

-- ============================================================================
-- TABLE 1: cis_trade_position
-- ============================================================================
-- Stores position snapshots with AVP (Average Price) calculations.
-- Each trade creates a new version (snapshot) of the position.
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_position;

CREATE TABLE cis_trade_position (
    -- Primary Key (auto-increment per snapshot)
    version_id BIGINT NOT NULL,

    -- Position Identity (same across all versions for a portfolio+security)
    position_id BIGINT NOT NULL,

    -- Snapshot date
    position_date STRING NOT NULL,

    -- Portfolio Reference
    portfolio_short_name STRING NOT NULL,

    -- Security Reference
    security_label STRING NOT NULL,

    -- Position State (8 decimal precision for AVP)
    quantity DECIMAL(20,8),              -- Current holding quantity
    average_cost DECIMAL(20,8),          -- Weighted average cost (AVP)
    total_cost DECIMAL(20,8),            -- Total cost basis

    -- P&L
    realized_pnl DECIMAL(20,8),          -- Cumulative realized P&L
    current_price DECIMAL(20,8),         -- Latest market price
    market_value DECIMAL(20,8),          -- qty * current_price
    unrealized_pnl DECIMAL(20,8),        -- market_value - total_cost

    -- Trade that caused this version
    trade_id BIGINT,
    trade_type STRING,                   -- BUY, SELL

    -- Additional Info
    lots_held INT,
    custodian STRING,
    sub_custodian STRING,

    -- Multi-currency support
    security_currency STRING,            -- Security's trading currency
    portfolio_currency STRING,           -- Portfolio's base currency
    fx_rate DECIMAL(20,8),               -- FX rate used
    average_cost_base DECIMAL(20,8),     -- AVP in base currency
    total_cost_base DECIMAL(20,8),       -- Total cost in base currency
    realized_pnl_base DECIMAL(20,8),     -- Realized P&L in base currency

    -- Status
    status STRING,                       -- OPEN, CLOSED
    is_active BOOLEAN,

    -- Metadata
    created_by STRING,
    created_at STRING,
    updated_by STRING,
    updated_at STRING,

    PRIMARY KEY (version_id)
)
PARTITION BY HASH (version_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);


-- ============================================================================
-- TABLE 2: cis_position_queue
-- ============================================================================
-- Queue table for async position calculation.
-- Trades are queued and processed by background worker.
-- SLA: < 5 minutes from trade save to position update.
-- ============================================================================

DROP TABLE IF EXISTS cis_position_queue;

CREATE TABLE cis_position_queue (
    -- Primary Key
    queue_id BIGINT NOT NULL,

    -- Trade Reference
    trade_id BIGINT,
    portfolio_id STRING,
    security_id STRING,
    trade_type STRING,

    -- Trade Values (8 decimal precision)
    quantity DECIMAL(20,8),
    price DECIMAL(20,8),
    charges DECIMAL(20,8),
    settle_date STRING,

    -- Multi-currency
    security_currency STRING,
    portfolio_currency STRING,
    isin STRING,
    security_name STRING,

    -- Queue Status: PENDING, PROCESSING, COMPLETED, FAILED, DEAD_LETTER
    status STRING,
    retry_count INT,
    error_message STRING,

    -- Timestamps (STRING for Kudu compatibility)
    queued_at STRING,
    queued_by STRING,
    processed_at STRING,
    updated_at STRING,

    -- SLA Monitoring
    sla_breach BOOLEAN,

    -- Processing date
    processing_date STRING,

    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);


-- ============================================================================
-- TABLE 3: cis_settlement_queue
-- ============================================================================
-- Queue table for trades with future settlement dates.
-- Trades are queued when settle_date > today and processed
-- by the daily settlement job when settle_date arrives.
-- ============================================================================

DROP TABLE IF EXISTS cis_settlement_queue;

CREATE TABLE cis_settlement_queue (
    -- Primary Key
    queue_id BIGINT NOT NULL,

    -- Trade Reference
    trade_id BIGINT,
    portfolio_id STRING,
    security_id STRING,
    trade_type STRING,

    -- Trade Values (8 decimal precision)
    quantity DECIMAL(20,8),
    price DECIMAL(20,8),
    charges DECIMAL(20,8),
    settle_date STRING,

    -- Multi-currency
    security_currency STRING,
    portfolio_currency STRING,
    isin STRING,
    security_name STRING,

    -- Queue Status: PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED
    status STRING,
    retry_count INT,
    error_message STRING,

    -- Timestamps (STRING for Kudu compatibility)
    queued_at STRING,
    queued_by STRING,
    processed_at STRING,
    updated_at STRING,

    -- Processing date
    processing_date STRING,

    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);


-- ============================================================================
-- Initialize sequences for queue IDs (if cis_sequence table exists)
-- ============================================================================

-- Position queue sequence
-- UPSERT INTO cis_sequence (sequence_name, current_value, increment_by)
-- VALUES ('position_queue_id', 1000000, 1);

-- Settlement queue sequence
-- UPSERT INTO cis_sequence (sequence_name, current_value, increment_by)
-- VALUES ('settlement_queue_id', 1000000, 1);

-- Position version sequence
-- UPSERT INTO cis_sequence (sequence_name, current_value, increment_by)
-- VALUES ('position_version_id', 1000000, 1);

-- Position ID sequence
-- UPSERT INTO cis_sequence (sequence_name, current_value, increment_by)
-- VALUES ('position_id', 1000000, 1);


-- ============================================================================
-- Sample Queries
-- ============================================================================

-- Get current position for a portfolio+security
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND status = 'OPEN'
-- ORDER BY version_id DESC
-- LIMIT 1;

-- Get pending items for processing
-- SELECT * FROM cis_position_queue
-- WHERE status = 'PENDING'
-- ORDER BY queued_at ASC
-- LIMIT 100;

-- Get pending settlements for today
-- SELECT * FROM cis_settlement_queue
-- WHERE settle_date <= CAST(CURRENT_DATE() AS STRING)
--   AND status = 'PENDING'
-- ORDER BY queued_at ASC;


-- ============================================================================
-- END OF DDL
-- ============================================================================
