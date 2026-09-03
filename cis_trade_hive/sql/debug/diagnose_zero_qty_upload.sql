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
-- CONFIRMED: Step 1 and Step 2 counts match, quantity=0 flows through correctly
-- up to position_upload_standardized. The gap is between there and cis_position.
-- =============================================================================

-- =============================================================================
-- STEP 3: cis_position -- is there ONE row for this natural key with the
-- wrong (nonzero) quantity, or TWO is_latest=true rows (the original nonzero
-- one AND a new zero one under a slightly different security_label)?
--
-- This is the same duplicate-is_latest pattern already found and fixed
-- earlier in this session for CORR positions -- Step 7A's UPSERT computes
-- position_id from a deterministic hash that includes security_label. If
-- this reset upload's security matching (Step 4 tiers: ISIN / ticker /
-- short name / full name) resolves to a DIFFERENT matched_security_name
-- than whatever the original nonzero position was created under, the hash
-- differs, and the UPSERT creates a second row instead of overwriting the
-- first.
-- =============================================================================
SELECT position_id, portfolio, security_label, position_basis, position_date,
       src_system, quantity, is_latest, version_id, processing_timestamp
FROM gmp_cis.cis_position
WHERE portfolio = '{PORTFOLIO}'
  AND position_date = '{POSITION_DATE}'   -- e.g. '2026-08-13'
  AND position_type = 'INT'
  AND src_system = 'USER_UPLOAD'
  AND (
    security_label = '{SECURITY_LABEL}'
    OR security_label LIKE '%{SECURITY_LABEL_PARTIAL}%'
  )
ORDER BY version_id DESC;

-- =============================================================================
-- STEP 4: What security did THIS reset upload's Step 6 staging actually
-- match to for this row? Compare matched_security_name /
-- security_match_method against whatever security_label the OLD nonzero
-- cis_position row (Step 3) actually has.
-- =============================================================================
-- Only works if position_upload_staging still exists from the run you're
-- chasing (it's DROP-then-CREATE each run):
-- SELECT portfolio, security_full_name, matched_security_name, final_isin,
--        security_status, security_match_method, final_quantity,
--        quantity_status, overall_status
-- FROM gmp_cis.position_upload_staging
-- WHERE src_id = '{SRC_ID}' AND processing_date = '{PROCESSING_DATE}'
--   AND portfolio = '{PORTFOLIO}';
