-- ============================================================================
-- ALTER TABLE: Add position_basis and position_date to queue tables
-- ============================================================================
-- Description:
--   Dual position logic requires each queue row to know:
--     - position_basis: 'TRADED' or 'SETTLED'
--     - position_date:  the effective date for this basis
--                       (trade_date for TRADED, settle_date for SETTLED)
--
--   Without these, the background worker cannot determine which basis chain
--   to update or which date to use as position_date in cis_trade_position.
--
-- Tables affected:
--   - cis_position_queue  (async position calc queue)
--   - cis_settlement_queue (future settlement EOD queue)
--
-- Database: gmp_cis
-- Created: 2026-04-08
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- cis_position_queue
-- ============================================================================

ALTER TABLE cis_position_queue ADD COLUMNS (position_basis STRING);
ALTER TABLE cis_position_queue ADD COLUMNS (position_date STRING);

-- ============================================================================
-- cis_settlement_queue
-- ============================================================================

ALTER TABLE cis_settlement_queue ADD COLUMNS (position_basis STRING);
ALTER TABLE cis_settlement_queue ADD COLUMNS (position_date STRING);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE cis_position_queue;
DESCRIBE cis_settlement_queue;

-- ============================================================================
-- BACKFILL existing rows (all pre-dual-logic rows are SETTLED basis)
-- ============================================================================
-- NOTE: Kudu does not support UPDATE without WHERE on primary key.
-- Run this only if there are existing PENDING rows that need backfilling.
-- New rows inserted after this DDL will always have position_basis set by code.
--
-- UPDATE gmp_cis.cis_position_queue
-- SET position_basis = 'SETTLED', position_date = settle_date
-- WHERE position_basis IS NULL;
--
-- UPDATE gmp_cis.cis_settlement_queue
-- SET position_basis = 'SETTLED', position_date = settle_date
-- WHERE position_basis IS NULL;

-- ============================================================================
-- END
-- ============================================================================
