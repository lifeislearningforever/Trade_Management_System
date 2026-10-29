-- ============================================================================
-- ALTER TABLE: Add is_latest flag for version-based position tracking
-- ============================================================================
-- Description: Adds is_latest BOOLEAN column to cis_trade_position for
--              efficient querying of current position state.
--
-- Design:
--   - is_latest = true: This is the most recent version for this position_date
--   - is_latest = false: This is a historical version (superseded by newer version)
--
-- Benefits:
--   - No DELETE operations - immutable audit trail
--   - Simple queries: WHERE is_latest = true
--   - Full history preserved for each position_date
--   - Backdated trades create new versions, not delete existing
--
-- Database: gmp_cis
-- Created: 2026-03-11
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- Add is_latest column
-- ============================================================================

ALTER TABLE cis_trade_position ADD COLUMNS (is_latest BOOLEAN);

-- ============================================================================
-- Set default value for existing records
-- ============================================================================
-- For existing records, we need to mark the highest version_id per
-- portfolio+security+position_date as is_latest=true

-- Step 1: Update all to false first (safe default)
-- Note: Kudu doesn't support UPDATE with subquery, so this needs to be done
-- in application code or via UPSERT with full row data

-- ============================================================================
-- Sample Queries for Version-Based Position Tracking
-- ============================================================================

-- Get CURRENT position for a portfolio+security (all dates, latest versions only)
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND is_latest = true
-- ORDER BY position_date DESC;

-- Get position as of a specific date (latest version for that date)
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND position_date = '2026-03-04'
--   AND is_latest = true;

-- Get position history (all versions for a date)
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND position_date = '2026-03-04'
-- ORDER BY version_id ASC;

-- Get the overall latest position (most recent date, latest version)
-- SELECT * FROM cis_trade_position
-- WHERE portfolio_short_name = 'FUND-001'
--   AND security_label = 'AAPL'
--   AND is_latest = true
-- ORDER BY position_date DESC
-- LIMIT 1;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_trade_position;

-- ============================================================================
-- NOTES ON USAGE:
-- ============================================================================
-- When creating new position version:
--   1. UPDATE existing record(s) for same portfolio+security+position_date
--      SET is_latest = false
--   2. INSERT new record with is_latest = true
--
-- For backdated trades:
--   1. For the backdated date: Create new version with is_latest=true
--      (mark any existing versions for that date as is_latest=false)
--   2. For all subsequent dates: Create new versions with recalculated AVP
--      (mark existing versions as is_latest=false)
--
-- Example flow for backdated trade (March 4 backdate with existing March 11):
--   Before:
--     | version_id | position_date | quantity | avg | is_latest |
--     | 1001       | 2026-03-11    | 100      | 130 | true      |
--
--   After backdated trade for March 4:
--     | version_id | position_date | quantity | avg    | is_latest |
--     | 1001       | 2026-03-11    | 100      | 130    | false     | <- marked old
--     | 1002       | 2026-03-04    | 50       | 150    | true      | <- new backdate
--     | 1003       | 2026-03-11    | 150      | 136.67 | true      | <- recalculated
-- ============================================================================
