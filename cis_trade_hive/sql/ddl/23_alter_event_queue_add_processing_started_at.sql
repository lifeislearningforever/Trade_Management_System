-- ============================================================================
-- ALTER cis_trade_event_queue: Add processing_started_at column
-- ============================================================================
-- Purpose:
--   Fix double-processing bug where the stale PROCESSING timeout check used
--   created_at (event queue time) instead of when the worker actually started.
--   Events queued for > 5 min before pickup were being re-fetched and
--   re-processed, causing qty doubling in cis_trade_position.
--
-- Fix:
--   Worker sets processing_started_at when it marks an event as PROCESSING.
--   Stale timeout check now compares processing_started_at < threshold, so
--   only events where the worker has been running > 5 min are recovered —
--   not events that sat in the PENDING queue for a long time.
--
-- Apply to: SIT, UAT, PROD
-- Created: 2026-04-20
-- ============================================================================

USE gmp_cis;

-- Add processing_started_at column to track when worker actually started
ALTER TABLE cis_trade_event_queue
ADD COLUMNS (
    processing_started_at STRING    -- When worker started processing (YYYY-MM-DD HH:MM:SS)
);

-- Verify
DESCRIBE cis_trade_event_queue;

-- ============================================================================
-- END OF DDL
-- ============================================================================
