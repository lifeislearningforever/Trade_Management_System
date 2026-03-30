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
-- Version: 1.1 (Added position_basis for trade-date vs settle-date tracking)
-- ============================================================================

-- ============================================================================
-- TABLE 1: cis_trade_position
-- ============================================================================
-- Stores position snapshots with AVP (Average Price) calculations.
-- Each trade creates a new version (snapshot) of the position.
--
-- POSITION BASIS:
--   - TRADE_DATE: Position calculated based on trade date (T+0 accounting)
--   - SETTLE_DATE: Position calculated based on settlement date (T+1/T+2 accounting)
--
-- A single trade creates TWO position records:
--   1. One with position_basis='TRADE_DATE' (reflects on trade_date)
--   2. One with position_basis='SETTLE_DATE' (reflects on settle_date)
--
-- This allows dual reporting: "What do I own?" vs "What has settled?"
-- ============================================================================

DROP TABLE IF EXISTS cis_trade_position;

CREATE TABLE cis_trade_position (
    -- Primary Key (auto-increment per snapshot)
    version_id BIGINT NOT NULL,

    -- Position Identity (same across all versions for a portfolio+security+basis)
    position_id BIGINT NOT NULL,

    -- POSITION BASIS: 'TRADE_DATE' or 'SETTLE_DATE'
    -- Determines when this position record takes effect
    position_basis STRING NOT NULL DEFAULT 'TRADE_DATE',

    -- Snapshot date (trade_date or settle_date depending on position_basis)
    position_date STRING NOT NULL,

    -- Reference dates from the trade
    trade_date STRING,                   -- Original trade date
    settle_date STRING,                  -- Original settlement date

    -- Portfolio Reference
    portfolio_short_name STRING NOT NULL,

    -- Security Reference
    security_label STRING NOT NULL,

    -- Position State (8 decimal precision for AVP)
    quantity DECIMAL(20,8),              -- Current holding quantity

    -- Cost in Foreign Currency (FC = Security Currency)
    average_cost_fc DECIMAL(20,8),       -- Weighted average cost (AVP) in FC
    total_cost_fc DECIMAL(20,8),         -- Total cost basis in FC

    -- Cost in Local Currency (LC = Portfolio Currency)
    average_cost_lc DECIMAL(20,8),       -- Weighted average cost (AVP) in LC
    total_cost_lc DECIMAL(20,8),         -- Total cost basis in LC

    -- P&L in Foreign Currency (Security Currency)
    realized_pnl_fc DECIMAL(20,8),       -- Cumulative realized P&L in FC
    unrealized_pnl_fc DECIMAL(20,8),     -- Unrealized P&L in FC (market_value - total_cost)

    -- P&L in Local Currency (Portfolio Currency)
    realized_pnl_lc DECIMAL(20,8),       -- Cumulative realized P&L in LC
    unrealized_pnl_lc DECIMAL(20,8),     -- Unrealized P&L in LC

    -- Market Value
    market_price DECIMAL(20,8),          -- Latest market price in FC
    market_value_fc DECIMAL(20,8),       -- qty * market_price (in FC)
    market_value_lc DECIMAL(20,8),       -- Market value in LC

    -- Dividend Tracking (accumulated from Corporate Actions)
    dividend_fc DECIMAL(20,8),           -- Accumulated dividends in FC
    dividend_lc DECIMAL(20,8),           -- Accumulated dividends in LC

    -- Trade that caused this version
    trade_id BIGINT,
    trade_type STRING,                   -- BUY, SELL

    -- Additional Info
    lots_held INT,
    custodian STRING,
    sub_custodian STRING,

    -- Multi-currency support
    security_currency STRING,            -- Security's trading currency (FC)
    portfolio_currency STRING,           -- Portfolio's base currency (LC)
    fx_rate DECIMAL(20,8),               -- FX rate used (FC to LC)

    -- Status
    status STRING,                       -- OPEN, CLOSED
    is_active BOOLEAN,
    is_latest BOOLEAN DEFAULT TRUE,      -- Latest version for this portfolio+security+basis

    -- Last Corporate Action / Cash Flow tracking
    last_ca_id BIGINT,                   -- Last CA that generated cash flow
    last_ca_number STRING,               -- Last CA number
    last_ca_type STRING,                 -- Last CA type (DIVIDEND, INTEREST, etc.)
    last_ca_date STRING,                 -- Date of last CA (ex_date)
    last_cash_flow_id BIGINT,            -- Last cash flow ID generated from CA
    last_cash_flow_number STRING,        -- Last cash flow number
    last_cash_flow_amount_fc DECIMAL(20,8), -- Amount of last cash flow in FC (foreign_ccy_amt)
    last_cash_flow_amount_lc DECIMAL(20,8), -- Amount of last cash flow in LC (local_ccy_amt)

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
-- POSITION BASIS EXAMPLES
-- ============================================================================
--
-- Example 1: BUY 100 AAPL on 2026-03-25 (trade date), settles 2026-03-27 (T+2)
--
-- Creates TWO position records:
--
-- Record 1 (Trade-Date Basis):
--   version_id: 1001
--   position_basis: 'TRADE_DATE'
--   position_date: '2026-03-25'    <-- Reflects on TRADE date
--   trade_date: '2026-03-25'
--   settle_date: '2026-03-27'
--   quantity: 100
--   average_cost: 175.50
--
-- Record 2 (Settle-Date Basis):
--   version_id: 1002
--   position_basis: 'SETTLE_DATE'
--   position_date: '2026-03-27'    <-- Reflects on SETTLE date
--   trade_date: '2026-03-25'
--   settle_date: '2026-03-27'
--   quantity: 100
--   average_cost: 175.50
--
-- ============================================================================
--
-- Example 2: Query positions by basis
--
-- Get TRADE DATE position (what did I buy today?):
--   SELECT * FROM cis_trade_position
--   WHERE portfolio_short_name = 'FUND-001'
--     AND security_label = 'AAPL'
--     AND position_basis = 'TRADE_DATE'
--     AND is_latest = true;
--
-- Get SETTLE DATE position (what has actually settled?):
--   SELECT * FROM cis_trade_position
--   WHERE portfolio_short_name = 'FUND-001'
--     AND security_label = 'AAPL'
--     AND position_basis = 'SETTLE_DATE'
--     AND is_latest = true;
--
-- ============================================================================
--
-- Example 3: Position differences between bases
--
-- Scenario: On 2026-03-26, you have:
--   - Trade-date position: 100 shares (bought on 2026-03-25)
--   - Settle-date position: 0 shares (settlement on 2026-03-27 not yet)
--
-- This is normal for T+2 settlement. On 2026-03-27 (settle date):
--   - Trade-date position: 100 shares
--   - Settle-date position: 100 shares (now settled)
--
-- ============================================================================
--
-- Example 4: Reporting Use Cases
--
-- Use TRADE_DATE for:
--   - "What positions did I take today?"
--   - Trade blotters and daily trading reports
--   - NAV calculation using trade date accounting
--   - Compliance: exposure limits at trade time
--
-- Use SETTLE_DATE for:
--   - "What do I actually own (settled)?"
--   - Custodian reconciliation
--   - Cash settlement and funding
--   - NAV calculation using settle date accounting
--   - Regulatory reporting (some require settled positions)
--
-- ============================================================================


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

-- ============================================================================
-- TRADE DATE BASIS QUERIES
-- ============================================================================

-- Get latest TRADE DATE position for a portfolio+security
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND position_basis = 'TRADE_DATE'
--   AND is_latest = true
--   AND status = 'OPEN';

-- Get all TRADE DATE positions for a portfolio
-- SELECT security_label, quantity, average_cost_fc, total_cost_fc, position_date,
--        dividend_fc, dividend_lc
-- FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND position_basis = 'TRADE_DATE'
--   AND is_latest = true
--   AND status = 'OPEN'
-- ORDER BY security_label;

-- ============================================================================
-- SETTLE DATE BASIS QUERIES
-- ============================================================================

-- Get latest SETTLE DATE position for a portfolio+security
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND position_basis = 'SETTLE_DATE'
--   AND is_latest = true
--   AND status = 'OPEN';

-- Get all SETTLE DATE positions for a portfolio (what has actually settled)
-- SELECT security_label, quantity, average_cost, total_cost, position_date
-- FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND position_basis = 'SETTLE_DATE'
--   AND is_latest = true
--   AND status = 'OPEN'
-- ORDER BY security_label;

-- ============================================================================
-- COMPARISON QUERIES (TRADE DATE vs SETTLE DATE)
-- ============================================================================

-- Compare positions between bases (find unsettled trades)
-- SELECT
--     t.security_label,
--     t.quantity AS trade_date_qty,
--     COALESCE(s.quantity, 0) AS settle_date_qty,
--     t.quantity - COALESCE(s.quantity, 0) AS unsettled_qty
-- FROM cis_trade_position t
-- LEFT JOIN cis_trade_position s
--     ON t.portfolio_short_name = s.portfolio_short_name
--     AND t.security_label = s.security_label
--     AND s.position_basis = 'SETTLE_DATE'
--     AND s.is_latest = true
-- WHERE t.portfolio_short_name = 'FUND-001'
--   AND t.position_basis = 'TRADE_DATE'
--   AND t.is_latest = true
--   AND t.quantity != COALESCE(s.quantity, 0);

-- Get pending settlements (trades executed but not yet settled)
-- SELECT
--     trade_id,
--     portfolio_short_name,
--     security_label,
--     quantity,
--     trade_date,
--     settle_date
-- FROM cis_trade_position
-- WHERE position_basis = 'SETTLE_DATE'
--   AND position_date > CAST(CURRENT_DATE() AS STRING)
--   AND is_latest = true;

-- ============================================================================
-- QUEUE QUERIES
-- ============================================================================

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
