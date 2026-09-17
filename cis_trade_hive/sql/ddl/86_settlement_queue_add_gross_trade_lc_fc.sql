-- ============================================================================
-- DDL 86: Add trade_lc / gross_amount_lc / gross_amount_fc to cis_settlement_queue
-- ============================================================================
-- Problem: cis_settlement_queue (T+1/T+2 future settlements) never stored the
--          trade's exact LC/FC amounts. process_pending_settlements() (the EOD
--          job that drains this queue) calls position_service.calculate_position()
--          without trade_lc/gross_amount_lc/gross_amount_fc, so cost_fc/lc for
--          any position whose SETTLED basis defers past today gets recomputed
--          from quantity * price / the FX table instead of using the trade's
--          tallied amount -- the same class of drift already fixed for the
--          T+0 (_process_immediate_settlement) and backdated
--          (_recalculate_position_chain) paths (SA feedback, Venkata Narayana
--          Adisetty, 30/07/2026).
--
-- Fix: ADD COLUMNS trade_lc, gross_amount_lc, gross_amount_fc (DECIMAL(30,8),
--      matching cis_trade's own column precision). _queue_for_settlement now
--      stores them; process_pending_settlements now reads them back.
--
-- Run on: SIT, UAT, PROD
-- Safe to re-run: ALTER TABLE ADD COLUMNS is idempotent in Impala
--                 (will error if column already exists -- verify first with DESCRIBE)
-- ============================================================================

USE gmp_cis;

ALTER TABLE cis_settlement_queue ADD COLUMNS (trade_lc DECIMAL(30,8));
ALTER TABLE cis_settlement_queue ADD COLUMNS (gross_amount_lc DECIMAL(30,8));
ALTER TABLE cis_settlement_queue ADD COLUMNS (gross_amount_fc DECIMAL(30,8));

DESCRIBE cis_settlement_queue;

-- Expected: trade_lc, gross_amount_lc, gross_amount_fc appear in the column
-- list. Existing PENDING rows will have NULL for these three columns --
-- process_pending_settlements() already treats missing amounts as "fall back
-- to quantity * price / FX table", so this is a safe no-op for rows queued
-- before this migration ran, not a correctness regression.

-- ============================================================================
-- END
-- ============================================================================
