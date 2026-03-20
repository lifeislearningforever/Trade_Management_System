-- ============================================================================
-- Trade Event Queue Table for Async Processing
-- ============================================================================
-- This table queues trade events (history, audit, settlement, AVP) for
-- background processing, allowing trade creation to return immediately.
--
-- Background worker picks up events and processes them asynchronously.
-- ============================================================================

-- Drop existing table if exists
DROP TABLE IF EXISTS gmp_cis.cis_trade_event_queue;

-- Create trade event queue table
CREATE TABLE gmp_cis.cis_trade_event_queue (
    event_id BIGINT,                          -- Primary key (timestamp-based)
    trade_id BIGINT,                          -- Reference to trade
    deal_number STRING,                       -- Trade deal number
    event_type STRING,                        -- HISTORY, AUDIT, SETTLEMENT, AVP
    event_data STRING,                        -- JSON payload with event details
    status STRING,                            -- PENDING, PROCESSING, COMPLETED, FAILED
    retry_count INT,                          -- Number of retry attempts
    error_message STRING,                     -- Error message if failed
    created_by STRING,                        -- User who created the trade
    created_at TIMESTAMP,                     -- When event was queued
    processed_at TIMESTAMP,                   -- When event was processed
    PRIMARY KEY (event_id)
)
PARTITION BY HASH(event_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.table_name' = 'cis_trade_event_queue',
    'kudu.num_tablet_replicas' = '1'
);

-- Create index for pending events lookup
-- Note: Kudu doesn't support secondary indexes, but we can optimize queries
-- by filtering on status = 'PENDING' and ordering by created_at

COMMENT ON TABLE gmp_cis.cis_trade_event_queue IS
'Queue for async trade event processing (history, audit, settlement, AVP).
Events are queued during trade creation and processed by background worker.';
