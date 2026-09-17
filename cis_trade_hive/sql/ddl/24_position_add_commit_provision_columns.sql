-- ============================================================================
-- ALTER TABLE: Add commit and provision columns to cis_trade_position
-- ============================================================================
-- Description: Adds columns required by new CF handlers:
--   - commit_fc / commit_lc   : Commitment amount (CF-COMMITMENT handler)
--   - provision_fc / provision_lc : Provision amount (CF-provision handler)
--
-- uncall_fc/lc and pipeline_fc/lc already exist (added in DDL 21).
-- realized_pnl_fc/lc already exist in cis_trade_position (DDL 13).
--
-- Database: gmp_cis
-- Created: 2026-04-21
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- ALTER cis_trade_position (Kudu table - AVP position tracking)
-- ============================================================================

ALTER TABLE cis_trade_position ADD COLUMNS (commit_fc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (commit_lc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (provision_fc DECIMAL(30,8));
ALTER TABLE cis_trade_position ADD COLUMNS (provision_lc DECIMAL(30,8));

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DESCRIBE cis_trade_position;
