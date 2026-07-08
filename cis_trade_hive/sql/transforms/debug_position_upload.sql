-- ============================================================================
-- DEBUG: Position Upload Transform
-- ============================================================================
-- Run these queries step by step to identify where the issue is
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- DEBUG 1: Check source data
-- ============================================================================
SELECT 'Source record count' AS check_name, COUNT(*) AS cnt FROM position_upload_standardized;

-- Sample source data
SELECT portfolio, isin, security_full_name, security_short_name, exchange_code, quantity
FROM position_upload_standardized
LIMIT 5;


-- ============================================================================
-- DEBUG 2: Check Portfolio matching
-- ============================================================================
-- Count how many portfolios exist in cis_portfolio
SELECT 'Portfolios in cis_portfolio' AS check_name, COUNT(*) AS cnt FROM cis_portfolio;

-- Check if portfolio names match
SELECT 'Portfolio match count' AS check_name, COUNT(*) AS cnt
FROM position_upload_standardized p
JOIN cis_portfolio pf ON p.portfolio = pf.name;

-- Show non-matching portfolios
SELECT DISTINCT p.portfolio AS upload_portfolio, 'NOT FOUND' AS status
FROM position_upload_standardized p
LEFT JOIN cis_portfolio pf ON p.portfolio = pf.name
WHERE pf.name IS NULL
LIMIT 10;

-- Show what portfolio names look like in each table
SELECT 'UPLOAD portfolios' AS source, portfolio FROM position_upload_standardized LIMIT 5
UNION ALL
SELECT 'CIS portfolios' AS source, name FROM cis_portfolio LIMIT 5;


-- ============================================================================
-- DEBUG 3: Check Security matching (ISIN)
-- ============================================================================
-- Count how many securities exist
SELECT 'Securities in cis_security_kudu' AS check_name, COUNT(*) AS cnt FROM cis_security_kudu WHERE is_active = true;

-- Check ISIN match count
SELECT 'ISIN match count' AS check_name, COUNT(*) AS cnt
FROM position_upload_standardized p
JOIN cis_security_kudu s ON p.isin = s.isin AND s.is_active = true;

-- Show sample ISINs from both tables
SELECT 'UPLOAD ISINs' AS source, isin FROM position_upload_standardized WHERE isin IS NOT NULL LIMIT 5
UNION ALL
SELECT 'CIS ISINs' AS source, isin FROM cis_security_kudu WHERE isin IS NOT NULL AND is_active = true LIMIT 5;

-- Check for whitespace or case issues
SELECT 'ISINs with leading/trailing spaces' AS check_name, COUNT(*) AS cnt
FROM position_upload_standardized
WHERE isin != TRIM(isin);


-- ============================================================================
-- DEBUG 4: Check if using wrong security table
-- ============================================================================
-- Try cis_security instead of cis_security_kudu
SELECT 'ISIN match (cis_security)' AS check_name, COUNT(*) AS cnt
FROM position_upload_standardized p
JOIN cis_security s ON p.isin = s.isin;


-- ============================================================================
-- DEBUG 5: Check staging tables if they exist
-- ============================================================================
-- Check pos_stage_3_security (ISIN match results)
SELECT 'Stage 3 - ISIN matches' AS check_name, COUNT(*) AS cnt
FROM pos_stage_3_security
WHERE matched_security_id IS NOT NULL;

SELECT 'Stage 3 - No ISIN match' AS check_name, COUNT(*) AS cnt
FROM pos_stage_3_security
WHERE matched_security_id IS NULL;

-- Check pos_stage_4_security_fallback
SELECT security_status, COUNT(*) AS cnt
FROM pos_stage_4_security_fallback
GROUP BY security_status;

-- Check pos_stage_2_portfolio
SELECT portfolio_status, COUNT(*) AS cnt
FROM pos_stage_2_portfolio
GROUP BY portfolio_status;


-- ============================================================================
-- DEBUG 6: Final staging status breakdown
-- ============================================================================
SELECT overall_status, COUNT(*) AS cnt
FROM position_upload_staging
GROUP BY overall_status
ORDER BY cnt DESC;

-- Show sample invalid records
SELECT portfolio, isin, security_full_name, overall_status, portfolio_status, security_status, exchange_status
FROM position_upload_staging
WHERE overall_status LIKE 'INVALID%'
LIMIT 10;


-- ============================================================================
-- END DEBUG
-- ============================================================================


-- ============================================================================
-- CASH FLOW RESET QUERIES
-- Use these to reset a cash flow so it can be reprocessed by
-- process_approved_cashflows. Run in Hue against gmp_cis.
-- ============================================================================

USE gmp_cis;

-- 1. Check current cash flow state
--    Replace 'CF-20260704-00001' with the actual cash flow number.
SELECT cash_flow_id, cash_flow_number, status, position_updated,
       portfolio_short_name, security_label, cash_flow_type,
       send_receive, local_ccy_amt, foreign_ccy_amt,
       payment_date, value_date, is_deleted
FROM gmp_cis.cis_cash_flow
WHERE cash_flow_number = 'CF-20260704-00001';

-- 2. Reset position_updated flag so the command picks it up again.
--    (Idempotency: once processed the flag is set to true — this clears it.)
UPDATE gmp_cis.cis_cash_flow
SET position_updated = false,
    updated_at = now()
WHERE cash_flow_number = 'CF-20260704-00001';

-- 3. (Optional) Reset ALL unprocessed cash flows for a portfolio
--    Useful when testing a full rerun for a portfolio.
-- UPDATE gmp_cis.cis_cash_flow
-- SET position_updated = false,
--     updated_at = now()
-- WHERE portfolio_short_name = 'Test_Prakash_ccy'
--   AND status IN ('APPROVED', 'VALIDATED')
--   AND (is_deleted = false OR is_deleted IS NULL);

-- 4. Check duplicate cis_position rows for a portfolio/security/date
--    (Run after process_approved_cashflows to verify UPSERT worked correctly.)
SELECT position_id, version_id, position_type, position_basis,
       src_system, dividend_lc, processing_timestamp
FROM gmp_cis.cis_position
WHERE portfolio      = 'Test_Prakash_ccy'
  AND security_label = '000898 CS'
  AND position_date  = '2026-02-27'
ORDER BY position_basis, processing_timestamp;

-- 5. Delete duplicate cis_position rows — keep only the one with correct position_id.
--    WARNING: run query 4 first to identify the duplicate position_ids to delete.
--    Replace <duplicate_position_id> with the actual value to remove.
-- DELETE FROM gmp_cis.cis_position
-- WHERE position_id = <duplicate_position_id>
--   AND portfolio   = 'Test_Prakash_ccy';

-- ============================================================================
-- END CASH FLOW RESET
-- ============================================================================

-- ============================================================================
-- DEBUG: PORTIARP-7364 — daily_limit ISIN lookup from multi_hold
-- Tests the LEFT JOIN between gmp_cis_sta_dly_stat_street_ams_daily_limit
-- and gmp_cis_sta_dly_ams_multi_hold on (security_desc=security_name,
-- ctry_of_exchange=country_code) to populate isin.
-- Replace '20260227' with the target processing_date before running.
-- ============================================================================

-- Step 1: Check row counts in both source tables for the date
SELECT 'daily_limit rows'  AS table_name, COUNT(*) AS cnt
FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit
WHERE processing_date = '20260227'
UNION ALL
SELECT 'multi_hold rows', COUNT(*)
FROM gmp_cis.gmp_cis_sta_dly_ams_multi_hold
WHERE processing_date = '20260227'
  AND isin IS NOT NULL AND TRIM(isin) != '';

-- Step 2: Sample one daily_limit row joined to multi_hold — verify ISIN is populated
SELECT
    dl.portfolio                                                AS portfolio,
    dl.security_desc                                            AS security_full_name,
    NULL                                                        AS security_short_name,
    mh.isin                                                     AS isin,
    dl.ticker                                                   AS ticker,
    CAST(dl.quantity_units   AS DECIMAL(30,8))                  AS quantity,
    CAST(NULL AS DECIMAL(30,8))                                 AS shares_outstanding,
    CAST(NULL AS DECIMAL(30,8))                                 AS shares_issued,
    CAST(dl.stake_holdings   AS DECIMAL(10,6))                  AS pct_holding,
    CAST(dl.market_price     AS DECIMAL(30,8))                  AS market_price,
    CAST(dl.unit_cost        AS DECIMAL(30,8))                  AS average_cost,
    CAST(dl.total_cost_fc    AS DECIMAL(30,8))                  AS cost_fc,
    CAST(dl.mkt_value_fc     AS DECIMAL(30,8))                  AS market_value_fc,
    CAST(dl.unrealised_p_l_fc AS DECIMAL(30,8))                 AS unrealized_pnl_fc,
    CAST(dl.total_cost_sgd   AS DECIMAL(30,8))                  AS cost_lc,
    CAST(dl.mkt_value_sgd    AS DECIMAL(30,8))                  AS market_value_lc,
    CAST(dl.unrealised_p_l_sgd AS DECIMAL(30,8))                AS unrealized_pnl_lc,
    dl.product_type                                             AS product_type,
    dl.quoted_unquoted                                          AS quoted_unquoted,
    dl.ctry_of_exchange                                         AS exchange,
    dl.ctry_of_exchange                                         AS country_of_exchange,
    dl.ctry_incorporation                                       AS country_of_incorporation,
    dl.ccy                                                      AS security_currency,
    dl.mas_6digit_code                                          AS mas_6d_code_sg,
    'TRADED'                                                    AS position_basis,
    COALESCE(dl.trade_date, dl.processing_date)                 AS reporting_date,
    'AMS_STREET'                                                AS src_system,
    dl.processing_date,
    -- join diagnostics: NULL means no match found in multi_hold
    mh.security_name                                            AS mh_matched_security_name,
    mh.country_code                                             AS mh_matched_country_code
FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit dl
LEFT JOIN (
    SELECT DISTINCT
        UPPER(TRIM(security_name)) AS security_name,
        UPPER(TRIM(country_code))  AS country_code,
        isin
    FROM gmp_cis.gmp_cis_sta_dly_ams_multi_hold
    WHERE processing_date = '20260227'
      AND isin IS NOT NULL
      AND TRIM(isin) != ''
) mh
    ON  UPPER(TRIM(dl.security_desc))    = mh.security_name
    AND UPPER(TRIM(dl.ctry_of_exchange)) = mh.country_code
WHERE dl.processing_date = '20260227'
LIMIT 1;

-- Step 3: ISIN match rate — how many daily_limit rows got an ISIN from multi_hold
SELECT
    COUNT(*)                                        AS total_rows,
    SUM(CASE WHEN mh.isin IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_isin,
    SUM(CASE WHEN mh.isin IS NULL     THEN 1 ELSE 0 END) AS rows_without_isin
FROM gmp_cis.gmp_cis_sta_dly_stat_street_ams_daily_limit dl
LEFT JOIN (
    SELECT DISTINCT
        UPPER(TRIM(security_name)) AS security_name,
        UPPER(TRIM(country_code))  AS country_code,
        isin
    FROM gmp_cis.gmp_cis_sta_dly_ams_multi_hold
    WHERE processing_date = '20260227'
      AND isin IS NOT NULL AND TRIM(isin) != ''
) mh
    ON  UPPER(TRIM(dl.security_desc))    = mh.security_name
    AND UPPER(TRIM(dl.ctry_of_exchange)) = mh.country_code
WHERE dl.processing_date = '20260227';

-- ============================================================================
-- END PORTIARP-7364 DEBUG
-- ============================================================================
