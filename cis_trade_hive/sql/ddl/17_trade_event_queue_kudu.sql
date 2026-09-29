-- ============================================================================
-- Trade Event Queue Table for Async Processing
-- ============================================================================
-- This table queues trade events (history, audit, settlement, AVP) for
-- background processing, allowing trade creation to return immediately.
--
-- Background worker picks up events and processes them asynchronously.
--
-- Event Types:
--   HISTORY         - Insert trade history record (audit trail)
--   SETTLEMENT      - Process settlement and AVP calculation
--   POSITION_MODIFY - Reverse old position and recalculate with new trade values
--   POSITION_CANCEL - Reverse position when trade is cancelled
--
-- Status Flow:
--   PENDING -> PROCESSING -> COMPLETED (success)
--   PENDING -> PROCESSING -> FAILED (retry up to 3 times)
--   FAILED -> PENDING (retry) -> PROCESSING -> COMPLETED or DEAD_LETTER
--
-- Recovery:
--   - FAILED events are retried automatically up to MAX_RETRIES (3)
--   - DEAD_LETTER events require manual intervention via recovery API
--   - Stale PROCESSING events (>5 min) are recovered automatically
-- ============================================================================

USE gmp_cis;

-- Drop existing table if exists
DROP TABLE IF EXISTS cis_trade_event_queue;

-- Create trade event queue table
CREATE TABLE cis_trade_event_queue (
    -- Primary key (timestamp-based unique ID)
    event_id BIGINT NOT NULL,

    -- Trade reference
    trade_id BIGINT NOT NULL,                 -- Reference to cis_trade.trade_id
    deal_number STRING,                       -- Trade deal number (for debugging)

    -- Event details
    event_type STRING NOT NULL,               -- HISTORY, SETTLEMENT
    event_data STRING,                        -- JSON payload with event-specific details

    -- Processing status
    -- PENDING: Waiting to be processed
    -- PROCESSING: Currently being processed
    -- COMPLETED: Successfully processed
    -- FAILED: Failed, will retry
    -- DEAD_LETTER: Max retries exceeded, requires manual intervention
    status STRING NOT NULL,

    -- Retry tracking
    retry_count INT DEFAULT 0,                -- Number of retry attempts (max 3)
    error_message STRING,                     -- Last error message if failed

    -- Audit trail
    created_by STRING,                        -- User who created the trade
    created_at STRING,                        -- When event was queued (YYYY-MM-DD HH:MM:SS)
    processing_started_at STRING,             -- When worker started processing (YYYY-MM-DD HH:MM:SS)
    processed_at STRING,                      -- When event was completed (YYYY-MM-DD HH:MM:SS)

    PRIMARY KEY (event_id)
)
PARTITION BY HASH(event_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251'
);

-- Initialize sequence for event_id generation
-- Note: If cis_sequence already exists, use UPSERT to add this sequence
UPSERT INTO cis_sequence VALUES ('trade_event_id', 1000000, 1);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_trade_event_queue;

-- ============================================================================
-- SAMPLE QUERIES (for monitoring and debugging)
-- ============================================================================

-- Get pending events count
-- SELECT COUNT(*) FROM gmp_cis.cis_trade_event_queue WHERE status = 'PENDING';

-- Get failed events for investigation
-- SELECT event_id, trade_id, event_type, retry_count, error_message, created_at
-- FROM gmp_cis.cis_trade_event_queue
-- WHERE status IN ('FAILED', 'DEAD_LETTER')
-- ORDER BY created_at DESC
-- LIMIT 100;

-- Get queue health metrics
-- SELECT status, COUNT(*) as count, MIN(created_at) as oldest
-- FROM gmp_cis.cis_trade_event_queue
-- GROUP BY status;

-- Manually reset a failed event for reprocessing
-- UPDATE gmp_cis.cis_trade_event_queue
-- SET status = 'PENDING', retry_count = 0, error_message = NULL
-- WHERE event_id = <event_id>;

-- ============================================================================
-- END OF DDL
-- ============================================================================
