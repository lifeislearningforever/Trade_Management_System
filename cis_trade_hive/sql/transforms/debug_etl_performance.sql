-- ============================================================================
-- Debug: ETL Performance — identify which step is slow
-- Run in Impala/Hue against gmp_cis database
-- Replace '20260302' with your actual processing_date
-- Replace 'cis_user_sta_adhoc_position_5' with your actual src_id
-- ============================================================================

-- ============================================================================
-- STEP A: How many rows are in the standardized table for this partition?
-- Expected: should match rows in the uploaded file (e.g. 3 for format 5)
-- If this is unexpectedly large, Step 0 (standardize) is the bottleneck.
-- ============================================================================
SELECT
    src_id,
    processing_date,
    COUNT(*) AS row_count
FROM gmp_cis.position_upload_standardized
WHERE processing_date = '20260302'
  AND src_id         = 'cis_user_sta_adhoc_position_5'
GROUP BY src_id, processing_date;


-- ============================================================================
-- STEP B: Check pos_stage_1_base row count and timing proxy
-- If this table has far more rows than the upload, a cross-join crept in.
-- ============================================================================
SELECT COUNT(*) AS stage1_row_count FROM pos_stage_1_base;


-- ============================================================================
-- STEP C: Check pos_stage_2_portfolio — portfolio validation result
-- ============================================================================
SELECT
    portfolio_status,
    COUNT(*) AS cnt
FROM pos_stage_2_portfolio
GROUP BY portfolio_status;


-- ============================================================================
-- STEP D: Check pos_stage_3_security — security match result
-- Shows match_type distribution and whether exchange match is resolving
-- ============================================================================
SELECT
    match_type,
    COUNT(*) AS cnt
FROM pos_stage_3_security
GROUP BY match_type;


-- ============================================================================
-- STEP E: Check pos_stage_4_security_fallback — fallback match result
-- ============================================================================
SELECT
    security_status,
    COUNT(*) AS cnt
FROM pos_stage_4_security_fallback
GROUP BY security_status;


-- ============================================================================
-- STEP F: Check position_upload_staging — consolidated staging result
-- This is the final pre-report staging table (Step 6 output)
-- ============================================================================
SELECT
    overall_status,
    portfolio_status,
    security_status,
    price_status,
    quantity_status,
    exchange_status,
    COUNT(*) AS cnt
FROM position_upload_staging
GROUP BY
    overall_status,
    portfolio_status,
    security_status,
    price_status,
    quantity_status,
    exchange_status;


-- ============================================================================
-- STEP G: Check lut_dedup resolves correctly for format 5 exchanges
-- Replace exchange values with what appears in your format 5 file
-- ============================================================================
SELECT
    lut.exchange_name,
    COALESCE(
        MIN(CASE WHEN sec.exchange_code IS NOT NULL THEN lut.country_name END),
        MIN(lut.country_name)
    ) AS resolved_country
FROM (
    SELECT UPPER(TRIM(exchange_name)) AS exchange_name, country_name
    FROM gmp_cis.cis_exchange_mapping_lut
) lut
LEFT JOIN (
    SELECT DISTINCT UPPER(TRIM(exchange_code)) AS exchange_code
    FROM gmp_cis.cis_security WHERE is_active = true
) sec ON lut.country_name = sec.exchange_code
GROUP BY lut.exchange_name
ORDER BY lut.exchange_name;


-- ============================================================================
-- STEP H: Check position_upload_report for this partition — final result
-- ============================================================================
SELECT
    row_status,
    fail_reason,
    portfolio_status,
    security_status,
    price_status,
    quantity_status,
    exchange_status,
    matched_security_id,
    matched_security_name,
    isin,
    portfolio
FROM gmp_cis.position_upload_report
WHERE processing_date = '20260302'
  AND src_id         = 'cis_user_sta_adhoc_position_5'
ORDER BY row_status, fail_reason;


-- ============================================================================
-- STEP I: Slowness diagnosis — check cis_security table size
-- Large cis_security tables make Step 3/4 JOINs slow even for 3 rows
-- because Impala full-scans cis_security on every ETL run.
-- ============================================================================
SELECT
    COUNT(*)                                        AS total_securities,
    SUM(CASE WHEN is_active = true  THEN 1 ELSE 0 END) AS active_securities,
    SUM(CASE WHEN is_active = false THEN 1 ELSE 0 END) AS inactive_securities
FROM gmp_cis.cis_security;


-- ============================================================================
-- STEP J: Check cis_portfolio table size
-- Large portfolio tables slow down Step 2 portfolio validation join.
-- ============================================================================
SELECT COUNT(*) AS total_portfolios FROM gmp_cis.cis_portfolio;


-- ============================================================================
-- STEP K: Check cis_exchange_mapping_lut size
-- Should be small (hundreds of rows). Large LUT slows lut_dedup CTE.
-- ============================================================================
SELECT COUNT(*) AS total_lut_rows FROM gmp_cis.cis_exchange_mapping_lut;


-- ============================================================================
-- STEP L: Shell command to extract step timings from application log
-- Run on CML terminal — replace log path as needed
-- ============================================================================
-- grep "position_etl.*Step\|position_etl.*complete\|position_etl.*failed" \
--     ~/CIS/logs/cistrade.log* | tail -100
--
-- Expected output (one line per step with elapsed seconds):
--   [position_etl] Step 0 complete — 3 rows standardized  (elapsed: 12.3s)
--   [position_etl] Step 1 complete                        (elapsed: 8.1s)
--   [position_etl] Step 2 complete                        (elapsed: 4.2s)
--   [position_etl] Step 3 complete                        (elapsed: 45.7s)  ← slow?
--   [position_etl] Step 4 complete                        (elapsed: 120.3s) ← slow?
--
-- If Step 3 or Step 4 are slow: cis_security is large — consider adding
--   COMPUTE STATS gmp_cis.cis_security; in Impala to speed up JOIN planning.
--
-- If Step 0 is slow: position_upload_standardized has too many partitions —
--   consider running MSCK REPAIR TABLE less frequently.
