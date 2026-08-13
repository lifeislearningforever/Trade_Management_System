-- Diagnose a Format 1 user-upload row with quantity_today = 0 that is
-- expected to reset/close a position but isn't showing up downstream.
--
-- Substitute the real values before running:
--   {SRC_ID}          e.g. 'cis_user_sta_adhoc_position_1'
--   {PROCESSING_DATE}  e.g. '20260813'  (YYYYMMDD)
--   {PORTFOLIO}/{SECURITY}  the specific row you're chasing (optional filter)
--
-- Run each step in order and compare row counts -- the step where the row
-- disappears (or where quantity stops being 0) is the actual bug location.

-- =============================================================================
-- STEP 1: Raw ingested row -- does it exist at all, and is quantity_today '0'?
-- =============================================================================
SELECT reporting_date, portfolio, counter, isin_code, quantity_yesterday, movement, quantity_today
FROM gmp_cis.cis_user_sta_adhoc_position_1
WHERE processing_date = '{PROCESSING_DATE}'
  AND src_id = '{SRC_ID}'
  -- AND portfolio = '{PORTFOLIO}' AND counter = '{SECURITY}'
ORDER BY portfolio, counter;

-- =============================================================================
-- STEP 2: position_upload_standardized -- did STANDARDIZE_SELECT keep the row,
-- and did safe_decimal() correctly turn '0' into DECIMAL 0 (not NULL)?
-- =============================================================================
SELECT portfolio, security_full_name, isin, quantity, position_basis, reporting_date
FROM gmp_cis.position_upload_standardized
WHERE processing_date = '{PROCESSING_DATE}'
  AND src_id = '{SRC_ID}'
  -- AND portfolio = '{PORTFOLIO}'
ORDER BY portfolio, security_full_name;

-- =============================================================================
-- STEP 3 (only if pos_stage_1_base / position_upload_staging still exist from
-- that run -- they're DROP-then-CREATE per run, so this only works if you
-- query immediately after, or re-run with a debug pause):
-- =============================================================================
-- SELECT portfolio, security_full_name, quantity FROM gmp_cis.pos_stage_1_base
-- WHERE src_id = '{SRC_ID}' AND processing_date = '{PROCESSING_DATE}';

-- SELECT portfolio, security_full_name, quantity, final_quantity, quantity_status,
--        overall_status, security_status, portfolio_status
-- FROM gmp_cis.position_upload_staging
-- WHERE src_id = '{SRC_ID}' AND processing_date = '{PROCESSING_DATE}';
