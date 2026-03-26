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
