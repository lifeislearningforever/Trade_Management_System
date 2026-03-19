-- ============================================================================
-- Corporate Action Cash Flow Queue Table
-- ============================================================================
-- Purpose: Queue table for processing corporate actions and generating
--          corresponding cash flow entries (dividends, interest, coupons, etc.)
--
-- Processing Flow:
--   1. When a CA is validated, an entry is added to this queue
--   2. EOD job processes pending queue items
--   3. For each CA, cash flows are generated based on portfolio holdings
--   4. Queue entry marked COMPLETED or FAILED
--
-- Author: CIS Trade Hive
-- Created: 2026-03-18
-- ============================================================================

-- Drop existing table if needed (commented out for safety)
-- DROP TABLE IF EXISTS gmp_cis.cis_ca_cash_flow_queue;

CREATE TABLE IF NOT EXISTS gmp_cis.cis_ca_cash_flow_queue (
    -- Primary Key
    queue_id BIGINT NOT NULL COMMENT 'Unique queue entry ID (timestamp-based)',

    -- Corporate Action Reference
    ca_id BIGINT NOT NULL COMMENT 'Reference to cis_corporate_actions.ca_id',
    ca_number STRING COMMENT 'Corporate Action number for display',
    ca_type STRING NOT NULL COMMENT 'Type: DIVIDEND, INTEREST, COUPON, etc.',

    -- Security & Portfolio
    security_name STRING NOT NULL COMMENT 'Security name(s) - comma separated if multiple',
    portfolio_name STRING COMMENT 'Portfolio name(s) - comma separated if multiple, NULL for all',

    -- Key Dates
    ex_date STRING COMMENT 'Ex-dividend date (YYYY-MM-DD)',
    record_date STRING COMMENT 'Record date (YYYY-MM-DD)',
    payment_date STRING COMMENT 'Payment date (YYYY-MM-DD)',

    -- Amount Information
    price DECIMAL(20,8) COMMENT 'Dividend/interest rate per share',
    currency STRING COMMENT 'Currency code',

    -- Processing Status
    status STRING DEFAULT 'PENDING' COMMENT 'PENDING, PROCESSING, COMPLETED, FAILED',
    retry_count BIGINT DEFAULT 0 COMMENT 'Number of processing attempts',
    error_message STRING COMMENT 'Error details if failed',

    -- Processing Metadata
    cash_flows_created BIGINT DEFAULT 0 COMMENT 'Number of cash flows created',
    total_amount DECIMAL(20,8) COMMENT 'Total amount of cash flows created',
    processed_at BIGINT COMMENT 'Timestamp when processing completed',

    -- Audit Fields
    created_at BIGINT NOT NULL COMMENT 'Creation timestamp (milliseconds)',
    created_by STRING COMMENT 'User who triggered the queue entry',

    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Corporate Action Cash Flow Log Table
-- ============================================================================
-- Purpose: Detailed log of cash flow generation from corporate actions
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_ca_cash_flow_log (
    -- Primary Key
    log_id BIGINT NOT NULL COMMENT 'Unique log entry ID',

    -- References
    queue_id BIGINT NOT NULL COMMENT 'Reference to cis_ca_cash_flow_queue.queue_id',
    ca_id BIGINT NOT NULL COMMENT 'Reference to corporate action',
    cf_id BIGINT COMMENT 'Reference to created cash flow (if successful)',

    -- Details
    portfolio_short_name STRING NOT NULL COMMENT 'Portfolio for this cash flow',
    security_name STRING NOT NULL COMMENT 'Security name',
    quantity DECIMAL(20,8) COMMENT 'Quantity held at ex-date',
    amount DECIMAL(20,8) COMMENT 'Calculated cash flow amount',
    currency STRING COMMENT 'Currency code',

    -- Status
    status STRING DEFAULT 'SUCCESS' COMMENT 'SUCCESS or FAILED',
    error_message STRING COMMENT 'Error details if failed',

    -- Timestamps
    created_at BIGINT NOT NULL COMMENT 'Log creation timestamp',

    PRIMARY KEY (log_id)
)
PARTITION BY HASH (log_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.num_tablet_replicas' = '1'
);

-- ============================================================================
-- Add CA reference columns to cis_cash_flow table (if not exists)
-- ============================================================================
-- Note: Run this ALTER statement manually if the columns don't exist
-- ALTER TABLE gmp_cis.cis_cash_flow ADD COLUMNS (
--     ca_id BIGINT COMMENT 'Reference to corporate action if generated from CA',
--     ca_number STRING COMMENT 'Corporate action number for display'
-- );

-- ============================================================================
-- Sample Data for Testing
-- ============================================================================
-- Uncomment to insert test data:

-- INSERT INTO gmp_cis.cis_ca_cash_flow_queue VALUES (
--     1710758400000,  -- queue_id
--     1710758300000,  -- ca_id
--     'CA-20260318-00001',  -- ca_number
--     'DIVIDEND',     -- ca_type
--     'AAPL',         -- security_name
--     NULL,           -- portfolio_name (all portfolios)
--     '2026-03-15',   -- ex_date
--     '2026-03-16',   -- record_date
--     '2026-03-20',   -- payment_date
--     0.25,           -- price (dividend per share)
--     'USD',          -- currency
--     'PENDING',      -- status
--     0,              -- retry_count
--     NULL,           -- error_message
--     0,              -- cash_flows_created
--     NULL,           -- total_amount
--     NULL,           -- processed_at
--     1710758400000,  -- created_at
--     'system'        -- created_by
-- );

-- ============================================================================
-- Indexes (Kudu creates automatic indexes on primary key)
-- Additional indexes can be created using Impala if needed:
-- ============================================================================
-- CREATE INDEX idx_ca_queue_status ON gmp_cis.cis_ca_cash_flow_queue(status);
-- CREATE INDEX idx_ca_queue_ca_id ON gmp_cis.cis_ca_cash_flow_queue(ca_id);
-- CREATE INDEX idx_ca_queue_payment_date ON gmp_cis.cis_ca_cash_flow_queue(payment_date);
