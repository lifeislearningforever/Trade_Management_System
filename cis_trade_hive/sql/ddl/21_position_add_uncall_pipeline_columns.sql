-- ============================================================================
-- ALTER TABLE: Add uncall, pipeline and position_type columns to position tables
-- ============================================================================
-- Description: Adds new columns for uncalled/pipeline tracking
--   - uncall_fc: Uncalled amount in Foreign Currency (Security Currency)
--   - uncall_lc: Uncalled amount in Local Currency (Portfolio Currency)
--   - pipeline_fc: Pipeline amount in Foreign Currency
--   - pipeline_lc: Pipeline amount in Local Currency
--   - position_type: Position type classification
--
-- Tables affected:
--   - cis_position (Kudu - gold/master position table)
--   - cis_trade_position (Kudu - AVP position tracking)
--   - cis_position_master (Hive/Parquet - consolidated positions)
--
-- Database: gmp_cis
-- Created: 2026-04-08
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- ALTER cis_position (Kudu table - gold/master position table)
-- ============================================================================
-- Note: Kudu ALTER TABLE ADD COLUMNS syntax
-- Uses DECIMAL(30,8) for wide monetary columns (handles large LC values)

ALTER TABLE cis_position ADD COLUMNS (uncall_fc DECIMAL(30,8));
ALTER TABLE cis_position ADD COLUMNS (uncall_lc DECIMAL(30,8));
ALTER TABLE cis_position ADD COLUMNS (pipeline_fc DECIMAL(30,8));
ALTER TABLE cis_position ADD COLUMNS (pipeline_lc DECIMAL(30,8));
ALTER TABLE cis_position ADD COLUMNS (position_type STRING);

-- ============================================================================
-- ALTER cis_trade_position (Kudu table - AVP position tracking)
-- ============================================================================
-- Note: Kudu ALTER TABLE ADD COLUMNS syntax

ALTER TABLE cis_trade_position ADD COLUMNS (uncall_fc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (uncall_lc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (pipeline_fc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (pipeline_lc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (position_type STRING);

-- ============================================================================
-- ALTER cis_position_master (Hive/Parquet table)
-- ============================================================================
-- Note: Hive ADD COLUMNS syntax for external Parquet tables

ALTER TABLE cis_position_master ADD COLUMNS (uncall_fc DECIMAL(20,6));
ALTER TABLE cis_position_master ADD COLUMNS (uncall_lc DECIMAL(20,6));
ALTER TABLE cis_position_master ADD COLUMNS (pipeline_fc DECIMAL(20,6));
ALTER TABLE cis_position_master ADD COLUMNS (pipeline_lc DECIMAL(20,6));
ALTER TABLE cis_position_master ADD COLUMNS (position_type STRING);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DESCRIBE cis_position;
DESCRIBE cis_trade_position;
DESCRIBE cis_position_master;

-- ============================================================================
-- COLUMN DEFINITIONS
-- ============================================================================
--
-- uncall_fc (DECIMAL):
--   Uncalled capital commitment amount in Foreign Currency (security currency).
--   Represents capital that has been committed but not yet called by the fund.
--   Used for private equity, venture capital, and other commitment-based investments.
--
-- uncall_lc (DECIMAL):
--   Uncalled capital commitment amount in Local Currency (portfolio base currency).
--   Same as uncall_fc but converted to portfolio's base currency.
--
-- pipeline_fc (DECIMAL):
--   Pipeline amount in Foreign Currency (security currency).
--   Represents pending trades or commitments that are in progress but not yet settled.
--   Could include: pending orders, committed purchases, or trades awaiting confirmation.
--
-- pipeline_lc (DECIMAL):
--   Pipeline amount in Local Currency (portfolio base currency).
--   Same as pipeline_fc but converted to portfolio's base currency.
--
-- position_type (STRING):
--   Classification of the position type. Examples:
--   - 'LONG': Standard long position
--   - 'SHORT': Short position
--   - 'COMMITTED': Capital commitment (PE/VC)
--   - 'PIPELINE': Pending/pipeline position
--   - 'HEDGE': Hedging position
--   - 'SYNTHETIC': Synthetic/derivative position
--
-- ============================================================================
-- END OF DDL
-- ============================================================================
